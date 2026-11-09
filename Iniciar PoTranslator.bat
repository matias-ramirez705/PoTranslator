@echo off
rem ============================================================
rem  PoTranslator - iniciador (Windows)
rem ============================================================
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 po_translator.py
) else (
    python po_translator.py
)
if errorlevel 1 (
    echo.
    echo Hubo un error al iniciar PoTranslator.
    echo Verifica que Python 3 este instalado desde python.org
    echo y que la opcion "tcl/tk and IDLE" este marcada.
    echo.
    pause
)
