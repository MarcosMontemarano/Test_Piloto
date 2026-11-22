"""Configuración, archivos de audio, contrabalanceos y registro de datos de una sesión."""

import csv
import glob
import json
import os
import re
import sys
from datetime import datetime
from itertools import permutations


def carpeta_base():
    """Carpeta donde se buscan audio/, config.json y datos/.

    Desde el código es la carpeta de test.py. En el ejecutable es la carpeta del .exe; en
    macOS, la carpeta que contiene TestPiloto.app (no el interior del bundle).
    """
    if getattr(sys, "frozen", False):
        carpeta = os.path.dirname(os.path.abspath(sys.executable))
        partes = carpeta.split(os.sep)
        for i in range(len(partes) - 1, -1, -1):
            if partes[i].endswith(".app"):
                return os.sep.join(partes[:i]) or os.sep
        return carpeta
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- configuración

CONFIG_DEFECTO = {
    "salida_ruido": {"nombre": None, "api": None},
    "salida_auriculares": {"nombre": None, "api": None},
    "ganancia_mssn_db": 0.0,
    "ganancia_voz_db": 0.0,
    "ganancia_trafico_db": 0.0,
    "ganancia_avion_db": 0.0,
    # Nivel fijo de la música en los anclajes. -15 dB es el paso 10 de 20 del slider.
    "nivel_anclaje_db": -15.0,
    "participante": 1,
    # Control del ANC con OpenSCQ30 (vacío: se busca la CLI y la MAC solos).
    "openscq30_cli": "",
    "anc_mac": "",
    "anc_submodo": "Transport",
}


def cargar_config(ruta):
    config = json.loads(json.dumps(CONFIG_DEFECTO))
    try:
        with open(ruta, encoding="utf-8") as f:
            guardada = json.load(f)
        config.update({k: v for k, v in guardada.items() if k in config})
    except (OSError, ValueError):
        pass
    return config


def guardar_config(ruta, config):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- textos del participante

ARCHIVO_TEXTOS = "textos_participante.json"
# clave -> cantidad de elementos si es una lista (None si es un texto)
CLAVES_TEXTOS = {
    "nombre_test": None, "marca": None, "duracion_encabezado": None, "pantalla": None, "etapas": 8,
    "bienvenida_subtitulo": None, "duracion": None, "comenzar": None, "continuar": None,
    "instrucciones_titulo": None, "instrucciones": None, "demo_titulo": None, "demo_texto": None,
    "demo_boton": None, "demo_en_curso": None, "demo_fin": None, "demo_fin_explicacion": None,
    "preparando": None, "tarea_a_titulo": None, "tarea_a_instrucciones": None, "transicion_titulo": None,
    "transicion_practica": None, "practica": None, "oracion": None, "escucha_oracion": None,
    "tarea_a_fin": None, "bloque_titulo": None, "bloque_texto": None, "anclaje_titulo": None,
    "anclaje_texto": None, "anclaje_texto_repeticion": None, "anclaje_musica": None, "escenario_titulo": None, "nivel_escucha": None,
    "menor_volumen": None, "mayor_volumen": None, "ok": None, "esfuerzo": None, "opciones_esfuerzo": 7,
    "cierre_titulo": None, "fatiga": None, "opciones_fatiga": 3, "comodidad": None,
    "opciones_comodidad": 3, "cierre_texto": None, "finalizar": None,
}
VALORES_PRUEBA = {"minutos": 25, "segundos": 21, "numero": 1, "total": 6, "actual": 1}


def cargar_textos(base):
    """Lee textos_participante.json. Devuelve (textos, None) o (None, descripción del problema)."""
    ruta = os.path.join(base, ARCHIVO_TEXTOS)
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            textos = json.load(f)
    except OSError:
        return None, "No se encontró {} junto al programa ({}).".format(ARCHIVO_TEXTOS, base)
    except ValueError as error:
        return None, "{} tiene un error de formato: {}".format(ARCHIVO_TEXTOS, error)
    problemas = []
    for clave, cantidad in CLAVES_TEXTOS.items():
        valor = textos.get(clave)
        if cantidad is None:
            if not isinstance(valor, str):
                problemas.append("falta el texto \"{}\"".format(clave))
                continue
            try:
                valor.format(**VALORES_PRUEBA)
            except (KeyError, IndexError, ValueError) as error:
                problemas.append("\"{}\": lo que va entre llaves no es válido ({})".format(clave, error))
        elif not (isinstance(valor, list) and len(valor) == cantidad and all(isinstance(v, str) for v in valor)):
            problemas.append("\"{}\" tiene que ser una lista de {} textos".format(clave, cantidad))
    if problemas:
        return None, "{}: {}.".format(ARCHIVO_TEXTOS, "; ".join(problemas))
    return textos, None


# ---------------------------------------------------------------- archivos de audio

LISTAS_TAREA_A = (1, 2)
LISTA_PRACTICA = 3
ORACIONES_POR_LISTA = 6


def ruta_oracion(base, lista, oracion):
    return os.path.join(base, "audio", "quicksin", "voz", "LISTA_{}_oracion_{}.wav".format(lista, oracion))


def buscar_archivos(base):
    """Devuelve (rutas, faltantes). La música se lee de audio/musica/*_eq.wav (tienen que ser 3)."""
    rutas = {
        "mssn": os.path.join(base, "audio", "mssn", "mssn_quicksin.wav"),
        "trafico": os.path.join(base, "audio", "clips", "ruido_autopista.ogg"),
        "avion": os.path.join(base, "audio", "clips", "ruido_avion.ogg"),
    }
    faltantes = [r for r in rutas.values() if not os.path.isfile(r)]
    for lista in LISTAS_TAREA_A + (LISTA_PRACTICA,):
        for oracion in range(1, ORACIONES_POR_LISTA + 1):
            ruta = ruta_oracion(base, lista, oracion)
            if not os.path.isfile(ruta):
                faltantes.append(ruta)
    musica = sorted(glob.glob(os.path.join(base, "audio", "musica", "*_eq.wav")))
    if len(musica) != 3:
        faltantes.append(os.path.join(base, "audio", "musica", "*_eq.wav (hay {}, tienen que ser 3)".format(
            len(musica))))
    rutas["musica"] = musica
    return rutas, [os.path.relpath(r, base) for r in faltantes]


def nombre_fragmento(ruta):
    """musica_jazz_eq.wav -> jazz"""
    nombre = os.path.splitext(os.path.basename(ruta))[0]
    nombre = re.sub(r"_eq$", "", nombre)
    return re.sub(r"^musica_", "", nombre)


def cargar_oraciones(base):
    """{nombre del WAV: (texto, [palabras clave], estado)} desde audio/quicksin/oraciones.csv.

    Se indexa por la columna "archivo" (el WAV que suena), así el texto siempre corresponde a lo
    que se reproduce. Las palabras clave van separadas por "|". Filas sin texto se ignoran.
    """
    ruta = os.path.join(base, "audio", "quicksin", "oraciones.csv")
    oraciones = {}
    try:
        with open(ruta, newline="", encoding="utf-8-sig") as f:
            for fila in csv.DictReader(f):
                texto = (fila.get("texto") or "").strip()
                archivo = (fila.get("archivo") or "").strip()
                if not texto or not archivo:
                    continue
                claves = [c.strip() for c in (fila.get("palabras_clave") or "").split("|") if c.strip()]
                oraciones[archivo] = (texto, claves, (fila.get("estado") or "").strip())
    except OSError:
        pass
    return oraciones


# ---------------------------------------------------------------- contrabalanceos

BLOQUES = ("silencio", "trafico", "avion")
NOMBRE_BLOQUE = {"silencio": "Silencio", "trafico": "Tráfico", "avion": "Cabina de avión"}
ORDENES_BLOQUES = list(permutations(BLOQUES))


def otro(estado):
    return "ON" if estado == "OFF" else "OFF"


def contrabalanceo(participante, fragmentos):
    """Asignaciones de la sesión a partir del número de participante (k = participante - 1).

    - Orden de los bloques: k mod 6 (las 6 permutaciones).
    - Música: cuadrado latino de 3, rotación (k + k div 6) mod 3. Dentro de cada grupo de 6
      participantes cada fragmento cae 2 veces en cada bloque, y cada orden de bloques pasa por
      las 3 rotaciones cada 18 participantes (no queda atado al orden).
    - Tarea A, lista -> estado del ANC: lista 1 con OFF si (k + k div 6) es par.
    - Tarea A, estado que va primero: OFF si (k div 2 + k div 12) es par.
    - Bloques, estado del ANC del primer escenario: en el primer bloque es OFF si
      (k div 3 + k div 12) es par, y alterna en los bloques siguientes.
    """
    k = participante - 1
    orden = ORDENES_BLOQUES[k % 6]
    rotacion = (k + k // 6) % 3
    musica = {b: fragmentos[(i + rotacion) % 3] for i, b in enumerate(BLOQUES)}
    lista_off = 1 if (k + k // 6) % 2 == 0 else 2
    primero_a = "OFF" if (k // 2 + k // 12) % 2 == 0 else "ON"
    primero_bloque = "OFF" if (k // 3 + k // 12) % 2 == 0 else "ON"
    anc_bloques = {}
    for j, bloque in enumerate(orden):
        primero = primero_bloque if j % 2 == 0 else otro(primero_bloque)
        anc_bloques[bloque] = (primero, otro(primero))
    return {
        "orden_bloques": orden,
        "musica": musica,
        "listas": {"OFF": lista_off, "ON": 3 - lista_off},
        "anc_tarea_a": (primero_a, otro(primero_a)),
        "anc_bloques": anc_bloques,
    }


# ---------------------------------------------------------------- calibración opcional

def cargar_calibracion(base):
    """calibracion_niveles.csv (columnas paso, laeq_dba y, opcional, fragmento).

    Devuelve una función (paso, fragmento) -> L_Aeq o None. Si el archivo no está, siempre None.
    """
    ruta = os.path.join(base, "calibracion_niveles.csv")
    tabla = {}
    try:
        with open(ruta, newline="", encoding="utf-8-sig") as f:
            for fila in csv.DictReader(f):
                tabla[(int(fila["paso"]), (fila.get("fragmento") or "").strip())] = float(fila["laeq_dba"])
    except (OSError, KeyError, ValueError):
        tabla = {}

    def nivel(paso, fragmento):
        return tabla.get((paso, fragmento), tabla.get((paso, "")))
    return nivel


# ---------------------------------------------------------------- registro

COLUMNAS = [
    "momento", "tipo", "tarea", "bloque", "posicion_bloque", "musica", "anc", "anc_cambio",
    "lista", "oracion", "practica", "palabras_correctas", "reproducciones", "paso_inicial", "paso_final",
    "ganancia_db", "nivel_dba", "ccr", "ccr_texto", "campo", "valor", "prueba",
]


class Registro:
    """CSV por participante en datos/. Se escribe y se vacía fila por fila."""

    def __init__(self, base, participante, prueba=False):
        carpeta = os.path.join(base, "datos")
        os.makedirs(carpeta, exist_ok=True)
        self.inicio = datetime.now()
        # prueba: todo lo que se registra va con prueba = "si" (y el archivo lleva _PRUEBA).
        self.prueba = prueba
        self.ruta = os.path.join(carpeta, "participante_{:03d}_{}{}.csv".format(
            participante, self.inicio.strftime("%Y%m%d-%H%M%S"), "_PRUEBA" if prueba else ""))
        self.archivo = open(self.ruta, "w", newline="", encoding="utf-8-sig")
        self.escritor = csv.DictWriter(self.archivo, fieldnames=COLUMNAS)
        self.escritor.writeheader()

    def fila(self, tipo, **campos):
        campos = {k: v for k, v in campos.items() if v is not None}
        campos.update(momento=datetime.now().isoformat(timespec="milliseconds"), tipo=tipo,
                      prueba="si" if self.prueba else "no")
        self.escritor.writerow(campos)
        self.archivo.flush()

    def sesion(self, campo, valor):
        self.fila("sesion", campo=campo, valor=valor)

    def cerrar(self):
        if not self.archivo.closed:
            self.archivo.close()
