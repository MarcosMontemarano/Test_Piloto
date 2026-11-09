"""Prueba de confiabilidad del control del ANC: N ciclos ON/OFF con verificación.

Cada ciclo pide ON y después OFF con piloto.anc_control.set_anc (lectura de verificación y un
reintento). Guarda herramientas/salidas/prueba_anc_<fecha>.csv con cada cambio (hora, pedido,
leído, intentos, latencia, error) y muestra al final la tasa de éxito y la latencia media y
máxima. Los auriculares quedan en OFF (modo normal).

La app gráfica de OpenSCQ30 tiene que estar cerrada.

Uso:
    python herramientas/prueba_anc.py
    python herramientas/prueba_anc.py --ciclos 10 --pausa 0.5 --cli ruta\\openscq30-cli.exe
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from piloto import anc_control  # noqa: E402

SALIDAS = os.path.join(RAIZ, "herramientas", "salidas")
COLUMNAS = ["ciclo", "hora", "pedido", "leido", "ok", "intentos", "latencia_s", "error"]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ciclos", type=int, default=50)
    parser.add_argument("--pausa", type=float, default=1.0, help="segundos entre cambios (default 1)")
    parser.add_argument("--cli", help="ruta a openscq30-cli (si no, se busca)")
    parser.add_argument("--mac", help="MAC de los auriculares (si no, la de paired-devices list)")
    args = parser.parse_args()

    cli = anc_control.buscar_cli(RAIZ, args.cli)
    if not cli:
        raise SystemExit("No se encontró la CLI de OpenSCQ30 (pasala con --cli).")
    control = anc_control.ControlANC(cli, args.mac)
    try:
        print("CLI: {}\nAuriculares: {}\nEstado inicial: {}".format(cli, control._mac(), control.get_anc()))
    except anc_control.ErrorANC as error:
        raise SystemExit("No se pudo leer el ANC: {}".format(error))

    os.makedirs(SALIDAS, exist_ok=True)
    ruta = os.path.join(SALIDAS, "prueba_anc_{}.csv".format(datetime.now().strftime("%Y%m%d-%H%M%S")))
    filas = []
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        escritor.writeheader()
        for ciclo in range(1, args.ciclos + 1):
            for estado in ("ON", "OFF"):
                fila = dict(control.set_anc(estado), ciclo=ciclo)
                escritor.writerow(fila)
                f.flush()
                filas.append(fila)
                print("ciclo {:>3} {:<3} -> {:<13} {:>6.2f} s  intentos {}{}".format(
                    ciclo, estado, fila["leido"] or "-", fila["latencia_s"], fila["intentos"],
                    "" if fila["ok"] else "  FALLA: " + fila["error"]))
                time.sleep(args.pausa)

    exitos = [f for f in filas if f["ok"]]
    latencias = [f["latencia_s"] for f in exitos]
    print("\nCambios: {}  exitosos: {} ({:.1f} %)  con reintento: {}  fallidos: {}".format(
        len(filas), len(exitos), 100 * len(exitos) / len(filas), sum(f["intentos"] > 1 for f in exitos),
        len(filas) - len(exitos)))
    if latencias:
        print("Latencia (cambio + verificación): media {:.2f} s, máxima {:.2f} s".format(
            sum(latencias) / len(latencias), max(latencias)))
    print("CSV: {}".format(ruta))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
