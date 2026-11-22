"""Tabla de contrabalanceo por participante, calculada con la misma función que usa el test.

Genera resultados/tabla_contrabalanceo.csv con, para cada participante: orden de los bloques,
fragmento musical de cada ambiente, estado del ANC del primer escenario de cada bloque, orden
del ANC en la Tarea A y lista asignada a cada estado. Los fragmentos se leen de audio/musica/
(*_eq.wav), igual que en la sesión.

Uso:
    python herramientas/tabla_contrabalanceo.py
    python herramientas/tabla_contrabalanceo.py --hasta 36
"""

import argparse
import csv
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from piloto import sesion as ses  # noqa: E402


def filas(hasta, fragmentos):
    for p in range(1, hasta + 1):
        cb = ses.contrabalanceo(p, fragmentos)
        fila = {"participante": p, "orden_bloques": " > ".join(cb["orden_bloques"])}
        fila.update({"musica_" + b: cb["musica"][b] for b in ses.BLOQUES})
        fila.update({"anc_primer_escenario_" + b: cb["anc_bloques"][b][0] for b in ses.BLOQUES})
        fila["tarea_A_orden_anc"] = " > ".join(cb["anc_tarea_a"])
        fila["tarea_A_lista_OFF"] = cb["listas"]["OFF"]
        fila["tarea_A_lista_ON"] = cb["listas"]["ON"]
        yield fila


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hasta", type=int, default=24, help="último participante (por defecto 24)")
    parser.add_argument("--salida", default=os.path.join(RAIZ, ses.CARPETA_RESULTADOS, "tabla_contrabalanceo.csv"))
    args = parser.parse_args()

    rutas, _ = ses.buscar_archivos(RAIZ)
    if len(rutas["musica"]) != 3:
        sys.exit("Tiene que haber exactamente 3 fragmentos en audio/musica/*_eq.wav (hay {}).".format(
            len(rutas["musica"])))
    fragmentos = [ses.nombre_fragmento(r) for r in rutas["musica"]]
    datos = list(filas(args.hasta, fragmentos))
    os.makedirs(os.path.dirname(os.path.abspath(args.salida)), exist_ok=True)
    with open(args.salida, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=list(datos[0]))
        escritor.writeheader()
        escritor.writerows(datos)
    print("Tabla: {} ({} participantes)".format(args.salida, len(datos)))


if __name__ == "__main__":
    main()
