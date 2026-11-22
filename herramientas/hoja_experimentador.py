"""Planilla genérica imprimible para puntuar la Tarea A (una sola, igual para todos los participantes).

Genera planilla_oraciones.pdf (A4) con:
- encabezado "Participante N.º ____" y "Fecha ____";
- las listas 1, 2 y 3 ("Lista 3 – familiarización"), cada oración en su orden original, con su
  número, el texto completo con las 5 palabras clave en negrita y un recuadro "__ / 5";
- si alguna oración tiene estado "provisorio" en oraciones.csv, una marca chica PROVISORIO al pie.

No incluye el estado del ANC ni nada del orden de la sesión: se imprime una vez y se fotocopia.
Los textos y las palabras clave salen de audio/quicksin/oraciones.csv (columna "archivo"), igual
que en el panel del experimentador del test. Si no entra en una hoja, pasa a dos.

Uso:
    python herramientas/hoja_experimentador.py
    python herramientas/hoja_experimentador.py --salida C:\\ruta\\planilla_oraciones.pdf
"""

import argparse
import os
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from matplotlib.textpath import TextToPath  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from piloto import sesion as ses  # noqa: E402

# Orden de la planilla: las dos listas de la prueba y, al final, la de familiarización.
LISTAS = ((1, "Lista 1"), (2, "Lista 2"), (ses.LISTA_PRACTICA, "Lista 3 – familiarización"))

MM = 72 / 25.4                     # puntos por milímetro
ANCHO, ALTO = 210 * MM, 297 * MM   # A4 en puntos
MARGEN = 16 * MM
FUENTE = "DejaVu Sans"             # viene con matplotlib: tiene todos los acentos y la ñ
TAM_TEXTO = 14                     # pt
INTERLINEA = 1.35
TAM_TITULO = 15
COL_NUMERO = 9 * MM
RECUADRO_ANCHO, RECUADRO_ALTO = 27 * MM, 10 * MM
SEPARACION_ORACIONES = 2.2 * MM

_medidor = TextToPath()


def ancho(texto, negrita, tam=TAM_TEXTO):
    if not texto:
        return 0.0
    prop = FontProperties(family=FUENTE, weight="bold" if negrita else "normal", size=tam)
    # Los espacios al final no tienen ancho propio: se miden entre dos letras.
    w = _medidor.get_text_width_height_descent("x" + texto + "x", prop, ismath=False)[0]
    return w - _medidor.get_text_width_height_descent("xx", prop, ismath=False)[0]


def segmentos(texto, claves):
    """[(texto, negrita)] con las palabras clave en negrita."""
    partes, previo = [], 0
    for inicio, fin in ses.posiciones_claves(texto, claves):
        partes += [(texto[previo:inicio], False), (texto[inicio:fin], True)]
        previo = fin
    partes.append((texto[previo:], False))
    return [p for p in partes if p[0]]


def renglones(texto, claves, ancho_max):
    """Corta el texto en renglones que entran en ancho_max: [[(x, trozo, negrita), ...], ...]."""
    fichas = []   # palabras con su puntuación pegada, cada trozo con su estilo
    for trozo, negrita in segmentos(texto, claves):
        for parte in re.split(r"(\s+)", trozo):
            if not parte:
                continue
            if parte.isspace():
                fichas.append(None)                     # límite de palabra
            elif fichas and fichas[-1] is not None:
                fichas[-1].append((parte, negrita))     # misma palabra, otro estilo (p. ej. "grueso" + ".")
            else:
                fichas.append([(parte, negrita)])
    palabras = [f for f in fichas if f is not None]
    espacio = ancho(" ", False)
    lineas, actual, x = [], [], 0.0
    for palabra in palabras:
        w = sum(ancho(t, n) for t, n in palabra)
        if actual and x + espacio + w > ancho_max:
            lineas.append(actual)
            actual, x = [], 0.0
        if actual:
            x += espacio
        for t, n in palabra:
            actual.append((x, t, n))
            x += ancho(t, n)
    if actual:
        lineas.append(actual)
    return lineas


def bloques(oraciones):
    """Lista de bloques a dibujar en orden: ('titulo', texto) o ('oracion', n, renglones)."""
    ancho_texto = ANCHO - 2 * MARGEN - COL_NUMERO - RECUADRO_ANCHO - 6 * MM
    salida, faltan, provisorio = [], [], False
    for lista, titulo in LISTAS:
        salida.append(("titulo", titulo))
        for n in range(1, ses.ORACIONES_POR_LISTA + 1):
            archivo = os.path.basename(ses.ruta_oracion(RAIZ, lista, n))
            if archivo not in oraciones:
                faltan.append(archivo)
                continue
            texto, claves, estado = oraciones[archivo]
            provisorio = provisorio or estado == "provisorio"
            salida.append(("oracion", n, renglones(texto, claves, ancho_texto)))
    return salida, faltan, provisorio


def alto_bloque(bloque):
    if bloque[0] == "titulo":
        return 9.5 * MM
    lineas = len(bloque[2])
    return max(RECUADRO_ALTO, lineas * TAM_TEXTO * INTERLINEA) + SEPARACION_ORACIONES


def encabezado(ax, y):
    for x, rotulo, largo in ((MARGEN, "Participante N.º", 32 * MM), (ANCHO / 2 + 10 * MM, "Fecha", 45 * MM)):
        ax.text(x, y, rotulo, fontsize=TAM_TITULO, family=FUENTE, weight="bold", va="baseline")
        x_linea = x + ancho(rotulo + " ", True, TAM_TITULO) + 1 * MM
        ax.plot([x_linea, x_linea + largo], [y - 1.2 * MM] * 2, color="black", lw=1)
    return y - 11 * MM


def dibujar(ax, bloque, y):
    """Dibuja un bloque con su borde superior en y; devuelve el y siguiente."""
    if bloque[0] == "titulo":
        y_base = y - 7 * MM
        ax.text(MARGEN, y_base, bloque[1], fontsize=TAM_TITULO, family=FUENTE, weight="bold", va="baseline")
        ax.plot([MARGEN, ANCHO - MARGEN], [y_base - 2 * MM] * 2, color="black", lw=1.2)
        return y - alto_bloque(bloque)
    _, n, lineas = bloque
    paso = TAM_TEXTO * INTERLINEA
    alto_texto = len(lineas) * paso
    alto = max(RECUADRO_ALTO, alto_texto)
    centro = y - alto / 2
    y_linea = centro + alto_texto / 2 - paso / 2 - TAM_TEXTO * 0.35   # baseline del primer renglón
    ax.text(MARGEN, y_linea, "{}.".format(n), fontsize=TAM_TEXTO, family=FUENTE, weight="bold", va="baseline")
    x0 = MARGEN + COL_NUMERO
    for renglon in lineas:
        for x, trozo, negrita in renglon:
            ax.text(x0 + x, y_linea, trozo, fontsize=TAM_TEXTO, family=FUENTE,
                    weight="bold" if negrita else "normal", va="baseline")
        y_linea -= paso
    xr = ANCHO - MARGEN - RECUADRO_ANCHO
    ax.add_patch(Rectangle((xr, centro - RECUADRO_ALTO / 2), RECUADRO_ANCHO, RECUADRO_ALTO,
                           fill=False, lw=1.2, edgecolor="black"))
    ax.text(xr + RECUADRO_ANCHO - 2.5 * MM, centro, "/ 5", fontsize=TAM_TEXTO, family=FUENTE,
            ha="right", va="center")
    return y - alto - SEPARACION_ORACIONES


def nueva_hoja():
    fig = plt.figure(figsize=(ANCHO / 72, ALTO / 72))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, ANCHO)
    ax.set_ylim(0, ALTO)
    ax.axis("off")
    return fig, ax


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--salida", default=os.path.join(RAIZ, "herramientas", "salidas", "planilla_oraciones.pdf"))
    args = parser.parse_args()

    oraciones = ses.cargar_oraciones(RAIZ)
    if not oraciones:
        sys.exit("No se encontró audio/quicksin/oraciones.csv (o no tiene filas con texto).")
    lista_bloques, faltan, provisorio = bloques(oraciones)
    if faltan:
        sys.exit("Faltan en oraciones.csv: " + ", ".join(faltan))

    plt.rcParams["pdf.fonttype"] = 42   # TrueType embebida: el texto del PDF se puede buscar y copiar
    os.makedirs(os.path.dirname(os.path.abspath(args.salida)), exist_ok=True)
    pie = MARGEN + 1 * MM
    hojas = 0
    with PdfPages(args.salida) as pdf:
        fig, ax = nueva_hoja()
        y = encabezado(ax, ALTO - MARGEN - 4 * MM)
        for i, bloque in enumerate(lista_bloques):
            # Un título nunca queda solo al final de la hoja: se lleva con su primera oración.
            necesario = alto_bloque(bloque) + (alto_bloque(lista_bloques[i + 1]) if bloque[0] == "titulo" else 0)
            if y - necesario < pie:
                hojas += 1
                cerrar_hoja(fig, ax, pdf, provisorio)
                fig, ax = nueva_hoja()
                y = ALTO - MARGEN
            y = dibujar(ax, bloque, y)
        hojas += 1
        cerrar_hoja(fig, ax, pdf, provisorio)
    print("Planilla: {} ({} hoja{})".format(args.salida, hojas, "" if hojas == 1 else "s"))
    if provisorio:
        print("Atención: hay oraciones con estado provisorio en oraciones.csv (marca PROVISORIO al pie).")


def cerrar_hoja(fig, ax, pdf, provisorio):
    if provisorio:
        ax.text(ANCHO - MARGEN, MARGEN - 4 * MM, "PROVISORIO", fontsize=7, family=FUENTE, color="#555555",
                ha="right", va="baseline")
    pdf.savefig(fig)
    plt.close(fig)


if __name__ == "__main__":
    main()
