#!/bin/sh
set -eu

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "No se encontro Python 3. Instala Python 3 y vuelve a ejecutar este script." >&2
    exit 1
fi

echo "Instalando dependencias (sounddevice, soundfile, numpy, scipy y PyInstaller)..."
"$PYTHON" -m pip install -r requirements.txt pyinstaller

# En macOS se genera dist/TestPiloto.app (--onedir: PyInstaller desaconseja
# --onefile para bundles .app); en Linux, un único ejecutable.
if [ "$(uname)" = "Darwin" ]; then
    MODO="--onedir"
else
    MODO="--onefile"
fi

"$PYTHON" -m PyInstaller --noconfirm "$MODO" --windowed --name TestPiloto test.py

echo "Build completado. Revisa la carpeta dist/ para encontrar el resultado."
echo "El audio y los textos no van dentro del ejecutable: copia la carpeta audio/ y"
echo "textos_participante.json junto al ejecutable"
echo "(en macOS, junto a TestPiloto.app)."
