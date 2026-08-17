@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo OCR Capture setup / launcher
echo ========================================

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
        echo Install Microsoft App Installer, then run this file again.
        pause
        exit /b 1
    )

    winget install --id tesseract-ocr.tesseract -e --source winget --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [WARN] Primary Tesseract package failed. Trying fallback package...
        winget install --id UB-Mannheim.TesseractOCR -e --source winget --accept-package-agreements --accept-source-agreements
    )

    set "PATH=C:\Program Files\Tesseract-OCR;%LOCALAPPDATA%\Programs\Tesseract-OCR;%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"

    where tesseract >nul 2>nul
    if errorlevel 1 (
        if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" if not exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" (
            echo.
            echo [ERROR] Tesseract installation could not be confirmed.
            echo Close this window and run run.bat again after installation finishes.
            pause
            exit /b 1
        )
    )
)

:tesseract_ok
echo [OK] Tesseract OCR engine detected.

rem ------------------------------------------------------------
rem 2. Prepare and validate Korean/English traineddata
rem ------------------------------------------------------------
if not exist "tessdata" mkdir "tessdata"

echo [SETUP] Checking OCR language data...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue';" ^
  "$files=@{" ^
  "'eng'='https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata';" ^
  "'kor'='https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/kor.traineddata'" ^
  "};" ^
  "foreach($lang in $files.Keys){" ^
  "$path=Join-Path '%CD%\tessdata' ($lang + '.traineddata');" ^
  "$download=$true;" ^
  "if(Test-Path $path){ if((Get-Item $path).Length -ge 100000){ $download=$false } };" ^
  "if($download){ Write-Host ('[SETUP] Downloading ' + $lang + '.traineddata ...'); Invoke-WebRequest -UseBasicParsing $files[$lang] -OutFile $path };" ^
  "if(!(Test-Path $path) -or (Get-Item $path).Length -lt 100000){ throw ('Invalid traineddata: ' + $path) };" ^
  "Write-Host ('[OK] ' + $lang + ': ' + (Get-Item $path).Length + ' bytes')" ^
  "}"
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to prepare OCR language data.
    echo Delete the tessdata folder and run this file again.
    pause
    exit /b 1
)

rem ------------------------------------------------------------
rem 3. Python virtual environment / dependencies
rem ------------------------------------------------------------
where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python launcher ^(py.exe^) was not found.
    echo Install Python 3.10 or newer and run this file again.
    pause
    exit /b 1
)

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
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pip_error

rem ------------------------------------------------------------
rem 4. Self-check before GUI start
rem ------------------------------------------------------------
echo.
echo [CHECK] Validating Tesseract and language packs...
".venv\Scripts\python.exe" main.py --check
if errorlevel 1 (
    echo.
    echo [ERROR] OCR self-check failed. See the messages above.
    pause
    exit /b 1
)

rem ------------------------------------------------------------
rem 5. Start app
rem ------------------------------------------------------------
echo.
echo [START] OCR Capture
echo Hotkey: Ctrl + Shift + O
".venv\Scripts\python.exe" main.py
exit /b %errorlevel%

:pip_error
echo.
echo [ERROR] Python dependency installation failed.
pause
exit /b 1
