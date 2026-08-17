@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment...
    py -m venv .venv
)

echo [2/3] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo [3/3] Starting OCR Capture...
".venv\Scripts\python.exe" main.py
