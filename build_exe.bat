@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found.
    echo Run run.bat once first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt

if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

".venv\Scripts\pyinstaller.exe" ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name OCRCapture ^
  main.py

echo.
echo Build complete:
echo %CD%\dist\OCRCapture.exe
echo.
echo NOTE: Tesseract OCR still needs to be installed on the target PC.
pause
