"""Reproducción por dos salidas independientes (monitores y auriculares) con sounddevice.

Cada Salida abre su propio OutputStream y mezcla en el callback las fuentes que tenga activas
(loops o sonidos de una sola vez), cada una con su ganancia. Los cambios de ganancia y los
cortes se hacen con una rampa lineal de un bloque (~23 ms) para que no haya clicks.

Los archivos se remuestrean al cargarlos si su frecuencia no coincide con la del dispositivo.
Los loops se remuestrean en forma circular (con el final antes del principio y viceversa), así
el empalme sigue sin saltos.
"""

import sys
import threading
import time
from math import gcd

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfiltfilt

BLOQUE = 1024
SIN_RESPUESTA_S = 2.0
# Perfiles que no sirven para reproducir (manos libres Bluetooth: mono a 16 kHz).
EXCLUIR = ("hands-free", "manos libres", "bthhfenum")


def api_preferida():
    """Única API de host que se usa para listar y abrir dispositivos.

    En Windows, WASAPI (modo compartido): los nombres coinciden con los de Configuración de sonido
    y no se truncan (MME los corta en 31 caracteres); cada dispositivo aparece una sola vez; anda
    con la Scarlett y con el Bluetooth A2DP a la frecuencia del mezclador de Windows (el programa
    remuestrea si hace falta). WDM-KS es inestable con el Bluetooth y DirectSound es una capa
    vieja encima de WASAPI. ASIO no está en el PortAudio de sounddevice.
    """
    if sys.platform.startswith("win"):
        return "Windows WASAPI"
    if sys.platform == "darwin":
        return "Core Audio"
    return None


def reiniciar_portaudio():
    """Vuelve a leer la lista de dispositivos (PortAudio la guarda al iniciar)."""
    sd._terminate()
    sd._initialize()


def listar_salidas(todas=False):
    """Salidas de la API preferida, una por nombre (todas=True: de todas las APIs)."""
    apis = sd.query_hostapis()
    preferida = api_preferida()
    salidas, nombres = [], set()
    for indice, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] < 1:
            continue
        nombre, api = d["name"], apis[d["hostapi"]]["name"]
        if any(x in nombre.lower() for x in EXCLUIR):
            continue
        if not todas and preferida and api != preferida:
            continue
        if not todas and nombre in nombres:
            continue
        nombres.add(nombre)
        salidas.append({"indice": indice, "nombre": nombre, "api": api,
                        "canales": d["max_output_channels"], "fs": int(d["default_samplerate"])})
    if not salidas and not todas:
        return listar_salidas(True)
    return salidas


def buscar(salidas, nombre, api=None):
    """Dispositivo con ese nombre (y API, si se puede); None si no está conectado."""
    if not nombre:
        return None
    candidatos = [s for s in salidas if s["nombre"] == nombre]
    for s in candidatos:
        if s["api"] == api:
            return s
    return candidatos[0] if candidatos else None


def preseleccionar(salidas, claves):
    for s in salidas:
        if any(c in s["nombre"].lower() for c in claves):
            return s
    return None


def pasa_altos(x, fs, fc_hz):
    """Butterworth de 2.º orden aplicado ida y vuelta: fase cero, 24 dB/oct en total."""
    sos = butter(2, fc_hz, "highpass", fs=fs, output="sos")
    return sosfiltfilt(sos, x, axis=0).astype(np.float32)


def leer_audio(ruta, fs, circular=False, pasa_altos_hz=None):
    """Lee un archivo como float32 estéreo a la frecuencia fs (con pasa-altos opcional)."""
    x, fs_archivo = sf.read(ruta, dtype="float32", always_2d=True)
    if pasa_altos_hz:
        x = pasa_altos(x, fs_archivo, pasa_altos_hz)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    x = x[:, :2]
    if fs_archivo != fs:
        divisor = gcd(int(fs), int(fs_archivo))
        sube, baja = int(fs) // divisor, int(fs_archivo) // divisor
        if circular:
            # Relleno circular de un múltiplo de 'baja' muestras: el recorte cae en muestras enteras.
            relleno = baja * max(1, int(np.ceil(0.1 * fs_archivo / baja)))
            relleno = min(relleno, len(x) // baja * baja)
            extendido = np.concatenate([x[-relleno:], x, x[:relleno]])
            y = resample_poly(extendido, sube, baja, axis=0)
            inicio = relleno * sube // baja
            x = y[inicio:inicio + int(round(len(x) * sube / baja))]
        else:
            x = resample_poly(x, sube, baja, axis=0)
    return np.ascontiguousarray(x, dtype=np.float32)


def ruido_rosa(fs, duracion_s=1.0, dbfs=-20.0):
    n = int(fs * duracion_s)
    espectro = np.fft.rfft(np.random.default_rng().standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / fs)
    f[0] = f[1]
    x = np.fft.irfft(espectro / np.sqrt(f), n)
    x *= 10 ** (dbfs / 20) / np.sqrt(np.mean(x ** 2))
    fundido = int(0.01 * fs)
    x[:fundido] *= np.linspace(0, 1, fundido)
    x[-fundido:] *= np.linspace(1, 0, fundido)
    return np.column_stack([x, x]).astype(np.float32)


def db_a_lineal(db):
    return float(10 ** (db / 20))


class Fuente:
    def __init__(self, datos, ganancia, loop, clave, fundido):
        self.datos, self.loop, self.clave = datos, loop, clave
        self.pos = 0
        self.g = 0.0 if fundido else ganancia
        self.objetivo = ganancia
        self.terminando = False
        self.terminada = False

    def leer(self, n):
        largo = len(self.datos)
        if self.loop:
            indices = (self.pos + np.arange(n)) % largo
            self.pos = (self.pos + n) % largo
            return self.datos[indices]
        bloque = np.zeros((n, 2), np.float32)
        fin = min(self.pos + n, largo)
        bloque[:fin - self.pos] = self.datos[self.pos:fin]
        self.pos = fin
        self.terminada = fin >= largo
        return bloque


class Salida:
    """Un dispositivo de salida con su stream y su mezcla de fuentes."""

    def __init__(self, zona):
        self.zona = zona
        self.dispositivo = None
        self.stream = None
        self.fs = None
        self.fuentes = []
        self.lock = threading.Lock()
        self.cache = {}
        self.error = None
        self.ultimo_callback = 0.0
        self._cerrando = False

    def abrir(self, dispositivo):
        self.cerrar()
        if self.fs != dispositivo["fs"]:
            self.cache.clear()
        self.dispositivo, self.fs = dispositivo, dispositivo["fs"]
        self.canales = min(2, dispositivo["canales"])
        self.error = None
        self._cerrando = False
        self.stream = sd.OutputStream(
            device=dispositivo["indice"], samplerate=self.fs, channels=self.canales,
            dtype="float32", blocksize=BLOQUE, latency="high",
            callback=self._callback, finished_callback=self._terminado)
        self.ultimo_callback = time.monotonic()
        self.stream.start()

    def cerrar(self):
        self._cerrando = True
        if self.stream is not None:
            try:
                self.stream.abort()
                self.stream.close()
            except Exception:
                pass
        self.stream = None

    def _terminado(self):
        if not self._cerrando:
            self.error = "el dispositivo dejó de responder"

    def problema(self):
        """Texto del problema si la salida se cortó (p. ej., se desconectó); None si anda."""
        if self.stream is None:
            return None
        if self.error:
            return self.error
        if time.monotonic() - self.ultimo_callback > SIN_RESPUESTA_S:
            return "el dispositivo no responde"
        return None

    def _callback(self, salida, frames, _tiempo, _estado):
        self.ultimo_callback = time.monotonic()
        mezcla = np.zeros((frames, 2), np.float32)
        with self.lock:
            vivas = []
            for f in self.fuentes:
                bloque = f.leer(frames)
                if f.g == f.objetivo:
                    bloque *= f.g
                else:
                    bloque *= np.linspace(f.g, f.objetivo, frames, dtype=np.float32)[:, None]
                    f.g = f.objetivo
                mezcla += bloque
                if not (f.terminada or (f.terminando and f.g == 0.0)):
                    vivas.append(f)
            self.fuentes = vivas
        np.clip(mezcla, -1.0, 1.0, out=mezcla)
        if self.canales == 1:
            salida[:, 0] = mezcla.mean(axis=1)
        else:
            salida[:] = mezcla

    def cargar(self, ruta, circular=False, pasa_altos_hz=None):
        clave = (ruta, circular, pasa_altos_hz)
        if clave not in self.cache:
            self.cache[clave] = leer_audio(ruta, self.fs, circular, pasa_altos_hz)
        return self.cache[clave]

    def reproducir(self, ruta, ganancia_db=0.0, loop=False, clave=None, fundido=True, pasa_altos_hz=None):
        self.reproducir_datos(self.cargar(ruta, circular=loop, pasa_altos_hz=pasa_altos_hz),
                              ganancia_db, loop, clave, fundido)

    def reproducir_datos(self, datos, ganancia_db=0.0, loop=False, clave=None, fundido=True):
        fuente = Fuente(datos, db_a_lineal(ganancia_db), loop, clave, fundido)
        with self.lock:
            if clave is not None:
                self._detener(clave)
            self.fuentes.append(fuente)

    def ganancia(self, clave, ganancia_db):
        with self.lock:
            for f in self.fuentes:
                if f.clave == clave and not f.terminando:
                    f.objetivo = db_a_lineal(ganancia_db)

    def _detener(self, clave=None):
        for f in self.fuentes:
            if clave is None or f.clave == clave:
                f.objetivo, f.terminando = 0.0, True

    def detener(self, clave=None):
        with self.lock:
            self._detener(clave)

    def sonando(self, clave):
        with self.lock:
            return any(f.clave == clave and not f.terminando for f in self.fuentes)
