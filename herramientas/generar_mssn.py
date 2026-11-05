"""Paso 4: MSSN (ruido estacionario con la forma espectral del habla del QuickSIN).

Ruido gaussiano blanco con semilla fija, filtrado con un FIR de fase lineal (firwin2) diseñado
a partir del LTASS de herramientas/salidas/ltass.csv (correr antes ltass.py). Como el ruido
blanco tiene densidad espectral plana, la ganancia de cada banda es su nivel del LTASS menos
10·log10 del ancho de banda. El diseño se corrige iterativamente con el espectro medido hasta
que todas las bandas queden dentro de --tolerancia dB.

Se normaliza al Leq (dBFS) del habla activa del LTASS y se exporta en 24 bits a
audio/mssn/mssn_quicksin.wav. La verificación (desvío por banda respecto del LTASS, objetivo
<= 1 dB) queda en herramientas/salidas/mssn_verificacion.csv y .png.

El MSSN es estacionario. --modulacion F M aplica una modulación senoidal de amplitud de
frecuencia F Hz y profundidad M (0-1); está desactivada por defecto.

Uso:
    python herramientas/generar_mssn.py
    python herramientas/generar_mssn.py --duracion 300 --semilla 7
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
from comun import (BANDAS_EXACTAS, BANDAS_NOMINALES, ajustar_fir, cargar_ltass,  # noqa: E402
                   con_fundidos, leq_dbfs, relativo_a_bandas, tercios_octava)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDAS = os.path.join(RAIZ, "herramientas", "salidas")
LTASS = os.path.join(SALIDAS, "ltass.csv")
FUENTE = os.path.join(RAIZ, "audio", "quicksin", "todasPalabras.wav")
DESTINO = os.path.join(RAIZ, "audio", "mssn", "mssn_quicksin.wav")
ANCHOS_BANDA = BANDAS_EXACTAS * (10 ** (1 / 20) - 10 ** (-1 / 20))

COLORES = ["#2a78d6", "#eb6834"]
TINTA, TINTA_SECUNDARIA, GRILLA, EJE = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"


def graficar(ruta, ltass, mssn, objetivo_db):
    x = np.arange(len(BANDAS_NOMINALES))
    etiquetas = [str(b) if b < 1000 else "{:g}k".format(b / 1000) for b in BANDAS_NOMINALES]
    fig, (arriba, abajo) = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True,
                                        gridspec_kw={"height_ratios": [3, 2]})
    arriba.plot(x, ltass, color=COLORES[0], lw=2, marker="o", ms=4, label="LTASS QuickSIN")
    arriba.plot(x, mssn, color=COLORES[1], lw=2, marker="o", ms=4, label="MSSN generado")
    abajo.plot(x, mssn - ltass, color=COLORES[1], lw=2, marker="o", ms=4, label="MSSN − LTASS")
    abajo.axhline(0, color=EJE, lw=1)
    for signo in (-1, 1):
        abajo.axhline(signo * objetivo_db, color=TINTA_SECUNDARIA, lw=1, ls="--")
    abajo.set_ylim(-max(2, objetivo_db * 2), max(2, objetivo_db * 2))

    arriba.set_ylabel("Nivel relativo al global (dB)")
    arriba.set_title("Verificación del MSSN (suma de bandas = 0 dB)", loc="left", color=TINTA)
    abajo.set_ylabel("Desvío (dB)")
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
        ax.legend(frameon=False, labelcolor=TINTA)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ltass", default=LTASS)
    parser.add_argument("--destino", default=DESTINO)
    parser.add_argument("--fs", type=int, help="frecuencia de muestreo (default: la de todasPalabras.wav)")
    parser.add_argument("--duracion", type=float, default=180.0, help="s (default 180)")
    parser.add_argument("--fundido", type=float, default=0.050, help="s (default 0.050)")
    parser.add_argument("--semilla", type=int, default=0)
    parser.add_argument("--coeficientes", type=int, default=2 ** 15 + 1,
                        help="impar; default 32769 (resolución de fs/N, ~1.3 Hz a 44.1 kHz)")
    parser.add_argument("--pendiente-fuera", type=float, default=48.0,
                        help="caída en dB/octava fuera de 63 Hz-16 kHz (default 48)")
    parser.add_argument("--iteraciones", type=int, default=6)
    parser.add_argument("--tolerancia", type=float, default=0.5,
                        help="dB; el ajuste para cuando todas las bandas están dentro (default 0.5)")
    parser.add_argument("--objetivo", type=float, default=1.0, help="desvío máximo aceptable en dB")
    parser.add_argument("--modulacion", type=float, nargs=2, metavar=("F_HZ", "PROFUNDIDAD"),
                        help="modulación senoidal de amplitud (desactivada por defecto)")
    args = parser.parse_args()

    fs = args.fs or sf.info(FUENTE).samplerate
    ltass_rel, leq_objetivo = cargar_ltass(args.ltass)
    print("LTASS: {} (Leq del habla activa {:.2f} dBFS), fs = {} Hz".format(args.ltass, leq_objetivo, fs))

    n = int(round(args.duracion * fs))
    margen = args.coeficientes - 1  # se descarta la mitad a cada lado: el transitorio del filtro
    ruido = np.random.default_rng(args.semilla).standard_normal(n + margen)

    ganancias = ltass_rel - 10 * np.log10(ANCHOS_BANDA)
    y, h, _, iteraciones = ajustar_fir(ruido, fs, ltass_rel, ganancias, args.coeficientes,
                                       args.iteraciones, args.tolerancia, args.pendiente_fuera)
    y = y[margen // 2:margen // 2 + n]
    print("FIR: {} coeficientes ({:.3f} s, resolución {:.2f} Hz), {} iteraciones de ajuste"
          .format(len(h), len(h) / fs, fs / len(h), iteraciones))

    if args.modulacion:
        frecuencia, profundidad = args.modulacion
        y = y * (1 + profundidad * np.sin(2 * np.pi * frecuencia * np.arange(n) / fs))
        print("Modulación de amplitud: {:g} Hz, profundidad {:g}".format(frecuencia, profundidad))

    y = con_fundidos(y, fs, args.fundido)
    y *= 10 ** ((leq_objetivo - leq_dbfs(y)) / 20)
    pico = 20 * np.log10(np.max(np.abs(y)))
    if pico >= -0.1:
        raise SystemExit("El MSSN recorta (pico {:.2f} dBFS): bajá el nivel.".format(pico))

    os.makedirs(os.path.dirname(args.destino), exist_ok=True)
    sf.write(args.destino, y, fs, subtype="PCM_24")
    print("Exportado: {} ({:.1f} s, 24 bits)".format(args.destino, n / fs))
    print("  Leq {:.2f} dBFS (objetivo {:.2f}), pico {:.2f} dBFS".format(leq_dbfs(y), leq_objetivo, pico))

    # Verificación sobre el archivo exportado (con fundidos, cuantizado a 24 bits).
    y, _ = sf.read(args.destino, dtype="float64")
    mssn_rel = relativo_a_bandas(tercios_octava(y, fs))
    desvio = mssn_rel - ltass_rel
    with open(os.path.join(SALIDAS, "mssn_verificacion.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["banda_hz", "ltass_rel_db", "mssn_rel_db", "desvio_db"])
        for i, banda in enumerate(BANDAS_NOMINALES):
            w.writerow([banda, "{:.2f}".format(ltass_rel[i]), "{:.2f}".format(mssn_rel[i]),
                        "{:.2f}".format(desvio[i])])
    graficar(os.path.join(SALIDAS, "mssn_verificacion.png"), ltass_rel, mssn_rel, args.objetivo)

    print("\nbanda (Hz)  LTASS  MSSN  desvío")
    for i, banda in enumerate(BANDAS_NOMINALES):
        print("{:>10}  {:>6.2f}  {:>6.2f}  {:>+6.2f}".format(banda, ltass_rel[i], mssn_rel[i], desvio[i]))
    peor = int(np.argmax(np.abs(desvio)))
    estado = "CUMPLE" if abs(desvio[peor]) <= args.objetivo else "NO CUMPLE"
    print("\nDesvío máximo: {:+.2f} dB en {} Hz -> {} el objetivo de ±{:g} dB"
          .format(desvio[peor], BANDAS_NOMINALES[peor], estado, args.objetivo))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
