@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON_BIN=.venv\Scripts\python.exe"
) else (
  set "PYTHON_BIN=python"
)
"%PYTHON_BIN%" tools\prepare_demo.py
"%PYTHON_BIN%" server.py --port 5001 --server-id S2 --music .demo_music/S2 --peer http://127.0.0.1:5000 %*
pause
