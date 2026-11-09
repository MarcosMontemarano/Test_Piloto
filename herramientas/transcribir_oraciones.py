"""Transcripción automática de las oraciones QuickSIN que usa el test -> audio/quicksin/oraciones.csv.

Toma exactamente los archivos que reproduce test.py (piloto.sesion.ruta_oracion, listas 1, 2 y 3,
oraciones 1 a 6, en ese orden), los transcribe con faster-whisper en español y propone como
palabras clave las 5 palabras de contenido de cada oración (sin artículos, preposiciones,
pronombres ni auxiliares), separadas por "|". Todas las filas quedan con estado = "provisorio":
las palabras clave se verifican contra la hoja original del QuickSIN rioplatense.

Columnas: lista, oracion, archivo, texto, palabras_clave, estado. "archivo" es el nombre del WAV
que suena, así el texto siempre corresponde a lo que se reproduce.

Si oraciones.csv ya tiene textos, no lo pisa salvo con --forzar.

Uso:
    python herramientas/transcribir_oraciones.py
    python herramientas/transcribir_oraciones.py --modelo small
"""

import argparse
import csv
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from piloto.sesion import LISTA_PRACTICA, LISTAS_TAREA_A, ORACIONES_POR_LISTA, ruta_oracion  # noqa: E402

SALIDA = os.path.join(RAIZ, "audio", "quicksin", "oraciones.csv")
COLUMNAS = ["lista", "oracion", "archivo", "texto", "palabras_clave", "estado"]
PALABRAS_CLAVE = 5

FUNCIONALES = set("""
a al algo algún alguna algunas alguno algunos ante aquel aquella aquellas aquellos aquí así aún
bajo bien cada como con contra cual cuales cuando de del desde donde dos durante e el ella ellas
ello ellos en entre era eran es esa esas ese eso esos esta estaba estaban estas este esto estos
está están estoy fue fueron ha había habían han has hasta hay he la las le les lo los me mi mis
muy más ni no nos nosotros o os otra otras otro otros para pero poco por porque que quien quienes
qué se sea ser si sido sin sobre son su sus suya suyo también tan tanto te ti tiene tienen todo
todos tras tu tus tú un una unas uno unos usted ustedes va vamos van vos y ya yo él
""".split())


def palabras(texto):
    return re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", texto)


def proponer_claves(texto):
    """Las palabras de contenido en orden; si sobran, se descartan las más cortas."""
    todas = palabras(texto)
    contenido = [p for p in todas if p.lower() not in FUNCIONALES]
    if len(contenido) < PALABRAS_CLAVE:
        extra = [p for p in todas if p not in contenido and len(p) > 2]
        contenido += extra[:PALABRAS_CLAVE - len(contenido)]
    while len(contenido) > PALABRAS_CLAVE:
        contenido.remove(min(contenido, key=len))
    return "|".join(contenido)


def leer_16k(ruta):
    """Audio mono float32 a 16 kHz (se lee con soundfile, sin depender de PyAV)."""
    from math import gcd

    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    x, fs = sf.read(ruta, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    divisor = gcd(16000, fs)
    return resample_poly(x, 16000 // divisor, fs // divisor).astype(np.float32)


def tiene_textos(ruta):
    try:
        with open(ruta, newline="", encoding="utf-8-sig") as f:
            return any((fila.get("texto") or "").strip() for fila in csv.DictReader(f))
    except OSError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--modelo", default="medium", help="modelo de faster-whisper (default medium)")
    parser.add_argument("--forzar", action="store_true", help="pisar un oraciones.csv que ya tiene textos")
    args = parser.parse_args()
    if tiene_textos(SALIDA) and not args.forzar:
        raise SystemExit("{} ya tiene textos; usá --forzar para regenerarlo.".format(SALIDA))

    from faster_whisper import WhisperModel
    print("Cargando modelo {} (CPU, int8)...".format(args.modelo))
    modelo = WhisperModel(args.modelo, device="cpu", compute_type="int8")

    filas = []
    for lista in sorted(LISTAS_TAREA_A + (LISTA_PRACTICA,)):
        for oracion in range(1, ORACIONES_POR_LISTA + 1):
            ruta = ruta_oracion(RAIZ, lista, oracion)
            segmentos, _ = modelo.transcribe(leer_16k(ruta), language="es", beam_size=5, vad_filter=False,
                                              condition_on_previous_text=False)
            texto = " ".join(s.text.strip() for s in segmentos).strip()
            texto = texto[:1].upper() + texto[1:]
            filas.append({"lista": lista, "oracion": oracion, "archivo": os.path.basename(ruta),
                          "texto": texto, "palabras_clave": proponer_claves(texto), "estado": "provisorio"})
            print("L{} O{}: {}".format(lista, oracion, texto))

    with open(SALIDA, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        escritor.writeheader()
        escritor.writerows(filas)
    print("Escrito: {}".format(SALIDA))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
