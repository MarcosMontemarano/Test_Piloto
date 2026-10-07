"""Genera los clips de audio en loop que usa test.py (audio/clips/).

Uso (solo para desarrollo, no lo necesita el ejecutable):
    pip install numpy scipy soundfile matplotlib
    python tools/recortar_audios.py

Requiere los archivos originales en audio/ (no se versionan en git).

Cada clip dura DURACION_S segundos, se exporta a 44.1 kHz estéreo en OGG Vorbis
y queda preparado para loop sin clicks: los últimos segundos del tramo se funden
(crossfade de igual potencia) sobre el inicio, así el final empalma con el
principio sin saltos ni bajones de nivel.

Selección objetiva del tramo de los ruidos ambientales (tren, avión, autopista)
-------------------------------------------------------------------------------
1. Se filtra el archivo original completo (remuestreado a FS) con la ponderación
   frecuencial A de IEC 61672-1, implementada como transformación bilineal de los
   polos y ceros analógicos de la norma, normalizada a 0 dB en 1 kHz.
2. Se calcula el nivel con ponderación temporal Fast (exponencial, tau = 125 ms),
   promediando la potencia de los dos canales. El medidor corre sobre el archivo
   completo y se lee cada 125 ms: L_AF(k) es la lectura al final de cada bloque
   y L_AFmax(k) el máximo de la lectura dentro del bloque.
3. Se recorren ventanas candidatas de DURACION_S con paso PASO_S, dejando afuera
   el primer y el último MARGEN_BORDE_S del archivo (silencios de codificación,
   fades o clicks en los bordes). Para cada una:
   L_Aeq (energía media de la señal ponderada A), L10 y L90 (percentiles 90 y 10
   de las lecturas L_AF de la ventana, interpolación lineal), L10 - L90 y
   L_AFmax - L_Aeq.
4. Se descartan las ventanas con L_AFmax - L_Aeq > UMBRAL_PICO_DB (eventos
   salientes) y, si UMBRAL_L10_L90_DB no es None, las de L10 - L90 mayor a ese
   valor. Entre las restantes se elige la de menor L10 - L90 (en caso de empate,
   la primera). Si ninguna cumple, se elige igualmente la de menor L10 - L90 y
   se marca en el reporte.
5. El clip exportado (con el crossfade ya aplicado) se lleva a un L_Aeq común de
   NIVEL_RUIDO_LAEQ_DBFS para que los ambientes queden parejos en escala digital.
   La calibración en dBA SPL se hace después, midiendo in situ en el lugar del test.

Los niveles son relativos a la escala digital (dBFS ponderados A): 0 dB
corresponde a una senoidal de 1 kHz a fondo de escala. No son dBA SPL.

Salidas: los clips .ogg, audio/clips/reporte_recorte.csv y una figura PNG por
ruido ambiental (audio/clips/nivel_<clip>.png).
"""
import csv
import os
from math import gcd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from scipy.signal import bilinear_zpk, lfilter, resample_poly, sosfilt, sosfreqz, zpk2sos

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGEN = os.path.join(RAIZ, "audio")
DESTINO = os.path.join(ORIGEN, "clips")
REPORTE = os.path.join(DESTINO, "reporte_recorte.csv")

FS = 44100
DURACION_S = 30.0
CRUCE_S = 0.5          # crossfade de la música y el ruido blanco
PICO_MAX_DBFS = -1.0

# Criterio de selección de los ruidos ambientales (editables)
UMBRAL_PICO_DB = 6.0       # máximo L_AFmax - L_Aeq admitido en la ventana
UMBRAL_L10_L90_DB = None   # máximo L10 - L90 admitido (None: sin límite, solo se minimiza)
TAU_FAST_S = 0.125         # constante de tiempo Fast y período de lectura del nivel
PASO_S = 1.0               # paso entre ventanas candidatas
MARGEN_BORDE_S = 1.0       # se excluyen el inicio y el final del archivo (silencios, fades, clicks)
CRUCE_RUIDO_S = 0.05       # crossfade final-inicio de los ruidos ambientales
NIVEL_RUIDO_LAEQ_DBFS = -27.0  # L_Aeq común de los clips exportados (el pico debe quedar <= PICO_MAX_DBFS)

# (archivo de salida, archivo de origen o None si se genera, inicio en s)
CLIPS = (
    ("musica_pop.ogg", "gr0za-pop-pop-music-577843.mp3", 55.0),
    # Placeholder del MSSN: ruido blanco a -20 dBFS RMS (no estaba
    # audiocheck.net_whitenoise.wav, se genera con semilla fija).
    ("ruido_blanco.ogg", None, 0.0),
)

# (archivo de salida, archivo de origen): el inicio lo elige el análisis
RUIDOS_AMBIENTE = (
    ("ruido_tren.ogg", "freesound_community-train-ride-inside-the-car-17382.mp3"),
    ("ruido_avion.ogg", "ernyslts-aircraft-cabin-sound-129404.mp3"),
    # Tránsito lejano y continuo: las grabaciones cercanas a la calle (pasadas de autos
    # individuales) no bajaban de L10 - L90 = 3.2 dB en ninguna ventana.
    ("ruido_autopista.ogg", "edr-distant-highway-traffic-at-night-8854.mp3"),
)

# Frecuencias de los polos de la ponderación A (IEC 61672-1, anexo E)
F1, F2, F3, F4 = 20.598997, 107.65265, 737.86223, 12194.217


def leer_original(nombre):
    datos, fs = sf.read(os.path.join(ORIGEN, nombre), always_2d=True)
    if datos.shape[1] == 1:
        datos = np.repeat(datos, 2, axis=1)
    datos = datos[:, :2]
    if fs != FS:
        divisor = gcd(FS, fs)
        datos = resample_poly(datos, FS // divisor, fs // divisor, axis=0)
    return datos


def cargar(nombre, inicio, cruce_s):
    total = int((DURACION_S + cruce_s) * FS)
    if nombre is None:
        rng = np.random.default_rng(1234)
        ruido = rng.standard_normal(total) * 10 ** (-20 / 20)
        return np.column_stack([ruido, ruido])

    primera = int(inicio * FS)
    tramo = leer_original(nombre)[primera:primera + total]
    if len(tramo) < total:
        raise ValueError("{}: el tramo pedido excede la duración del archivo".format(nombre))
    return tramo


def preparar_loop(tramo, cruce_s, laeq_objetivo=None, sos=None):
    """Devuelve el clip listo para loop y la ganancia aplicada en dB.

    Sin laeq_objetivo, solo se baja la ganancia si el pico supera PICO_MAX_DBFS.
    Con laeq_objetivo, el clip se lleva a ese L_Aeq; si así el pico supera
    PICO_MAX_DBFS se detiene, porque limitarlo rompería la igualdad de niveles.
    """
    largo = int(DURACION_S * FS)
    cruce = int(cruce_s * FS)
    t = np.linspace(0, np.pi / 2, cruce)[:, None]
    clip = tramo[:largo].copy()
    clip[:cruce] = tramo[:cruce] * np.sin(t) + tramo[largo:largo + cruce] * np.cos(t)
    pico = np.abs(clip).max()
    limite = 10 ** (PICO_MAX_DBFS / 20)
    ganancia = 1.0
    if laeq_objetivo is not None:
        ganancia = 10 ** ((laeq_objetivo - laeq(clip, sos)) / 20)
        if pico * ganancia > limite:
            raise ValueError("Con L_Aeq = {:g} dBFS el pico llega a {:.1f} dBFS (máximo {:g}): bajar "
                             "NIVEL_RUIDO_LAEQ_DBFS.".format(laeq_objetivo, 20 * np.log10(pico * ganancia),
                                                             PICO_MAX_DBFS))
    elif pico > limite:
        ganancia = limite / pico
    clip *= ganancia
    return clip, 20 * np.log10(ganancia)


def laeq(datos, sos):
    """L_Aeq en dBFS de toda la señal (potencia promediada entre canales)."""
    return 10 * np.log10(np.mean(sosfilt(sos, datos, axis=0) ** 2) + 1e-20)


def guardar_ogg(clip, salida):
    ruta = os.path.join(DESTINO, salida)
    # Escritura por bloques: libsndfile desborda la pila en Windows si
    # se le pasa todo el clip OGG de una sola vez.
    with sf.SoundFile(ruta, "w", FS, 2, format="OGG", subtype="VORBIS") as archivo:
        for inicio_bloque in range(0, len(clip), FS):
            archivo.write(clip[inicio_bloque:inicio_bloque + FS])
    print("{}: {:.1f} s, {:.0f} kB".format(salida, len(clip) / FS, os.path.getsize(ruta) / 1024))


def ganancia_a_analogica(f):
    """Respuesta analítica de la ponderación A en dB (IEC 61672-1, anexo E)."""
    f2 = np.asarray(f, dtype=float) ** 2
    h = (F4 ** 2 * f2 ** 2) / ((f2 + F1 ** 2) * np.sqrt(f2 + F2 ** 2) * np.sqrt(f2 + F3 ** 2) * (f2 + F4 ** 2))
    h1k = (F4 ** 2 * 1e12) / ((1e6 + F1 ** 2) * np.sqrt(1e6 + F2 ** 2) * np.sqrt(1e6 + F3 ** 2) * (1e6 + F4 ** 2))
    return 20 * np.log10(h / h1k)


def filtro_a(fs):
    """Ponderación A digital (bilineal) en secciones de segundo orden, 0 dB en 1 kHz."""
    polos = -2 * np.pi * np.array([F1, F1, F2, F3, F4, F4])
    ceros = np.zeros(4)
    z, p, k = bilinear_zpk(ceros, polos, 1.0, fs)
    sos = zpk2sos(z, p, k)
    _, h = sosfreqz(sos, worN=[1000.0], fs=fs)
    sos[0, :3] /= np.abs(h[0])
    return sos


def informar_filtro_a(sos):
    """Imprime la desviación del filtro digital respecto de la respuesta analítica."""
    bandas = np.array([10, 20, 31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 10000, 12500, 16000, 20000])
    _, h = sosfreqz(sos, worN=bandas, fs=FS)
    desvio = 20 * np.log10(np.abs(h)) - ganancia_a_analogica(bandas)
    print("Ponderación A digital (fs = {} Hz), desvío respecto de IEC 61672-1:".format(FS))
    print("  " + "  ".join("{:g} Hz: {:+.2f}".format(f, d) for f, d in zip(bandas, desvio)))


def nivel_a_fast(datos, sos):
    """Lecturas cada TAU_FAST_S: energía media, L_AF al final y L_AFmax del bloque."""
    p2 = np.mean(sosfilt(sos, datos, axis=0) ** 2, axis=1)
    n_bloques = int(len(p2) / (TAU_FAST_S * FS))
    bordes = np.round(np.arange(n_bloques + 1) * TAU_FAST_S * FS).astype(int)
    p2 = p2[:bordes[-1]]

    c = np.exp(-1 / (TAU_FAST_S * FS))
    # El medidor arranca en la potencia media del primer bloque (sin transitorio inicial)
    inicial = p2[:bordes[1]].mean()
    fast, _ = lfilter([1 - c], [1, -c], p2, zi=[c * inicial])

    energia = np.add.reduceat(p2, bordes[:-1]) / np.diff(bordes)
    l_af = 10 * np.log10(fast[bordes[1:] - 1] + 1e-20)
    l_afmax = 10 * np.log10(np.maximum.reduceat(fast, bordes[:-1]) + 1e-20)
    return energia, l_af, l_afmax, np.diff(bordes)


def evaluar_ventanas(energia, l_af, l_afmax, muestras, duracion_s):
    """Métricas de cada ventana candidata de DURACION_S con paso PASO_S."""
    por_ventana = int(round(DURACION_S / TAU_FAST_S))
    por_paso = int(round(PASO_S / TAU_FAST_S))
    ventanas = []
    k = int(round(MARGEN_BORDE_S / TAU_FAST_S))
    while (k + por_ventana <= len(l_af)
           and k * TAU_FAST_S + DURACION_S + CRUCE_RUIDO_S <= duracion_s - MARGEN_BORDE_S):
        tramo = slice(k, k + por_ventana)
        laeq = 10 * np.log10(np.sum(energia[tramo] * muestras[tramo]) / np.sum(muestras[tramo]) + 1e-20)
        l10, l90 = np.percentile(l_af[tramo], [90, 10])
        lmax = l_afmax[tramo].max()
        ventanas.append({"inicio_s": k * TAU_FAST_S, "laeq": laeq, "l10": l10, "l90": l90,
                         "l10_l90": l10 - l90, "lmax_laeq": lmax - laeq})
        k += por_paso
    for v in ventanas:
        v["cumple"] = v["lmax_laeq"] <= UMBRAL_PICO_DB and (
            UMBRAL_L10_L90_DB is None or v["l10_l90"] <= UMBRAL_L10_L90_DB)
    return ventanas


def elegir_ventana(ventanas, nombre):
    validas = [v for v in ventanas if v["cumple"]]
    if not validas:
        print("AVISO: {}: ninguna ventana cumple los umbrales; se elige la de menor L10 - L90.".format(nombre))
        validas = ventanas
    return min(validas, key=lambda v: v["l10_l90"])


def graficar(salida, origen, l_af, ventanas, elegida):
    tiempo = (np.arange(len(l_af)) + 1) * TAU_FAST_S
    inicios = np.array([v["inicio_s"] for v in ventanas])
    dispersion = np.array([v["l10_l90"] for v in ventanas])
    cumple = np.array([v["cumple"] for v in ventanas])
    tinta, tinta_2, serie, superficie = "#0b0b0b", "#52514e", "#2a78d6", "#fcfcfb"
    a, b = elegida["inicio_s"], elegida["inicio_s"] + DURACION_S

    fig, (arriba, abajo) = plt.subplots(2, 1, figsize=(10, 6.5), height_ratios=[3, 2],
                                        constrained_layout=True, facecolor=superficie)
    arriba.axvspan(a, b, color=serie, alpha=0.12, lw=0)
    arriba.plot(tiempo, l_af, color=serie, lw=1.0)
    arriba.hlines([elegida["l10"], elegida["l90"]], a, b, color=tinta_2, lw=1.0, ls="--")
    arriba.set_title("{}: nivel L_AF (Fast, 125 ms) del archivo original {}\n"
                     "Tramo elegido (sombreado) {:.0f} a {:.0f} s: L_Aeq = {:.1f} dBFS, L10 = {:.1f}, L90 = {:.1f}"
                     " (trazos), L10 - L90 = {:.2f} dB, L_AFmax - L_Aeq = {:.2f} dB".format(
                         salida, origen, a, b, elegida["laeq"], elegida["l10"], elegida["l90"],
                         elegida["l10_l90"], elegida["lmax_laeq"]),
                     fontsize=8.5, color=tinta, loc="left", linespacing=1.5)
    arriba.set_ylabel("Nivel ponderado A (dBFS)", color=tinta_2)
    arriba.set_xlabel("Tiempo (s)", color=tinta_2)

    abajo.plot(inicios[cumple], dispersion[cumple], "o", ms=3.5, color=serie,
               label="cumple L_AFmax - L_Aeq ≤ {:g} dB".format(UMBRAL_PICO_DB))
    if (~cumple).any():
        abajo.plot(inicios[~cumple], dispersion[~cumple], "x", ms=4, color=tinta_2, label="descartada")
    abajo.plot([a], [elegida["l10_l90"]], "o", ms=9, mfc="none", mec=tinta, mew=1.5, label="elegida")
    abajo.set_ylabel("L10 - L90 (dB)", color=tinta_2)
    abajo.set_xlabel("Inicio de la ventana candidata de {:g} s (s)".format(DURACION_S), color=tinta_2)
    abajo.legend(fontsize=8, frameon=False, loc="best")

    for eje in (arriba, abajo):
        eje.set_facecolor(superficie)
        eje.grid(True, color="#e4e3df", lw=0.6)
        eje.set_axisbelow(True)
        eje.tick_params(colors=tinta_2, labelsize=8)
        for lado in ("top", "right"):
            eje.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            eje.spines[lado].set_color("#c3c2b7")
        eje.set_xlim(0, tiempo[-1])

    ruta = os.path.join(DESTINO, "nivel_{}.png".format(os.path.splitext(salida)[0]))
    fig.savefig(ruta, dpi=150, facecolor=superficie)
    plt.close(fig)


def procesar_ruido_ambiente(salida, origen, sos):
    datos = leer_original(origen)
    duracion_s = len(datos) / FS
    energia, l_af, l_afmax, muestras = nivel_a_fast(datos, sos)
    ventanas = evaluar_ventanas(energia, l_af, l_afmax, muestras, duracion_s)
    elegida = elegir_ventana(ventanas, salida)

    primera = int(round(elegida["inicio_s"] * FS))
    tramo = datos[primera:primera + int((DURACION_S + CRUCE_RUIDO_S) * FS)]
    clip, ganancia_db = preparar_loop(tramo, CRUCE_RUIDO_S, NIVEL_RUIDO_LAEQ_DBFS, sos)
    guardar_ogg(clip, salida)
    exportado, _ = sf.read(os.path.join(DESTINO, salida), always_2d=True)
    graficar(salida, origen, l_af, ventanas, elegida)

    print("  inicio {:.0f} s, L_Aeq {:.1f} dBFS, L10 - L90 {:.2f} dB, L_AFmax - L_Aeq {:.2f} dB, {}".format(
        elegida["inicio_s"], elegida["laeq"], elegida["l10_l90"], elegida["lmax_laeq"],
        "cumple" if elegida["cumple"] else "NO CUMPLE"))
    return {
        "clip": salida,
        "archivo_original": origen,
        "inicio_s": "{:.0f}".format(elegida["inicio_s"]),
        "fin_s": "{:.0f}".format(elegida["inicio_s"] + DURACION_S),
        "LAeq_dBFS": "{:.2f}".format(elegida["laeq"]),
        "L10_dBFS": "{:.2f}".format(elegida["l10"]),
        "L90_dBFS": "{:.2f}".format(elegida["l90"]),
        "L10_menos_L90_dB": "{:.2f}".format(elegida["l10_l90"]),
        "LAFmax_menos_LAeq_dB": "{:.2f}".format(elegida["lmax_laeq"]),
        "cumple_umbrales": "si" if elegida["cumple"] else "no",
        "ventanas_candidatas": len(ventanas),
        "ventanas_que_cumplen": sum(v["cumple"] for v in ventanas),
        "ganancia_exportacion_dB": "{:.2f}".format(ganancia_db),
        "LAeq_clip_exportado_dBFS": "{:.2f}".format(laeq(exportado, sos)),
        "pico_clip_exportado_dBFS": "{:.2f}".format(20 * np.log10(np.abs(exportado).max())),
    }


def escribir_reporte(filas):
    with open(REPORTE, "w", newline="", encoding="utf-8") as archivo:
        archivo.write("# Selección de tramos de ruido ambiental (tools/recortar_audios.py)\n")
        archivo.write("# Niveles relativos a escala digital: dBFS ponderados A (0 dB = senoidal de 1 kHz a fondo"
                      " de escala). NO son dBA SPL.\n")
        archivo.write("# Ponderación A IEC 61672-1 (bilineal, fs = {} Hz); ponderación temporal Fast"
                      " (tau = {:g} s), lecturas cada {:g} s; potencia promediada entre canales.\n".format(
                          FS, TAU_FAST_S, TAU_FAST_S))
        archivo.write("# Ventanas de {:g} s con paso de {:g} s, excluyendo {:g} s en cada borde del archivo."
                      " Umbrales: L_AFmax - L_Aeq <= {:g} dB; {}."
                      " Se elige la de menor L10 - L90 entre las que cumplen.\n".format(
                          DURACION_S, PASO_S, MARGEN_BORDE_S, UMBRAL_PICO_DB,
                          "L10 - L90 sin límite" if UMBRAL_L10_L90_DB is None
                          else "L10 - L90 <= {:g} dB".format(UMBRAL_L10_L90_DB)))
        archivo.write("# Niveles de selección medidos sobre el archivo original, antes del crossfade de {:g} s y"
                      " de la ganancia de exportación (ganancia_exportacion_dB), que lleva cada clip a L_Aeq ="
                      " {:g} dBFS. Las dos últimas columnas se miden sobre el OGG exportado.\n".format(
                          CRUCE_RUIDO_S, NIVEL_RUIDO_LAEQ_DBFS))
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0]))
        escritor.writeheader()
        escritor.writerows(filas)


def main():
    os.makedirs(DESTINO, exist_ok=True)
    for salida, origen, inicio in CLIPS:
        clip, _ = preparar_loop(cargar(origen, inicio, CRUCE_S), CRUCE_S)
        guardar_ogg(clip, salida)

    sos = filtro_a(FS)
    informar_filtro_a(sos)
    filas = [procesar_ruido_ambiente(salida, origen, sos) for salida, origen in RUIDOS_AMBIENTE]
    escribir_reporte(filas)
    print("Reporte: {}".format(os.path.relpath(REPORTE, RAIZ)))


if __name__ == "__main__":
    main()
