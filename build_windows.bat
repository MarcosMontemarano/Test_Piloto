@echo off
setlocal

where py >nul 2>&1
if errorlevel 1 (
    echo No se encontro el launcher de Python "py".
    echo Instala Python 3 y vuelve a ejecutar este archivo.
    pause
    exit /b 1
)

echo Instalando dependencias (sounddevice, soundfile, numpy, scipy y PyInstaller)...
py -3 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo No se pudieron instalar las dependencias.
    pause
    exit /b 1
)

py -3 -m PyInstaller --noconfirm --onefile --windowed --name TestPiloto test.py
if errorlevel 1 (
    echo Fallo la generacion del ejecutable.
    pause
    exit /b 1
)

echo Ejecutable generado en dist\TestPiloto.exe
echo Copia la carpeta audio\ junto al .exe: el audio no va dentro del ejecutable.
pause
