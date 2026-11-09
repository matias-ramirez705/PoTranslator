@echo off
rem ============================================================
rem  PoTranslator - compilador del ejecutable (Windows)
rem
rem  Genera:  dist\PoTranslator.exe   (un unico archivo,
rem  no necesita Python para funcionar)
rem
rem  Requisito: Python 3.8+ instalado desde python.org
rem ============================================================
cd /d "%~dp0"

set PY=python
where py >nul 2>nul && set PY=py -3

echo [1/3] Comprobando Python...
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: no se encontro Python.
    echo Instalalo desde https://www.python.org/downloads/ y vuelve a intentarlo.
    pause
    exit /b 1
)

echo [2/3] Instalando/actualizando PyInstaller...
%PY% -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo ERROR: no se pudo instalar PyInstaller.
    pause
    exit /b 1
)

echo [3/3] Compilando PoTranslator.exe...
%PY% -m PyInstaller PoTranslator.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo ERROR: la compilacion fallo. Revisa los mensajes de arriba.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Listo. El ejecutable esta en:   dist\PoTranslator.exe
echo ============================================================
start "" explorer "dist"
pause
