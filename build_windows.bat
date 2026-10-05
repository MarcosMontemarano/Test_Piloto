@echo off
setlocal

where py >nul 2>&1
if errorlevel 1 (
    echo No se encontro el launcher de Python "py".
    echo Instala Python 3 y vuelve a ejecutar este archivo.
    pause
    exit /b 1
)

py -3 -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller para generar el ejecutable...
    py -3 -m pip install pyinstaller
    if errorlevel 1 (
        echo No se pudo instalar PyInstaller.
        pause
        exit /b 1
    )
)

py -3 -m PyInstaller --onefile --windowed --name TestPiloto test.py
if errorlevel 1 (
    echo Fallo la generacion del ejecutable.
    pause
    exit /b 1
)

echo Ejecutable generado en dist\TestPiloto.exe
pause
