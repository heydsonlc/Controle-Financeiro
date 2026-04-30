@echo off
setlocal

echo ========================================
echo   Sistema de Controle Financeiro
echo   Iniciando servidor...
echo ========================================
echo.

cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
set "VENV_PYTHON=%PROJECT_DIR%\venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo ERRO: Ambiente virtual nao encontrado em:
    echo %VENV_PYTHON%
    echo.
    echo Crie o ambiente com:
    echo python -m venv venv
    echo venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM Chamar o Python do venv diretamente evita problemas quando o projeto muda de pasta/unidade.
"%VENV_PYTHON%" backend\app.py

pause
