import ctypes
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


# Configuración editable
NOMBRE_TEST = (
    "Impacto de auriculares ANC en la percepción musical y comprensión de letras "
    "en español rioplatense"
)
TITULO_VENTANA = "Piloto psicoacústico"
DURACION_MINUTOS = 16
FRAGMENTO_MUSICAL = "fragmento_musical.wav"

ESCENARIOS = [
    {"ambiente": "Sin ruido", "anc": "ON"},
    {"ambiente": "Sin ruido", "anc": "OFF"},
    {"ambiente": "Con ruido", "anc": "ON"},
    {"ambiente": "Con ruido", "anc": "OFF"},
]

TEXTOS = {
    "marca": "PILOTO PSICOACÚSTICO",
    "bienvenida_subtitulo": "Test psicoacústico · sesión piloto",
    "duracion": "Duración aproximada: {minutos} minutos",
    "comenzar": "Comenzar",
    "calibracion_titulo": "Calibración · Fase 0",
    "calibracion": "Antes de comenzar, el sistema fue calibrado con un acoplador acústico de prueba (ATF).",
    "continuar": "Continuar",
    "instrucciones_titulo": "Instrucciones generales",
    "instrucciones": "El test tiene 3 partes: repetir oraciones, ajustar el nivel de escucha en distintos escenarios y comparar el esfuerzo con un sonido de referencia.",
    "tarea_a_titulo": "Tarea A · Inteligibilidad",
    "tarea_a_instrucciones": "A continuación vas a escuchar oraciones de prueba. Repetí en voz alta lo que entiendas.",
    "ruido_fondo": "Reproducir ruido de fondo",
    "ruido_persistente": "(el ruido de fondo queda sonando durante toda la tarea)",
    "oracion": "Oración {numero} de 12",
    "reproducir_oracion": "Reproducir oración",
    "panel_experimentador": "Panel del experimentador (no para el oyente)",
    "tarea_a_completa": "Las 12 respuestas quedaron registradas.",
    "anclaje_titulo": "Anclaje: referencia {ambiente}",
    "anclaje_texto": "Vas a escuchar el mismo fragmento musical que en las pruebas siguientes, con la cancelación de ruido (ANC) apagada y {condicion_ruido}. Usalo como punto de comparación.",
    "reproducir_anclaje": "Reproducir anclaje",
    "ruido_apagado": "Ruido de fondo: apagado",
    "ruido_activo": "Ruido de fondo: activo",
    "nivel_escucha": "Ajustá el nivel de escucha (nivel ajustable en 20 pasos).",
    "nivel_seleccionado": "Nivel seleccionado: {nivel}",
    "menor_volumen": "Menor volumen",
    "mayor_volumen": "Mayor volumen",
    "ok": "OK",
    "esfuerzo": "Esfuerzo de escucha: compará con el anclaje",
    "comparado": "Comparado con la referencia {ambiente}",
    "anc": "ANC {estado}",
    "fragmento_auto": "Fragmento musical · reproducción automática simulada",
    "reproducido": "Reproducido",
    "siguiente": "Siguiente",
    "atras": "Atrás",
    "cierre_titulo": "¡Muchas gracias por participar!",
    "fatiga": "¿Sentiste fatiga auditiva durante el test?",
    "comodidad": "¿Los auriculares te resultaron incómodos de colocar?",
    "cierre_texto": "La sesión piloto ha finalizado. ¡Muchas gracias!",
    "finalizar": "Finalizar",
    "pantalla": "PANTALLA {actual:02d} / {total:02d}",
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
ETIQUETAS_STEPPER = (
    "Bienvenida", "Calibración", "Instrucciones", "Tarea A",
    "Anclaje\n(sin ruido)", "Escenario 1", "Escenario 2",
    "Anclaje\n(con ruido)", "Escenario 3", "Escenario 4", "Cierre",
)
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


def resource_path(relative_path):
    """Resuelve recursos junto al script o dentro del bundle de PyInstaller."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def log(message):
    """Escribe mensajes de placeholder sin fallar en ejecutables windowed."""
    try:
        print(message)
    except Exception:
        pass


def enable_windows_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


class PsychoacousticPilot(tk.Tk):
    def __init__(self):
        super().__init__()
        self._set_display_geometry()
        self.font_family = self._select_font_family()
        self.fullscreen = False
        self._bind_presentation_shortcuts()

        self.title(TITULO_VENTANA)
        self.configure(bg=FONDO)

        self.sentence_scores = []
        self.selected_level = tk.IntVar(value=50)
        self.scenario_levels = [50] * len(ESCENARIOS)
        self.scenario_confirmed = [False] * len(ESCENARIOS)
        self.scenario_effort = {}
        self.fatigue_answer = tk.StringVar(value="")
        self.comfort_answer = tk.StringVar(value="")
        self.steps = [
            "welcome", "calibration", "instructions", "task_a",
            "anchor_silent", "scenario_0", "scenario_1",
            "anchor_noise", "scenario_2", "scenario_3", "closing",
        ]
        self.current_index = 0
        self.rendered_step = None

        self._configure_styles()
        self._build_shell()
        self.show_step()

    def _set_display_geometry(self):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.scale_factor = min(1.6, max(0.8, min(screen_width / 1280, screen_height / 720)))
        width = min(screen_width, max(1000, int(screen_width * 0.9)))
        height = min(screen_height, max(650, int(screen_height * 0.9)))
        x_position = max(0, (screen_width - width) // 2)
        y_position = max(0, (screen_height - height) // 2)
        self.geometry("{}x{}+{}+{}".format(width, height, x_position, y_position))
        self.minsize(min(1000, screen_width), min(650, screen_height))
        self.resizable(True, True)

    def _select_font_family(self):
        installed = {family.casefold(): family for family in tkfont.families(self)}
        for preferred in FUENTES_PREFERIDAS:
            if preferred.casefold() in installed:
                return installed[preferred.casefold()]
        return tkfont.nametofont("TkDefaultFont").actual("family")

    def _font(self, size, weight="normal"):
        scaled_size = max(8, int(round(size * self.scale_factor)))
        return self.font_family, scaled_size, weight

    def _bind_presentation_shortcuts(self):
        self.bind_all("<Right>", self._shortcut_next)
        self.bind_all("<Left>", self._shortcut_back)
        self.bind_all("<F11>", self._toggle_fullscreen)
        self.bind_all("<Escape>", self._leave_fullscreen)

    def _shortcut_next(self, _event):
        if self._can_advance():
            self.next_step()
        return "break"

    def _shortcut_back(self, _event):
        self.previous_step()
        return "break"

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
        style.configure("Primary.TButton", font=self._font(13, "bold"),
                        padding=self._scaled_pair(22, 12))
        style.configure("Audio.TButton", font=self._font(16, "bold"),
                        padding=self._scaled_pair(22, 15))
        style.configure("Played.TButton", font=self._font(16, "bold"),
                        padding=self._scaled_pair(22, 15), foreground=ACENTO_OSCURO)

    def _scaled_pair(self, horizontal, vertical):
        return max(6, int(horizontal * self.scale_factor)), max(5, int(vertical * self.scale_factor))

    def _build_shell(self):
        outer_pad = max(16, int(34 * self.scale_factor))
        header = tk.Frame(self, bg=FONDO)
        header.pack(fill="x", padx=outer_pad, pady=(max(12, int(20 * self.scale_factor)), 6))

        top_line = tk.Frame(header, bg=FONDO)
        top_line.pack(fill="x")
        tk.Label(top_line, text=TEXTOS["marca"], bg=FONDO, fg=ACENTO_OSCURO,
                 font=self._font(10, "bold")).pack(side="left")
        tk.Label(top_line, text="{} minutos".format(DURACION_MINUTOS), bg=FONDO,
                 fg=MUTED, font=self._font(11)).pack(side="right")

        self.progress_text = tk.Label(header, bg=FONDO, fg=TEXTO,
                                      font=self._font(11, "bold"), anchor="w")
        self.progress_text.pack(fill="x", pady=(10, 6))
        self.stepper = tk.Frame(header, bg=FONDO)
        self.stepper.pack(fill="x")

        self.content = tk.Frame(self, bg=FONDO)
        self.content.pack(fill="both", expand=True, padx=outer_pad, pady=(10, 6))
        self.footer = tk.Frame(self, bg=FONDO)
        self.footer.pack(fill="x", padx=outer_pad, pady=(3, max(10, int(18 * self.scale_factor))))

    def _refresh_stepper(self):
        for child in self.stepper.winfo_children():
            child.destroy()

        for index, label in enumerate(ETIQUETAS_STEPPER):
            segment = tk.Frame(self.stepper, bg=FONDO)
            segment.pack(side="left", fill="x", expand=True,
                         padx=(0 if index == 0 else 4, 0))
            color = ACENTO if index <= self.current_index else BORDES
            tk.Frame(segment, bg=color, height=max(3, int(5 * self.scale_factor))).pack(
                fill="x", pady=(0, 4))
            tk.Label(segment, text=label, bg=FONDO,
                     fg=ACENTO_OSCURO if index == self.current_index else MUTED,
                     font=self._font(8, "bold" if index == self.current_index else "normal"),
                     anchor="center", justify="center",
                     wraplength=max(55, int(92 * self.scale_factor))).pack(fill="x")

        self.progress_text.configure(
            text=TEXTOS["pantalla"].format(actual=self.current_index + 1, total=len(self.steps))
        )

    def _card(self):
        card = tk.Frame(self.content, bg=SUPERFICIE, highlightbackground=BORDES,
                        highlightthickness=1)
        card.pack(fill="both", expand=True)
        body_pad = max(12, int(30 * self.scale_factor))
        body = tk.Frame(card, bg=SUPERFICIE)
        body.pack(expand=True, fill="both", padx=body_pad, pady=max(10, int(18 * self.scale_factor)))
        return body

    def _heading(self, parent, text, size=25):
        tk.Label(parent, text=text, bg=SUPERFICIE, fg=TEXTO,
                 font=self._font(size, "bold"), wraplength=int(900 * self.scale_factor),
                 justify="center").pack(pady=(0, max(6, int(10 * self.scale_factor))))

    def _paragraph(self, parent, text, size=16):
        tk.Label(parent, text=text, bg=SUPERFICIE, fg=MUTED,
                 font=self._font(size), wraplength=int(860 * self.scale_factor),
                 justify="center").pack(pady=max(3, int(5 * self.scale_factor)))

    def _audio_button(self, parent, label, message, large=False):
        style = "Audio.TButton" if large else "TButton"
        button = ttk.Button(parent, text=label, style=style)

        def play_placeholder():
            log(message)
            button.configure(text=TEXTOS["reproducido"], style="Played.TButton")

        button.configure(command=play_placeholder)
        return button

    def _can_advance(self):
        step = self.steps[self.current_index]
        if step == "task_a":
            return len(self.sentence_scores) == 12
        if step.startswith("scenario_"):
            return int(step.rsplit("_", 1)[1]) in self.scenario_effort
        return self.current_index < len(self.steps) - 1

    def _add_footer(self, first=False, last=False):
        for child in self.footer.winfo_children():
            child.destroy()

        step = self.steps[self.current_index]
        if first:
            ttk.Button(self.footer, text=TEXTOS["comenzar"], style="Primary.TButton",
                       command=self.next_step).pack(side="right")
            return
        if step == "calibration":
            ttk.Button(self.footer, text=TEXTOS["continuar"], style="Primary.TButton",
                       command=self.next_step).pack(side="right")
            return

        ttk.Button(self.footer, text=TEXTOS["atras"], command=self.previous_step).pack(side="left")
        if step.startswith("anchor_"):
            ttk.Button(self.footer, text=TEXTOS["continuar"], style="Primary.TButton",
                       command=self.next_step).pack(side="right")
            return
        if last:
            ttk.Button(self.footer, text=TEXTOS["finalizar"], style="Primary.TButton",
                       command=self.destroy).pack(side="right")
            return

        ttk.Button(self.footer, text=TEXTOS["siguiente"], style="Primary.TButton",
                   command=self.next_step,
                   state="normal" if self._can_advance() else "disabled").pack(side="right")

    def show_step(self):
        step = self.steps[self.current_index]
        if step.startswith("scenario_") and step != self.rendered_step:
            scenario_index = int(step.rsplit("_", 1)[1])
            fragment_path = resource_path(FRAGMENTO_MUSICAL)
            log("Reproducción automática simulada: {} ({})".format(
                os.path.basename(fragment_path), ESCENARIOS[scenario_index]["ambiente"]
            ))
        self.rendered_step = step

        self._refresh_stepper()
        for child in self.content.winfo_children():
            child.destroy()
        body = self._card()

        if step == "welcome":
            self._heading(body, NOMBRE_TEST, 34)
            self._paragraph(body, TEXTOS["bienvenida_subtitulo"], 17)
            tk.Label(body, text=TEXTOS["duracion"].format(minutos=DURACION_MINUTOS),
                     bg=SUPERFICIE, fg=MUTED, font=self._font(13)).pack(pady=(4, 20))
            self._add_footer(first=True)
        elif step == "calibration":
            self._heading(body, TEXTOS["calibracion_titulo"])
            self._paragraph(body, TEXTOS["calibracion"])
            self._add_footer()
        elif step == "instructions":
            self._heading(body, TEXTOS["instrucciones_titulo"])
            self._paragraph(body, TEXTOS["instrucciones"])
            self._add_footer()
        elif step == "task_a":
            self._heading(body, TEXTOS["tarea_a_titulo"], 24)
            self._paragraph(body, TEXTOS["tarea_a_instrucciones"], 16)
            if not self.sentence_scores:
                self._audio_button(body, TEXTOS["ruido_fondo"],
                                   "Reproducción simulada: ruido de fondo.", large=True).pack(
                                       pady=(12, 4))
                self._paragraph(body, TEXTOS["ruido_persistente"], 12)

            sentence_number = min(len(self.sentence_scores) + 1, 12)
            tk.Label(body, text=TEXTOS["oracion"].format(numero=sentence_number),
                     bg=SUPERFICIE, fg=TEXTO,
                     font=self._font(19, "bold")).pack(pady=(8, 6))
            if len(self.sentence_scores) < 12:
                self._audio_button(body, TEXTOS["reproducir_oracion"],
                                   "Reproducción simulada: oración {}.".format(sentence_number)).pack(
                                       pady=(0, 8))
                panel = tk.Frame(body, bg="#edf3f1", highlightbackground=BORDES,
                                 highlightthickness=1, padx=18, pady=9)
                panel.pack(fill="x", padx=40, pady=(2, 4))
                tk.Label(panel, text=TEXTOS["panel_experimentador"],
                         bg="#edf3f1", fg=TEXTO,
                         font=self._font(12, "bold")).pack(pady=(0, 5))
                scores = tk.Frame(panel, bg="#edf3f1")
                scores.pack()
                for score in range(4):
                    tk.Button(scores, text=str(score), width=5, height=2,
                              font=self._font(15, "bold"), bg=SUPERFICIE,
                              fg=ACENTO_OSCURO, activebackground=ACENTO_CLARO,
                              relief="solid", bd=1,
                              command=lambda value=score: self.record_sentence_score(value)
                              ).pack(side="left", padx=8)
            else:
                self._paragraph(body, TEXTOS["tarea_a_completa"], 14)
            self._add_footer()
        elif step.startswith("anchor_"):
            has_background_noise = step == "anchor_noise"
            environment_label = "con ruido" if has_background_noise else "sin ruido"
            noise_condition = "con ruido de fondo" if has_background_noise else "sin ruido de fondo"
            noise_status = TEXTOS["ruido_activo"] if has_background_noise else TEXTOS["ruido_apagado"]
            self._heading(body, TEXTOS["anclaje_titulo"].format(ambiente=environment_label))
            self._paragraph(body, TEXTOS["anclaje_texto"].format(
                condicion_ruido=noise_condition
            ))
            self._audio_button(body, TEXTOS["reproducir_anclaje"],
                               "Reproducción simulada del anclaje: {}.".format(
                                   os.path.basename(resource_path(FRAGMENTO_MUSICAL))
                               ), large=True).pack(pady=18)
            badges = tk.Frame(body, bg=SUPERFICIE)
            badges.pack(pady=7)
            tk.Label(badges, text="ANC OFF", bg=GRIS, fg="#505957",
                     font=self._font(11, "bold"), padx=12, pady=7).pack(side="left", padx=8)
            tk.Label(badges, text=noise_status, bg=SUPERFICIE,
                     fg=TEXTO, font=self._font(12, "bold")).pack(side="left", padx=8)
            self._add_footer()
        elif step.startswith("scenario_"):
            scenario_index = int(step.rsplit("_", 1)[1])
            scenario = ESCENARIOS[scenario_index]
            anc_is_on = scenario["anc"] == "ON"
            has_background_noise = scenario["ambiente"] == "Con ruido"
            self._heading(
                body,
                "Escenario {} de 4: {} + ANC {}".format(
                    scenario_index + 1, scenario["ambiente"], scenario["anc"]
                ),
                24,
            )
            tk.Label(body, text=TEXTOS["anc"].format(estado=scenario["anc"]),
                     bg=ACENTO if anc_is_on else GRIS,
                     fg="white" if anc_is_on else "#505957",
                     font=self._font(10, "bold"), padx=11, pady=5).pack(pady=(0, 3))
            noise_status = TEXTOS["ruido_activo"] if has_background_noise else TEXTOS["ruido_apagado"]
            tk.Label(body, text=noise_status, bg=SUPERFICIE, fg=MUTED,
                     font=self._font(10, "bold")).pack(pady=(0, 3))
            tk.Label(body, text=TEXTOS["fragmento_auto"],
                     bg=ACENTO_CLARO, fg=ACENTO_OSCURO,
                     font=self._font(11, "bold"), padx=12, pady=6).pack(pady=(0, 3))
            self._paragraph(body, TEXTOS["nivel_escucha"], 13)
            self.selected_level.set(self.scenario_levels[scenario_index])
            self.level_label = tk.Label(
                body,
                text=TEXTOS["nivel_seleccionado"].format(nivel=self.selected_level.get()),
                bg=SUPERFICIE, fg=ACENTO_OSCURO, font=self._font(12, "bold")
            )
            self.level_label.pack(pady=(0, 1))

            level_area = tk.Frame(body, bg=SUPERFICIE)
            level_area.pack(fill="x", padx=8)
            tk.Scale(level_area, from_=0, to=100, orient="horizontal", resolution=5,
                     showvalue=True, tickinterval=20, variable=self.selected_level,
                     command=lambda value: self._update_level(scenario_index, value),
                     length=int(600 * self.scale_factor), sliderlength=24,
                     troughcolor=ACENTO_CLARO, activebackground=ACENTO,
                     highlightthickness=0, bg=SUPERFICIE, bd=0,
                     font=self._font(9), label="").pack(
                         side="left", fill="x", expand=True, padx=(0, 8))
            self.level_canvas = tk.Canvas(
                level_area, width=int(160 * self.scale_factor),
                height=int(74 * self.scale_factor), bg=SUPERFICIE, highlightthickness=0
            )
            self.level_canvas.pack(side="right")
            self._draw_level_triangle(self.scenario_levels[scenario_index])

            endpoints = tk.Frame(body, bg=SUPERFICIE)
            endpoints.pack(fill="x", padx=(10, int(170 * self.scale_factor)), pady=(0, 2))
            tk.Label(endpoints, text=TEXTOS["menor_volumen"], bg=SUPERFICIE,
                     fg=MUTED, font=self._font(9)).pack(side="left")
            tk.Label(endpoints, text=TEXTOS["mayor_volumen"], bg=SUPERFICIE,
                     fg=MUTED, font=self._font(9)).pack(side="right")
            ttk.Button(body, text=TEXTOS["ok"], style="Primary.TButton",
                       command=lambda: self.confirm_level(scenario_index)).pack(pady=(1, 5))

            enabled = self.scenario_confirmed[scenario_index]
            ccr_bg = "#edf3f1" if enabled else GRIS
            ccr = tk.Frame(body, bg=ccr_bg, highlightbackground=BORDES,
                           highlightthickness=1, padx=8, pady=5)
            ccr.pack(fill="x", padx=4, pady=(1, 0))
            label_color = TEXTO if enabled else "#818987"
            tk.Label(ccr, text=TEXTOS["esfuerzo"], bg=ccr_bg, fg=label_color,
                     font=self._font(10, "bold")).pack(pady=(0, 2))
            reference_environment = "con ruido" if has_background_noise else "sin ruido"
            tk.Label(ccr, text=TEXTOS["comparado"].format(ambiente=reference_environment),
                     bg=ccr_bg, fg=label_color, font=self._font(9)).pack(pady=(0, 2))
            tk.Label(ccr, text=noise_status, bg=ccr_bg, fg=label_color,
                     font=self._font(9, "bold")).pack(pady=(0, 3))
            option_row = tk.Frame(ccr, bg=ccr_bg)
            option_row.pack(fill="x")
            for label, score in OPCIONES_CCR:
                tk.Button(option_row, text=label, wraplength=int(106 * self.scale_factor),
                          width=12, height=3, font=self._font(8, "bold"), relief="solid", bd=1,
                          bg=SUPERFICIE if enabled else "#d9dddc",
                          fg=TEXTO if enabled else "#8a918f",
                          disabledforeground="#8a918f",
                          state="normal" if enabled else "disabled",
                          command=lambda value=score: self.record_effort(scenario_index, value)
                          ).pack(side="left", fill="both", expand=True, padx=2)
            self._add_footer()
        else:
            self._heading(body, TEXTOS["cierre_titulo"])
            survey = tk.Frame(body, bg=SUPERFICIE)
            survey.pack(pady=(4, 8))
            tk.Label(survey, text=TEXTOS["fatiga"], bg=SUPERFICIE,
                     fg=TEXTO, font=self._font(13, "bold")).pack(pady=(0, 4))
            fatigue_row = tk.Frame(survey, bg=SUPERFICIE)
            fatigue_row.pack(pady=(0, 8))
            for answer in OPCIONES_FATIGA:
                ttk.Radiobutton(fatigue_row, text=answer, value=answer,
                                variable=self.fatigue_answer).pack(side="left", padx=10)
            tk.Label(survey, text=TEXTOS["comodidad"], bg=SUPERFICIE,
                     fg=TEXTO, font=self._font(13, "bold")).pack(pady=(3, 4))
            comfort_row = tk.Frame(survey, bg=SUPERFICIE)
            comfort_row.pack()
            for answer in OPCIONES_COMODIDAD:
                ttk.Radiobutton(comfort_row, text=answer, value=answer,
                                variable=self.comfort_answer).pack(side="left", padx=10)
            self._paragraph(body, TEXTOS["cierre_texto"], 15)
            self._add_footer(last=True)

    def _update_level(self, scenario_index, value):
        level = int(float(value))
        self.scenario_levels[scenario_index] = level
        self.level_label.configure(text=TEXTOS["nivel_seleccionado"].format(nivel=level))
        self._draw_level_triangle(level)

    def _draw_level_triangle(self, level):
        self.level_canvas.delete("all")
        canvas_width = int(150 * self.scale_factor)
        center = int(37 * self.scale_factor)
        height = max(4, int(58 * self.scale_factor * level / 100))
        self.level_canvas.create_polygon(
            6, center, canvas_width, center - height // 2,
            canvas_width, center + height // 2,
            fill=ACENTO, outline=ACENTO_OSCURO, width=2,
        )

    def record_sentence_score(self, score):
        if len(self.sentence_scores) < 12:
            self.sentence_scores.append(score)
            self.show_step()

    def confirm_level(self, scenario_index):
        self.scenario_confirmed[scenario_index] = True
        self.show_step()

    def record_effort(self, scenario_index, score):
        self.scenario_effort[scenario_index] = score
        self.current_index += 1
        self.show_step()

    def next_step(self):
        if self._can_advance() and self.current_index < len(self.steps) - 1:
            self.current_index += 1
            self.show_step()

    def previous_step(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.show_step()


if __name__ == "__main__":
    enable_windows_dpi_awareness()
    app = PsychoacousticPilot()
    app.mainloop()