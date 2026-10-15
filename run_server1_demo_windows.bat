@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON_BIN=.venv\Scripts\python.exe"
) else (
  set "PYTHON_BIN=python"
)
"%PYTHON_BIN%" tools\prepare_demo.py
"%PYTHON_BIN%" server.py --port 5000 --server-id S1 --music .demo_music/S1 --peer http://127.0.0.1:5001 %*
pause
