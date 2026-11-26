@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Instale o Python 3.10 ou mais recente e extraia este ZIP inteiro.
  pause
  exit /b 1
)
if not exist ".teste-venv\Scripts\python.exe" py -3 -m venv .teste-venv
if errorlevel 1 goto falha
".teste-venv\Scripts\python.exe" -c "import reportlab" >nul 2>nul
if errorlevel 1 ".teste-venv\Scripts\python.exe" -m pip install -r requisitos-teste.txt
if errorlevel 1 goto falha
".teste-venv\Scripts\python.exe" servidor.py servir --teste --abrir
goto fim
:falha
echo Nao foi possivel iniciar o teste. Confira a mensagem acima.
:fim
pause
