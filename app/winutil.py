"""Drobnosti pro Windows: jen jedna spuštěná kopie programu, signál "ukonči se"
pro program běžící na pozadí a okénko se zprávou. Mimo Windows (testy) se
chovají rozumně, ale nic z toho nedělají doopravdy."""

from __future__ import annotations

import os
import sys

IS_WINDOWS = os.name == "nt"
MUTEX_NAME = "Local\\DbDRichPresence"
QUIT_EVENT_NAME = "Local\\DbDRichPresenceQuit"
SHOW_EVENT_NAME = "Local\\DbDRichPresenceShow"
WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.CreateMutexW.restype = wintypes.HANDLE
    _k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.CreateEventW.restype = wintypes.HANDLE
    _k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.OpenEventW.restype = wintypes.HANDLE
    _k32.SetEvent.argtypes = [wintypes.HANDLE]
    _k32.SetEvent.restype = wintypes.BOOL
    _k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.WaitForSingleObject.restype = wintypes.DWORD
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL


class SingleInstance:
    """Drží pojmenovaný mutex, dokud program běží. `ok` = jsme jediná kopie."""

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self.handle = None
        self.ok = True
        if IS_WINDOWS:
            h = _k32.CreateMutexW(None, False, name)
            err = ctypes.get_last_error()
            if not h:
                return          # mutex nejde vytvořit -> radši poběžíme, než abychom nic neukázali
            if err == ERROR_ALREADY_EXISTS:
                _k32.CloseHandle(h)
                self.ok = False
            else:
                self.handle = h
        else:
            self._lock_file()

    def _lock_file(self) -> None:
        try:
            import fcntl
            import tempfile

            self._f = open(os.path.join(tempfile.gettempdir(), "dbd_rich_presence.lock"), "w")
            fcntl.flock(self._f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.ok = False
        except Exception:
            pass

    def release(self) -> None:
        if IS_WINDOWS and self.handle:
            _k32.CloseHandle(self.handle)
            self.handle = None


class QuitSignal:
    """Pojmenovaná událost: `DbD-Rich-Presence.exe --ukoncit` (nebo main.py --ukoncit)
    jí řekne běžícímu programu na pozadí, ať se ukončí."""

    def __init__(self, name: str = QUIT_EVENT_NAME) -> None:
        self.handle = _k32.CreateEventW(None, True, False, name) if IS_WINDOWS else None
        self._flag = False

    def is_set(self) -> bool:
        if self._flag:
            return True
        if self.handle:
            self._flag = _k32.WaitForSingleObject(self.handle, 0) == WAIT_OBJECT_0
        return self._flag

    def close(self) -> None:
        if self.handle:
            _k32.CloseHandle(self.handle)
            self.handle = None


def ask_running_instance_to_quit(name: str = QUIT_EVENT_NAME) -> bool:
    """True = nějaký program na pozadí běžel a dostal pokyn skončit."""
    return _fire(name)


def _fire(name: str) -> bool:
    if not IS_WINDOWS:
        return False
    h = _k32.OpenEventW(EVENT_MODIFY_STATE | SYNCHRONIZE, False, name)
    if not h:
        return False
    try:
        return bool(_k32.SetEvent(h))
    finally:
        _k32.CloseHandle(h)


class ShowSignal:
    """Pojmenovaná událost: druhé spuštění programu řekne běžící kopii, ať ukáže okno."""

    def __init__(self, name: str = SHOW_EVENT_NAME) -> None:
        self.handle = _k32.CreateEventW(None, False, False, name) if IS_WINDOWS else None

    def wait(self, timeout: float) -> bool:
        """True = někdo chce okno. Mimo Windows jen počká."""
        if not self.handle:
            import time

            time.sleep(timeout)
            return False
        return _k32.WaitForSingleObject(self.handle, int(timeout * 1000)) == WAIT_OBJECT_0

    def close(self) -> None:
        if self.handle:
            _k32.CloseHandle(self.handle)
            self.handle = None


def ask_running_instance_to_show(name: str = SHOW_EVENT_NAME) -> bool:
    """True = běžící kopie dostala pokyn ukázat okno."""
    return _fire(name)


def webview2_version() -> str | None:
    """Verze Microsoft Edge WebView2 Runtime (vykresluje okno aplikace), nebo None.
    Ve Windows 11 je vždycky, ve Windows 10 se instaluje s Edgem."""
    if not IS_WINDOWS:
        return None
    import winreg

    places = (
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
        (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
    )
    for root, path in places:
        try:
            with winreg.OpenKey(root, path) as k:
                value, _ = winreg.QueryValueEx(k, "pv")
            if value and str(value) != "0.0.0.0":
                return str(value)
        except OSError:
            continue
    return None


def message_box(text: str, title: str = "DbD Rich Presence", error: bool = False) -> None:
    if not IS_WINDOWS:
        print(f"[{title}] {text}", file=sys.stderr if sys.stderr else None)
        return
    try:
        flags = 0x10 if error else 0x40          # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, text, title, flags | 0x00010000)   # MB_SETFOREGROUND
    except Exception:
        pass


def ask_yes_no(text: str, title: str = "DbD Rich Presence") -> bool:
    """Okénko s otázkou Ano/Ne. Mimo Windows vrací False."""
    if not IS_WINDOWS:
        return False
    try:
        # MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND; IDYES = 6
        return ctypes.windll.user32.MessageBoxW(None, text, title, 0x4 | 0x20 | 0x00010000) == 6
    except Exception:
        return False


def open_path(path) -> None:
    """Otevře soubor nebo složku (Průzkumník / Poznámkový blok...)."""
    try:
        if IS_WINDOWS:
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass
