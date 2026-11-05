"""Funciones compartidas por las herramientas de análisis de audio.

Los niveles son Leq lineales (sin ponderación) en dBFS, con 0 dBFS = RMS de 1.0
sobre las muestras float en [-1, 1) que devuelve soundfile.
"""

import csv

import numpy as np
from scipy.signal import firwin2, oaconvolve, welch

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


def con_fundidos(x, fs, fundido_s):
    """Copia de x con fundidos de entrada y salida de medio coseno de fundido_s segundos."""
    n = int(round(fundido_s * fs))
    rampa = 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / n)
    y = np.array(x, dtype=np.float64)
    y[:n] *= rampa
    y[-n:] *= rampa[::-1]
    return y


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


def disenar_fir(ganancias_db, fs, coeficientes, pendiente_fuera_db_oct=0.0):
    """FIR de fase lineal (firwin2) con la ganancia dada en cada frecuencia central.

    La ganancia se interpola en dB sobre frecuencia logarítmica. Fuera de 63 Hz-16 kHz (desde
    los bordes de las bandas extremas) se mantiene el valor del borde, o cae con
    pendiente_fuera_db_oct dB por octava si es mayor que cero.
    """
    if coeficientes % 2 == 0:
        raise ValueError("La cantidad de coeficientes tiene que ser impar (FIR tipo I).")
    nyquist = fs / 2
    borde_bajo, borde_alto = BANDAS_EXACTAS[0] * 10 ** (-1 / 20), BANDAS_EXACTAS[-1] * 10 ** (1 / 20)
    f = np.geomspace(1.0, nyquist, 4000)
    g = np.interp(np.log10(f), np.log10(np.concatenate(([borde_bajo], BANDAS_EXACTAS, [borde_alto]))),
                  np.concatenate(([ganancias_db[0]], ganancias_db, [ganancias_db[-1]])))
    if pendiente_fuera_db_oct > 0:
        g -= pendiente_fuera_db_oct * np.clip(np.log2(borde_bajo / f), 0, None)
        g -= pendiente_fuera_db_oct * np.clip(np.log2(f / borde_alto), 0, None)
    f = np.concatenate(([0.0], f))
    g = np.concatenate(([g[0]], g))
    nfreqs = 1 + 2 ** (int(np.ceil(np.log2(coeficientes))) + 1)
    return firwin2(coeficientes, f, 10 ** (g / 20), nfreqs=nfreqs, fs=fs)


def filtrar(x, h):
    """Filtra con un FIR de fase lineal y compensa su retardo: la salida queda alineada con x."""
    retardo = (len(h) - 1) // 2
    return oaconvolve(x, h)[retardo:retardo + len(x)]


def ajustar_fir(x, fs, objetivo_rel, ganancias_db, coeficientes, iteraciones, tolerancia_db,
                pendiente_fuera_db_oct=0.0):
    """Diseña, filtra y corrige la ganancia por banda hasta que el espectro de la salida
    (relativo a su suma de bandas) quede a tolerancia_db del objetivo o se agoten las iteraciones.

    Devuelve (salida, filtro, desvío por banda en dB, iteraciones usadas).
    """
    ganancias_db = np.array(ganancias_db, dtype=np.float64)
    for iteracion in range(1, iteraciones + 1):
        h = disenar_fir(ganancias_db, fs, coeficientes, pendiente_fuera_db_oct)
        y = filtrar(x, h)
        desvio = relativo_a_bandas(tercios_octava(y, fs)) - objetivo_rel
        if np.max(np.abs(desvio)) <= tolerancia_db:
            break
        ganancias_db -= desvio
    return y, h, desvio, iteracion


def relativo_a_bandas(niveles):
    """Niveles por banda relativos a su suma energética (la suma de las bandas queda en 0 dB)."""
    niveles = np.asarray(niveles, dtype=np.float64)
    return niveles - 10 * np.log10(np.sum(10 ** (niveles / 10)))


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
