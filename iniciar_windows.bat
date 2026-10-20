@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    set PY=py
) else (
    set PY=python
)
if not exist .venv\Scripts\python.exe (
    echo Criando ambiente Python...
    %PY% -m venv .venv
    if errorlevel 1 goto erro
)
if not exist .env (
    copy /Y .env.example .env >nul
    echo Arquivo .env criado. Ajuste DEMO_SEED=true para carregar contas ficticias.
)
echo Instalando/verificando dependencias...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto erro
echo.
echo Abrindo Conecta Unis em http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
exit /b 0
:erro
echo Ocorreu uma falha. Confira se o Python 3.11+ esta instalado.
pause
exit /b 1
