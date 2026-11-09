"""Control del ANC de los Soundcore Life Q30 (A3028) con la CLI de OpenSCQ30.

    ON  = ambientSoundMode NoiseCanceling
    OFF = ambientSoundMode Normal (no transparencia)

Comandos de la CLI 2.13 (verificados con su --help):
    openscq30 paired-devices list
    openscq30 device -a <MAC> setting --get ambientSoundMode --json
    openscq30 device -a <MAC> setting --set ambientSoundMode=<VALOR>

Un --get en la misma llamada que el --set devuelve el valor pedido, no necesariamente el del
auricular: set_anc verifica con una lectura aparte y, si no coincide, reintenta una vez.

La app gráfica de OpenSCQ30 tiene que estar cerrada: el auricular admite una sola conexión.
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

AJUSTE = "ambientSoundMode"
VALORES = {"ON": "NoiseCanceling", "OFF": "Normal"}
ESTADOS = {"NoiseCanceling": "ON", "Normal": "OFF", "Transparency": "TRANSPARENCIA"}
SUBMODO = "noiseCancelingMode"
TIMEOUT_S = 8.0


class ErrorANC(Exception):
    pass


def buscar_cli(base, configurada=None):
    """Ruta a la CLI: la de config.json, herramientas/bin/, la carpeta base, el PATH o Descargas."""
    candidatos = [configurada] if configurada else []
    for carpeta in (os.path.join(base, "herramientas", "bin"), base,
                    os.path.join(os.path.expanduser("~"), "Downloads")):
        candidatos += sorted(glob.glob(os.path.join(carpeta, "openscq30-cli*")))
    candidatos += [shutil.which("openscq30-cli"), shutil.which("openscq30")]
    for ruta in candidatos:
        if ruta and os.path.isfile(ruta):
            return ruta
    return None


def _explicar(error):
    texto = error.strip().splitlines()[-1] if error.strip() else "sin detalle"
    if "0x80072740" in texto or "socket" in texto.lower():
        return "la app gráfica de OpenSCQ30 está abierta (cerrala): " + texto
    if "not found" in texto.lower():
        return "los auriculares no están conectados por Bluetooth: " + texto
    return texto


class ControlANC:
    def __init__(self, cli, mac=None, timeout_s=TIMEOUT_S, registrar=None):
        self.cli, self.mac, self.timeout_s = cli, mac, timeout_s
        self.registrar = registrar or (lambda fila: None)

    def _correr(self, *argumentos):
        if not self.cli:
            raise ErrorANC("no se encontró la CLI de OpenSCQ30")
        opciones = {}
        if sys.platform.startswith("win"):
            opciones["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            r = subprocess.run([self.cli] + list(argumentos), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=self.timeout_s, **opciones)
        except subprocess.TimeoutExpired:
            raise ErrorANC("la CLI no respondió en {:g} s".format(self.timeout_s))
        except OSError as error:
            raise ErrorANC("no se pudo ejecutar la CLI: {}".format(error))
        if r.returncode != 0:
            raise ErrorANC(_explicar(r.stderr or r.stdout))
        return r.stdout

    def buscar_mac(self):
        """Primer Soundcore A3028 de 'paired-devices list' (o el primero que haya)."""
        filas = [l.split() for l in self._correr("paired-devices", "list").splitlines()[1:] if l.strip()]
        if not filas:
            raise ErrorANC("no hay auriculares vinculados en OpenSCQ30 (openscq30 paired-devices add)")
        for fila in filas:
            if "A3028" in fila[0]:
                return fila[1]
        return filas[0][1]

    def _mac(self):
        if not self.mac:
            self.mac = self.buscar_mac()
        return self.mac

    def leer(self, ajuste):
        salida = self._correr("device", "-a", self._mac(), "setting", "--get", ajuste, "--json")
        try:
            return json.loads(salida)[0]["value"]["value"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise ErrorANC("respuesta inesperada de la CLI: {!r}".format(salida[:200]))

    def get_anc(self):
        """'ON', 'OFF' o 'TRANSPARENCIA'."""
        valor = self.leer(AJUSTE)
        return ESTADOS.get(valor, valor)

    def set_anc(self, estado):
        """Cambia el ANC, verifica leyendo el estado y reintenta una vez. Devuelve el registro."""
        if estado not in VALORES:
            raise ValueError("estado tiene que ser 'ON' u 'OFF'")
        inicio = time.monotonic()
        fila = {"hora": datetime.now().isoformat(timespec="milliseconds"), "pedido": estado,
                "leido": "", "latencia_s": "", "intentos": 0, "ok": False, "error": ""}
        for intento in (1, 2):
            fila["intentos"] = intento
            try:
                self._correr("device", "-a", self._mac(), "setting", "--set", "{}={}".format(AJUSTE, VALORES[estado]))
                fila["leido"] = self.get_anc()
                fila["error"] = ""
            except ErrorANC as error:
                fila["error"] = str(error)
                continue
            if fila["leido"] == estado:
                fila["ok"] = True
                break
            fila["error"] = "se leyó {} después de pedir {}".format(fila["leido"], estado)
        fila["latencia_s"] = round(time.monotonic() - inicio, 3)
        self.registrar(fila)
        return fila

    def fijar_submodo(self, submodo="Transport"):
        """Submodo de la cancelación (Transport, Indoor u Outdoor), verificado."""
        self._correr("device", "-a", self._mac(), "setting", "--set", "{}={}".format(SUBMODO, submodo))
        leido = self.leer(SUBMODO)
        if leido != submodo:
            raise ErrorANC("submodo: se leyó {} después de pedir {}".format(leido, submodo))
        return leido


_control = None


def configurar(cli, mac=None, timeout_s=TIMEOUT_S, registrar=None):
    global _control
    _control = ControlANC(cli, mac, timeout_s, registrar)
    return _control


def set_anc(estado):
    if _control is None:
        raise ErrorANC("ANC sin configurar (llamar antes a configurar())")
    return _control.set_anc(estado)


def get_anc():
    if _control is None:
        raise ErrorANC("ANC sin configurar (llamar antes a configurar())")
    return _control.get_anc()
