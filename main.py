from __future__ import annotations

import ctypes
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import mss
import pyperclip
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
MIN_TRAINEDDATA_BYTES = 100_000


def app_dir() -> Path:
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


CONFIG_PATH = app_dir() / "config.json"


def set_windows_dpi_awareness() -> None:
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
            value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                config.update(value)
        except Exception as exc:
            print(f"[WARN] config.json 읽기 실패: {exc}")
    else:
        CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def find_tesseract() -> Optional[Path]:
    found = shutil.which("tesseract")
    if found:
        return Path(found).resolve()
    if os.name != "nt":
        return None
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    la = Path(os.environ.get("LOCALAPPDATA", ""))
    for path in (
        pf / "Tesseract-OCR" / "tesseract.exe",
        la / "Programs" / "Tesseract-OCR" / "tesseract.exe",
        la / "Microsoft" / "WinGet" / "Links" / "tesseract.exe",
        pf / "WinGet" / "Links" / "tesseract.exe",
    ):
        if path.exists():
            return path.resolve()
    return None


def win_subprocess_options() -> dict:
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}


@dataclass(frozen=True)
class TesseractRuntime:
    executable: Path
    tessdata_dir: Path
    languages: frozenset[str]


def check_traineddata(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"OCR 언어 파일이 없습니다: {path}")
    size = path.stat().st_size
    if size < MIN_TRAINEDDATA_BYTES:
        raise RuntimeError(f"OCR 언어 파일이 비정상적으로 작습니다: {path} ({size:,} bytes)")
    head = path.read_bytes()[:64].lower()
    if b"<html" in head or b"<!doctype" in head:
        raise RuntimeError(f"traineddata 대신 HTML이 저장되었습니다: {path}")
    print(f"[OK] {path.name}: {size:,} bytes")


def configure_tesseract(required_languages: list[str]) -> TesseractRuntime:
    executable = find_tesseract()
    if not executable:
        raise RuntimeError("Tesseract OCR을 찾을 수 없습니다. run.bat을 실행해 주세요.")

    tessdata_dir = (app_dir() / "tessdata").resolve()
    if not tessdata_dir.is_dir():
        raise RuntimeError(f"tessdata 폴더가 없습니다: {tessdata_dir}")
    for lang in required_languages:
        check_traineddata(tessdata_dir / f"{lang}.traineddata")

    # IMPORTANT: list args are used instead of a quoted config string.
    # This avoids the Windows path bug: "C:\\...\\tessdata"/kor.traineddata.
    result = subprocess.run(
        [str(executable), "--tessdata-dir", str(tessdata_dir), "--list-langs"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **win_subprocess_options(),
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Tesseract 언어 확인 실패:\n{result.stdout.strip()}")

    languages = frozenset(
        line.strip() for line in result.stdout.splitlines()
        if line.strip() and not line.lower().startswith("list of available languages")
    )
    missing = [lang for lang in required_languages if lang not in languages]
    if missing:
        raise RuntimeError(
            "Tesseract가 언어를 로드하지 못했습니다: " + ", ".join(missing)
            + f"\nTesseract: {executable}\ntessdata: {tessdata_dir}"
            + f"\n감지 언어: {', '.join(sorted(languages)) or '(없음)'}"
        )
    print(f"[OK] Tesseract: {executable}")
    print(f"[OK] tessdata: {tessdata_dir}")
    return TesseractRuntime(executable, tessdata_dir, languages)


def run_ocr(image: Image.Image, runtime: TesseractRuntime, language: str, psm: int) -> str:
    fd, temp_name = tempfile.mkstemp(prefix="ocr_capture_", suffix=".png")
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        image.save(temp_path, "PNG")
        cmd = [
            str(runtime.executable), str(temp_path), "stdout",
            "-l", language, "--oem", "1", "--psm", str(psm),
            "--tessdata-dir", str(runtime.tessdata_dir),
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **win_subprocess_options(),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Tesseract exit code {result.returncode}\n"
                f"Tesseract: {runtime.executable}\n"
                f"tessdata: {runtime.tessdata_dir}\n\n"
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


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
        ctypes.windll.user32.ShowWindow(hwnd, 9)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def clean_ocr_text(text: str) -> str:
    result, previous_empty = [], False
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.rstrip()
        empty = not line.strip()
        if not (empty and previous_empty):
            result.append(line)
        previous_empty = empty
    return "\n".join(result).strip()


def preprocess_image(image: Image.Image, config: dict) -> Image.Image:
    out = image.convert("L") if config.get("grayscale", True) else image
    scale = float(config.get("ocr_scale", 2.0))
    if scale > 1.0:
        out = out.resize((int(out.width * scale), int(out.height * scale)), Image.Resampling.LANCZOS)
    contrast = float(config.get("contrast", 1.0))
    if contrast != 1.0:
        out = ImageEnhance.Contrast(out).enhance(contrast)
    return out.filter(ImageFilter.SHARPEN) if config.get("sharpen", True) else out


@dataclass
class VirtualScreenCapture:
    image: Image.Image
    left: int
    top: int
    width: int
    height: int


def capture_virtual_screen() -> VirtualScreenCapture:
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        return VirtualScreenCapture(
            Image.frombytes("RGB", shot.size, bytes(shot.rgb)),
            int(monitor["left"]), int(monitor["top"]),
            int(monitor["width"]), int(monitor["height"]),
        )


class SelectionOverlay:
    def __init__(self, root, capture, on_selected, on_cancelled) -> None:
        self.capture, self.on_selected, self.on_cancelled = capture, on_selected, on_cancelled
        self.start_x = self.start_y = self.rect_id = None
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.geometry(f"{capture.width}x{capture.height}{capture.left:+d}{capture.top:+d}")
        self.canvas = tk.Canvas(self.window, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.photo = ImageTk.PhotoImage(capture.image)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        self.canvas.create_rectangle(14, 14, 405, 54, fill="black", outline="")
        self.canvas.create_text(28, 34, anchor=tk.W, fill="white", text="OCR 영역을 드래그하세요  |  ESC: 취소", font=("Malgun Gothic", 12, "bold"))
        self.canvas.bind("<ButtonPress-1>", self._down)
        self.canvas.bind("<B1-Motion>", self._move)
        self.canvas.bind("<ButtonRelease-1>", self._up)
        self.window.bind("<Escape>", self._cancel)
        self.window.focus_force()

    def _down(self, event) -> None:
        self.start_x, self.start_y = int(event.x), int(event.y)
        if self.rect_id is not None:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="#ff3b30", width=3)

    def _move(self, event) -> None:
        if self.rect_id is not None:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def _up(self, event) -> None:
        x1, x2 = sorted((max(0, self.start_x), min(self.capture.width, int(event.x))))
        y1, y2 = sorted((max(0, self.start_y), min(self.capture.height, int(event.y))))
        self.window.destroy()
        if x2 - x1 < 8 or y2 - y1 < 8:
            self.on_cancelled()
        else:
            self.on_selected(self.capture.image.crop((x1, y1, x2, y2)))

    def _cancel(self, _event=None) -> None:
        self.window.destroy()
        self.on_cancelled()


class OCRCaptureApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root, self.config = root, load_config()
        self.queue, self.controller = queue.Queue(), keyboard.Controller()
        self.hotkeys, self.busy, self.target_hwnd = None, False, None
        self.root.withdraw()
        langs = [x for x in str(self.config.get("language", "kor+eng")).split("+") if x]
        try:
            self.runtime = configure_tesseract(langs)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Tesseract 설정에 실패했습니다.\n\n{exc}")
            raise SystemExit(1)
        self._start_hotkeys()
        self.root.after(40, self._poll)
        print(f"{APP_NAME} 실행 중 / OCR: {self.config['hotkey']} / 종료: {self.config['quit_hotkey']}")

    def _start_hotkeys(self) -> None:
        self.hotkeys = keyboard.GlobalHotKeys({
            str(self.config.get("hotkey")): lambda: self.queue.put(("capture", None)),
            str(self.config.get("quit_hotkey")): lambda: self.queue.put(("quit", None)),
        })
        self.hotkeys.start()

    def _poll(self) -> None:
        try:
            while True:
                command, payload = self.queue.get_nowait()
                if command == "capture": self._begin_capture()
                elif command == "quit": self._quit(); return
                elif command == "ocr_done": self._finish_ocr(*payload)
                elif command == "ocr_error": self.busy = False; messagebox.showerror(APP_NAME, payload)
        except queue.Empty:
            pass
        self.root.after(40, self._poll)

    def _begin_capture(self) -> None:
        if self.busy: return
        self.busy, self.target_hwnd = True, get_foreground_window()
        try:
            capture = capture_virtual_screen()
        except Exception as exc:
            self.busy = False
            messagebox.showerror(APP_NAME, f"화면 캡처에 실패했습니다.\n\n{exc}")
            return
        SelectionOverlay(self.root, capture, self._start_ocr, self._cancel_capture)

    def _cancel_capture(self) -> None:
        self.busy = False
        restore_foreground_window(self.target_hwnd)

    def _start_ocr(self, image: Image.Image) -> None:
        threading.Thread(target=self._ocr_worker, args=(image, self.target_hwnd), daemon=True).start()

    def _ocr_worker(self, image: Image.Image, hwnd: Optional[int]) -> None:
        try:
            processed = preprocess_image(image, self.config)
            text = run_ocr(processed, self.runtime, str(self.config.get("language", "kor+eng")), int(self.config.get("psm", 6)))
            self.queue.put(("ocr_done", (clean_ocr_text(text), hwnd)))
        except Exception as exc:
            self.queue.put(("ocr_error", f"OCR 처리에 실패했습니다.\n\n{exc}"))

    def _finish_ocr(self, text: str, hwnd: Optional[int]) -> None:
        try:
            if not text:
                messagebox.showinfo(APP_NAME, "인식된 텍스트가 없습니다.")
                return
            pyperclip.copy(text)
            print("\n--- OCR RESULT ---\n" + text + "\n------------------")
            if self.config.get("auto_paste", True):
                restore_foreground_window(hwnd)
                self.root.after(max(0, int(self.config.get("paste_delay_ms", 250))), self._paste)
        finally:
            self.busy = False

    def _paste(self) -> None:
        try:
            with self.controller.pressed(keyboard.Key.ctrl):
                self.controller.press("v"); self.controller.release("v")
        except Exception as exc:
            messagebox.showwarning(APP_NAME, f"복사는 됐지만 자동 붙여넣기에 실패했습니다.\n\n{exc}")

    def _quit(self) -> None:
        if self.hotkeys: self.hotkeys.stop()
        self.root.quit(); self.root.destroy()


def run_self_check() -> int:
    config = load_config()
    langs = [x for x in str(config.get("language", "kor+eng")).split("+") if x]
    try:
        runtime = configure_tesseract(langs)
    except Exception as exc:
        print(f"[SELF-CHECK] FAILED\n{exc}")
        return 1
    print(f"[SELF-CHECK] OK\nTesseract: {runtime.executable}\ntessdata: {runtime.tessdata_dir}")
    return 0


def main() -> None:
    if "--check" in sys.argv:
        raise SystemExit(run_self_check())
    set_windows_dpi_awareness()
    root = tk.Tk(); root.title(APP_NAME)
    try:
        OCRCaptureApp(root); root.mainloop()
    except SystemExit:
        try: root.destroy()
        except Exception: pass
        raise


if __name__ == "__main__":
    main()
