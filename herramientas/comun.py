"""Funciones compartidas por las herramientas de análisis de audio.

Los niveles son Leq lineales (sin ponderación) en dBFS, con 0 dBFS = RMS de 1.0
sobre las muestras float en [-1, 1) que devuelve soundfile.
"""

import csv

import numpy as np
from scipy.signal import welch

EPS = 1e-12

# Bandas de tercio de octava de 63 Hz a 16 kHz, base 10 (IEC 61260-1): fm = 1000 * 10^(k/10).
BANDAS_NOMINALES = [63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250,
                    1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000]
BANDAS_EXACTAS = 1000.0 * 10 ** (np.arange(-12, 13) / 10)
RESOLUCION_MAX_HZ = 6.0


def leq_dbfs(x):
    """Leq lineal en dBFS (RMS = 1.0 -> 0 dBFS)."""
    x = np.asarray(x, dtype=np.float64)
    return 10 * np.log10(np.mean(x ** 2) + EPS)


def niveles_tramas(x, fs, trama_s=0.020):
    """Nivel (dBFS) de cada trama no solapada de trama_s segundos: la envolvente de energía."""
    n = int(round(trama_s * fs))
    cantidad = len(x) // n
    tramas = np.asarray(x[:cantidad * n], dtype=np.float64).reshape(cantidad, n)
    return 10 * np.log10(np.mean(tramas ** 2, axis=1) + EPS)


def porcentaje_pausas(x, fs, umbral_db=30.0, trama_s=0.020):
    """Porcentaje de tramas que están umbral_db o más por debajo del máximo de la envolvente."""
    niveles = niveles_tramas(x, fs, trama_s)
    return 100.0 * np.mean(niveles <= niveles.max() - umbral_db)


def quitar_pausas(x, fs, umbral_db=30.0, trama_s=0.020):
    """Concatena las tramas activas (a menos de umbral_db del máximo). Devuelve (señal, % activo)."""
    n = int(round(trama_s * fs))
    niveles = niveles_tramas(x, fs, trama_s)
    activa = niveles > niveles.max() - umbral_db
    tramas = np.asarray(x[:len(niveles) * n], dtype=np.float64).reshape(len(niveles), n)
    return tramas[activa].ravel(), 100.0 * np.mean(activa)


def psd_welch(x, fs, resolucion_hz=RESOLUCION_MAX_HZ):
    """PSD de Welch (Hann, 50 % de solapamiento) con resolución <= resolucion_hz."""
    nperseg = int(2 ** np.ceil(np.log2(fs / resolucion_hz)))
    return welch(x, fs, window="hann", nperseg=nperseg, noverlap=nperseg // 2,
                 detrend=False, scaling="density")


def potencia_bandas(f, psd):
    """Integra la PSD en cada tercio de octava, ponderando los bins que caen en un borde."""
    df = f[1] - f[0]
    bajo, alto = f - df / 2, f + df / 2
    potencias = []
    for fm in BANDAS_EXACTAS:
        fl, fh = fm * 10 ** (-1 / 20), fm * 10 ** (1 / 20)
        solape = np.clip(np.minimum(alto, fh) - np.maximum(bajo, fl), 0, None)
        potencias.append(np.sum(psd * solape))
    return np.array(potencias)


def tercios_octava(x, fs):
    """Nivel (dBFS) de cada tercio de octava de 63 Hz a 16 kHz."""
    f, psd = psd_welch(x, fs)
    return 10 * np.log10(potencia_bandas(f, psd) + EPS)


def cargar_ltass(ruta):
    """Lee la salida de ltass.py. Devuelve (niveles relativos por banda en dB, Leq global en dBFS)."""
    relativos, leq = {}, None
    with open(ruta, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            if fila["banda_hz"] == "global":
                leq = float(fila["nivel_dbfs"])
            else:
                relativos[int(fila["banda_hz"])] = float(fila["nivel_rel_db"])
    return np.array([relativos[b] for b in BANDAS_NOMINALES]), leq
