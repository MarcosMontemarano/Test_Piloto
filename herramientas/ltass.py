"""Paso 3: LTASS del QuickSIN rioplatense en tercios de octava (63 Hz a 16 kHz).

Quita las pausas de la fuente (tramas de 20 ms a --umbral dB o más del máximo de la
envolvente), calcula la PSD por Welch (Hann, 50 % de solapamiento, resolución <= 6 Hz) y la
integra en tercios de octava.

Todas las curvas se normalizan al mismo nivel global: la suma energética de sus 25 bandas
(63 Hz-16 kHz) vale 0 dB. Para el habla, la energía fuera de ese rango es despreciable, así
que la diferencia con el Leq de banda ancha es de centésimas de dB.

Referencias de comparación:
    Listas U3F (Piegari): Lista1.wav a Lista10.wav de audio/referencias/u3f/, concatenadas,
        con el mismo análisis (sin pausas, mismo umbral). Otro corpus rioplatense.
    Byrne et al. (1994), voz femenina: referencias/byrne1994_femenino.csv (banda_hz, nivel_db),
        cargado a mano. Si la columna nivel_db está vacía, se omite.
    --comparar: otros archivos, cada uno con el mismo análisis (p. ej. el ruido de
        calibración U3F cuando aparezca).

Salidas en herramientas/salidas/:
    ltass.csv   banda_hz, nivel_rel_db, nivel_dbfs[, nivel_db_spl] y, por cada referencia,
                <ref>_rel_db y dif_<ref>_db (LTASS QuickSIN menos referencia). La fila
                "global" lleva el Leq del habla activa en dBFS.
    ltass.png   curvas superpuestas y diferencias por banda.

Calibración (opcional): --calibrador recibe la grabación del calibrador (94 dB SPL en 1 kHz)
hecha con el ECM8000 y suma el offset resultante a los niveles en dBFS. Solo tiene sentido si
la --fuente es una grabación hecha con la misma cadena y la misma ganancia, por ejemplo la
reproducción del QuickSIN por el auricular captada con el ECM8000.

Uso:
    python herramientas/ltass.py
    python herramientas/ltass.py --comparar audio/referencias/RuidoCalibracion_Listas_U3F.wav
    python herramientas/ltass.py --fuente grabacion.wav --calibrador calibrador.wav
"""

import argparse
import csv
import glob
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import (BANDAS_NOMINALES, leq_dbfs, quitar_pausas, relativo_a_bandas,  # noqa: E402
                   tercios_octava)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUENTE = os.path.join(RAIZ, "audio", "quicksin", "todasPalabras.wav")
CARPETA_U3F = os.path.join(RAIZ, "audio", "referencias", "u3f")
BYRNE = os.path.join(RAIZ, "referencias", "byrne1994_femenino.csv")
SALIDAS = os.path.join(RAIZ, "herramientas", "salidas")
SPL_CALIBRADOR = 94.0

# Paleta categórica de referencia y tinta del gráfico.
COLORES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
TINTA, TINTA_SECUNDARIA, GRILLA, EJE = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"


def leer_mono(ruta):
    x, fs = sf.read(ruta, dtype="float64", always_2d=True)
    if x.shape[1] > 1:
        print("  {}: {} canales, se usa el primero.".format(os.path.basename(ruta), x.shape[1]))
    return x[:, 0], fs


def leer_concatenado(rutas):
    senales, frecuencias = zip(*(leer_mono(r) for r in rutas))
    if len(set(frecuencias)) != 1:
        raise SystemExit("Los archivos a concatenar tienen distinta frecuencia de muestreo.")
    return np.concatenate(senales), frecuencias[0]


def analizar(x, fs, umbral_db):
    """LTASS de una señal: niveles por banda en dBFS, Leq del habla activa y % activo."""
    activa, porcentaje = quitar_pausas(x, fs, umbral_db)
    return {"bandas": tercios_octava(activa, fs), "leq": leq_dbfs(activa), "activo": porcentaje}


def offset_calibracion(ruta, spl=SPL_CALIBRADOR):
    """dB a sumar a un nivel en dBFS para obtener dB SPL, según la grabación del calibrador.

    Usa el nivel de la banda de 1 kHz, para que el ruido de fondo de la grabación no lo sesgue.
    """
    x, fs = leer_mono(ruta)
    return spl - tercios_octava(x, fs)[BANDAS_NOMINALES.index(1000)]


def cargar_byrne(ruta):
    """Niveles de Byrne en dB, o None si la plantilla está vacía o incompleta."""
    if not os.path.exists(ruta):
        return None
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        niveles = {int(fila["banda_hz"]): fila["nivel_db"].strip() for fila in csv.DictReader(f)}
    cargados = [niveles.get(b, "") for b in BANDAS_NOMINALES]
    if not any(cargados):
        return None
    if not all(cargados):
        print("ATENCIÓN: {} tiene bandas sin cargar; se omite.".format(ruta))
        return None
    return np.array([float(v.replace(",", ".")) for v in cargados])


def crear_plantilla_byrne(ruta):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["banda_hz", "nivel_db"])
        for b in BANDAS_NOMINALES:
            w.writerow([b, ""])
    print("Plantilla creada: {} (completá nivel_db con la curva femenina de Byrne et al., 1994)."
          .format(ruta))


def graficar(ruta, ltass, referencias):
    x = np.arange(len(BANDAS_NOMINALES))
    etiquetas = [str(b) if b < 1000 else "{:g}k".format(b / 1000) for b in BANDAS_NOMINALES]
    fig, (arriba, abajo) = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True,
                                        gridspec_kw={"height_ratios": [3, 2]})
    arriba.plot(x, ltass, color=COLORES[0], lw=2, marker="o", ms=4, label="LTASS QuickSIN")
    for i, (nombre, niveles) in enumerate(referencias.items(), start=1):
        arriba.plot(x, niveles, color=COLORES[i], lw=2, marker="o", ms=4, label=nombre)
        abajo.plot(x, ltass - niveles, color=COLORES[i], lw=2, marker="o", ms=4,
                   label="QuickSIN − " + nombre)
    abajo.axhline(0, color=EJE, lw=1)

    arriba.set_ylabel("Nivel relativo al global (dB)")
    arriba.set_title("LTASS en tercios de octava (suma de bandas = 0 dB)", loc="left", color=TINTA)
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
    if not referencias:
        abajo.text(0.5, 0.5, "Sin curvas de referencia cargadas", transform=abajo.transAxes,
                   ha="center", va="center", color=TINTA_SECUNDARIA)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def numero_lista(ruta):
    return int(re.search(r"(\d+)", os.path.basename(ruta)).group(1))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fuente", default=FUENTE)
    parser.add_argument("--umbral", type=float, default=30.0,
                        help="dB bajo el máximo para considerar pausa (default 30)")
    parser.add_argument("--u3f", default=CARPETA_U3F, help="carpeta con Lista1.wav ... Lista10.wav")
    parser.add_argument("--comparar", nargs="*", default=[], help="otros archivos de referencia")
    parser.add_argument("--byrne", default=BYRNE)
    parser.add_argument("--calibrador", help="grabación del calibrador de 94 dB SPL (opcional)")
    args = parser.parse_args()

    print("Fuente: {}".format(args.fuente))
    ltass = analizar(*leer_mono(args.fuente), args.umbral)
    relativos = relativo_a_bandas(ltass["bandas"])
    print("  Habla activa: {:.1f} % (umbral {:.0f} dB)".format(ltass["activo"], args.umbral))
    print("  Leq del habla activa: {:.2f} dBFS".format(ltass["leq"]))

    offset = None
    if args.calibrador:
        offset = offset_calibracion(args.calibrador)
        print("  Calibración: {:+.2f} dB (dBFS -> dB SPL)".format(offset))

    # nombre para el gráfico -> (clave para el CSV, niveles relativos)
    referencias = {}
    rutas_u3f = sorted(glob.glob(os.path.join(args.u3f, "Lista*.wav")), key=numero_lista)
    if rutas_u3f:
        r = analizar(*leer_concatenado(rutas_u3f), args.umbral)
        print("Listas U3F: {} archivos concatenados, {:.1f} % activo, Leq {:.2f} dBFS"
              .format(len(rutas_u3f), r["activo"], r["leq"]))
        referencias["Listas U3F (Piegari)"] = ("u3f", relativo_a_bandas(r["bandas"]))
    else:
        print("Listas U3F: no hay archivos en {}, se omite.".format(args.u3f))

    if not os.path.exists(args.byrne):
        crear_plantilla_byrne(args.byrne)
    byrne = cargar_byrne(args.byrne)
    if byrne is not None:
        referencias["Byrne et al. (1994), femenino"] = ("byrne", relativo_a_bandas(byrne))
    else:
        print("Byrne et al. (1994): sin datos cargados, se omite.")

    for ruta in args.comparar:
        nombre = os.path.splitext(os.path.basename(ruta))[0]
        r = analizar(*leer_mono(ruta), args.umbral)
        print("{}: {:.1f} % activo, Leq {:.2f} dBFS".format(nombre, r["activo"], r["leq"]))
        referencias[nombre] = (nombre, relativo_a_bandas(r["bandas"]))

    os.makedirs(SALIDAS, exist_ok=True)
    encabezado = ["banda_hz", "nivel_rel_db", "nivel_dbfs"] + (["nivel_db_spl"] if offset is not None else [])
    for clave, _ in referencias.values():
        encabezado += ["{}_rel_db".format(clave), "dif_{}_db".format(clave)]

    with open(os.path.join(SALIDAS, "ltass.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(encabezado)
        for i, banda in enumerate(BANDAS_NOMINALES):
            fila = [banda, "{:.2f}".format(relativos[i]), "{:.2f}".format(ltass["bandas"][i])]
            if offset is not None:
                fila.append("{:.2f}".format(ltass["bandas"][i] + offset))
            for _, niveles in referencias.values():
                fila += ["{:.2f}".format(niveles[i]), "{:.2f}".format(relativos[i] - niveles[i])]
            w.writerow(fila)
        fila = ["global", "0.00", "{:.2f}".format(ltass["leq"])]
        if offset is not None:
            fila.append("{:.2f}".format(ltass["leq"] + offset))
        w.writerow(fila + [""] * (len(encabezado) - len(fila)))

    graficar(os.path.join(SALIDAS, "ltass.png"), relativos,
             {nombre: niveles for nombre, (_, niveles) in referencias.items()})

    claves = [clave for clave, _ in referencias.values()]
    print("\nbanda (Hz)  QuickSIN  " + "  ".join("{:>8}  dif {:<5}".format(c, c) for c in claves))
    for i, banda in enumerate(BANDAS_NOMINALES):
        print("{:>10}  {:>8.2f}  ".format(banda, relativos[i]) + "  ".join(
            "{:>8.2f}  {:>+9.2f}".format(n[i], relativos[i] - n[i]) for _, n in referencias.values()))
    print("\nSalidas en {}".format(SALIDAS))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
