from __future__ import annotations

import ctypes
import json
import os
import queue
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import mss
import pyperclip
import pytesseract
import tkinter as tk
from PIL import Image, ImageEnhance, ImageFilter, ImageTk
from pynput import keyboard
from tkinter import messagebox


APP_NAME = "OCR Capture"
DEFAULT_CONFIG = {
    "hotkey": "<ctrl>+<shift>+o",
    "quit_hotkey": "<ctrl>+<shift>+q",
    "language": "kor+eng",
    "psm": 6,
    "ocr_scale": 2.0,
    "auto_paste": True,
    "paste_delay_ms": 250,
    "grayscale": True,
    "contrast": 1.4,
    "sharpen": True,
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_PATH = app_dir() / "config.json"


def set_windows_dpi_awareness() -> None:
    """Keep Tk/MSS coordinates aligned on high-DPI Windows displays."""
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            user_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(user_config, dict):
                config.update(user_config)
        except Exception as exc:
            print(f"[WARN] config.json을 읽지 못했습니다: {exc}")
    else:
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return config


def find_tesseract() -> Optional[str]:
    """Find tesseract.exe from PATH or common Windows install locations."""
    from_path = shutil.which("tesseract")
    if from_path:
        return from_path

    candidates = []
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidates.extend(
            [
                Path(program_files) / "Tesseract-OCR" / "tesseract.exe",
                Path(local_app_data) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
                Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "tesseract.exe",
                Path(program_files) / "WinGet" / "Links" / "tesseract.exe",
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def get_foreground_window() -> Optional[int]:
    if os.name != "nt":
        return None
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        return int(hwnd) if hwnd else None
    except Exception:
        return None


def restore_foreground_window(hwnd: Optional[int]) -> None:
    if os.name != "nt" or not hwnd:
        return
    try:
        SW_RESTORE = 9
        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def clean_ocr_text(text: str) -> str:
    """Trim line-end noise while preserving OCR line breaks."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]

    cleaned = []
    previous_empty = False
    for line in lines:
        empty = not line.strip()
        if empty and previous_empty:
            continue
        cleaned.append(line)
        previous_empty = empty

    return "\n".join(cleaned).strip()


def preprocess_image(image: Image.Image, config: dict) -> Image.Image:
    processed = image

    if config.get("grayscale", True):
        processed = processed.convert("L")

    scale = float(config.get("ocr_scale", 2.0))
    if scale > 1.0:
        width, height = processed.size
        processed = processed.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.LANCZOS,
        )

    contrast = float(config.get("contrast", 1.0))
    if contrast != 1.0:
        processed = ImageEnhance.Contrast(processed).enhance(contrast)

    if config.get("sharpen", True):
        processed = processed.filter(ImageFilter.SHARPEN)

    return processed


@dataclass
class VirtualScreenCapture:
    image: Image.Image
    left: int
    top: int
    width: int
    height: int


def capture_virtual_screen() -> VirtualScreenCapture:
    """Capture the entire virtual desktop, including all monitors."""
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, bytes(shot.rgb))
        return VirtualScreenCapture(
            image=image,
            left=int(monitor["left"]),
            top=int(monitor["top"]),
            width=int(monitor["width"]),
            height=int(monitor["height"]),
        )


class SelectionOverlay:
    def __init__(self, root: tk.Tk, capture: VirtualScreenCapture, on_selected, on_cancelled) -> None:
        self.root = root
        self.capture = capture
        self.on_selected = on_selected
        self.on_cancelled = on_cancelled
        self.start_x: Optional[int] = None
        self.start_y: Optional[int] = None
        self.rect_id: Optional[int] = None

        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        geometry = f"{capture.width}x{capture.height}{capture.left:+d}{capture.top:+d}"
        self.window.geometry(geometry)

        self.canvas = tk.Canvas(self.window, width=capture.width, height=capture.height, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.photo = ImageTk.PhotoImage(capture.image)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        self.canvas.create_rectangle(14, 14, 405, 54, fill="black", outline="")
        self.canvas.create_text(28, 34, anchor=tk.W, fill="white", text="OCR 영역을 드래그하세요  |  ESC: 취소", font=("Malgun Gothic", 12, "bold"))

        self.canvas.bind("<ButtonPress-1>", self._mouse_down)
        self.canvas.bind("<B1-Motion>", self._mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self._mouse_up)
        self.window.bind("<Escape>", self._cancel)
        self.window.focus_force()

    def _mouse_down(self, event) -> None:
        self.start_x = max(0, min(int(event.x), self.capture.width))
        self.start_y = max(0, min(int(event.y), self.capture.height))
        if self.rect_id is not None:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="#ff3b30", width=3)

    def _mouse_move(self, event) -> None:
        if self.start_x is None or self.start_y is None or self.rect_id is None:
            return
        x = max(0, min(int(event.x), self.capture.width))
        y = max(0, min(int(event.y), self.capture.height))
        self.canvas.coords(self.rect_id, self.start_x, self.start_y, x, y)

    def _mouse_up(self, event) -> None:
        if self.start_x is None or self.start_y is None:
            return
        end_x = max(0, min(int(event.x), self.capture.width))
        end_y = max(0, min(int(event.y), self.capture.height))
        x1, x2 = sorted((self.start_x, end_x))
        y1, y2 = sorted((self.start_y, end_y))
        self.window.destroy()
        if (x2 - x1) < 8 or (y2 - y1) < 8:
            self.on_cancelled()
            return
        cropped = self.capture.image.crop((x1, y1, x2, y2))
        self.on_selected(cropped)

    def _cancel(self, _event=None) -> None:
        self.window.destroy()
        self.on_cancelled()


class OCRCaptureApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.config = load_config()
        self.queue: queue.Queue = queue.Queue()
        self.controller = keyboard.Controller()
        self.hotkeys = None
        self.busy = False
        self.target_hwnd: Optional[int] = None
        self.tessdata_config = ""

        self.root.withdraw()
        self._configure_tesseract()
        self._start_hotkeys()
        self.root.after(40, self._poll_queue)

        print(f"{APP_NAME} 실행 중")
        print(f"OCR 캡처: {self.config['hotkey']}")
        print(f"종료: {self.config['quit_hotkey']}")
        print("모드:", "OCR 후 자동 붙여넣기" if self.config.get("auto_paste", True) else "OCR 후 클립보드 복사만")

    def _configure_tesseract(self) -> None:
        executable = find_tesseract()
        if not executable:
            messagebox.showerror(
                APP_NAME,
                "Tesseract OCR을 찾을 수 없습니다.\n\n"
                "run.bat을 실행하면 자동 설치를 시도합니다.\n"
                r"기본 검색 경로: C:\Program Files\Tesseract-OCR\tesseract.exe",
            )
            raise SystemExit(1)

        pytesseract.pytesseract.tesseract_cmd = executable

        local_tessdata = app_dir() / "tessdata"
        if local_tessdata.is_dir():
            self.tessdata_config = f'--tessdata-dir "{local_tessdata}"'

        try:
            languages = set(pytesseract.get_languages(config=self.tessdata_config))
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Tesseract 실행에 실패했습니다.\n\n{exc}")
            raise SystemExit(1)

        requested = str(self.config.get("language", "kor+eng")).split("+")
        missing = [lang for lang in requested if lang and lang not in languages]
        if missing:
            messagebox.showerror(
                APP_NAME,
                "OCR 언어 데이터가 없습니다: " + ", ".join(missing) + "\n\nrun.bat을 다시 실행해 주세요.",
            )
            raise SystemExit(1)

    def _start_hotkeys(self) -> None:
        hotkey = str(self.config.get("hotkey", "<ctrl>+<shift>+o"))
        quit_hotkey = str(self.config.get("quit_hotkey", "<ctrl>+<shift>+q"))
        self.hotkeys = keyboard.GlobalHotKeys({hotkey: lambda: self.queue.put(("capture", None)), quit_hotkey: lambda: self.queue.put(("quit", None))})
        self.hotkeys.start()

    def _poll_queue(self) -> None:
        try:
            while True:
                command, payload = self.queue.get_nowait()
                if command == "capture":
                    self._begin_capture()
                elif command == "quit":
                    self._quit()
                    return
                elif command == "ocr_done":
                    text, hwnd = payload
                    self._finish_ocr(text, hwnd)
                elif command == "ocr_error":
                    self.busy = False
                    messagebox.showerror(APP_NAME, payload)
        except queue.Empty:
            pass
        self.root.after(40, self._poll_queue)

    def _begin_capture(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.target_hwnd = get_foreground_window()
        try:
            capture = capture_virtual_screen()
        except Exception as exc:
            self.busy = False
            messagebox.showerror(APP_NAME, f"화면 캡처에 실패했습니다.\n\n{exc}")
            return
        SelectionOverlay(self.root, capture, on_selected=self._start_ocr, on_cancelled=self._capture_cancelled)

    def _capture_cancelled(self) -> None:
        self.busy = False
        restore_foreground_window(self.target_hwnd)

    def _start_ocr(self, image: Image.Image) -> None:
        worker = threading.Thread(target=self._ocr_worker, args=(image, self.target_hwnd), daemon=True)
        worker.start()

    def _ocr_worker(self, image: Image.Image, hwnd: Optional[int]) -> None:
        try:
            processed = preprocess_image(image, self.config)
            language = str(self.config.get("language", "kor+eng"))
            psm = int(self.config.get("psm", 6))
            ocr_config = f"--oem 1 --psm {psm}"
            if self.tessdata_config:
                ocr_config += f" {self.tessdata_config}"
            text = pytesseract.image_to_string(processed, lang=language, config=ocr_config)
            text = clean_ocr_text(text)
            self.queue.put(("ocr_done", (text, hwnd)))
        except Exception as exc:
            self.queue.put(("ocr_error", f"OCR 처리에 실패했습니다.\n\n{exc}"))

    def _finish_ocr(self, text: str, hwnd: Optional[int]) -> None:
        try:
            if not text:
                messagebox.showinfo(APP_NAME, "인식된 텍스트가 없습니다.")
                return
            pyperclip.copy(text)
            print("\n--- OCR RESULT ---")
            print(text)
            print("------------------")
            if self.config.get("auto_paste", True):
                restore_foreground_window(hwnd)
                delay_ms = max(0, int(self.config.get("paste_delay_ms", 250)))
                self.root.after(delay_ms, self._send_paste)
        finally:
            self.busy = False

    def _send_paste(self) -> None:
        try:
            with self.controller.pressed(keyboard.Key.ctrl):
                self.controller.press("v")
                self.controller.release("v")
        except Exception as exc:
            messagebox.showwarning(APP_NAME, "클립보드 복사는 완료됐지만 자동 붙여넣기에 실패했습니다.\n\n" + str(exc))

    def _quit(self) -> None:
        try:
            if self.hotkeys:
                self.hotkeys.stop()
        finally:
            self.root.quit()
            self.root.destroy()


def main() -> None:
    set_windows_dpi_awareness()
    root = tk.Tk()
    root.title(APP_NAME)
    try:
        OCRCaptureApp(root)
        root.mainloop()
    except SystemExit:
        try:
            root.destroy()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
