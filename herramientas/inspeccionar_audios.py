"""Paso 1: inspección de las listas del QuickSIN rioplatense y del ruido de referencia U3F.

Reporta formato y duración de cada archivo, el Leq (dBFS) y el porcentaje de pausas de
cada canal, propone cuál canal de las listas CS es la voz (la voz tiene pausas, el babble
es continuo) y caracteriza todasPalabras.wav y ruidoQuickSIN.wav.

Uso:
    python herramientas/inspeccionar_audios.py
    python herramientas/inspeccionar_audios.py --quicksin "ruta/a/las/listas"
"""

import argparse
import os
import sys

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import leq_dbfs, niveles_tramas, porcentaje_pausas  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LISTAS = ["LISTA {}CS_R19.wav".format(i) for i in range(1, 9)]
EXTRAS = ["todasPalabras.wav", "ruidoQuickSIN.wav"]
REFERENCIA_U3F = "RuidoCalibracion_Listas_U3F.wav"

UMBRAL_DB = 30.0
# Un canal con menos de este porcentaje de pausas se considera continuo.
PAUSAS_MIN_HABLA = 5.0
TOLERANCIA_DURACION_S = 0.05
FS_CORRELACION = 8000
EXTRACTO_S = 3.0


def leer(ruta):
    x, fs = sf.read(ruta, dtype="float64", always_2d=True)
    return x, fs, sf.info(ruta)


def describir_canal(x, fs):
    niveles = niveles_tramas(x, fs)
    return {
        "leq": leq_dbfs(x),
        "pausas": porcentaje_pausas(x, fs, UMBRAL_DB),
        # Dispersión de la envolvente sobre las tramas activas: alta en habla, baja en ruido.
        "desvio": float(np.std(niveles[niveles > niveles.max() - UMBRAL_DB])),
    }


def extracto_activo(x, fs):
    """EXTRACTO_S segundos desde la primera trama a menos de 20 dB del máximo."""
    niveles = niveles_tramas(x, fs)
    inicio = int(np.argmax(niveles > niveles.max() - 20)) * int(0.020 * fs)
    return x[inicio:inicio + int(EXTRACTO_S * fs)]


def correlacion_maxima(extracto, senal, fs):
    """Máximo de la correlación cruzada normalizada (0-1) y su posición en s."""
    e = resample_poly(extracto, FS_CORRELACION, fs)
    s = resample_poly(senal, FS_CORRELACION, fs)
    if len(s) < len(e):
        return 0.0, 0.0
    n = len(e)
    tam = 1 << int(np.ceil(np.log2(len(s) + n)))
    num = np.fft.irfft(np.fft.rfft(s, tam) * np.conj(np.fft.rfft(e, tam)), tam)[:len(s) - n + 1]
    energia = np.concatenate(([0.0], np.cumsum(s ** 2)))
    den = np.sqrt((energia[n:] - energia[:-n]) * np.sum(e ** 2)) + 1e-12
    ncc = np.abs(num) / den
    k = int(np.argmax(ncc))
    return float(ncc[k]), k / FS_CORRELACION


def tabla(encabezados, filas):
    anchos = [max(len(str(c)) for c in col) for col in zip(encabezados, *filas)]
    linea = "  ".join("{:<%d}" % a for a in anchos)
    print(linea.format(*encabezados))
    print("  ".join("-" * a for a in anchos))
    for fila in filas:
        print(linea.format(*fila))
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quicksin", default=os.path.join(RAIZ, "audio", "quicksin"))
    parser.add_argument("--referencias", default=os.path.join(RAIZ, "audio", "referencias"))
    args = parser.parse_args()

    archivos = [(os.path.join(args.quicksin, n), n) for n in LISTAS + EXTRAS]
    archivos.append((os.path.join(args.referencias, REFERENCIA_U3F), REFERENCIA_U3F))

    datos = {}
    faltantes = []
    for ruta, nombre in archivos:
        if os.path.isfile(ruta):
            datos[nombre] = leer(ruta)
        else:
            faltantes.append(ruta)

    print("\n== Formato ==\n")
    tabla(["archivo", "canales", "fs (Hz)", "resolución", "duración (s)"],
          [[n, info.channels, fs, info.subtype, "{:.3f}".format(len(x) / fs)]
           for n, (x, fs, info) in datos.items()])

    print("== Canales (Leq lineal en dBFS; pausas = tramas de 20 ms a >= {:.0f} dB del máximo) ==\n"
          .format(UMBRAL_DB))
    filas = []
    canales = {}
    for nombre, (x, fs, _) in datos.items():
        for c in range(x.shape[1]):
            d = describir_canal(x[:, c], fs)
            canales[(nombre, c)] = d
            filas.append([nombre, c + 1, "{:.2f}".format(d["leq"]), "{:.1f}".format(d["pausas"]),
                          "{:.1f}".format(d["desvio"])])
    tabla(["archivo", "canal", "Leq (dBFS)", "pausas (%)", "desvío env. (dB)"], filas)

    print("== Canal de voz propuesto en las listas CS ==\n")
    voz = {}
    filas = []
    for nombre in LISTAS:
        if nombre not in datos:
            continue
        x = datos[nombre][0]
        if x.shape[1] != 2:
            filas.append([nombre, "-", "-", "no es estéreo"])
            continue
        p = [canales[(nombre, c)]["pausas"] for c in range(2)]
        voz[nombre] = int(np.argmax(p))
        otro = 1 - voz[nombre]
        filas.append([nombre, voz[nombre] + 1, otro + 1,
                      "voz {:.1f} % pausas, babble {:.1f} %".format(p[voz[nombre]], p[otro])])
    tabla(["lista", "voz", "babble", "criterio"], filas)
    if voz:
        unicos = sorted(set(voz.values()))
        if len(unicos) == 1:
            print("El canal de voz es el {} en las {} listas.\n".format(unicos[0] + 1, len(voz)))
        else:
            print("ATENCIÓN: el canal de voz no es el mismo en todas las listas.\n")

    print("== todasPalabras.wav y ruidoQuickSIN.wav ==\n")
    duraciones = {n: len(datos[n][0]) / datos[n][1] for n in LISTAS if n in datos}
    suma_listas = sum(duraciones.values())
    for nombre in EXTRAS:
        if nombre not in datos:
            continue
        x, fs, _ = datos[nombre]
        dur = len(x) / fs
        for c in range(x.shape[1]):
            d = canales[(nombre, c)]
            tipo = ("habla con pausas (concatenada)" if d["pausas"] >= PAUSAS_MIN_HABLA
                    else "ruido continuo")
            print("{} canal {}: {} ({:.1f} % pausas, desvío de la envolvente {:.1f} dB)"
                  .format(nombre, c + 1, tipo, d["pausas"], d["desvio"]))

        coincidencias = [n for n, dl in duraciones.items() if abs(dl - dur) <= TOLERANCIA_DURACION_S]
        if coincidencias:
            print("  Duración {:.3f} s: igual a {}".format(dur, ", ".join(coincidencias)))
        elif abs(suma_listas - dur) <= TOLERANCIA_DURACION_S * len(duraciones):
            print("  Duración {:.3f} s: igual a la suma de las listas ({:.3f} s)".format(dur, suma_listas))
        else:
            print("  Duración {:.3f} s: no coincide con ninguna lista (rango {:.3f}-{:.3f} s) "
                  "ni con su suma ({:.3f} s)".format(dur, min(duraciones.values(), default=0),
                                                    max(duraciones.values(), default=0), suma_listas))

        # ¿El contenido aparece dentro de las listas? Se busca un extracto de cada canal
        # de las listas dentro del primer canal del archivo.
        senal = x[:, 0]
        for nombre_lista in LISTAS:
            if nombre_lista not in voz:
                continue
            xl, fsl, _ = datos[nombre_lista]
            if fsl != fs:
                continue
            for c, rol in ((voz[nombre_lista], "voz"), (1 - voz[nombre_lista], "babble")):
                r, t = correlacion_maxima(extracto_activo(xl[:, c], fs), senal, fs)
                if r >= 0.5:
                    print("  Contiene el {} de {} (correlación {:.2f} en t = {:.2f} s)"
                          .format(rol, nombre_lista, r, t))
        print()

    if faltantes:
        print("Archivos no encontrados:")
        for ruta in faltantes:
            print("  " + ruta)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
