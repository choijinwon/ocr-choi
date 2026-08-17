@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo OCR Capture setup / launcher
echo ========================================

rem Make newly installed Tesseract discoverable in this process.
set "PATH=C:\Program Files\Tesseract-OCR;%LOCALAPPDATA%\Programs\Tesseract-OCR;%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"

rem ------------------------------------------------------------
rem 1. Ensure Tesseract OCR engine exists
rem ------------------------------------------------------------
where tesseract >nul 2>nul
if errorlevel 1 (
    if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" goto tesseract_ok
    if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" goto tesseract_ok

    echo.
    echo [SETUP] Tesseract OCR is not installed.
    echo [SETUP] Trying automatic installation with WinGet...

    where winget >nul 2>nul
    if errorlevel 1 (
        echo.
        echo [ERROR] WinGet is not available on this PC.
        echo Install "App Installer" from Microsoft Store, then run this file again.
        pause
        exit /b 1
    )

    winget install --id tesseract-ocr.tesseract -e --source winget --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [WARN] Primary Tesseract package failed. Trying fallback package...
        winget install --id UB-Mannheim.TesseractOCR -e --source winget --accept-package-agreements --accept-source-agreements
    )

    rem Refresh known install locations for this process.
    set "PATH=C:\Program Files\Tesseract-OCR;%LOCALAPPDATA%\Programs\Tesseract-OCR;%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"

    where tesseract >nul 2>nul
    if errorlevel 1 (
        if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" if not exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" (
            echo.
            echo [ERROR] Tesseract installation could not be confirmed.
            echo Close this window and run run.bat again after the installer finishes.
            pause
            exit /b 1
        )
    )
)

:tesseract_ok
echo [OK] Tesseract OCR engine detected.

rem ------------------------------------------------------------
rem 2. Download project-local Korean/English traineddata
rem ------------------------------------------------------------
if not exist "tessdata" mkdir "tessdata"

if not exist "tessdata\eng.traineddata" (
    echo [SETUP] Downloading English OCR data...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata' -OutFile '%CD%\tessdata\eng.traineddata'"
    if errorlevel 1 (
        echo [ERROR] Failed to download eng.traineddata.
        pause
        exit /b 1
    )
)

if not exist "tessdata\kor.traineddata" (
    echo [SETUP] Downloading Korean OCR data...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/kor.traineddata' -OutFile '%CD%\tessdata\kor.traineddata'"
    if errorlevel 1 (
        echo [ERROR] Failed to download kor.traineddata.
        pause
        exit /b 1
    )
)

echo [OK] Korean/English OCR data ready.

rem ------------------------------------------------------------
rem 3. Python virtual environment / dependencies
rem ------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [SETUP] Creating virtual environment...
    py -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create Python virtual environment.
        pause
        exit /b 1
    )
)

echo [SETUP] Installing Python dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto pip_error

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pip_error

rem ------------------------------------------------------------
rem 4. Start app
rem ------------------------------------------------------------
echo.
echo [START] OCR Capture
".venv\Scripts\python.exe" main.py
exit /b %errorlevel%

:pip_error
echo.
echo [ERROR] Python dependency installation failed.
pause
exit /b 1
