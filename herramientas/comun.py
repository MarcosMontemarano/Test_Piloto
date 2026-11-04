"""Funciones compartidas por las herramientas de análisis de audio.

Los niveles son Leq lineales (sin ponderación) en dBFS, con 0 dBFS = RMS de 1.0
sobre las muestras float en [-1, 1) que devuelve soundfile.
"""

import numpy as np

EPS = 1e-12


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
