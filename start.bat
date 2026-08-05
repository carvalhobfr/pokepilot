@echo off
REM PokeAI 2026 - clique duplo para rodar no Windows.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo [ERRO] Python nao encontrado.
  echo Instale o Python 3.11 ou superior em https://www.python.org/downloads/
  echo Marque "Add python.exe to PATH" durante a instalacao.
  echo.
  pause
  exit /b 1
)

python start.py %*
if errorlevel 1 pause
