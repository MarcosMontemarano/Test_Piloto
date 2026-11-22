import ctypes
import os
import queue
import random
import threading
import re
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import numpy as np

from piloto import anc_control, audio, volumen
from piloto import sesion as ses


# Configuración editable
TITULO_VENTANA = "Piloto psicoacústico"
DURACION_MINUTOS = 25

# Slider de nivel preferido: PASOS_SLIDER pasos de PASO_DB dB (el último paso = 0 dB).
PASOS_SLIDER = 20
# Voz de la Tarea A: pasa-altos al cargarla (solo lo que suena en el test; los archivos, el LTASS
# y el MSSN no cambian). Atenúa golpes graves de 60-90 Hz de la grabación (L3-O3, L3-O2, L2-O4);
# la F0 de la hablante no baja de ~156 Hz (ahí el filtro resta 0,9 dB).
PASA_ALTOS_VOZ_HZ = 90
PASO_DB = 2.0  # rango: paso 1 = -38 dB ... paso 20 = 0 dB

# Demostración del ANC: ruido de tráfico DEMO_ANC_S segundos; el ANC cambia cada DEMO_INTERVALO_S.
DEMO_ANC_S = 21
DEMO_INTERVALO_S = 7
DEMO_SECUENCIA = ("OFF", "ON", "OFF")

# Las pantallas de pausa avanzan solas cuando el ANC está confirmado, con este mínimo en pantalla.
MIN_TRANSICION_S = 2.5

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

# Modo prueba: "Empezar desde" (configuración) -> índice de sección. Ctrl+Shift+S salta de pantalla.
EMPEZAR_DESDE = (("Inicio (sesión completa)", 0), ("Instrucciones", 1), ("Tarea A", 3), ("Bloque 1", 4),
                 ("Bloque 2", 5), ("Bloque 3", 6), ("Cierre", 7))

SECCIONES = ("bienvenida", "instrucciones", "demo_anc", "tarea_A", "bloque_1", "bloque_2",
             "bloque_3", "cierre")

# Textos que ve el participante: textos_participante.json (junto al programa), que se lee al
# iniciar y se suma a TEXTOS. Acá quedan solo los del experimentador.
TEXTOS = {
    "panel_experimentador": "Panel del experimentador (no para el oyente)",
    "puntaje_correctas": "Palabras correctas",
    "puntaje_menor": "Palabras con error menor\n(número o género)",
    "puntaje_oracion": "Puntaje: {puntaje} / 5",
    "puntaje_pendiente": "Marcá las palabras correctas",
    "puntaje_confirmar": "Registrar y seguir",
    "anc_aviso_manual": "Experimentador: OpenSCQ30 falló ({error}). Cambiá el ANC a {estado} a mano y confirmá.",
    "anc_hecho_manual": "Listo, ANC en {estado}",
}
# Valores internos del CCR, en el orden de "opciones_esfuerzo" del JSON.
VALORES_CCR = (-3, -2, -1, 0, 1, 2, 3)
PALABRAS_CLAVE = 5
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


CONTRASTE = "#e8590c"         # manija del slider (naranja, contrasta con el verde azulado)
CONTRASTE_OSCURO = "#b8460a"


class SliderGrande(tk.Canvas):
    """Deslizador horizontal de 'pasos' posiciones con una manija grande y flechas ◀ ▶.

    Se mueve arrastrando la manija, haciendo clic en la pista o con las flechas del teclado.
    Llama a al_mover(paso) con pasos de 1 a 'pasos'. Debajo, la escala visible de 0 a 100.
    """

    def __init__(self, padre, pasos, inicial, al_mover, escala, fuente_manija, fuente_escala):
        self.alto_manija = int(58 * escala)
        self.ancho_manija = int(104 * escala)
        super().__init__(padre, height=self.alto_manija + int(34 * escala), bg=SUPERFICIE,
                         highlightthickness=0, cursor="sb_h_double_arrow", takefocus=1)
        self.pasos, self.paso, self.al_mover, self.escala = pasos, inicial, al_mover, escala
        self.fuente_manija, self.fuente_escala = fuente_manija, fuente_escala
        self.bind("<Configure>", lambda _e: self._dibujar())
        for evento in ("<Button-1>", "<B1-Motion>"):
            self.bind(evento, self._mouse)
        self.bind("<Left>", lambda _e: self._mover(self.paso - 1))
        self.bind("<Right>", lambda _e: self._mover(self.paso + 1))

    def _x(self, paso):
        margen = self.ancho_manija / 2 + 4
        return margen + (paso - 1) / (self.pasos - 1) * (self.winfo_width() - 2 * margen)

    def _mouse(self, evento):
        self.focus_set()
        margen = self.ancho_manija / 2 + 4
        fraccion = (evento.x - margen) / max(1, self.winfo_width() - 2 * margen)
        self._mover(1 + round(fraccion * (self.pasos - 1)))

    def _mover(self, paso):
        paso = max(1, min(self.pasos, paso))
        if paso != self.paso:
            self.paso = paso
            self._dibujar()
            self.al_mover(paso)
        return "break"

    def _dibujar(self):
        self.delete("all")
        centro = self.alto_manija / 2 + 2
        grosor = int(12 * self.escala)
        x0, x1, x = self._x(1), self._x(self.pasos), self._x(self.paso)
        self.create_line(x0, centro, x1, centro, fill=ACENTO_CLARO, width=grosor, capstyle="round")
        self.create_line(x0, centro, x, centro, fill=ACENTO, width=grosor, capstyle="round")
        for p in range(1, self.pasos + 1):
            xp = self._x(p)
            self.create_line(xp, centro + grosor, xp, centro + grosor + int(6 * self.escala), fill=BORDES)
        base = self.alto_manija + int(8 * self.escala)
        for valor in (0, 25, 50, 75, 100):
            xv = x0 + valor / 100 * (x1 - x0)
            self.create_text(xv, base, text=str(valor), fill=MUTED, font=self.fuente_escala, anchor="n")
        a, h = self.ancho_manija / 2, self.alto_manija / 2
        r = int(14 * self.escala)
        puntos = [x - a + r, centro - h, x + a - r, centro - h, x + a, centro - h, x + a, centro - h + r,
                  x + a, centro + h - r, x + a, centro + h, x + a - r, centro + h, x - a + r, centro + h,
                  x - a, centro + h, x - a, centro + h - r, x - a, centro - h + r, x - a, centro - h]
        self.create_polygon(puntos, smooth=True, fill=CONTRASTE, outline=CONTRASTE_OSCURO, width=3)
        self.create_text(x, centro, text="◀  ▶", fill="white", font=self.fuente_manija)


def paso_a_db(paso):
    return (paso - PASOS_SLIDER) * PASO_DB


class ArchivoFaltante(Exception):
    """Falta un archivo de audio durante la sesión: se detiene, nunca se reemplaza por otra señal."""


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
        # Solo para el experimentador: saltar a la pantalla siguiente (queda registrado como prueba).
        self.bind_all("<Control-Shift-S>", self._saltar)
        self.bind_all("<Control-Shift-s>", self._saltar)
        self.title(TITULO_VENTANA)
        self.configure(bg=FONDO)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.base = ses.carpeta_base()
        textos, error_textos = ses.cargar_textos(self.base)
        if textos is None:
            self.salidas, self.registro = {}, None
            self._error_textos(error_textos)
            return
        TEXTOS.update({k: v for k, v in textos.items() if not k.startswith("_")})
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
        self.anc_manual = False
        self.anc_error = ""
        self.anc_modo = ""
        self.control_anc = None
        self.control_cfg = None
        self.anc_conectado = False
        self.transicion_inicio = 0.0
        # Un solo hilo ejecuta, en orden, todo lo que llama a la CLI de OpenSCQ30.
        self.tareas = queue.Queue()
        self.resultados = queue.Queue()
        threading.Thread(target=self._trabajador, daemon=True).start()
        self.ambiente_actual = None
        self.ambiente_info = None
        self.ambiente_label = None
        self.mssn_iniciado = False
        self.demo = {"estado": "espera"}
        self.reproducciones = 0
        self.puntaje_sel = {"correctas": None, "menor": 0}
        self.escenario = {}
        self.fatiga = tk.StringVar(value="")
        self.comodidad = tk.StringVar(value="")
        self.sesion_terminada = False
        self.detenida = False

        self._configure_styles()
        self._build_shell()
        self.pantalla_config()
        self.after(500, self._vigilar_audio)
        self.after(100, self._revisar_resultados)

    def _error_textos(self, mensaje):
        marco = tk.Frame(self, bg=FONDO)
        marco.pack(expand=True, fill="both", padx=40, pady=40)
        tk.Label(marco, text="No se pudieron cargar los textos del participante", bg=FONDO, fg=ALERTA,
                 font=self._font(18, "bold")).pack(pady=(0, 12))
        tk.Label(marco, text=mensaje, bg=FONDO, fg=TEXTO, font=self._font(12), justify="left",
                 wraplength=int(900 * self.scale_factor)).pack()
        ttk.Button(marco, text="Cerrar", command=self.destroy).pack(pady=20)

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
        tk.Label(linea, text=TEXTOS["duracion_encabezado"].format(minutos=DURACION_MINUTOS), bg=FONDO, fg=MUTED,
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
        ttk.Button(opciones, text="Actualizar dispositivos", style="Small.TButton",
                   command=lambda: self._refrescar_dispositivos(True)).pack(side="left")
        tk.Label(opciones, text="Dispositivos de {} (una entrada por dispositivo)".format(audio.api_preferida() or "audio"),
                 bg=SUPERFICIE, fg=MUTED, font=self._font(9)).pack(side="left", padx=12)
        for bloque in ("avion", "trafico"):
            ttk.Button(opciones, text="Escuchar {} (4 s)".format(ses.NOMBRE_BLOQUE[bloque].lower()),
                       style="Small.TButton", command=lambda b=bloque: self._probar_ambiente(b)).pack(
                           side="right", padx=(6, 0))
        self.aviso_dispositivos = tk.Label(body, bg=SUPERFICIE, fg=ALERTA, font=self._font(11, "bold"))
        self.aviso_dispositivos.pack(pady=(0, 4))

        fila_anc = tk.Frame(body, bg=SUPERFICIE)
        fila_anc.pack(fill="x", pady=(0, 4))
        self.estado_anc = tk.Label(fila_anc, text="ANC: buscando OpenSCQ30…", bg=SUPERFICIE, fg=MUTED,
                                   font=self._font(11, "bold"), anchor="w", justify="left",
                                   wraplength=int(780 * self.scale_factor))
        self.estado_anc.pack(side="left", fill="x", expand=True)
        ttk.Button(fila_anc, text="Probar ANC", command=self._probar_anc).pack(side="right")
        ttk.Button(fila_anc, text="Reconectar", style="Small.TButton",
                   command=self._buscar_anc).pack(side="right", padx=8)
        self._buscar_anc()

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
        tk.Label(ganancias, text="Empezar desde", bg=SUPERFICIE, fg=TEXTO, font=self._font(11, "bold"),
                 anchor="e").grid(row=fila_p, column=2, sticky="e", padx=(16, 6), pady=(10, 3))
        self.empezar_desde = ttk.Combobox(ganancias, state="readonly", width=22, font=self._font(11),
                                          values=[nombre for nombre, _ in EMPEZAR_DESDE])
        self.empezar_desde.current(0)
        self.empezar_desde.grid(row=fila_p, column=3, sticky="w", pady=(10, 3))
        tk.Label(ganancias, text="Modo prueba: empezar en otra parte o saltar pantallas con Ctrl+Shift+S "
                                 "queda registrado como prueba en el CSV.",
                 bg=SUPERFICIE, fg=MUTED, font=self._font(9)).grid(row=fila_p + 1, column=0, columnspan=4, pady=(2, 0))

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
        self.confirmo_advertencias = False
        self.after(2000, self._vigilar_volumen)
        self._refrescar_dispositivos(False)

    def _buscar_anc(self):
        """Indicador de la configuración: ¿OpenSCQ30 llega a los auriculares?"""
        cli = anc_control.buscar_cli(self.base, self.cfg.get("openscq30_cli") or None)
        if not cli:
            self.control_cfg = None
            self.estado_anc.configure(text="ANC: no encontrado (falta la CLI de OpenSCQ30; ver LEEME)", fg=ALERTA)
            return
        self.control_cfg = anc_control.ControlANC(cli, self.cfg.get("anc_mac") or None)
        self.estado_anc.configure(text="ANC: buscando los auriculares…", fg=MUTED)
        control = self.control_cfg
        self._en_hilo(lambda: (control._mac(), control.get_anc()), self._anc_encontrado)

    def _anc_encontrado(self, resultado):
        if not (hasattr(self, "estado_anc") and self.estado_anc.winfo_exists()):
            return
        if isinstance(resultado, Exception):
            self.anc_conectado = False
            self.estado_anc.configure(text="ANC: no encontrado — {}".format(resultado), fg=ALERTA)
        else:
            self.anc_conectado = True
            self.estado_anc.configure(text="ANC: conectado · {} · modo actual {}".format(*resultado), fg=ACENTO_OSCURO)

    def _probar_anc(self):
        if self.control_cfg is None:
            return
        control = self.control_cfg
        self.estado_anc.configure(text="ANC: probando ON → OFF…", fg=MUTED)
        self._en_hilo(lambda: [control.set_anc("ON"), control.set_anc("OFF")], self._anc_probado)

    def _anc_probado(self, resultado):
        if not (hasattr(self, "estado_anc") and self.estado_anc.winfo_exists()):
            return
        if isinstance(resultado, Exception):
            self.anc_conectado = False
            self.estado_anc.configure(text="ANC: falló — {}".format(resultado), fg=ALERTA)
            return
        partes = ["{} {}".format(f["pedido"], "ok {:.1f} s".format(f["latencia_s"]) if f["ok"] else "FALLÓ: " + f["error"])
                  for f in resultado]
        self.anc_conectado = all(f["ok"] for f in resultado)
        self.estado_anc.configure(text="ANC: prueba " + " · ".join(partes),
                                  fg=ACENTO_OSCURO if self.anc_conectado else ALERTA)

    def _etiqueta(self, d):
        return d["nombre"]

    def _refrescar_dispositivos(self, reiniciar):
        elegidos = {z: s.dispositivo for z, s in self.salidas.items()}
        if reiniciar:
            for s in self.salidas.values():
                s.cerrar()
            audio.reiniciar_portaudio()
        self.dispositivos = audio.listar_salidas()
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
        self.confirmo_advertencias = False
        try:
            self.salidas[zona].abrir(d)
            self.estado_zona[zona].configure(fg=MUTED)
            self._mostrar_estado_zona(zona)
        except Exception as error:
            self.salidas[zona].cerrar()
            self.estado_zona[zona].configure(text="No se pudo abrir: {}".format(error), fg=ALERTA)

    def _mostrar_estado_zona(self, zona):
        d = self.salidas[zona].dispositivo
        if d is None or self.salidas[zona].stream is None:
            return
        self.estado_zona[zona].configure(text="Abierta: {} · {} Hz · {} canales · volumen de Windows: {}".format(
            d["api"], d["fs"], d["canales"], volumen.describir(volumen.leer_volumen(d["nombre"]))))

    def _advertencias_salidas(self):
        """Advertencias de la configuración: mismo dispositivo, perfil manos libres, volumen de Windows."""
        avisos = []
        ruido, auriculares = (self.salidas[z].dispositivo for z in ("ruido", "auriculares"))
        if ruido is not None and auriculares is not None and ruido["nombre"] == auriculares["nombre"]:
            avisos.append("Elegiste el mismo dispositivo para el ruido ambiente y los auriculares.")
        if auriculares is not None:
            if volumen.es_manos_libres(auriculares):
                avisos.append("Los auriculares están en el perfil Manos libres / Hands-Free ({} canal(es), {} Hz): "
                              "elegí el perfil estéreo (\"Auriculares\").".format(auriculares["canales"], auriculares["fs"]))
            vol = volumen.leer_volumen(auriculares["nombre"])
            if vol is not None and (vol["porcentaje"] != 100 or vol["silenciado"]):
                avisos.append("El volumen de Windows de los auriculares está en {}: ponelo al 100 %.".format(
                    volumen.describir(vol)))
        return avisos

    def _verificar_mismo_dispositivo(self):
        avisos = self._advertencias_salidas()
        self.aviso_dispositivos.configure(text="\n".join("Atención: " + a for a in avisos))

    def _vigilar_volumen(self):
        """En la configuración, relee cada 2 s el volumen de Windows (puede cambiarse con las teclas)."""
        if self.pasos or not (hasattr(self, "aviso_dispositivos") and self.aviso_dispositivos.winfo_exists()):
            return
        for zona in ZONAS:
            self._mostrar_estado_zona(zona)
        self._verificar_mismo_dispositivo()
        self.after(2000, self._vigilar_volumen)

    def _probar(self, zona):
        salida = self.salidas[zona]
        if salida.stream is None:
            self.estado_zona[zona].configure(text="Primero elegí un dispositivo que abra bien.", fg=ALERTA)
            return
        salida.reproducir_datos(audio.ruido_rosa(salida.fs, 1.0, -20.0), clave="prueba", fundido=False)

    def _probar_ambiente(self, bloque):
        """4 s del ruido del bloque por los monitores, con la ganancia escrita en la configuración."""
        salida, ruta = self.salidas["ruido"], self.rutas.get(bloque)
        if salida.stream is None:
            self.estado_zona["ruido"].configure(text="Primero elegí un dispositivo que abra bien.", fg=ALERTA)
            return
        if not ruta or not os.path.isfile(ruta):
            self.estado_zona["ruido"].configure(text="No está el archivo {}".format(ruta), fg=ALERTA)
            return
        try:
            ganancia = float(self.vars_ganancia[GANANCIA_AMBIENTE[bloque]].get().replace(",", "."))
        except ValueError:
            ganancia = 0.0
        datos = salida.cargar(ruta, circular=True)[:int(4 * salida.fs)].copy()
        fundido = int(0.05 * salida.fs)
        datos[-fundido:] *= np.linspace(1, 0, fundido, dtype=np.float32)[:, None]
        salida.reproducir_datos(datos, ganancia, clave="prueba")
        self.estado_zona["ruido"].configure(text="Sonando {} por {} con {:g} dB…".format(
            os.path.basename(ruta), salida.dispositivo["nombre"], ganancia), fg=ACENTO_OSCURO)

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
            self.error_config.configure(text="\n".join(errores), fg=ALERTA)
            return
        auriculares = self.salidas["auriculares"].dispositivo
        if volumen.es_manos_libres(auriculares) and not self.confirmo_advertencias:
            self.confirmo_advertencias = True
            self.error_config.configure(text="Atención: los auriculares están en el perfil Manos libres. Elegí el "
                                             "perfil estéreo, o tocá Iniciar sesión otra vez para seguir igual.",
                                        fg=ALERTA)
            return

        self.cfg.update(ganancias)
        self.cfg["participante"] = participante
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
                    auriculares.cargar(ses.ruta_oracion(self.base, lista, n), pasa_altos_hz=PASA_ALTOS_VOZ_HZ)
            for ruta in self.rutas["musica"]:
                auriculares.cargar(ruta, circular=True)
            for clave in ("mssn", "trafico", "avion"):
                ruido.cargar(self.rutas[clave], circular=True)
        except Exception as error:
            self.error_config.configure(text="No se pudo cargar el audio: {}".format(error), fg=ALERTA)
            return

        nombre_inicio, self.seccion_inicio = EMPEZAR_DESDE[max(0, self.empezar_desde.current())]
        self.registro = ses.Registro(self.base, participante, prueba=self.seccion_inicio != 0)
        if self.seccion_inicio != 0:
            self.registro.sesion("modo_prueba", "empieza desde: " + nombre_inicio)
        control = self.control_cfg if getattr(self, "anc_conectado", False) else None
        if control is None:
            self._anc_listo(participante, None, None)
            return
        self.error_config.configure(text="Preparando el ANC…", fg=MUTED)
        submodo = self.cfg.get("anc_submodo") or "Transport"
        self._en_hilo(lambda: (control.fijar_submodo(submodo), control.get_anc()),
                      lambda resultado: self._anc_listo(participante, control, resultado))

    def _anc_listo(self, participante, control, resultado):
        if control is not None and isinstance(resultado, Exception):
            self.registro.sesion("anc_error_inicio", str(resultado))
            control = None
        self.control_anc = control
        self._registrar_sesion(participante)
        if control is not None:
            submodo, estado = resultado
            self.anc_actual = estado if estado in ("ON", "OFF") else None
            self.anc_modo = "automatico"
            self.registro.sesion("anc_submodo", submodo)
            self.registro.sesion("anc_estado_inicial", estado)
        self.pasos = self._armar_pasos()
        self.indice = next(i for i, p in enumerate(self.pasos) if p["seccion"] == self.seccion_inicio)
        self.show_step()
        self._tic_ambiente()

    def _saltar(self, _evento=None):
        """Ctrl+Shift+S: pasa a la pantalla siguiente sin registrar respuesta (modo prueba)."""
        if not self.pasos or self.detenida or self.indice >= len(self.pasos) - 1:
            return "break"
        if not self.registro.prueba:
            self.registro.prueba = True
            self._fila("sesion", campo="modo_prueba", valor="salto con Ctrl+Shift+S")
        tipo = self.pasos[self.indice]["tipo"]
        if tipo == "demo" and self.demo["estado"] != "terminada":
            self.demo["estado"] = "terminada"
            self.salidas["ruido"].detener("demo")
        self._fila("evento", campo="salto", valor="{} (pantalla {})".format(tipo, self.indice + 1))
        self.indice += 1
        self.show_step()
        return "break"

    def _registrar_sesion(self, participante):
        r, cb = self.registro, self.cb
        r.sesion("participante", participante)
        r.sesion("fecha", r.inicio.strftime("%Y-%m-%d %H:%M:%S"))
        for zona, (titulo, _c, _cl) in ZONAS.items():
            d = self.salidas[zona].dispositivo
            r.sesion("dispositivo_" + zona, "{} [{}] {} Hz, {} canales".format(d["nombre"], d["api"], d["fs"], d["canales"]))
            r.sesion("volumen_windows_" + zona, volumen.describir(volumen.leer_volumen(d["nombre"])))
        auriculares = self.salidas["auriculares"].dispositivo
        r.sesion("perfil_auriculares", "MANOS LIBRES" if volumen.es_manos_libres(auriculares) else "estereo")
        r.sesion("microfono_auriculares", "no se abre (el programa solo usa salidas)")
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
        r.sesion("modo_anc", "openscq30" if self.control_anc else "manual (OpenSCQ30 no disponible)")
        if self.control_anc:
            r.sesion("openscq30_cli", self.control_anc.cli)
            r.sesion("anc_mac", self.control_anc.mac)
        r.sesion("voz_pasa_altos", "Butterworth 2.º orden ida y vuelta, {} Hz".format(PASA_ALTOS_VOZ_HZ))
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

    def _trabajador(self):
        while True:
            funcion, al_terminar = self.tareas.get()
            try:
                resultado = funcion()
            except Exception as error:
                resultado = error
            self.resultados.put((al_terminar, resultado))

    def _en_hilo(self, funcion, al_terminar):
        """Corre funcion() en el hilo de OpenSCQ30 y llama a al_terminar(resultado) en la interfaz."""
        self.tareas.put((funcion, al_terminar))

    def _revisar_resultados(self):
        while True:
            try:
                al_terminar, resultado = self.resultados.get_nowait()
            except queue.Empty:
                break
            try:
                al_terminar(resultado)
            except tk.TclError:
                pass
        self.after(100, self._revisar_resultados)

    def cambiar_anc(self, estado, motivo=""):
        """Único punto de cambio del ANC: lo cambia OpenSCQ30 (anc_control.set_anc) y lo verifica.

        Mientras cambia, el participante ve solo un aviso genérico. Si OpenSCQ30 falla después del
        reintento, se le pide el cambio al experimentador (letra chica, con confirmación) y se
        registra como manual.
        """
        self.anc_pendiente, self.anc_manual, self.anc_error = estado, False, ""
        self._fila("anc_solicitado", anc=estado, campo="motivo", valor=motivo)
        if self.control_anc is None:
            self._pedir_anc_manual(estado, "OpenSCQ30 no disponible")
            return
        self._en_hilo(lambda: self.control_anc.set_anc(estado),
                      lambda resultado: self._anc_cambiado(estado, resultado))
        self._dibujar_aviso_anc()

    def _anc_cambiado(self, estado, resultado):
        if isinstance(resultado, Exception):
            resultado = {"ok": False, "error": str(resultado), "leido": "", "latencia_s": "", "intentos": ""}
        detalle = "leido={} latencia_s={} intentos={}".format(
            resultado["leido"], resultado["latencia_s"], resultado["intentos"])
        if resultado["ok"]:
            self.anc_actual, self.anc_modo = estado, "automatico"
            self._fila("anc", anc=estado, anc_cambio="automatico", campo="openscq30", valor=detalle)
            if estado == self.anc_pendiente:
                self.anc_pendiente = None
        else:
            self._fila("anc_falla", anc=estado, campo="openscq30", valor="{} error={}".format(detalle, resultado["error"]))
            if estado == self.anc_pendiente:
                self._pedir_anc_manual(estado, resultado["error"])
                return
        self._refrescar_tras_anc()

    def _pedir_anc_manual(self, estado, error):
        self.anc_pendiente, self.anc_manual, self.anc_error = estado, True, error
        self._refrescar_tras_anc()

    def _confirmar_anc(self):
        if self.anc_pendiente is None:
            return
        self.anc_actual, self.anc_pendiente, self.anc_manual = self.anc_pendiente, None, False
        self.anc_modo = "manual"
        self._fila("anc", anc=self.anc_actual, anc_cambio="manual", campo="motivo", valor=self.anc_error)
        self._refrescar_tras_anc()

    def _refrescar_tras_anc(self):
        if not self.pasos or self.detenida:
            return
        tipo = self.pasos[self.indice]["tipo"]
        if tipo == "demo":
            self._actualizar_demo_label()
            self._dibujar_aviso_anc()
        elif tipo in ("transicion", "bloque_inicio"):
            self.show_step()
        else:
            self._dibujar_aviso_anc()

    def _dibujar_aviso_anc(self):
        """Zona del experimentador (letra chica, rincón inferior): solo si hay que cambiar a mano."""
        if hasattr(self, "aviso_anc") and self.aviso_anc.winfo_exists():
            self.aviso_anc.destroy()
        if not self.anc_manual or self.anc_pendiente is None:
            return
        self.aviso_anc = tk.Frame(self.footer, bg=FONDO)
        self.aviso_anc.pack(side="right", padx=(0, 16))
        tk.Label(self.aviso_anc, text=TEXTOS["anc_aviso_manual"].format(estado=self.anc_pendiente, error=self.anc_error),
                 bg=FONDO, fg=MUTED, font=self._font(8), wraplength=int(520 * self.scale_factor),
                 justify="right").pack(side="left", padx=(0, 6))
        ttk.Button(self.aviso_anc, text=TEXTOS["anc_hecho_manual"].format(estado=self.anc_pendiente),
                   style="Small.TButton", command=self._confirmar_anc).pack(side="left")

    # ------------------------------------------------------------ registro

    def _fila(self, tipo, **campos):
        if self.registro is not None:
            self.registro.fila(tipo, **campos)

    # ------------------------------------------------------------ navegación

    def _refresh_stepper(self):
        for child in self.stepper.winfo_children():
            child.destroy()
        actual = self.pasos[self.indice]["seccion"]
        for i, etiqueta in enumerate(TEXTOS["etapas"]):
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
        elif tipo not in ("oracion", "escenario", "transicion"):
            texto = TEXTOS["comenzar"] if tipo == "bienvenida" else TEXTOS["continuar"]
            ttk.Button(self.footer, text=texto, style="Primary.TButton", command=self.next_step,
                       state="normal" if self._puede_avanzar() else "disabled").pack(side="right")
        self._dibujar_ambiente()
        self._dibujar_aviso_anc()

    def _entrar_seccion(self, seccion):
        if seccion == self.seccion_actual:
            return
        if self.seccion_actual is not None:
            self._fila("evento", campo="fin", valor=SECCIONES[self.seccion_actual])
        self._fila("evento", campo="inicio", valor=SECCIONES[seccion])
        self.seccion_actual = seccion

    def _reproducir(self, zona, ruta, ganancia_db, **opciones):
        """Reproduce un archivo por una salida. Si el archivo no está, detiene la sesión."""
        if not os.path.isfile(ruta):
            raise ArchivoFaltante(ruta)
        self.salidas[zona].reproducir(ruta, ganancia_db, **opciones)

    def _detener_por_falta(self, ruta):
        for salida in self.salidas.values():
            salida.detener()
        relativa = os.path.relpath(ruta, self.base)
        self._fila("evento", campo="archivo_faltante", valor=relativa)
        self.detenida = True
        for frame in (self.content, self.footer):
            for child in frame.winfo_children():
                child.destroy()
        body = self._card()
        self._heading(body, "Falta un archivo de audio", 24)
        tk.Label(body, text=relativa, bg=SUPERFICIE, fg=ALERTA, font=self._font(14, "bold")).pack(pady=8)
        self._paragraph(body, "La sesión se detuvo. Copiá el archivo en la carpeta audio/ y volvé a empezar.", 14)
        ttk.Button(self.footer, text="Cerrar", style="Primary.TButton", command=self.close).pack(side="right")

    def _poner_ambiente(self, bloque):
        """Ruido ambiente continuo de todo el bloque (silencio: nada) por los monitores."""
        if bloque == self.ambiente_actual:
            return
        ruido = self.salidas["ruido"]
        ruido.detener("ambiente")
        d = ruido.dispositivo
        if bloque in GANANCIA_AMBIENTE:
            ruta = self.rutas[bloque]
            ganancia = self.cfg[GANANCIA_AMBIENTE[bloque]]
            self._reproducir("ruido", ruta, ganancia, loop=True, clave="ambiente")
            self.ambiente_info = {"bloque": bloque, "archivo": os.path.basename(ruta), "salida": d["nombre"],
                                  "ganancia": ganancia, "inicio": time.monotonic(), "nivel_registrado": False}
            self._fila("bloque", bloque=bloque, campo="ruido_ambiente",
                       valor="{} -> {} [{}] {} Hz, ganancia {:g} dB".format(
                           os.path.relpath(ruta, self.base), d["nombre"], d["api"], d["fs"], ganancia))
        elif bloque is not None:
            self.ambiente_info = {"bloque": bloque, "archivo": None, "salida": d["nombre"]}
            self._fila("bloque", bloque=bloque, campo="ruido_ambiente", valor="ninguno")
        else:
            self.ambiente_info = None
        self.ambiente_actual = bloque

    def _texto_ambiente(self):
        """Texto de la zona del experimentador sobre el ruido ambiente (y si es una alerta)."""
        info = self.ambiente_info
        nombre = ses.NOMBRE_BLOQUE[info["bloque"]]
        if info["archivo"] is None:
            return "Ruido ambiente · {}: ninguno (monitores: {})".format(nombre, info["salida"]), False
        nivel = self.salidas["ruido"].nivel_dbfs("ambiente")
        problema = self.salidas["ruido"].problema()
        if problema:
            medido, alerta = "SALIDA CORTADA ({})".format(problema), True
        elif nivel is None or nivel < -80:
            medido, alerta = "SIN SEÑAL", time.monotonic() - info["inicio"] > 1.0
        else:
            medido, alerta = "nivel enviado {} dBFS".format(formato_puntaje(round(nivel, 1))), False
        return "Ruido ambiente · {}: {} → monitores: {} · ganancia {:g} dB · {}".format(
            nombre, info["archivo"], info["salida"], info["ganancia"], medido), alerta

    def _dibujar_ambiente(self):
        if self.ambiente_info is None:
            self.ambiente_label = None
            return
        texto, alerta = self._texto_ambiente()
        self.ambiente_label = tk.Label(self.footer, text=texto, bg=FONDO, fg=ALERTA if alerta else MUTED,
                                       font=self._font(8, "bold" if alerta else "normal"), anchor="w",
                                       justify="left", wraplength=int(620 * self.scale_factor))
        self.ambiente_label.pack(side="left")

    def _tic_ambiente(self):
        """Cada 500 ms: actualiza el nivel del ruido ambiente en pantalla y, a los 2 s de empezar
        el bloque, deja en el CSV el nivel que realmente se está mandando a los monitores."""
        info = self.ambiente_info
        if info is not None:
            if self.ambiente_label is not None and self.ambiente_label.winfo_exists():
                texto, alerta = self._texto_ambiente()
                self.ambiente_label.configure(text=texto, fg=ALERTA if alerta else MUTED,
                                              font=self._font(8, "bold" if alerta else "normal"))
            if (info["archivo"] is not None and not info["nivel_registrado"]
                    and time.monotonic() - info["inicio"] >= 2.0):
                info["nivel_registrado"] = True
                nivel = self.salidas["ruido"].nivel_dbfs("ambiente")
                self._fila("bloque", bloque=info["bloque"], campo="ruido_ambiente_nivel_enviado_dbfs",
                           valor="sin señal" if nivel is None else "{:.1f}".format(nivel))
        if not self.sesion_terminada:
            self.after(500, self._tic_ambiente)

    def show_step(self):
        paso = self.pasos[self.indice]
        tipo = paso["tipo"]
        if self.detenida:
            return
        nuevo = self.indice != self.paso_dibujado
        # Se marca antes de preparar: si al preparar se vuelve a llamar a show_step (p. ej., el ANC
        # pasa a manual porque OpenSCQ30 no está), no se prepara dos veces ni entra en recursión.
        self.paso_dibujado = self.indice
        try:
            if nuevo:
                self._preparar_paso(paso)
        except ArchivoFaltante as falta:
            self._detener_por_falta(str(falta))
            return
        if self.indice != self.paso_dibujado:
            return  # al preparar ya se pasó a otra pantalla y se dibujó

        self._refresh_stepper()
        for child in self.content.winfo_children():
            child.destroy()
        body = self._card()
        getattr(self, "_pantalla_" + tipo)(body, paso)
        self._dibujar_footer()

    def _preparar_paso(self, paso):
        """Audio y ANC al entrar a una pantalla nueva."""
        tipo = paso["tipo"]
        self.salidas["auriculares"].detener()
        self._entrar_seccion(paso["seccion"])
        if "bloque" in paso:
            self._poner_ambiente(paso["bloque"])
        elif tipo == "cierre":
            self._poner_ambiente(None)
        if tipo == "transicion" or tipo == "bloque_inicio":
            if paso["anc"] != self.anc_actual or self.anc_pendiente is not None:
                self.cambiar_anc(paso["anc"], motivo=tipo)
            if tipo == "transicion":
                self.transicion_inicio = time.monotonic()
                indice = self.indice
                self.after(200, lambda: self._avanzar_transicion(indice))
        elif tipo == "a_inicio":
            self._iniciar_mssn()
        elif tipo == "a_fin":
            self.salidas["ruido"].detener("mssn")
            self._fila("evento", tarea="A", campo="mssn", valor="fin")
        elif tipo == "oracion":
            self.reproducciones = 0
            self.puntaje_sel = {"correctas": None, "menor": 0}
            indice = self.indice
            self.after(1000, lambda: self._reproducir_oracion(indice))
        elif tipo == "anclaje":
            self._reproducir("auriculares", self.ruta_fragmento[paso["musica"]],
                             self.cfg["nivel_anclaje_db"], loop=True, clave="musica")
            self._fila("anclaje", tarea="BC", bloque=paso["bloque"], posicion_bloque=paso["posicion"],
                       musica=paso["musica"], anc=self.anc_actual, ganancia_db=self.cfg["nivel_anclaje_db"],
                       campo="vez", valor=paso["vez"])
        elif tipo == "escenario":
            inicial = random.Random(self.cfg["participante"] * 100 + paso["numero"]).randint(1, PASOS_SLIDER)
            self.escenario = {"inicial": inicial, "paso": inicial, "confirmado": False,
                              "inicio": time.monotonic()}
            self._reproducir("auriculares", self.ruta_fragmento[paso["musica"]], paso_a_db(inicial),
                             loop=True, clave="musica")

    # ------------------------------------------------------------ pantallas

    def _pantalla_bienvenida(self, body, _paso):
        self._heading(body, TEXTOS["nombre_test"], 34)
        self._paragraph(body, TEXTOS["bienvenida_subtitulo"], 17)
        tk.Label(body, text=TEXTOS["duracion"].format(minutos=DURACION_MINUTOS), bg=SUPERFICIE, fg=MUTED,
                 font=self._font(13)).pack(pady=(4, 20))

    def _pantalla_instrucciones(self, body, _paso):
        self._heading(body, TEXTOS["instrucciones_titulo"])
        self._paragraph(body, TEXTOS["instrucciones"], 16, justify="left")

    def _pantalla_demo(self, body, _paso):
        if self.demo["estado"] == "terminada":
            # Al terminar se ve solo el cierre de la demostración, sin el texto anterior.
            self._heading(body, TEXTOS["demo_fin"])
            self._paragraph(body, TEXTOS["demo_fin_explicacion"])
            return
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
        try:
            self._reproducir("ruido", self.rutas["trafico"], self.cfg["ganancia_trafico_db"], loop=True,
                             clave="demo")
        except ArchivoFaltante as falta:
            self._detener_por_falta(str(falta))
            return
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
        if transcurrido >= DEMO_ANC_S and self.anc_pendiente is None:
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
        elif self.anc_pendiente is not None:
            self.demo_label.configure(text=TEXTOS["preparando"])
        else:
            restante = max(0, DEMO_ANC_S - int(time.monotonic() - self.demo["inicio"]))
            self.demo_label.configure(text=TEXTOS["demo_en_curso"].format(segundos=restante))

    def _pantalla_a_inicio(self, body, _paso):
        self._heading(body, TEXTOS["tarea_a_titulo"], 24)
        self._paragraph(body, TEXTOS["tarea_a_instrucciones"])

    def _iniciar_mssn(self):
        """El MSSN arranca solo al entrar a la Tarea A y suena hasta el final de la tarea."""
        if not self.mssn_iniciado:
            self._reproducir("ruido", self.rutas["mssn"], self.cfg["ganancia_mssn_db"], loop=True, clave="mssn")
            self.mssn_iniciado = True
            self._fila("evento", tarea="A", campo="mssn", valor="inicio")

    def _pantalla_transicion(self, body, paso):
        self._heading(body, TEXTOS["transicion_titulo"])
        if paso.get("practica"):
            self._paragraph(body, TEXTOS["transicion_practica"])
        self._paragraph(body, TEXTOS["preparando"])

    def _avanzar_transicion(self, indice):
        """La pausa avanza sola cuando el ANC quedó confirmado (y pasó el mínimo en pantalla)."""
        if self.detenida or indice != self.indice:
            return
        if self.anc_pendiente is None and time.monotonic() - self.transicion_inicio >= MIN_TRANSICION_S:
            self.indice += 1
            self.show_step()
            return
        self.after(200, lambda: self._avanzar_transicion(indice))

    def _pantalla_oracion(self, body, paso):
        titulo = TEXTOS["tarea_a_titulo"] + (" · " + TEXTOS["practica"] if paso["practica"] else "")
        self._heading(body, titulo, 22)
        tk.Label(body, text=TEXTOS["oracion"].format(numero=paso["oracion"], total=ses.ORACIONES_POR_LISTA),
                 bg=SUPERFICIE, fg=TEXTO, font=self._font(19, "bold")).pack(pady=(4, 6))
        tk.Label(body, text=TEXTOS["escucha_oracion"], bg=SUPERFICIE, fg=MUTED, font=self._font(14)).pack(
            pady=(0, 10))

        panel = tk.Frame(body, bg=PANEL, highlightbackground=BORDES, highlightthickness=1, padx=14, pady=8)
        panel.pack(fill="x", padx=20, pady=(4, 0))
        tk.Label(panel, text=TEXTOS["panel_experimentador"], bg=PANEL, fg=TEXTO,
                 font=self._font(11, "bold")).pack()
        archivo = os.path.basename(ses.ruta_oracion(self.base, paso["lista"], paso["oracion"]))
        datos = self.oraciones.get(archivo)
        rotulo = "Lista {} – Oración {}".format(paso["lista"], paso["oracion"])
        if datos:
            texto, claves, estado = datos
            caja = tk.Text(panel, height=2, wrap="word", bg=PANEL, fg=TEXTO, relief="flat",
                           font=self._font(17), highlightthickness=0)
            caja.insert("1.0", texto)
            caja.tag_configure("clave", font=self._font(17, "bold"), foreground=ACENTO_OSCURO, underline=True)
            caja.tag_configure("centro", justify="center")
            caja.tag_add("centro", "1.0", "end")
            # Cada palabra clave se marca en orden, a partir de la anterior (así una palabra
            # repetida o funcional se resalta solo donde corresponde).
            desde = 0
            for palabra in claves:
                m = re.compile(r"\b{}\b".format(re.escape(palabra)), re.IGNORECASE).search(texto, desde)
                if m:
                    caja.tag_add("clave", "1.0+{}c".format(m.start()), "1.0+{}c".format(m.end()))
                    desde = m.end()
            caja.configure(state="disabled")
            caja.pack(fill="x", pady=(4, 0))
            tk.Label(panel, text=rotulo + (" · claves provisorias" if estado == "provisorio" else ""),
                     bg=PANEL, fg=MUTED, font=self._font(9)).pack()
        else:
            tk.Label(panel, text=rotulo, bg=PANEL, fg=TEXTO, font=self._font(15, "bold")).pack(pady=(4, 0))
        habilitado = self.reproducciones > 0
        sel = self.puntaje_sel
        correctas = sel["correctas"]
        grilla = tk.Frame(panel, bg=PANEL)
        grilla.pack(pady=(8, 2))
        filas = (("correctas", TEXTOS["puntaje_correctas"], lambda n: habilitado),
                 ("menor", TEXTOS["puntaje_menor"],
                  lambda n: habilitado and correctas is not None and n <= PALABRAS_CLAVE - correctas))
        for r, (campo, rotulo, permitido) in enumerate(filas):
            tk.Label(grilla, text=rotulo, bg=PANEL, fg=TEXTO, font=self._font(12, "bold"), justify="right",
                     anchor="e").grid(row=r, column=0, sticky="e", padx=(0, 12), pady=4)
            for n in range(PALABRAS_CLAVE + 1):
                elegido = sel[campo] == n and (campo == "correctas" or correctas is not None)
                self._boton(grilla, str(n), lambda c=campo, v=n: self._elegir_puntaje(c, v),
                            bg=ACENTO if elegido else SUPERFICIE, fg="white" if elegido else ACENTO_OSCURO,
                            habilitado=permitido(n), font=self._font(17, "bold"), width=3,
                            pady=max(2, int(4 * self.scale_factor))).grid(row=r, column=n + 1, padx=4, pady=4)
        resultado = tk.Frame(panel, bg=PANEL)
        resultado.pack(pady=(4, 2))
        if correctas is None:
            tk.Label(resultado, text=TEXTOS["puntaje_pendiente"], bg=PANEL, fg=MUTED,
                     font=self._font(14, "bold")).pack(side="left", padx=(0, 20))
        else:
            tk.Label(resultado, text=TEXTOS["puntaje_oracion"].format(puntaje=formato_puntaje(self._puntaje())),
                     bg=PANEL, fg=ACENTO_OSCURO, font=self._font(28, "bold")).pack(side="left", padx=(0, 24))
        ttk.Button(resultado, text=TEXTOS["puntaje_confirmar"], style="Primary.TButton",
                   state="normal" if habilitado and correctas is not None else "disabled",
                   command=lambda: self._puntuar(paso)).pack(side="left")

    def _boton(self, padre, texto, comando, bg, fg, habilitado=True, font=None, **opciones):
        """Botón de color hecho con un Label (en macOS, tk.Button ignora el color de fondo)."""
        boton = tk.Label(padre, text=texto, bg=bg if habilitado else "#d9dddc", fg=fg if habilitado else "#9aa19f",
                         font=font, relief="solid", bd=1, cursor="hand2" if habilitado else "arrow", **opciones)
        if habilitado:
            boton.bind("<ButtonRelease-1>", lambda _e: comando())
        return boton

    def _elegir_puntaje(self, campo, valor):
        sel = self.puntaje_sel
        sel[campo] = valor
        if campo == "correctas":
            sel["menor"] = min(sel["menor"], PALABRAS_CLAVE - valor)
        self.show_step()

    def _puntaje(self):
        """Puntaje de la oración = correctas + 0,5 × con error menor (máximo 5)."""
        sel = self.puntaje_sel
        return min(PALABRAS_CLAVE, sel["correctas"] + 0.5 * sel["menor"])

    def _reproducir_oracion(self, indice):
        """Reproduce una sola vez la oración de la pantalla 'indice', si todavía es la actual."""
        if self.detenida or indice != self.indice or self.reproducciones > 0:
            return
        paso = self.pasos[indice]
        try:
            self._reproducir("auriculares", ses.ruta_oracion(self.base, paso["lista"], paso["oracion"]),
                             self.cfg["ganancia_voz_db"], clave="oracion", fundido=False,
                             pasa_altos_hz=PASA_ALTOS_VOZ_HZ)
        except ArchivoFaltante as falta:
            self._detener_por_falta(str(falta))
            return
        self.reproducciones = 1
        self.show_step()

    def _puntuar(self, paso):
        sel = self.puntaje_sel
        if sel["correctas"] is None:
            return
        self._fila("ensayo", tarea="A", anc=self.anc_actual, anc_cambio=self.anc_modo, lista=paso["lista"],
                   oracion=paso["oracion"], practica="si" if paso["practica"] else "no",
                   correctas=sel["correctas"], error_menor=sel["menor"],
                   puntaje=formato_puntaje(self._puntaje()), reproducciones=self.reproducciones)
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
        tk.Label(body, text=TEXTOS["anclaje_musica"], bg=ACENTO_CLARO, fg=ACENTO_OSCURO,
                 font=self._font(12, "bold"), padx=12, pady=6).pack(pady=16)

    def _pantalla_escenario(self, body, paso):
        estado = self.escenario
        if estado["confirmado"]:
            # Después de OK desaparece todo lo del volumen y queda solo el CCR.
            self._ccr(body, paso, habilitado=True)
            return
        self._heading(body, TEXTOS["escenario_titulo"], 24)
        self._paragraph(body, TEXTOS["nivel_escucha"], 14)

        area = tk.Frame(body, bg=SUPERFICIE)
        area.pack(fill="x", padx=8, pady=(6, 0))
        izquierda = tk.Frame(area, bg=SUPERFICIE)
        izquierda.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.slider = SliderGrande(izquierda, PASOS_SLIDER, estado["paso"], self._mover_slider,
                                   self.scale_factor, self._font(15, "bold"), self._font(10))
        self.slider.pack(fill="x")
        self.slider.focus_set()
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

        ttk.Button(body, text=TEXTOS["ok"], style="Primary.TButton", command=self._confirmar_nivel).pack(pady=(8, 6))
        self._ccr(body, paso, habilitado=False)

    def _ccr(self, body, paso, habilitado):
        """Escala de esfuerzo: en gris (bloqueada) antes de OK; después de OK, sola y más grande."""
        fondo = PANEL if habilitado else GRIS
        escala = 1.4 if habilitado else 1.0
        ccr = tk.Frame(body, bg=fondo, highlightbackground=BORDES, highlightthickness=1, padx=8, pady=6)
        ccr.pack(fill="x", padx=4, expand=habilitado)
        tk.Label(ccr, text=TEXTOS["esfuerzo"], bg=fondo, fg=TEXTO if habilitado else "#818987",
                 font=self._font(12 * escala, "bold"), wraplength=int(900 * self.scale_factor)).pack(
                     pady=(10 if habilitado else 0, 8 if habilitado else 4))
        fila = tk.Frame(ccr, bg=fondo)
        fila.pack(fill="x")
        for texto, valor in zip(TEXTOS["opciones_esfuerzo"], VALORES_CCR):
            tk.Button(fila, text=texto, wraplength=int((125 if habilitado else 106) * self.scale_factor), width=12,
                      height=4 if habilitado else 3, font=self._font(9 * escala, "bold"), relief="solid", bd=1,
                      bg=SUPERFICIE if habilitado else "#d9dddc", fg=TEXTO if habilitado else "#8a918f",
                      disabledforeground="#8a918f", activebackground=ACENTO_CLARO,
                      state="normal" if habilitado else "disabled",
                      command=lambda t=texto, v=valor: self._elegir_ccr(paso, t, v)).pack(
                          side="left", fill="both", expand=True, padx=2)

    def _mover_slider(self, paso):
        if paso == self.escenario["paso"]:
            return
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
                   musica=paso["musica"], anc=self.anc_actual, anc_cambio=self.anc_modo, paso_inicial=self.escenario["inicial"],
                   paso_final=final, ganancia_db="{:g}".format(paso_a_db(final)),
                   nivel_dba="" if nivel is None else "{:g}".format(nivel), ccr=valor, ccr_texto=texto,
                   campo="escenario", valor=paso["vez"])
        self.indice += 1
        self.show_step()

    def _pantalla_cierre(self, body, _paso):
        self._heading(body, TEXTOS["cierre_titulo"])
        encuesta = tk.Frame(body, bg=SUPERFICIE)
        encuesta.pack(pady=(4, 8))
        for pregunta, opciones, var in ((TEXTOS["fatiga"], TEXTOS["opciones_fatiga"], self.fatiga),
                                        (TEXTOS["comodidad"], TEXTOS["opciones_comodidad"], self.comodidad)):
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
        # (Antes también reprogramaba _revisar_resultados acá: cada 500 ms se sumaba otro bucle de
        # 100 ms que nunca terminaba y la interfaz se iba cargando a lo largo de la sesión.)
        self.after(500, self._vigilar_audio)

    def _reintentar_audio(self):
        for salida in self.salidas.values():
            salida.cerrar()
        try:
            audio.reiniciar_portaudio()
            dispositivos = audio.listar_salidas()
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
        if getattr(self, "registro", None) is not None:
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
