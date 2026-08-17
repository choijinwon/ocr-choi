# OCR Capture

Windows 화면의 원하는 영역을 드래그해서 **한글/영문 OCR → 클립보드 복사 → 원래 입력창에 자동 붙여넣기**하는 Python 도구입니다.

## 동작

1. 입력할 프로그램(메모장, VS Code, 브라우저 등)에 커서를 둡니다.
2. `Ctrl + Shift + O`
3. OCR할 화면 영역을 마우스로 드래그합니다.
4. 선택 영역을 Tesseract로 OCR합니다.
5. 결과를 클립보드에 복사합니다.
6. 원래 활성 창으로 돌아간 뒤 `Ctrl + V`를 자동 전송합니다.

`ESC`는 캡처를 취소합니다.

종료 단축키는 `Ctrl + Shift + Q`입니다.

---

## 1. 준비

### Python

Python 3.10 이상 권장.

확인:

```bat
py --version
```

### Tesseract OCR

Windows에 Tesseract OCR 프로그램이 별도로 설치되어 있어야 합니다.

프로그램은 다음 순서로 자동 탐색합니다.

1. PATH에 등록된 `tesseract`
2. `C:\Program Files\Tesseract-OCR\tesseract.exe`
3. `%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe`

한글+영어를 사용하려면 Tesseract `tessdata`에 아래 데이터가 있어야 합니다.

```text
kor.traineddata
eng.traineddata
```

---

## 2. 가장 간단한 실행

프로젝트 폴더에서:

```bat
run.bat
```

처음 실행하면 `.venv`를 만들고 필요한 Python 패키지를 자동 설치합니다.

직접 실행하려면:

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

---

## 3. 설정

`config.json`:

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

### OCR만 복사하고 자동 붙여넣기는 하지 않기

```json
"auto_paste": false
```

### 한 줄 OCR

```json
"psm": 7
```

### 일반 문단 OCR

```json
"psm": 6
```

### 화면에 텍스트가 흩어져 있는 경우

```json
"psm": 11
```

### 작은 글자 인식률 개선

```json
"ocr_scale": 3.0
```

너무 크게 올리면 OCR 시간이 늘어날 수 있습니다.

---

## 4. EXE 만들기

먼저 `run.bat`을 한 번 실행해서 `.venv`를 만든 뒤:

```bat
build_exe.bat
```

완료되면:

```text
dist\OCRCapture.exe
```

가 생성됩니다.

> EXE로 빌드해도 Tesseract OCR 엔진 자체는 대상 PC에 설치되어 있어야 합니다.

---

## 5. 주요 구조

```text
Global Hotkey
    ↓
Windows foreground HWND 저장
    ↓
MSS로 Virtual Desktop 캡처
    ↓
Tkinter 영역 선택
    ↓
Pillow 전처리
    ↓
Tesseract OCR (kor+eng)
    ↓
Clipboard
    ↓
원래 HWND 복구
    ↓
Ctrl+V
```

OCR 작업은 별도 스레드에서 실행하여 Tkinter UI가 멈추지 않도록 했습니다.

---

## 6. 멀티 모니터 / 배율

Windows DPI Awareness를 활성화하고 MSS의 virtual monitor를 사용해 멀티 모니터를 한 번에 캡처합니다.

모니터가 좌측에 있어 좌표가 음수인 환경도 Tkinter virtual desktop geometry를 사용하도록 구현되어 있습니다.

특정 PC에서 Windows 디스플레이 배율 조합에 따라 선택 위치가 어긋나면 각 모니터 배율을 같은 값으로 맞춘 뒤 먼저 확인해 보세요.

---

## 7. 문제 해결

### `Tesseract OCR을 찾을 수 없습니다`

Tesseract를 설치하고 아래 파일이 있는지 확인합니다.

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

### `OCR 언어 데이터가 없습니다: kor`

아래 경로를 확인합니다.

```text
C:\Program Files\Tesseract-OCR\tessdata\kor.traineddata
```

### 자동 Ctrl+V가 안 되는 프로그램

Windows 권한 수준이 다른 프로그램(예: 관리자 권한으로 실행 중인 프로그램)에는 일반 권한 프로세스의 키 입력이 차단될 수 있습니다.

이 경우 OCR 결과는 클립보드에는 복사되어 있으므로 직접 `Ctrl+V`를 사용할 수 있습니다.

### OCR이 한 줄인데 결과가 이상함

`config.json`:

```json
"psm": 7
```

로 바꿔 보세요.

### 문단 OCR

```json
"psm": 6
```

가 기본값입니다.
