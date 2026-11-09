import ctypes
import os
import random
import re
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from piloto import audio
from piloto import sesion as ses


# Configuración editable
NOMBRE_TEST = (
    "Impacto de auriculares ANC en la percepción musical y comprensión de letras "
    "en español rioplatense"
)
TITULO_VENTANA = "Piloto psicoacústico"
DURACION_MINUTOS = 25

# Slider de nivel preferido: PASOS_SLIDER pasos de PASO_DB dB (el último paso = 0 dB).
PASOS_SLIDER = 20
PASO_DB = 1.5

# Demostración del ANC: ruido de tráfico DEMO_ANC_S segundos; el ANC cambia cada DEMO_INTERVALO_S.
DEMO_ANC_S = 20
DEMO_INTERVALO_S = 5
DEMO_SECUENCIA = ("OFF", "ON", "OFF", "ON")

# "manual": cambiar_anc() le pide el cambio al experimentador. Más adelante, "openscq30".
MODO_ANC = "manual"

CLAVES_MONITORES = ("scarlett", "focusrite")
CLAVES_AURICULARES = ("soundcore", "q30")
ZONAS = {
    "ruido": ("Salida ruido ambiente (monitores)", "salida_ruido", CLAVES_MONITORES),
    "auriculares": ("Salida auriculares (voz y música)", "salida_auriculares", CLAVES_AURICULARES),
}
GANANCIAS = (
    ("ganancia_mssn_db", "Ganancia del MSSN (Tarea A)"),
    ("ganancia_voz_db", "Ganancia de la voz (Tarea A)"),
    ("ganancia_trafico_db", "Ganancia del ruido de tráfico"),
    ("ganancia_avion_db", "Ganancia del ruido de cabina de avión"),
    ("nivel_anclaje_db", "Nivel fijo del anclaje (música)"),
)
GANANCIA_AMBIENTE = {"trafico": "ganancia_trafico_db", "avion": "ganancia_avion_db"}

SECCIONES = ("bienvenida", "instrucciones", "demo_anc", "tarea_A", "bloque_1", "bloque_2",
             "bloque_3", "cierre")
ETIQUETAS_STEPPER = ("Bienvenida", "Instrucciones", "Demostración", "Tarea A", "Parte 1",
                     "Parte 2", "Parte 3", "Cierre")

TEXTOS = {
    "marca": "PILOTO PSICOACÚSTICO",
    "bienvenida_subtitulo": "Test psicoacústico · sesión piloto",
    "duracion": "Duración aproximada: {minutos} minutos",
    "comenzar": "Comenzar",
    "continuar": "Continuar",
    "instrucciones_titulo": "Instrucciones",
    "instrucciones": (
        "El test tiene tres partes:\n\n"
        "1. Una demostración breve de la cancelación de ruido de los auriculares.\n"
        "2. Oraciones: vas a escuchar oraciones con ruido de fondo y tenés que repetir en voz alta "
        "lo que entiendas.\n"
        "3. Música: en distintos ambientes vas a elegir el volumen al que te gusta escuchar un "
        "fragmento musical y a contar cuánto esfuerzo te costó escucharlo.\n\n"
        "Durante todo el test usá los auriculares. Si algo no queda claro, preguntá."
    ),
    "demo_titulo": "Demostración de la cancelación de ruido",
    "demo_texto": (
        "Va a sonar ruido de tráfico por los parlantes durante unos {segundos} segundos. "
        "Mientras tanto, la cancelación de ruido de los auriculares se va a activar y desactivar "
        "varias veces: prestá atención a cómo cambia lo que escuchás."
    ),
    "demo_boton": "Comenzar demostración",
    "demo_en_curso": "Demostración en curso… {segundos} s",
    "demo_fin": "Fin de la demostración.",
    "tarea_a_titulo": "Tarea A · Oraciones",
    "tarea_a_instrucciones": (
        "Vas a escuchar oraciones con un ruido de fondo. Después de cada una, repetí en voz alta "
        "lo que hayas entendido, aunque sea una parte. Empezamos con unas oraciones de práctica."
    ),
    "ruido_fondo": "Reproducir ruido de fondo",
    "ruido_persistente": "(el ruido de fondo queda sonando durante toda la tarea)",
    "reproducido": "Ruido de fondo sonando",
    "practica": "Práctica",
    "oracion": "Oración {numero} de {total}",
    "reproducir_oracion": "Reproducir oración",
    "panel_experimentador": "Panel del experimentador (no para el oyente)",
    "puntaje_ayuda": "Palabras clave correctas (0,5 = error menor de número o género)",
    "tarea_a_fin": "Terminaste la tarea de oraciones. ¡Muy bien!",
    "transicion_titulo": "Pausa breve",
    "transicion_texto": "Esperá un momento: enseguida seguimos.",
    "transicion_practica": "Primero, unas oraciones de práctica.",
    "bloque_titulo": "Parte {numero} de 3",
    "bloque_texto": (
        "En esta parte vas a escuchar un fragmento musical, primero como referencia y después "
        "para elegir el volumen. Se repite dos veces."
    ),
    "anclaje_titulo": "Escuchá la referencia",
    "anclaje_texto": (
        "Esta música es la referencia. Escuchala con atención: en la pantalla siguiente vas a "
        "escuchar la misma música y vas a comparar cuánto esfuerzo te cuesta escucharla con "
        "respecto a lo que estás escuchando ahora."
    ),
    "escenario_titulo": "Elegí el volumen",
    "nivel_escucha": (
        "Mové el control hasta el volumen al que te gustaría escuchar esta música. "
        "Cuando estés conforme, tocá OK."
    ),
    "menor_volumen": "Menor volumen",
    "mayor_volumen": "Mayor volumen",
    "ok": "OK",
    "esfuerzo": "Comparado con la referencia, escuchar la música ahora te costó…",
    "cierre_titulo": "¡Muchas gracias por participar!",
    "fatiga": "¿Sentiste fatiga auditiva durante el test?",
    "comodidad": "¿Los auriculares te resultaron incómodos de colocar?",
    "cierre_texto": "La sesión piloto ha finalizado. ¡Muchas gracias!",
    "finalizar": "Finalizar",
    "pantalla": "PANTALLA {actual:02d} / {total:02d}",
    "anc_aviso": "Experimentador: cambiar ANC a {estado}",
    "anc_hecho": "Hecho",
}

OPCIONES_CCR = (
    ("Mucho más esfuerzo", -3),
    ("Bastante más esfuerzo", -2),
    ("Un poco más esfuerzo", -1),
    ("Igual esfuerzo", 0),
    ("Un poco más fácil", 1),
    ("Bastante más fácil", 2),
    ("Mucho más fácil", 3),
)
OPCIONES_FATIGA = ("Mucho", "Intermedio", "Poco")
OPCIONES_COMODIDAD = ("Sí", "No", "Intermedio")
PUNTAJES = [i / 2 for i in range(11)]
FUENTES_PREFERIDAS = ("Calibri", "Segoe UI", "Arial", "Helvetica", "DejaVu Sans")

FONDO = "#f3f6f5"
SUPERFICIE = "#ffffff"
TEXTO = "#20302e"
MUTED = "#62716e"
ACENTO = "#087e78"
ACENTO_OSCURO = "#06645f"
ACENTO_CLARO = "#dcefeb"
BORDES = "#dce5e2"
GRIS = "#e5e8e7"
PANEL = "#edf3f1"
ALERTA = "#b3261e"
ALERTA_FONDO = "#fde8e6"


def enable_windows_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def paso_a_db(paso):
    return (paso - PASOS_SLIDER) * PASO_DB


def formato_puntaje(valor):
    return "{:g}".format(valor).replace(".", ",")


class PsychoacousticPilot(tk.Tk):
    def __init__(self):
        super().__init__()
        self._set_display_geometry()
        self.font_family = self._select_font_family()
        self.fullscreen = False
        self.bind_all("<F11>", self._toggle_fullscreen)
        self.bind_all("<Escape>", self._leave_fullscreen)
        self.title(TITULO_VENTANA)
        self.configure(bg=FONDO)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.base = ses.carpeta_base()
        self.ruta_config = os.path.join(self.base, "config.json")
        self.cfg = ses.cargar_config(self.ruta_config)
        self.salidas = {zona: audio.Salida(zona) for zona in ZONAS}
        self.dispositivos = []
        self.registro = None
        self.pasos = []
        self.indice = 0
        self.paso_dibujado = None
        self.seccion_actual = None
        self.anc_actual = None
        self.anc_pendiente = None
        self.ambiente_actual = None
        self.mssn_iniciado = False
        self.demo = {"estado": "espera"}
        self.reproducciones = 0
        self.escenario = {}
        self.fatiga = tk.StringVar(value="")
        self.comodidad = tk.StringVar(value="")
        self.sesion_terminada = False

        self._configure_styles()
        self._build_shell()
        self.pantalla_config()
        self.after(500, self._vigilar_audio)

    # ------------------------------------------------------------ ventana y estilos

    def _set_display_geometry(self):
        ancho, alto = self.winfo_screenwidth(), self.winfo_screenheight()
        self.scale_factor = min(1.6, max(0.8, min(ancho / 1280, alto / 720)))
        w = min(ancho, max(1000, int(ancho * 0.9)))
        h = min(alto, max(650, int(alto * 0.9)))
        self.geometry("{}x{}+{}+{}".format(w, h, max(0, (ancho - w) // 2), max(0, (alto - h) // 2)))
        self.minsize(min(1000, ancho), min(650, alto))

    def _select_font_family(self):
        instaladas = {f.casefold(): f for f in tkfont.families(self)}
        for preferida in FUENTES_PREFERIDAS:
            if preferida.casefold() in instaladas:
                return instaladas[preferida.casefold()]
        return tkfont.nametofont("TkDefaultFont").actual("family")

    def _font(self, size, weight="normal"):
        return self.font_family, max(8, int(round(size * self.scale_factor))), weight

    def _scaled_pair(self, h, v):
        return max(6, int(h * self.scale_factor)), max(5, int(v * self.scale_factor))

    def _toggle_fullscreen(self, _event):
        self.fullscreen = not self.fullscreen
        self.attributes("-fullscreen", self.fullscreen)
        return "break"

    def _leave_fullscreen(self, _event):
        if self.fullscreen:
            self.fullscreen = False
            self.attributes("-fullscreen", False)
        return "break"

    def _configure_styles(self):
        style = ttk.Style(self)
        style.configure("TButton", font=self._font(12), padding=self._scaled_pair(14, 9))
        style.configure("Small.TButton", font=self._font(9), padding=self._scaled_pair(8, 3))
        style.configure("Primary.TButton", font=self._font(13, "bold"), padding=self._scaled_pair(22, 12))
        style.configure("Audio.TButton", font=self._font(16, "bold"), padding=self._scaled_pair(22, 15))
        style.configure("Played.TButton", font=self._font(16, "bold"), padding=self._scaled_pair(22, 15),
                        foreground=ACENTO_OSCURO)

    def _build_shell(self):
        pad = max(16, int(34 * self.scale_factor))
        self.banner = tk.Frame(self, bg=ALERTA_FONDO, highlightbackground=ALERTA, highlightthickness=1)
        self.banner_texto = tk.Label(self.banner, bg=ALERTA_FONDO, fg=ALERTA, font=self._font(11, "bold"),
                                     justify="left", wraplength=int(900 * self.scale_factor))
        self.banner_texto.pack(side="left", padx=12, pady=8)
        ttk.Button(self.banner, text="Reintentar", command=self._reintentar_audio).pack(side="right", padx=12)

        self.header = tk.Frame(self, bg=FONDO)
        self.header.pack(fill="x", padx=pad, pady=(max(12, int(20 * self.scale_factor)), 6))
        linea = tk.Frame(self.header, bg=FONDO)
        linea.pack(fill="x")
        tk.Label(linea, text=TEXTOS["marca"], bg=FONDO, fg=ACENTO_OSCURO,
                 font=self._font(10, "bold")).pack(side="left")
        tk.Label(linea, text="{} minutos".format(DURACION_MINUTOS), bg=FONDO, fg=MUTED,
                 font=self._font(11)).pack(side="right")
        self.progress_text = tk.Label(self.header, bg=FONDO, fg=TEXTO, font=self._font(11, "bold"), anchor="w")
        self.progress_text.pack(fill="x", pady=(10, 6))
        self.stepper = tk.Frame(self.header, bg=FONDO)
        self.stepper.pack(fill="x")

        self.content = tk.Frame(self, bg=FONDO)
        self.content.pack(fill="both", expand=True, padx=pad, pady=(10, 6))
        self.footer = tk.Frame(self, bg=FONDO)
        self.footer.pack(fill="x", padx=pad, pady=(3, max(10, int(18 * self.scale_factor))))

    def _limpiar(self):
        for frame in (self.content, self.footer):
            for child in frame.winfo_children():
                child.destroy()

    def _card(self):
        card = tk.Frame(self.content, bg=SUPERFICIE, highlightbackground=BORDES, highlightthickness=1)
        card.pack(fill="both", expand=True)
        body = tk.Frame(card, bg=SUPERFICIE)
        body.pack(expand=True, fill="both", padx=max(12, int(30 * self.scale_factor)),
                  pady=max(10, int(18 * self.scale_factor)))
        return body

    def _heading(self, parent, text, size=25):
        tk.Label(parent, text=text, bg=SUPERFICIE, fg=TEXTO, font=self._font(size, "bold"),
                 wraplength=int(900 * self.scale_factor), justify="center").pack(
                     pady=(0, max(6, int(10 * self.scale_factor))))

    def _paragraph(self, parent, text, size=16, justify="center"):
        tk.Label(parent, text=text, bg=SUPERFICIE, fg=MUTED, font=self._font(size),
                 wraplength=int(860 * self.scale_factor), justify=justify).pack(
                     pady=max(3, int(5 * self.scale_factor)))

    # ------------------------------------------------------------ configuración (experimentador)

    def pantalla_config(self):
        self._limpiar()
        self.progress_text.configure(text="CONFIGURACIÓN DE LA SESIÓN · solo para el experimentador")
        for child in self.stepper.winfo_children():
            child.destroy()
        body = self._card()
        self._heading(body, "Configuración de la sesión", 22)

        grilla = tk.Frame(body, bg=SUPERFICIE)
        grilla.pack(fill="x", pady=(4, 2))
        self.combos, self.estado_zona, self.mapa_dispositivos = {}, {}, {}
        for fila, (zona, (titulo, _clave, _claves)) in enumerate(ZONAS.items()):
            tk.Label(grilla, text=titulo, bg=SUPERFICIE, fg=TEXTO, font=self._font(12, "bold"),
                     anchor="w").grid(row=fila * 2, column=0, sticky="w", padx=(0, 10), pady=(6, 0))
            combo = ttk.Combobox(grilla, state="readonly", width=60, font=self._font(11))
            combo.grid(row=fila * 2, column=1, sticky="we", pady=(6, 0))
            combo.bind("<<ComboboxSelected>>", lambda _e, z=zona: self._elegir_dispositivo(z))
            ttk.Button(grilla, text="Probar", command=lambda z=zona: self._probar(z)).grid(
                row=fila * 2, column=2, padx=(10, 0), pady=(6, 0))
            estado = tk.Label(grilla, bg=SUPERFICIE, fg=MUTED, font=self._font(9), anchor="w")
            estado.grid(row=fila * 2 + 1, column=1, sticky="w")
            self.combos[zona], self.estado_zona[zona] = combo, estado
        grilla.columnconfigure(1, weight=1)

        opciones = tk.Frame(body, bg=SUPERFICIE)
        opciones.pack(fill="x", pady=(2, 2))
        self.todas_apis = tk.BooleanVar(value=bool(self.cfg["mostrar_todas_las_apis"]))
        ttk.Checkbutton(opciones, text="Mostrar todas las APIs de audio", variable=self.todas_apis,
                        command=lambda: self._refrescar_dispositivos(False)).pack(side="left")
        ttk.Button(opciones, text="Actualizar dispositivos", style="Small.TButton",
                   command=lambda: self._refrescar_dispositivos(True)).pack(side="left", padx=12)
        self.aviso_dispositivos = tk.Label(body, bg=SUPERFICIE, fg=ALERTA, font=self._font(11, "bold"))
        self.aviso_dispositivos.pack(pady=(0, 4))

        ganancias = tk.Frame(body, bg=SUPERFICIE)
        ganancias.pack(pady=(4, 4))
        self.vars_ganancia = {}
        for i, (clave, titulo) in enumerate(GANANCIAS):
            tk.Label(ganancias, text=titulo + " (dB)", bg=SUPERFICIE, fg=TEXTO, font=self._font(11),
                     anchor="e").grid(row=i // 2, column=(i % 2) * 2, sticky="e", padx=(16, 6), pady=3)
            var = tk.StringVar(value="{:g}".format(float(self.cfg[clave])))
            ttk.Entry(ganancias, textvariable=var, width=8, font=self._font(11)).grid(
                row=i // 2, column=(i % 2) * 2 + 1, sticky="w", pady=3)
            self.vars_ganancia[clave] = var
        fila_p = (len(GANANCIAS) + 1) // 2
        tk.Label(ganancias, text="Número de participante", bg=SUPERFICIE, fg=TEXTO,
                 font=self._font(11, "bold"), anchor="e").grid(row=fila_p, column=0, sticky="e",
                                                               padx=(16, 6), pady=(10, 3))
        self.var_participante = tk.StringVar(value=str(self.cfg["participante"]))
        ttk.Entry(ganancias, textvariable=self.var_participante, width=8, font=self._font(11)).grid(
            row=fila_p, column=1, sticky="w", pady=(10, 3))

        self.rutas, faltantes = ses.buscar_archivos(self.base)
        texto_audio = ("Audio: todos los archivos encontrados en {}".format(os.path.join(self.base, "audio"))
                       if not faltantes else "Faltan archivos de audio:\n" + "\n".join(faltantes[:12]) +
                       ("\n… y {} más".format(len(faltantes) - 12) if len(faltantes) > 12 else ""))
        tk.Label(body, text=texto_audio, bg=SUPERFICIE, fg=ALERTA if faltantes else MUTED,
                 font=self._font(9), justify="left").pack(pady=(4, 0))
        self.faltantes = faltantes
        self.error_config = tk.Label(body, bg=SUPERFICIE, fg=ALERTA, font=self._font(11, "bold"))
        self.error_config.pack(pady=(4, 0))

        ttk.Button(self.footer, text="Iniciar sesión", style="Primary.TButton",
                   command=self._iniciar_sesion).pack(side="right")
        self._refrescar_dispositivos(False)

    def _etiqueta(self, d):
        return "{}   [{}]".format(d["nombre"], d["api"]) if self.todas_apis.get() else d["nombre"]

    def _refrescar_dispositivos(self, reiniciar):
        elegidos = {z: s.dispositivo for z, s in self.salidas.items()}
        if reiniciar:
            for s in self.salidas.values():
                s.cerrar()
            audio.reiniciar_portaudio()
        self.dispositivos = audio.listar_salidas(self.todas_apis.get())
        self.mapa_dispositivos = {self._etiqueta(d): d for d in self.dispositivos}
        for zona, (_titulo, clave, claves) in ZONAS.items():
            combo = self.combos[zona]
            combo.configure(values=list(self.mapa_dispositivos))
            previo = elegidos[zona] or self.cfg[clave]
            d = (audio.buscar(self.dispositivos, previo.get("nombre"), previo.get("api"))
                 or audio.preseleccionar(self.dispositivos, claves))
            if d is None:
                combo.set("")
                self.salidas[zona].cerrar()
                self.estado_zona[zona].configure(text="Sin dispositivo elegido", fg=ALERTA)
            else:
                combo.set(self._etiqueta(d))
                if reiniciar or self.salidas[zona].stream is None or self.salidas[zona].dispositivo != d:
                    self._abrir_zona(zona, d)
        self._verificar_mismo_dispositivo()

    def _elegir_dispositivo(self, zona):
        d = self.mapa_dispositivos.get(self.combos[zona].get())
        if d is not None:
            self._abrir_zona(zona, d)
        self._verificar_mismo_dispositivo()

    def _abrir_zona(self, zona, d):
        try:
            self.salidas[zona].abrir(d)
            self.estado_zona[zona].configure(
                text="Abierta: {} · {} Hz · {}".format(d["api"], d["fs"], d["nombre"]), fg=MUTED)
        except Exception as error:
            self.salidas[zona].cerrar()
            self.estado_zona[zona].configure(text="No se pudo abrir: {}".format(error), fg=ALERTA)

    def _verificar_mismo_dispositivo(self):
        a, b = (self.salidas[z].dispositivo for z in ZONAS)
        mismo = a is not None and b is not None and a["nombre"] == b["nombre"]
        self.aviso_dispositivos.configure(
            text="Atención: elegiste el mismo dispositivo para el ruido ambiente y los auriculares." if mismo else "")

    def _probar(self, zona):
        salida = self.salidas[zona]
        if salida.stream is None:
            self.estado_zona[zona].configure(text="Primero elegí un dispositivo que abra bien.", fg=ALERTA)
            return
        salida.reproducir_datos(audio.ruido_rosa(salida.fs, 1.0, -20.0), clave="prueba", fundido=False)

    def _iniciar_sesion(self):
        errores = []
        try:
            participante = int(self.var_participante.get().strip())
            if participante < 1:
                raise ValueError
        except ValueError:
            errores.append("El número de participante tiene que ser un entero mayor que 0.")
            participante = None
        ganancias = {}
        for clave, titulo in GANANCIAS:
            try:
                ganancias[clave] = float(self.vars_ganancia[clave].get().replace(",", "."))
            except ValueError:
                errores.append("{}: no es un número.".format(titulo))
        for zona, (titulo, _c, _cl) in ZONAS.items():
            if self.salidas[zona].stream is None:
                errores.append("{}: no hay un dispositivo abierto.".format(titulo))
        if self.faltantes:
            errores.append("Faltan archivos de audio (ver la lista).")
        if errores:
            self.error_config.configure(text="\n".join(errores))
            return

        self.cfg.update(ganancias)
        self.cfg["participante"] = participante
        self.cfg["mostrar_todas_las_apis"] = bool(self.todas_apis.get())
        for zona, (_t, clave, _cl) in ZONAS.items():
            d = self.salidas[zona].dispositivo
            self.cfg[clave] = {"nombre": d["nombre"], "api": d["api"]}
        try:
            ses.guardar_config(self.ruta_config, self.cfg)
        except OSError as error:
            self.error_config.configure(text="No se pudo guardar config.json: {}".format(error))
            return

        self.error_config.configure(text="Cargando audio…", fg=MUTED)
        self.update()
        self.fragmentos = [ses.nombre_fragmento(r) for r in self.rutas["musica"]]
        self.ruta_fragmento = dict(zip(self.fragmentos, self.rutas["musica"]))
        self.cb = ses.contrabalanceo(participante, self.fragmentos)
        self.oraciones = ses.cargar_oraciones(self.base)
        self.calibracion = ses.cargar_calibracion(self.base)
        try:
            auriculares, ruido = self.salidas["auriculares"], self.salidas["ruido"]
            for lista in ses.LISTAS_TAREA_A + (ses.LISTA_PRACTICA,):
                for n in range(1, ses.ORACIONES_POR_LISTA + 1):
                    auriculares.cargar(ses.ruta_oracion(self.base, lista, n))
            for ruta in self.rutas["musica"]:
                auriculares.cargar(ruta, circular=True)
            for clave in ("mssn", "trafico", "avion"):
                ruido.cargar(self.rutas[clave], circular=True)
        except Exception as error:
            self.error_config.configure(text="No se pudo cargar el audio: {}".format(error), fg=ALERTA)
            return

        self.registro = ses.Registro(self.base, participante)
        self._registrar_sesion(participante)
        self.pasos = self._armar_pasos()
        self.indice = 0
        self.show_step()

    def _registrar_sesion(self, participante):
        r, cb = self.registro, self.cb
        r.sesion("participante", participante)
        r.sesion("fecha", r.inicio.strftime("%Y-%m-%d %H:%M:%S"))
        for zona, (titulo, _c, _cl) in ZONAS.items():
            d = self.salidas[zona].dispositivo
            r.sesion("dispositivo_" + zona, "{} [{}] {} Hz".format(d["nombre"], d["api"], d["fs"]))
        for clave, _t in GANANCIAS:
            r.sesion(clave, self.cfg[clave])
        r.sesion("orden_bloques", " > ".join(cb["orden_bloques"]))
        for bloque in ses.BLOQUES:
            r.sesion("musica_" + bloque, cb["musica"][bloque])
            r.sesion("anc_" + bloque, " > ".join(cb["anc_bloques"][bloque]))
        r.sesion("tarea_A_orden_anc", " > ".join(cb["anc_tarea_a"]))
        r.sesion("tarea_A_lista_anc_OFF", cb["listas"]["OFF"])
        r.sesion("tarea_A_lista_anc_ON", cb["listas"]["ON"])
        r.sesion("tarea_A_lista_practica", ses.LISTA_PRACTICA)
        r.sesion("modo_anc", MODO_ANC)
        r.sesion("slider", "{} pasos de {:g} dB (paso {} = 0 dB)".format(PASOS_SLIDER, PASO_DB, PASOS_SLIDER))
        r.sesion("calibracion_niveles", "si" if self.calibracion(PASOS_SLIDER, "") is not None else "no")

    def _armar_pasos(self):
        cb, pasos = self.cb, []
        pasos += [{"tipo": "bienvenida", "seccion": 0}, {"tipo": "instrucciones", "seccion": 1},
                  {"tipo": "demo", "seccion": 2}, {"tipo": "a_inicio", "seccion": 3},
                  {"tipo": "transicion", "seccion": 3, "anc": "OFF", "practica": True}]
        pasos += [{"tipo": "oracion", "seccion": 3, "lista": ses.LISTA_PRACTICA, "oracion": n, "practica": True}
                  for n in range(1, ses.ORACIONES_POR_LISTA + 1)]
        for estado in cb["anc_tarea_a"]:
            lista = cb["listas"][estado]
            pasos.append({"tipo": "transicion", "seccion": 3, "anc": estado})
            pasos += [{"tipo": "oracion", "seccion": 3, "lista": lista, "oracion": n, "practica": False}
                      for n in range(1, ses.ORACIONES_POR_LISTA + 1)]
        pasos.append({"tipo": "a_fin", "seccion": 3})
        numero_escenario = 0
        for j, bloque in enumerate(cb["orden_bloques"]):
            comun = {"seccion": 4 + j, "bloque": bloque, "posicion": j + 1, "musica": cb["musica"][bloque]}
            pasos.append(dict(comun, tipo="bloque_inicio", anc="OFF"))
            for vez, estado in enumerate(cb["anc_bloques"][bloque], start=1):
                if vez == 2:
                    pasos.append(dict(comun, tipo="transicion", anc="OFF"))
                pasos.append(dict(comun, tipo="anclaje", vez=vez))
                if estado != "OFF":
                    pasos.append(dict(comun, tipo="transicion", anc=estado))
                numero_escenario += 1
                pasos.append(dict(comun, tipo="escenario", vez=vez, estado=estado, numero=numero_escenario))
        pasos.append({"tipo": "cierre", "seccion": 7})
        return pasos

    # ------------------------------------------------------------ ANC

    def cambiar_anc(self, estado, motivo=""):
        """Único punto de cambio del ANC. Hoy le pide el cambio al experimentador; más adelante
        va a llamar a OpenSCQ30 sin cambiar el resto del programa."""
        if MODO_ANC != "manual":
            raise NotImplementedError("Control automático del ANC todavía no integrado")
        self.anc_pendiente = estado
        self._fila("anc_solicitado", anc=estado, anc_cambio="manual", campo="motivo", valor=motivo)
        self._dibujar_aviso_anc()

    def _confirmar_anc(self):
        if self.anc_pendiente is None:
            return
        self.anc_actual, self.anc_pendiente = self.anc_pendiente, None
        self._fila("anc", anc=self.anc_actual, anc_cambio="manual")
        self._dibujar_footer()

    def _dibujar_aviso_anc(self):
        if hasattr(self, "aviso_anc") and self.aviso_anc.winfo_exists():
            self.aviso_anc.destroy()
        if self.anc_pendiente is None:
            return
        self.aviso_anc = tk.Frame(self.footer, bg=FONDO)
        self.aviso_anc.pack(side="right", padx=(0, 16))
        tk.Label(self.aviso_anc, text=TEXTOS["anc_aviso"].format(estado=self.anc_pendiente), bg=FONDO,
                 fg=MUTED, font=self._font(8)).pack(side="left", padx=(0, 6))
        ttk.Button(self.aviso_anc, text=TEXTOS["anc_hecho"], style="Small.TButton",
                   command=self._confirmar_anc).pack(side="left")

    # ------------------------------------------------------------ registro

    def _fila(self, tipo, **campos):
        if self.registro is not None:
            self.registro.fila(tipo, **campos)

    # ------------------------------------------------------------ navegación

    def _refresh_stepper(self):
        for child in self.stepper.winfo_children():
            child.destroy()
        actual = self.pasos[self.indice]["seccion"]
        for i, etiqueta in enumerate(ETIQUETAS_STEPPER):
            segmento = tk.Frame(self.stepper, bg=FONDO)
            segmento.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 4, 0))
            tk.Frame(segmento, bg=ACENTO if i <= actual else BORDES,
                     height=max(3, int(5 * self.scale_factor))).pack(fill="x", pady=(0, 4))
            tk.Label(segmento, text=etiqueta, bg=FONDO, fg=ACENTO_OSCURO if i == actual else MUTED,
                     font=self._font(8, "bold" if i == actual else "normal")).pack(fill="x")
        self.progress_text.configure(text=TEXTOS["pantalla"].format(actual=self.indice + 1, total=len(self.pasos)))

    def _puede_avanzar(self):
        paso = self.pasos[self.indice]
        tipo = paso["tipo"]
        if tipo == "transicion" or tipo == "bloque_inicio":
            return self.anc_pendiente is None
        if tipo == "a_inicio":
            return self.mssn_iniciado
        if tipo == "demo":
            return self.demo["estado"] == "terminada"
        if tipo in ("oracion", "escenario", "cierre"):
            return False
        return True

    def next_step(self):
        if self._puede_avanzar() and self.indice < len(self.pasos) - 1:
            self.indice += 1
            self.show_step()

    def _dibujar_footer(self):
        for child in self.footer.winfo_children():
            child.destroy()
        tipo = self.pasos[self.indice]["tipo"]
        if tipo == "cierre":
            listo = bool(self.fatiga.get() and self.comodidad.get())
            ttk.Button(self.footer, text=TEXTOS["finalizar"], style="Primary.TButton", command=self.finalizar,
                       state="normal" if listo else "disabled").pack(side="right")
        elif tipo not in ("oracion", "escenario"):
            texto = TEXTOS["comenzar"] if tipo == "bienvenida" else TEXTOS["continuar"]
            ttk.Button(self.footer, text=texto, style="Primary.TButton", command=self.next_step,
                       state="normal" if self._puede_avanzar() else "disabled").pack(side="right")
        self._dibujar_aviso_anc()

    def _entrar_seccion(self, seccion):
        if seccion == self.seccion_actual:
            return
        if self.seccion_actual is not None:
            self._fila("evento", campo="fin", valor=SECCIONES[self.seccion_actual])
        self._fila("evento", campo="inicio", valor=SECCIONES[seccion])
        self.seccion_actual = seccion

    def _poner_ambiente(self, bloque):
        """Ruido ambiente continuo de todo el bloque (silencio: nada) por los monitores."""
        if bloque == self.ambiente_actual:
            return
        ruido = self.salidas["ruido"]
        ruido.detener("ambiente")
        if bloque in GANANCIA_AMBIENTE:
            ruido.reproducir(self.rutas[bloque], self.cfg[GANANCIA_AMBIENTE[bloque]], loop=True, clave="ambiente")
        self.ambiente_actual = bloque

    def show_step(self):
        paso = self.pasos[self.indice]
        tipo = paso["tipo"]
        nuevo = self.indice != self.paso_dibujado
        if nuevo:
            self.salidas["auriculares"].detener()
            self._entrar_seccion(paso["seccion"])
            if "bloque" in paso:
                self._poner_ambiente(paso["bloque"])
            elif tipo == "cierre":
                self._poner_ambiente(None)
            if tipo == "transicion" or tipo == "bloque_inicio":
                if paso["anc"] != self.anc_actual:
                    self.cambiar_anc(paso["anc"], motivo=tipo)
            elif tipo == "a_fin":
                self.salidas["ruido"].detener("mssn")
            elif tipo == "oracion":
                self.reproducciones = 0
            elif tipo == "anclaje":
                self.salidas["auriculares"].reproducir(self.ruta_fragmento[paso["musica"]],
                                                       self.cfg["nivel_anclaje_db"], loop=True, clave="musica")
                self._fila("anclaje", tarea="BC", bloque=paso["bloque"], posicion_bloque=paso["posicion"],
                           musica=paso["musica"], anc=self.anc_actual, ganancia_db=self.cfg["nivel_anclaje_db"],
                           campo="vez", valor=paso["vez"])
            elif tipo == "escenario":
                inicial = random.Random(self.cfg["participante"] * 100 + paso["numero"]).randint(1, PASOS_SLIDER)
                self.escenario = {"inicial": inicial, "paso": inicial, "confirmado": False,
                                  "inicio": time.monotonic()}
                self.salidas["auriculares"].reproducir(self.ruta_fragmento[paso["musica"]], paso_a_db(inicial),
                                                       loop=True, clave="musica")
        self.paso_dibujado = self.indice

        self._refresh_stepper()
        for child in self.content.winfo_children():
            child.destroy()
        body = self._card()
        getattr(self, "_pantalla_" + tipo)(body, paso)
        self._dibujar_footer()

    # ------------------------------------------------------------ pantallas

    def _pantalla_bienvenida(self, body, _paso):
        self._heading(body, NOMBRE_TEST, 34)
        self._paragraph(body, TEXTOS["bienvenida_subtitulo"], 17)
        tk.Label(body, text=TEXTOS["duracion"].format(minutos=DURACION_MINUTOS), bg=SUPERFICIE, fg=MUTED,
                 font=self._font(13)).pack(pady=(4, 20))

    def _pantalla_instrucciones(self, body, _paso):
        self._heading(body, TEXTOS["instrucciones_titulo"])
        self._paragraph(body, TEXTOS["instrucciones"], 16, justify="left")

    def _pantalla_demo(self, body, _paso):
        self._heading(body, TEXTOS["demo_titulo"])
        self._paragraph(body, TEXTOS["demo_texto"].format(segundos=DEMO_ANC_S))
        if self.demo["estado"] == "espera":
            ttk.Button(body, text=TEXTOS["demo_boton"], style="Audio.TButton",
                       command=self._iniciar_demo).pack(pady=18)
        else:
            self.demo_label = tk.Label(body, bg=SUPERFICIE, fg=ACENTO_OSCURO, font=self._font(16, "bold"))
            self.demo_label.pack(pady=18)
            self._actualizar_demo_label()

    def _iniciar_demo(self):
        self.demo = {"estado": "en_curso", "inicio": time.monotonic(), "cambios": 0}
        self.salidas["ruido"].reproducir(self.rutas["trafico"], self.cfg["ganancia_trafico_db"], loop=True,
                                         clave="demo")
        self._fila("evento", campo="demo_anc", valor="inicio")
        self.show_step()
        self._tic_demo()

    def _tic_demo(self):
        if self.demo["estado"] != "en_curso":
            return
        transcurrido = time.monotonic() - self.demo["inicio"]
        while (self.demo["cambios"] < len(DEMO_SECUENCIA)
               and transcurrido >= self.demo["cambios"] * DEMO_INTERVALO_S):
            self.cambiar_anc(DEMO_SECUENCIA[self.demo["cambios"]], motivo="demo")
            self.demo["cambios"] += 1
        if transcurrido >= DEMO_ANC_S:
            self.demo["estado"] = "terminada"
            self.salidas["ruido"].detener("demo")
            self._fila("evento", campo="demo_anc", valor="fin")
            if self.pasos[self.indice]["tipo"] == "demo":
                self.show_step()
            return
        if self.pasos[self.indice]["tipo"] == "demo":
            self._actualizar_demo_label()
        self.after(250, self._tic_demo)

    def _actualizar_demo_label(self):
        if not (hasattr(self, "demo_label") and self.demo_label.winfo_exists()):
            return
        if self.demo["estado"] == "terminada":
            self.demo_label.configure(text=TEXTOS["demo_fin"])
        else:
            restante = max(0, DEMO_ANC_S - int(time.monotonic() - self.demo["inicio"]))
            self.demo_label.configure(text=TEXTOS["demo_en_curso"].format(segundos=restante))

    def _pantalla_a_inicio(self, body, _paso):
        self._heading(body, TEXTOS["tarea_a_titulo"], 24)
        self._paragraph(body, TEXTOS["tarea_a_instrucciones"])
        boton = ttk.Button(body, text=TEXTOS["reproducido"] if self.mssn_iniciado else TEXTOS["ruido_fondo"],
                           style="Played.TButton" if self.mssn_iniciado else "Audio.TButton",
                           command=self._iniciar_mssn)
        boton.pack(pady=(14, 4))
        self._paragraph(body, TEXTOS["ruido_persistente"], 12)

    def _iniciar_mssn(self):
        if not self.mssn_iniciado:
            self.salidas["ruido"].reproducir(self.rutas["mssn"], self.cfg["ganancia_mssn_db"], loop=True,
                                             clave="mssn")
            self.mssn_iniciado = True
            self._fila("evento", tarea="A", campo="mssn", valor="inicio")
        self.show_step()

    def _pantalla_transicion(self, body, paso):
        self._heading(body, TEXTOS["transicion_titulo"])
        self._paragraph(body, TEXTOS["transicion_practica"] if paso.get("practica") else TEXTOS["transicion_texto"])

    def _pantalla_oracion(self, body, paso):
        titulo = TEXTOS["tarea_a_titulo"] + (" · " + TEXTOS["practica"] if paso["practica"] else "")
        self._heading(body, titulo, 22)
        tk.Label(body, text=TEXTOS["oracion"].format(numero=paso["oracion"], total=ses.ORACIONES_POR_LISTA),
                 bg=SUPERFICIE, fg=TEXTO, font=self._font(19, "bold")).pack(pady=(4, 6))
        ttk.Button(body, text=TEXTOS["reproducir_oracion"], style="Audio.TButton",
                   command=lambda: self._reproducir_oracion(paso)).pack(pady=(0, 10))

        panel = tk.Frame(body, bg=PANEL, highlightbackground=BORDES, highlightthickness=1, padx=14, pady=8)
        panel.pack(fill="x", padx=20, pady=(4, 0))
        tk.Label(panel, text=TEXTOS["panel_experimentador"], bg=PANEL, fg=TEXTO,
                 font=self._font(11, "bold")).pack()
        datos = self.oraciones.get((paso["lista"], paso["oracion"]))
        rotulo = "Lista {} – Oración {}".format(paso["lista"], paso["oracion"])
        if datos:
            texto, claves = datos
            caja = tk.Text(panel, height=2, wrap="word", bg=PANEL, fg=TEXTO, relief="flat",
                           font=self._font(14), highlightthickness=0)
            caja.insert("1.0", texto)
            caja.tag_configure("clave", font=self._font(14, "bold"), foreground=ACENTO_OSCURO, underline=True)
            caja.tag_configure("centro", justify="center")
            caja.tag_add("centro", "1.0", "end")
            for palabra in claves:
                for m in re.finditer(r"\b{}\b".format(re.escape(palabra)), texto, re.IGNORECASE):
                    caja.tag_add("clave", "1.0+{}c".format(m.start()), "1.0+{}c".format(m.end()))
            caja.configure(state="disabled")
            caja.pack(fill="x", pady=(4, 0))
            tk.Label(panel, text=rotulo, bg=PANEL, fg=MUTED, font=self._font(9)).pack()
        else:
            tk.Label(panel, text=rotulo, bg=PANEL, fg=TEXTO, font=self._font(15, "bold")).pack(pady=(4, 0))
        tk.Label(panel, text=TEXTOS["puntaje_ayuda"], bg=PANEL, fg=MUTED, font=self._font(9)).pack(pady=(4, 4))
        fila = tk.Frame(panel, bg=PANEL)
        fila.pack()
        habilitado = self.reproducciones > 0
        for valor in PUNTAJES:
            tk.Button(fila, text=formato_puntaje(valor), width=4, height=2, font=self._font(15, "bold"),
                      bg=SUPERFICIE if habilitado else "#d9dddc", fg=ACENTO_OSCURO, activebackground=ACENTO_CLARO,
                      relief="solid", bd=1, state="normal" if habilitado else "disabled",
                      command=lambda v=valor: self._puntuar(paso, v)).pack(side="left", padx=3)

    def _reproducir_oracion(self, paso):
        self.salidas["auriculares"].reproducir(ses.ruta_oracion(self.base, paso["lista"], paso["oracion"]),
                                               self.cfg["ganancia_voz_db"], clave="oracion", fundido=False)
        self.reproducciones += 1
        if self.reproducciones == 1:
            self.show_step()

    def _puntuar(self, paso, valor):
        self._fila("ensayo", tarea="A", anc=self.anc_actual, anc_cambio="manual", lista=paso["lista"],
                   oracion=paso["oracion"], practica="si" if paso["practica"] else "no",
                   puntaje=formato_puntaje(valor), reproducciones=self.reproducciones)
        self.indice += 1
        self.show_step()

    def _pantalla_a_fin(self, body, _paso):
        self._heading(body, TEXTOS["tarea_a_titulo"])
        self._paragraph(body, TEXTOS["tarea_a_fin"])

    def _pantalla_bloque_inicio(self, body, paso):
        self._heading(body, TEXTOS["bloque_titulo"].format(numero=paso["posicion"]))
        self._paragraph(body, TEXTOS["bloque_texto"])

    def _pantalla_anclaje(self, body, _paso):
        self._heading(body, TEXTOS["anclaje_titulo"])
        self._paragraph(body, TEXTOS["anclaje_texto"])
        tk.Label(body, text="♪  La música suena sola", bg=ACENTO_CLARO, fg=ACENTO_OSCURO,
                 font=self._font(12, "bold"), padx=12, pady=6).pack(pady=16)

    def _pantalla_escenario(self, body, paso):
        estado = self.escenario
        self._heading(body, TEXTOS["escenario_titulo"], 24)
        self._paragraph(body, TEXTOS["nivel_escucha"], 14)

        area = tk.Frame(body, bg=SUPERFICIE)
        area.pack(fill="x", padx=8, pady=(6, 0))
        izquierda = tk.Frame(area, bg=SUPERFICIE)
        izquierda.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.var_slider = tk.IntVar(value=estado["paso"])
        tk.Scale(izquierda, from_=1, to=PASOS_SLIDER, orient="horizontal", resolution=1, showvalue=False,
                 variable=self.var_slider, command=self._mover_slider, length=int(600 * self.scale_factor),
                 sliderlength=28, width=22, troughcolor=ACENTO_CLARO, activebackground=ACENTO,
                 highlightthickness=0, bg=SUPERFICIE, bd=0,
                 state="disabled" if estado["confirmado"] else "normal").pack(fill="x")
        escala = tk.Frame(izquierda, bg=SUPERFICIE)
        escala.pack(fill="x")
        for texto, lado in (("0", "left"), ("100", "right")):
            tk.Label(escala, text=texto, bg=SUPERFICIE, fg=MUTED, font=self._font(10)).pack(side=lado)
        tk.Label(escala, text="50", bg=SUPERFICIE, fg=MUTED, font=self._font(10)).pack()
        extremos = tk.Frame(izquierda, bg=SUPERFICIE)
        extremos.pack(fill="x")
        tk.Label(extremos, text=TEXTOS["menor_volumen"], bg=SUPERFICIE, fg=MUTED,
                 font=self._font(10, "bold")).pack(side="left")
        tk.Label(extremos, text=TEXTOS["mayor_volumen"], bg=SUPERFICIE, fg=MUTED,
                 font=self._font(10, "bold")).pack(side="right")
        self.level_canvas = tk.Canvas(area, width=int(160 * self.scale_factor), height=int(74 * self.scale_factor),
                                      bg=SUPERFICIE, highlightthickness=0)
        self.level_canvas.pack(side="right")
        self._dibujar_triangulo(estado["paso"])

        ttk.Button(body, text=TEXTOS["ok"], style="Primary.TButton", command=self._confirmar_nivel,
                   state="disabled" if estado["confirmado"] else "normal").pack(pady=(8, 6))

        habilitado = estado["confirmado"]
        fondo = PANEL if habilitado else GRIS
        ccr = tk.Frame(body, bg=fondo, highlightbackground=BORDES, highlightthickness=1, padx=8, pady=6)
        ccr.pack(fill="x", padx=4)
        tk.Label(ccr, text=TEXTOS["esfuerzo"], bg=fondo, fg=TEXTO if habilitado else "#818987",
                 font=self._font(12, "bold")).pack(pady=(0, 4))
        fila = tk.Frame(ccr, bg=fondo)
        fila.pack(fill="x")
        for texto, valor in OPCIONES_CCR:
            tk.Button(fila, text=texto, wraplength=int(106 * self.scale_factor), width=12, height=3,
                      font=self._font(9, "bold"), relief="solid", bd=1,
                      bg=SUPERFICIE if habilitado else "#d9dddc", fg=TEXTO if habilitado else "#8a918f",
                      disabledforeground="#8a918f", state="normal" if habilitado else "disabled",
                      command=lambda t=texto, v=valor: self._elegir_ccr(paso, t, v)).pack(
                          side="left", fill="both", expand=True, padx=2)

    def _mover_slider(self, valor):
        paso = int(float(valor))
        self.escenario["paso"] = paso
        self.salidas["auriculares"].ganancia("musica", paso_a_db(paso))
        self._dibujar_triangulo(paso)

    def _dibujar_triangulo(self, paso):
        self.level_canvas.delete("all")
        ancho = int(150 * self.scale_factor)
        centro = int(37 * self.scale_factor)
        alto = max(4, int(58 * self.scale_factor * paso / PASOS_SLIDER))
        self.level_canvas.create_polygon(6, centro, ancho, centro - alto // 2, ancho, centro + alto // 2,
                                         fill=ACENTO, outline=ACENTO_OSCURO, width=2)

    def _confirmar_nivel(self):
        self.escenario["confirmado"] = True
        self.show_step()

    def _elegir_ccr(self, paso, texto, valor):
        final = self.escenario["paso"]
        nivel = self.calibracion(final, paso["musica"])
        self._fila("ensayo", tarea="BC", bloque=paso["bloque"], posicion_bloque=paso["posicion"],
                   musica=paso["musica"], anc=self.anc_actual, anc_cambio="manual", paso_inicial=self.escenario["inicial"],
                   paso_final=final, ganancia_db="{:g}".format(paso_a_db(final)),
                   nivel_dba="" if nivel is None else "{:g}".format(nivel), ccr=valor, ccr_texto=texto,
                   campo="escenario", valor=paso["vez"])
        self.indice += 1
        self.show_step()

    def _pantalla_cierre(self, body, _paso):
        self._heading(body, TEXTOS["cierre_titulo"])
        encuesta = tk.Frame(body, bg=SUPERFICIE)
        encuesta.pack(pady=(4, 8))
        for pregunta, opciones, var in ((TEXTOS["fatiga"], OPCIONES_FATIGA, self.fatiga),
                                        (TEXTOS["comodidad"], OPCIONES_COMODIDAD, self.comodidad)):
            tk.Label(encuesta, text=pregunta, bg=SUPERFICIE, fg=TEXTO, font=self._font(13, "bold")).pack(pady=(6, 4))
            fila = tk.Frame(encuesta, bg=SUPERFICIE)
            fila.pack()
            for opcion in opciones:
                ttk.Radiobutton(fila, text=opcion, value=opcion, variable=var,
                                command=self._dibujar_footer).pack(side="left", padx=10)
        self._paragraph(body, TEXTOS["cierre_texto"], 15)

    # ------------------------------------------------------------ audio: cortes de dispositivo

    def _vigilar_audio(self):
        problemas = []
        for zona, (titulo, _c, _cl) in ZONAS.items():
            salida = self.salidas[zona]
            problema = salida.problema()
            if problema:
                problemas.append("{} ({}): {}.".format(titulo, salida.dispositivo["nombre"], problema))
        if problemas:
            self.banner_texto.configure(text="Se cortó el audio. " + " ".join(problemas) +
                                        " Reconectá el dispositivo y tocá Reintentar.")
            if not self.banner.winfo_ismapped():
                self.banner.pack(fill="x", padx=16, pady=(8, 0), before=self.header)
                self._fila("evento", campo="audio_cortado", valor=" ".join(problemas))
        elif self.banner.winfo_ismapped():
            self.banner.pack_forget()
        self.after(500, self._vigilar_audio)

    def _reintentar_audio(self):
        for salida in self.salidas.values():
            salida.cerrar()
        try:
            audio.reiniciar_portaudio()
            dispositivos = audio.listar_salidas(True)
        except Exception:
            dispositivos = []
        for zona, salida in self.salidas.items():
            previo = salida.dispositivo
            d = audio.buscar(dispositivos, previo["nombre"], previo["api"]) if previo else None
            if d is None:
                salida.error = "no está conectado"
                continue
            try:
                salida.abrir(d)
            except Exception as error:
                salida.error = str(error)
        self._fila("evento", campo="audio_reintento",
                   valor="ok" if all(s.problema() is None for s in self.salidas.values()) else "falla")

    # ------------------------------------------------------------ cierre

    def finalizar(self):
        self._fila("cierre", campo="fatiga", valor=self.fatiga.get())
        self._fila("cierre", campo="incomodidad_auriculares", valor=self.comodidad.get())
        self._fila("evento", campo="fin", valor="cierre")
        self._fila("evento", campo="fin", valor="sesion")
        self.sesion_terminada = True
        self.close()

    def close(self):
        if self.registro is not None:
            if not self.sesion_terminada:
                self._fila("evento", campo="sesion_interrumpida", valor=SECCIONES[self.pasos[self.indice]["seccion"]])
            self.registro.cerrar()
        for salida in self.salidas.values():
            salida.cerrar()
        self.destroy()


if __name__ == "__main__":
    enable_windows_dpi_awareness()
    app = PsychoacousticPilot()
    app.mainloop()
