#!/bin/sh
set -eu

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "No se encontro Python 3. Instala Python 3 y vuelve a ejecutar este script." >&2
    exit 1
fi

if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
    echo "Instalando PyInstaller para generar la aplicacion..."
    "$PYTHON" -m pip install pyinstaller
fi

"$PYTHON" -m PyInstaller --onefile --windowed --name TestPiloto test.py

echo "Build completado. Revisa la carpeta dist/ para encontrar el resultado."
