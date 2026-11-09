"""Volumen maestro de Windows de un dispositivo de salida (con pycaw) y control del perfil Bluetooth.

Solo lectura: el programa no cambia el volumen de Windows. En otros sistemas, o si pycaw no está,
leer_volumen devuelve None.
"""

import sys

# Perfil manos libres del Bluetooth (HFP): mono a 16 kHz, pensado para llamadas.
MARCAS_MANOS_LIBRES = ("hands-free", "handsfree", "manos libres", "bthhfenum")


def es_manos_libres(dispositivo):
    """True si el dispositivo parece el perfil manos libres y no el estéreo (A2DP)."""
    nombre = dispositivo["nombre"].lower()
    return (any(m in nombre for m in MARCAS_MANOS_LIBRES)
            or dispositivo["canales"] < 2 or dispositivo["fs"] <= 16000)


def leer_volumen(nombre):
    """{'porcentaje': 0-100, 'silenciado': bool} del dispositivo de salida 'nombre', o None."""
    if not sys.platform.startswith("win"):
        return None
    try:
        from pycaw.constants import AudioDeviceState
        from pycaw.pycaw import AudioUtilities
        for d in AudioUtilities.GetAllDevices():
            # Los id de salida empiezan con {0.0.0.…}; los de entrada (micrófonos), con {0.0.1.…}.
            if d.FriendlyName == nombre and d.state == AudioDeviceState.Active and str(d.id).startswith("{0.0.0."):
                volumen = d.EndpointVolume
                return {"porcentaje": round(volumen.GetMasterVolumeLevelScalar() * 100),
                        "silenciado": bool(volumen.GetMute())}
    except Exception:
        return None
    return None


def describir(volumen):
    if volumen is None:
        return "no se pudo leer"
    return "{} %{}".format(volumen["porcentaje"], " (silenciado)" if volumen["silenciado"] else "")
