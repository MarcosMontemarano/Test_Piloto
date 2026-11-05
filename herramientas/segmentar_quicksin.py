"""Paso 2: extracción del canal de voz de las listas QuickSIN y segmentación en oraciones.

Para cada lista escribe en audio/quicksin/voz/:
    LISTA_X_voz.wav          canal de voz completo (mono, misma fs y resolución, sin normalizar)
    LISTA_X_oracion_N.wav    cada oración, con margen antes y después y fundidos
y deja audio/quicksin/segmentacion.csv (lista, oracion, inicio_s, fin_s). Los tiempos son los
del corte con margen, medidos sobre la lista original.

La segmentación usa la envolvente de energía (tramas de 20 ms): una trama es activa si está a
menos de --umbral dB del máximo, y dos tramos activos se unen si los separa una pausa menor
que --pausa-min. Si una lista no da exactamente 6 oraciones, se avisa y no se corta.

También crea la plantilla audio/quicksin/oraciones.csv si todavía no existe.

Uso:
    python herramientas/segmentar_quicksin.py
"""

import argparse
import csv
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import niveles_tramas  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(RAIZ, "audio", "quicksin")
CANAL_VOZ = 0  # Left, confirmado de oído
ORACIONES_POR_LISTA = 6
TRAMA_S = 0.020


def tramos_activos(x, fs, umbral_db, pausa_min_s):
    """Pares (inicio, fin) en muestras de los tramos de habla separados por pausas largas."""
    niveles = niveles_tramas(x, fs, TRAMA_S)
    activa = niveles > niveles.max() - umbral_db
    bordes = np.diff(np.concatenate(([0], activa.astype(int), [0])))
    inicios = list(np.where(bordes == 1)[0])
    fines = list(np.where(bordes == -1)[0])
    tramos = [[inicios[0], fines[0]]]
    for i, f in zip(inicios[1:], fines[1:]):
        if (i - tramos[-1][1]) * TRAMA_S < pausa_min_s:
            tramos[-1][1] = f
        else:
            tramos.append([i, f])
    n = int(round(TRAMA_S * fs))
    return [(i * n, f * n) for i, f in tramos]


def con_fundidos(x, fs, fundido_s):
    n = int(round(fundido_s * fs))
    rampa = 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / n)
    y = x.copy()
    y[:n] *= rampa
    y[-n:] *= rampa[::-1]
    return y


def crear_plantilla(ruta):
    if os.path.exists(ruta):
        print("La plantilla {} ya existe: no se modifica.".format(ruta))
        return
    # utf-8-sig para que Excel abra bien los acentos.
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["lista", "oracion", "texto", "palabras_clave"])
        for lista in range(1, 9):
            for oracion in range(1, ORACIONES_POR_LISTA + 1):
                w.writerow([lista, oracion, "", ""])
    print("Plantilla creada: {}".format(ruta))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--carpeta", default=CARPETA)
    parser.add_argument("--umbral", type=float, default=30.0, help="dB bajo el máximo (default 30)")
    parser.add_argument("--pausa-min", type=float, default=1.0,
                        help="pausa mínima entre oraciones en s (default 1.0)")
    parser.add_argument("--margen", type=float, default=0.100, help="s (default 0.100)")
    parser.add_argument("--fundido", type=float, default=0.010, help="s (default 0.010)")
    args = parser.parse_args()

    salida = os.path.join(args.carpeta, "voz")
    os.makedirs(salida, exist_ok=True)

    filas = []
    con_problemas = []
    for lista in range(1, 9):
        ruta = os.path.join(args.carpeta, "LISTA {}CS_R19.wav".format(lista))
        info = sf.info(ruta)
        x, fs = sf.read(ruta, dtype="float64", always_2d=True)
        voz = x[:, CANAL_VOZ]
        sf.write(os.path.join(salida, "LISTA_{}_voz.wav".format(lista)), voz, fs, subtype=info.subtype)

        tramos = tramos_activos(voz, fs, args.umbral, args.pausa_min)
        if len(tramos) != ORACIONES_POR_LISTA:
            con_problemas.append((lista, tramos, fs))
            continue

        margen = int(round(args.margen * fs))
        for oracion, (i, f) in enumerate(tramos, start=1):
            i, f = max(0, i - margen), min(len(voz), f + margen)
            sf.write(os.path.join(salida, "LISTA_{}_oracion_{}.wav".format(lista, oracion)),
                     con_fundidos(voz[i:f], fs, args.fundido), fs, subtype=info.subtype)
            filas.append([lista, oracion, "{:.3f}".format(i / fs), "{:.3f}".format(f / fs)])

    with open(os.path.join(args.carpeta, "segmentacion.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lista", "oracion", "inicio_s", "fin_s"])
        w.writerows(filas)

    print("\nlista  oración  inicio (s)  fin (s)  duración (s)")
    for lista, oracion, inicio, fin in filas:
        print("{:<5}  {:<7}  {:>10}  {:>7}  {:>12.3f}".format(
            lista, oracion, inicio, fin, float(fin) - float(inicio)))

    for lista, tramos, fs in con_problemas:
        print("\nATENCIÓN: la LISTA {} dio {} segmentos en lugar de {}; no se cortó. Tramos (s): {}".format(
            lista, len(tramos), ORACIONES_POR_LISTA,
            ", ".join("{:.2f}-{:.2f}".format(i / fs, f / fs) for i, f in tramos)))

    print()
    crear_plantilla(os.path.join(args.carpeta, "oraciones.csv"))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
