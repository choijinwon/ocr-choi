# OCR Capture

Windows 화면의 원하는 영역을 드래그해서 **한글/영문 OCR → 클립보드 복사 → 원래 입력창에 자동 붙여넣기**하는 Python 도구입니다.

## 빠른 실행

1. 저장소를 내려받습니다.
2. `run.bat`을 실행합니다.
3. `Ctrl + Shift + O`를 누릅니다.
4. OCR할 영역을 드래그합니다.
5. 결과가 클립보드에 복사되고, 설정에 따라 자동으로 붙여넣어집니다.

종료 단축키는 `Ctrl + Shift + Q`입니다.

## Tesseract

`run.bat`은 Tesseract OCR 엔진을 확인하고, 없으면 WinGet으로 설치를 시도합니다. 또한 프로젝트의 `tessdata` 폴더에 `kor.traineddata`와 `eng.traineddata`를 준비합니다.

Windows에서는 `TESSDATA_PREFIX` 값에 따옴표를 포함하면 경로 인식이 깨질 수 있으므로, 앱은 프로젝트의 `tessdata` 실제 경로를 따옴표 없이 직접 설정합니다.

## 설정

`config.json`에서 단축키, OCR 언어, PSM, 자동 붙여넣기 등을 조정할 수 있습니다.

```json
{
  "hotkey": "<ctrl>+<shift>+o",
  "quit_hotkey": "<ctrl>+<shift>+q",
  "language": "kor+eng",
  "psm": 6,
  "ocr_scale": 2.0,
  "auto_paste": true,
  "paste_delay_ms": 250,
  "grayscale": true,
  "contrast": 1.4,
  "sharpen": true
}
```

## 문제 해결

### `Tesseract OCR을 찾을 수 없습니다`

`run.bat`을 다시 실행하세요. Tesseract 자동 설치를 시도합니다.

### `Error opening data file ... kor.traineddata`

최신 `main.py`는 프로젝트의 `tessdata` 경로를 `TESSDATA_PREFIX`에 따옴표 없이 설정합니다. 저장소를 최신 상태로 받은 뒤 `run.bat`을 다시 실행하세요.

### 자동 붙여넣기 대신 복사만 하기

`config.json`에서 아래처럼 설정합니다.

```json
"auto_paste": false
```
