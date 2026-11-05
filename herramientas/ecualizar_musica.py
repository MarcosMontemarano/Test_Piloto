"""Paso 5: ecualización de los clips musicales al LTASS del QuickSIN.

Para cada clip (por defecto, audio/clips/musica_*.ogg):
1. Calcula su espectro en tercios de octava sobre el clip completo, con el mismo método que
   el LTASS (Welch, Hann, 50 %, <= 6 Hz), promediando la potencia de los dos canales.
2. Diseña un FIR de fase lineal con la corrección LTASS / espectro del clip y lo ajusta
   iterativamente con el espectro medido. Se aplica el mismo FIR a los dos canales.
3. Filtra en forma circular: los clips son loops (recortar_audios.py funde el final sobre el
   principio), así que el relleno de los bordes es el propio clip dado vuelta (antes del
   principio va el final y viceversa), de al menos la longitud del FIR. Después se compensa el
   retardo y se recorta a la duración original. El resultado sigue empalmando sin clicks; no se
   agregan fundidos.
4. Renormaliza al Leq original del clip. Si el pico supera --pico-max dBFS, baja la ganancia
   hasta ese pico y lo reporta.
5. Exporta audio/musica/<nombre>_eq.wav (24 bits) y deja los clips originales sin tocar.

La desviación residual por banda respecto del LTASS queda en
herramientas/salidas/eq_<nombre>.csv y .png.

Uso:
    python herramientas/ecualizar_musica.py
    python herramientas/ecualizar_musica.py --archivo audio/clips/musica_piano.ogg
"""

import argparse
import csv
import glob
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comun import (BANDAS_NOMINALES, ajustar_fir, cargar_ltass, leq_dbfs,  # noqa: E402
                   relativo_a_bandas, tercios_octava)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPS = os.path.join(RAIZ, "audio", "clips")
DESTINO = os.path.join(RAIZ, "audio", "musica")
SALIDAS = os.path.join(RAIZ, "herramientas", "salidas")
LTASS = os.path.join(SALIDAS, "ltass.csv")

COLORES = ["#2a78d6", "#eb6834", "#1baf7a"]
TINTA, TINTA_SECUNDARIA, GRILLA, EJE = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"


def salto_empalme(x):
    """Salto entre la última y la primera muestra del loop, comparado con los saltos internos.

    Devuelve (salto en el empalme, percentil 99.9 de los saltos entre muestras consecutivas).
    """
    x = x if x.ndim == 2 else x[:, None]
    return float(np.max(np.abs(x[0] - x[-1]))), float(np.percentile(np.abs(np.diff(x, axis=0)), 99.9))


def graficar(ruta, nombre, ltass, original, ecualizado, objetivo_db):
    x = np.arange(len(BANDAS_NOMINALES))
    etiquetas = [str(b) if b < 1000 else "{:g}k".format(b / 1000) for b in BANDAS_NOMINALES]
    fig, (arriba, abajo) = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True,
                                        gridspec_kw={"height_ratios": [3, 2]})
    arriba.plot(x, ltass, color=COLORES[0], lw=2, marker="o", ms=4, label="LTASS QuickSIN")
    arriba.plot(x, original, color=COLORES[2], lw=2, marker="o", ms=4, label="{} original".format(nombre))
    arriba.plot(x, ecualizado, color=COLORES[1], lw=2, marker="o", ms=4, label="{} ecualizado".format(nombre))
    abajo.plot(x, ecualizado - ltass, color=COLORES[1], lw=2, marker="o", ms=4,
               label="Residual (ecualizado − LTASS)")
    abajo.axhline(0, color=EJE, lw=1)
    for signo in (-1, 1):
        abajo.axhline(signo * objetivo_db, color=TINTA_SECUNDARIA, lw=1, ls="--")
    limite = max(2, objetivo_db * 2, np.max(np.abs(ecualizado - ltass)) * 1.2)
    abajo.set_ylim(-limite, limite)

    arriba.set_ylabel("Nivel relativo al global (dB)")
    arriba.set_title("Ecualización de {} (suma de bandas = 0 dB)".format(nombre), loc="left", color=TINTA)
    abajo.set_ylabel("Residual (dB)")
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


def ecualizar(ruta, ltass_rel, args):
    nombre = os.path.splitext(os.path.basename(ruta))[0]
    x, fs = sf.read(ruta, dtype="float64")
    n = len(x)
    leq_original = leq_dbfs(x)
    original_rel = relativo_a_bandas(tercios_octava(x, fs))
    print("\n{}: {:.2f} s, {} canal(es), {} Hz, Leq {:.2f} dBFS, pico {:.2f} dBFS".format(
        os.path.basename(ruta), n / fs, x.shape[1] if x.ndim == 2 else 1, fs, leq_original,
        20 * np.log10(np.max(np.abs(x)))))

    # Relleno circular de al menos la longitud del FIR a cada lado.
    relleno = args.coeficientes
    extendido = x[np.arange(-relleno, n + relleno) % n]
    y, h, _, iteraciones = ajustar_fir(extendido, fs, ltass_rel, ltass_rel - original_rel,
                                       args.coeficientes, args.iteraciones, args.tolerancia,
                                       recorte=slice(relleno, relleno + n))
    print("  FIR: {} coeficientes, {} iteraciones de ajuste".format(len(h), iteraciones))

    y *= 10 ** ((leq_original - leq_dbfs(y)) / 20)
    pico = 20 * np.log10(np.max(np.abs(y)))
    if pico > args.pico_max:
        reduccion = args.pico_max - pico
        y *= 10 ** (reduccion / 20)
        print("  ATENCIÓN: el pico llegaba a {:.2f} dBFS; se bajó la ganancia {:.2f} dB "
              "(Leq {:.2f} dBFS en lugar de {:.2f}).".format(pico, -reduccion, leq_dbfs(y), leq_original))
    else:
        print("  Leq {:.2f} dBFS (igual al original), pico {:.2f} dBFS".format(leq_dbfs(y), pico))

    os.makedirs(DESTINO, exist_ok=True)
    destino = os.path.join(DESTINO, "{}_eq.wav".format(nombre))
    sf.write(destino, y, fs, subtype="PCM_24")
    print("  Exportado: {}".format(destino))

    # Verificación sobre el archivo exportado.
    y, _ = sf.read(destino, dtype="float64")
    ecualizado_rel = relativo_a_bandas(tercios_octava(y, fs))
    residual = ecualizado_rel - ltass_rel
    salto_original, tipico_original = salto_empalme(x)
    salto, tipico = salto_empalme(y)
    print("  Empalme del loop: salto {:.4f} (p99.9 interno {:.4f}); en el original {:.4f} ({:.4f})"
          .format(salto, tipico, salto_original, tipico_original))

    os.makedirs(SALIDAS, exist_ok=True)
    with open(os.path.join(SALIDAS, "eq_{}.csv".format(nombre)), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["banda_hz", "ltass_rel_db", "original_rel_db", "ecualizado_rel_db", "residual_db"])
        for i, banda in enumerate(BANDAS_NOMINALES):
            w.writerow([banda] + ["{:.2f}".format(v[i]) for v in
                                  (ltass_rel, original_rel, ecualizado_rel, residual)])
    graficar(os.path.join(SALIDAS, "eq_{}.png".format(nombre)), nombre, ltass_rel, original_rel,
             ecualizado_rel, args.objetivo)

    print("\n  banda (Hz)  original-LTASS  residual")
    for i, banda in enumerate(BANDAS_NOMINALES):
        print("  {:>10}  {:>+14.2f}  {:>+8.2f}".format(banda, original_rel[i] - ltass_rel[i], residual[i]))
    peor = int(np.argmax(np.abs(residual)))
    estado = "CUMPLE" if abs(residual[peor]) <= args.objetivo else "NO CUMPLE"
    print("  Residual máximo: {:+.2f} dB en {} Hz -> {} el objetivo de ±{:g} dB"
          .format(residual[peor], BANDAS_NOMINALES[peor], estado, args.objetivo))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archivo", help="procesar solo este clip")
    parser.add_argument("--ltass", default=LTASS)
    parser.add_argument("--coeficientes", type=int, default=2 ** 15 + 1, help="impar (default 32769)")
    parser.add_argument("--iteraciones", type=int, default=6)
    parser.add_argument("--tolerancia", type=float, default=0.5, help="dB (default 0.5)")
    parser.add_argument("--objetivo", type=float, default=1.0, help="residual máximo aceptable en dB")
    parser.add_argument("--pico-max", type=float, default=-1.0, help="dBFS (default -1)")
    args = parser.parse_args()

    ltass_rel, _ = cargar_ltass(args.ltass)
    archivos = [args.archivo] if args.archivo else sorted(glob.glob(os.path.join(CLIPS, "musica_*.ogg")))
    if not archivos:
        raise SystemExit("No hay clips musicales en {}".format(CLIPS))
    print("Clips a ecualizar: " + ", ".join(os.path.basename(a) for a in archivos))
    for ruta in archivos:
        ecualizar(ruta, ltass_rel, args)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
