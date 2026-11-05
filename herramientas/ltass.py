"""Paso 3: LTASS del QuickSIN rioplatense en tercios de octava (63 Hz a 16 kHz).

Quita las pausas de la fuente (tramas de 20 ms a --umbral dB o más del máximo de la
envolvente), calcula la PSD por Welch (Hann, 50 % de solapamiento, resolución <= 6 Hz), la
integra en tercios de octava y expresa cada banda relativa al Leq global del habla activa.

Salidas en herramientas/salidas/:
    ltass.csv   banda_hz, nivel_rel_db, nivel_dbfs[, nivel_db_spl] y, por cada comparación,
                <nombre>_rel_db y dif_<nombre>_db (LTASS menos comparación). La fila
                "global" lleva el Leq del habla activa.
    ltass.png   curvas superpuestas y diferencias por banda.

Comparaciones:
    --comparar   uno o más archivos a los que se aplica el mismo análisis.
    Byrne et al. (1994), voz femenina: referencias/byrne1994_femenino.csv (banda_hz, nivel_db).
                 Se carga a mano; si la columna nivel_db está vacía, se omite. Como el archivo no
                 trae el nivel global, se normaliza a la suma energética de sus 25 bandas.

Calibración (opcional): --calibrador recibe la grabación del calibrador (94 dB SPL en 1 kHz)
hecha con el ECM8000 y suma el offset resultante a los niveles en dBFS. Solo tiene sentido si
la --fuente es una grabación hecha con la misma cadena y la misma ganancia, por ejemplo la
reproducción del QuickSIN por el auricular captada con el ECM8000.

Uso:
    python herramientas/ltass.py
    python herramientas/ltass.py --comparar audio/referencias/otro.wav
    python herramientas/ltass.py --fuente grabacion.wav --calibrador calibrador.wav
"""

import argparse
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import (BANDAS_NOMINALES, leq_dbfs, quitar_pausas, tercios_octava,  # noqa: E402
                   potencia_bandas, psd_welch)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUENTE = os.path.join(RAIZ, "audio", "quicksin", "todasPalabras.wav")
BYRNE = os.path.join(RAIZ, "referencias", "byrne1994_femenino.csv")
SALIDAS = os.path.join(RAIZ, "herramientas", "salidas")
SPL_CALIBRADOR = 94.0

# Paleta categórica de referencia (slots 1-3) y tinta del gráfico.
COLORES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
TINTA, TINTA_SECUNDARIA, GRILLA, EJE = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"


def leer_mono(ruta):
    x, fs = sf.read(ruta, dtype="float64", always_2d=True)
    if x.shape[1] > 1:
        print("  {}: {} canales, se usa el primero.".format(os.path.basename(ruta), x.shape[1]))
    return x[:, 0], fs


def analizar(ruta, umbral_db):
    """LTASS de un archivo: niveles por banda en dBFS, Leq global del habla activa y % activo."""
    x, fs = leer_mono(ruta)
    activa, porcentaje = quitar_pausas(x, fs, umbral_db)
    bandas = tercios_octava(activa, fs)
    leq = leq_dbfs(activa)
    # Energía que queda fuera de 63 Hz-16 kHz, para saber cuánto se aparta la suma de bandas del global.
    f, psd = psd_welch(activa, fs)
    fuera = 1 - potencia_bandas(f, psd).sum() / (np.sum(psd) * (f[1] - f[0]))
    return {"bandas": bandas, "leq": leq, "activo": porcentaje, "fuera": 100 * fuera}


def offset_calibracion(ruta, spl=SPL_CALIBRADOR):
    """dB a sumar a un nivel en dBFS para obtener dB SPL, según la grabación del calibrador.

    Usa el nivel de la banda de 1 kHz, para que el ruido de fondo de la grabación no lo sesgue.
    """
    x, fs = leer_mono(ruta)
    return spl - tercios_octava(x, fs)[BANDAS_NOMINALES.index(1000)]


def cargar_byrne(ruta):
    """Niveles de Byrne relativos a su suma energética, o None si el archivo no está completo."""
    if not os.path.exists(ruta):
        return None
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        niveles = {int(fila["banda_hz"]): fila["nivel_db"].strip() for fila in csv.DictReader(f)}
    cargados = [niveles.get(b, "") for b in BANDAS_NOMINALES]
    if not any(cargados):
        return None
    if not all(cargados):
        print("ATENCIÓN: {} tiene bandas sin cargar; se omite del gráfico.".format(ruta))
        return None
    niveles = np.array([float(v.replace(",", ".")) for v in cargados])
    return niveles - 10 * np.log10(np.sum(10 ** (niveles / 10)))


def crear_plantilla_byrne(ruta):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["banda_hz", "nivel_db"])
        for b in BANDAS_NOMINALES:
            w.writerow([b, ""])
    print("Plantilla creada: {} (completá nivel_db con la curva femenina de Byrne et al., 1994)."
          .format(ruta))


def graficar(ruta, ltass, comparaciones):
    x = np.arange(len(BANDAS_NOMINALES))
    etiquetas = [str(b) if b < 1000 else "{:g}k".format(b / 1000) for b in BANDAS_NOMINALES]
    fig, (arriba, abajo) = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True,
                                        gridspec_kw={"height_ratios": [3, 2]})
    arriba.plot(x, ltass, color=COLORES[0], lw=2, marker="o", ms=4, label="LTASS QuickSIN")
    for i, (nombre, niveles) in enumerate(comparaciones.items(), start=1):
        arriba.plot(x, niveles, color=COLORES[i], lw=2, marker="o", ms=4, label=nombre)
        abajo.plot(x, ltass - niveles, color=COLORES[i], lw=2, marker="o", ms=4,
                   label="QuickSIN − " + nombre)
    abajo.axhline(0, color=EJE, lw=1)

    arriba.set_ylabel("Nivel relativo al global (dB)")
    arriba.set_title("LTASS en tercios de octava", loc="left", color=TINTA)
    abajo.set_ylabel("Diferencia (dB)")
    abajo.set_xlabel("Frecuencia central (Hz)")
    abajo.set_xticks(x)
    abajo.set_xticklabels(etiquetas, rotation=45)
    for ax in (arriba, abajo):
        ax.grid(True, color=GRILLA, lw=0.6)
        ax.tick_params(colors=TINTA_SECUNDARIA)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color(EJE)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(frameon=False, labelcolor=TINTA)
    if not comparaciones:
        abajo.text(0.5, 0.5, "Sin curvas de comparación cargadas", transform=abajo.transAxes,
                   ha="center", va="center", color=TINTA_SECUNDARIA)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fuente", default=FUENTE)
    parser.add_argument("--umbral", type=float, default=30.0,
                        help="dB bajo el máximo para considerar pausa (default 30)")
    parser.add_argument("--comparar", nargs="*", default=[], help="archivos de audio a comparar")
    parser.add_argument("--byrne", default=BYRNE)
    parser.add_argument("--calibrador", help="grabación del calibrador de 94 dB SPL (opcional)")
    args = parser.parse_args()

    print("Fuente: {}".format(args.fuente))
    ltass = analizar(args.fuente, args.umbral)
    relativos = ltass["bandas"] - ltass["leq"]
    print("  Habla activa: {:.1f} % (umbral {:.0f} dB)".format(ltass["activo"], args.umbral))
    print("  Leq global del habla activa: {:.2f} dBFS".format(ltass["leq"]))
    print("  Energía fuera de 63 Hz-16 kHz: {:.2f} %".format(ltass["fuera"]))

    offset = None
    if args.calibrador:
        offset = offset_calibracion(args.calibrador)
        print("  Calibración: {:+.2f} dB (dBFS -> dB SPL)".format(offset))

    comparaciones = {}
    for ruta in args.comparar:
        nombre = os.path.splitext(os.path.basename(ruta))[0]
        print("Comparación: {}".format(ruta))
        r = analizar(ruta, args.umbral)
        print("  Activo: {:.1f} %, Leq {:.2f} dBFS".format(r["activo"], r["leq"]))
        comparaciones[nombre] = r["bandas"] - r["leq"]

    if not os.path.exists(args.byrne):
        crear_plantilla_byrne(args.byrne)
    byrne = cargar_byrne(args.byrne)
    if byrne is not None:
        comparaciones["Byrne et al. (1994), femenino"] = byrne
    else:
        print("Byrne et al. (1994): sin datos cargados, se omite.")

    os.makedirs(SALIDAS, exist_ok=True)
    claves = {nombre: "byrne" if nombre.startswith("Byrne") else nombre for nombre in comparaciones}
    encabezado = ["banda_hz", "nivel_rel_db", "nivel_dbfs"] + (["nivel_db_spl"] if offset is not None else [])
    for nombre in comparaciones:
        encabezado += ["{}_rel_db".format(claves[nombre]), "dif_{}_db".format(claves[nombre])]

    with open(os.path.join(SALIDAS, "ltass.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(encabezado)
        for i, banda in enumerate(BANDAS_NOMINALES):
            fila = [banda, "{:.2f}".format(relativos[i]), "{:.2f}".format(ltass["bandas"][i])]
            if offset is not None:
                fila.append("{:.2f}".format(ltass["bandas"][i] + offset))
            for niveles in comparaciones.values():
                fila += ["{:.2f}".format(niveles[i]), "{:.2f}".format(relativos[i] - niveles[i])]
            w.writerow(fila)
        fila = ["global", "0.00", "{:.2f}".format(ltass["leq"])]
        if offset is not None:
            fila.append("{:.2f}".format(ltass["leq"] + offset))
        w.writerow(fila + [""] * (len(encabezado) - len(fila)))

    graficar(os.path.join(SALIDAS, "ltass.png"), relativos, comparaciones)

    print("\nbanda (Hz)  rel. (dB)  " + "  ".join("dif {}".format(claves[n]) for n in comparaciones))
    for i, banda in enumerate(BANDAS_NOMINALES):
        difs = "  ".join("{:>+{}.2f}".format(relativos[i] - c[i], len(claves[n]) + 4)
                         for n, c in comparaciones.items())
        print("{:>10}  {:>9.2f}  {}".format(banda, relativos[i], difs))
    print("\nSalidas en {}".format(SALIDAS))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
