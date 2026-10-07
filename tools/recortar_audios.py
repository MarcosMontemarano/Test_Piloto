"""Genera los clips de audio en loop que usa test.py (audio/clips/).

Uso (solo para desarrollo, no lo necesita el ejecutable):
    pip install numpy scipy soundfile
    python tools/recortar_audios.py

Cada clip dura DURACION_S segundos, se exporta a 44.1 kHz estéreo en OGG Vorbis
y queda preparado para loop sin clicks: los últimos CRUCE_S segundos del tramo
se funden (crossfade de igual potencia) sobre el inicio, así el final empalma
con el principio sin saltos ni bajones de nivel.
"""
import os
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGEN = os.path.join(RAIZ, "audio")
DESTINO = os.path.join(ORIGEN, "clips")

FS = 44100
DURACION_S = 30.0
CRUCE_S = 0.5
PICO_MAX_DBFS = -1.0

# (archivo de salida, archivo de origen o None si se genera, inicio en s)
CLIPS = (
    ("musica_pop.ogg", "gr0za-pop-pop-music-577843.mp3", 55.0),
    ("ruido_tren.ogg", "freesound_community-train-ride-inside-the-car-17382.mp3", 0.0),
    # Placeholder del MSSN: ruido blanco a -20 dBFS RMS (no estaba
    # audiocheck.net_whitenoise.wav, se genera con semilla fija).
    ("ruido_blanco.ogg", None, 0.0),
)


def cargar(nombre, inicio):
    total = int((DURACION_S + CRUCE_S) * FS)
    if nombre is None:
        rng = np.random.default_rng(1234)
        ruido = rng.standard_normal(total) * 10 ** (-20 / 20)
        return np.column_stack([ruido, ruido])

    datos, fs = sf.read(os.path.join(ORIGEN, nombre), always_2d=True)
    if datos.shape[1] == 1:
        datos = np.repeat(datos, 2, axis=1)
    datos = datos[:, :2]
    if fs != FS:
        divisor = gcd(FS, fs)
        datos = resample_poly(datos, FS // divisor, fs // divisor, axis=0)
    primera = int(inicio * FS)
    tramo = datos[primera:primera + total]
    if len(tramo) < total:
        raise ValueError("{}: el tramo pedido excede la duración del archivo".format(nombre))
    return tramo


def preparar_loop(tramo):
    largo = int(DURACION_S * FS)
    cruce = int(CRUCE_S * FS)
    t = np.linspace(0, np.pi / 2, cruce)[:, None]
    clip = tramo[:largo].copy()
    clip[:cruce] = tramo[:cruce] * np.sin(t) + tramo[largo:largo + cruce] * np.cos(t)
    pico = np.abs(clip).max()
    limite = 10 ** (PICO_MAX_DBFS / 20)
    if pico > limite:
        clip *= limite / pico
    return clip


def main():
    os.makedirs(DESTINO, exist_ok=True)
    for salida, origen, inicio in CLIPS:
        clip = preparar_loop(cargar(origen, inicio))
        ruta = os.path.join(DESTINO, salida)
        # Escritura por bloques: libsndfile desborda la pila en Windows si
        # se le pasa todo el clip OGG de una sola vez.
        with sf.SoundFile(ruta, "w", FS, 2, format="OGG", subtype="VORBIS") as archivo:
            for inicio_bloque in range(0, len(clip), FS):
                archivo.write(clip[inicio_bloque:inicio_bloque + FS])
        print("{}: {:.1f} s, {:.0f} kB".format(salida, len(clip) / FS, os.path.getsize(ruta) / 1024))


if __name__ == "__main__":
    main()
