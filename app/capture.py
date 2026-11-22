"""Najde běžící Dead by Daylight, jeho okno a pořídí snímek obrazovky.

Nic se nečte z paměti hry a nic se do hry nevkládá: jen se zjistí, jestli
proces běží, kde je jeho okno, a vyfotí se obrazovka (stejně jako to dělá
OBS nebo Discord při streamování).
"""

from __future__ import annotations

import logging
import re
import sys
import time
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("dbd")

GAME_EXE = re.compile(r"^DeadByDaylight.*-Shipping\.exe$", re.IGNORECASE)
IS_WINDOWS = sys.platform == "win32"


# ------------------------------------------------------------------ process
@dataclass(frozen=True)
class GameProcess:
    pids: frozenset[int]
    started_at: float


def game_alive(game: GameProcess) -> bool:
    """Levná kontrola, že už nalezená hra pořád běží (bez procházení všech procesů)."""
    import psutil

    try:
        return any(psutil.pid_exists(pid) and GAME_EXE.match(psutil.Process(pid).name() or "")
                   for pid in game.pids)
    except Exception:
        return False


def find_game() -> GameProcess | None:
    import psutil

    pids, started = set(), None
    for p in psutil.process_iter(["name", "create_time"]):
        try:
            name = p.info.get("name") or ""
            if GAME_EXE.match(name):
                pids.add(p.pid)
                ct = p.info.get("create_time")
                if ct and (started is None or ct < started):
                    started = ct
        except Exception:
            continue
    if not pids:
        return None
    return GameProcess(frozenset(pids), started or time.time())


# ------------------------------------------------------------------ window
@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    rect: tuple[int, int, int, int]  # klientská oblast v souřadnicích obrazovky (l, t, r, b)
    minimized: bool


if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetClientRect.restype = wintypes.BOOL
    _user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    _user32.ClientToScreen.restype = wintypes.BOOL
    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.MonitorFromWindow.restype = ctypes.c_void_p
    _MONITOR_DEFAULTTONEAREST = 2


def enable_dpi_awareness() -> None:
    """Aby souřadnice oken byly ve skutečných pixelech i při zvětšení 125 % apod."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _pid_of(hwnd) -> int:
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def find_window(pids: frozenset[int]) -> GameWindow | None:
    """Největší viditelné okno patřící hře."""
    if not IS_WINDOWS or not pids:
        return None
    found: list[tuple[int, int, tuple[int, int, int, int], bool]] = []

    def callback(hwnd, _lparam):
        try:
            if not _user32.IsWindowVisible(hwnd) or _pid_of(hwnd) not in pids:
                return True
            minimized = bool(_user32.IsIconic(hwnd))
            rc = wintypes.RECT()
            if not _user32.GetClientRect(hwnd, ctypes.byref(rc)):
                return True
            w, h = rc.right - rc.left, rc.bottom - rc.top
            pt = wintypes.POINT(0, 0)
            _user32.ClientToScreen(hwnd, ctypes.byref(pt))
            area = w * h if not minimized else 0
            if minimized or (w >= 640 and h >= 360):
                found.append((area, int(hwnd or 0), (pt.x, pt.y, pt.x + w, pt.y + h), minimized))
        except Exception:
            pass
        return True

    try:
        _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    except Exception as e:  # pragma: no cover - jen Windows
        log.debug("EnumWindows selhalo: %s", e)
        return None
    if not found:
        return None
    area, hwnd, rect, minimized = max(found, key=lambda f: f[0])
    return GameWindow(hwnd, rect, minimized)


def game_hidden(win: GameWindow | None, pids: frozenset[int]) -> bool:
    """True, když hru právě není vidět (je minimalizovaná nebo je přes ni
    jiné okno na stejném monitoru). Pak se nic nevyhodnocuje a stav se drží."""
    if not IS_WINDOWS or win is None:
        return False
    if win.minimized:
        return True
    try:
        fg = _user32.GetForegroundWindow()
        if not fg or _pid_of(fg) in pids:
            return False
        mon_fg = _user32.MonitorFromWindow(fg, _MONITOR_DEFAULTTONEAREST)
        mon_game = _user32.MonitorFromWindow(win.hwnd, _MONITOR_DEFAULTTONEAREST)
        return bool(mon_fg) and mon_fg == mon_game
    except Exception:
        return False


# ------------------------------------------------------------------ grabbing
def to_16x9(frame: np.ndarray) -> np.ndarray:
    """DbD kreslí UI do oblasti 16:9; u jiných poměrů stran odřízne okraje."""
    h, w = frame.shape[:2]
    if h <= 0 or w <= 0:
        return frame
    target_w = round(h * 16 / 9)
    if w > target_w + 4:
        x = (w - target_w) // 2
        return frame[:, x:x + target_w]
    target_h = round(w * 9 / 16)
    if h > target_h + 4:
        y = (h - target_h) // 2
        return frame[y:y + target_h]
    return frame


class Grabber:
    """Snímání obrazovky: DXGI (dxcam) když je k dispozici, jinak mss.

    mode: 'auto' | 'dxcam' | 'mss'
    """

    def __init__(self, mode: str = "auto") -> None:
        self.mode = mode if mode in ("auto", "dxcam", "mss") else "auto"
        self._cam = None
        self._cam_failed = False
        self._sct = None
        self._black = 0
        self._warned_black = False
        self._same = 0
        self._last_sig: bytes | None = None
        self.backend = None

    # -- dxcam (jen primární monitor)
    def _dxcam(self):
        if self._cam is not None or self._cam_failed or not IS_WINDOWS:
            return self._cam
        try:
            import dxcam

            for dev in range(4):
                try:
                    cam = dxcam.create(device_idx=dev, output_color="BGR")
                except Exception:
                    cam = None
                if cam is not None:
                    self._cam = cam
                    break
        except Exception as e:
            log.debug("dxcam nejde použít: %s", e)
        if self._cam is None:
            self._cam_failed = True
        return self._cam

    def _grab_dxcam(self, rect):
        cam = self._dxcam()
        if cam is None:
            return None
        w, h = int(cam.width), int(cam.height)
        if rect is None:
            region = (0, 0, w, h)
        else:
            l, t, r, b = rect
            if l < 0 or t < 0 or r > w or b > h:
                return None  # okno není na primárním monitoru -> mss
            region = (l, t, r, b)
        for _ in range(10):
            frame = cam.grab(region=region, new_frame_only=False)
            if frame is not None:
                return np.ascontiguousarray(frame[:, :, :3])
            time.sleep(0.03)
        return None

    # -- mss (libovolný monitor / okno)
    def _grab_mss(self, rect):
        if self._sct is None:
            import mss

            self._sct = mss.mss()
        if rect is None:
            mon = self._sct.monitors[1]
        else:
            l, t, r, b = rect
            mon = {"left": int(l), "top": int(t), "width": int(r - l), "height": int(b - t)}
        shot = self._sct.grab(mon)
        return np.ascontiguousarray(np.asarray(shot)[:, :, :3])

    def grab(self, rect: tuple[int, int, int, int] | None) -> np.ndarray | None:
        order = {"auto": ("dxcam", "mss"), "dxcam": ("dxcam", "mss"), "mss": ("mss",)}[self.mode]
        frame = None
        for backend in order:
            try:
                frame = self._grab_dxcam(rect) if backend == "dxcam" else self._grab_mss(rect)
            except Exception as e:
                log.debug("Snímání přes %s selhalo: %s", backend, e)
                frame = None
            if frame is not None and frame.size:
                if backend != self.backend:
                    log.info("Snímání obrazovky: %s", backend)
                    self.backend = backend
                break
        if frame is None:
            return None
        # Pořád úplně stejný snímek = snímání "zamrzlo" (hra se pořád hýbe, i v menu).
        sig = frame[::32, ::32].tobytes()
        if sig == self._last_sig:
            self._same += 1
            if self._same >= 20 and self.backend == "dxcam":
                log.warning("Snímání přes dxcam vrací pořád stejný obraz, přepínám na mss.")
                self.mode, self._same = "mss", 0
        else:
            self._same = 0
        self._last_sig = sig
        # Úplně černý obraz = snímání nevidí hru (typicky exkluzivní fullscreen).
        # (Krátce černo je normální: přechody, načítání. Proto až po ~40 s.)
        if float(frame[::8, ::8].mean()) < 3.0:
            self._black += 1
            if self._black >= 30:
                self._black = 0
                if not self._warned_black:
                    self._warned_black = True
                    log.warning("Snímek obrazovky je pořád černý. Přepni ve hře Display Mode na "
                                "'Windowed Fullscreen' (okno přes celou obrazovku).")
                if self.backend == "dxcam":
                    self.mode = "mss"
                elif not self._cam_failed and IS_WINDOWS:
                    self.mode = "dxcam"
        else:
            self._black = 0
        return frame

    def close(self) -> None:
        try:
            if self._cam is not None:
                self._cam.release()
        except Exception:
            pass
        try:
            if self._sct is not None:
                self._sct.close()
        except Exception:
            pass
