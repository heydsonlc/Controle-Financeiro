@echo off
echo ========================================
echo   Sistema de Controle Financeiro
echo   Iniciando servidor...
echo ========================================
echo.

cd /d "%~dp0"

REM Ativar ambiente virtual e iniciar servidor
call venv\Scripts\activate.bat
python backend\app.py

pause
