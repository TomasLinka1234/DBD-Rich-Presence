"""Spouštění se zapnutím Windows.

Používá standardní místo, kam se zapisují i Discord, Steam nebo Spotify:
    HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
hodnota "DbD Rich Presence" = "C:\\...\\DbD-Rich-Presence.exe" --autostart

Nepotřebuje práva správce, je vidět ve Správci úloh (karta Po spuštění)
a jde kdykoli vypnout v menu ikonky. Žádné skripty ani PowerShell.
Verze 2.0.0 místo toho dávala zástupce do složky Po spuštění; ten se
při zapnutí/vypnutí sám uklidí.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from paths import FROZEN

APP = Path(__file__).resolve().parent
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "DbD Rich Presence"
OLD_SHORTCUT = "DbD Rich Presence.lnk"     # verze 2.0.0

try:
    import winreg
except ImportError:          # Linux / macOS: autostart jen na Windows
    winreg = None


# ------------------------------------------------------------ příkaz
def pythonw() -> Path:
    """pythonw.exe (bez okna) k Pythonu, který právě běží."""
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return cand if cand.exists() else exe


def command() -> str:
    """Co má Windows spustit po přihlášení."""
    if FROZEN:
        return f'"{Path(sys.executable)}" --autostart'
    return f'"{pythonw()}" -X utf8 "{APP / "main.py"}" --autostart'


def _norm(cmd: str) -> str:
    return " ".join(cmd.replace('"', " ").split()).casefold()


# ------------------------------------------------------------ registry
def _read() -> str | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            value, _ = winreg.QueryValueEx(k, VALUE_NAME)
            return str(value)
    except OSError:
        return None


def _write(cmd: str) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, cmd)


def _delete() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, VALUE_NAME)
    except FileNotFoundError:
        pass


# ------------------------------------------------------------ starý zástupce (2.0.0)
def old_shortcut() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / OLD_SHORTCUT


def _remove_old_shortcut() -> None:
    link = old_shortcut()
    if link and link.exists():
        try:
            link.unlink()
        except OSError:
            pass


# ------------------------------------------------------------ veřejné funkce
def is_enabled() -> bool:
    link = old_shortcut()
    return _read() is not None or bool(link and link.exists())


def points_here() -> bool:
    """Spouští se po zapnutí Windows právě tenhle program? (po přesunutí .exe jinam ne)"""
    current = _read()
    return current is not None and _norm(current) == _norm(command())


def enable() -> tuple[bool, str]:
    if winreg is None:
        return False, "Spouštění se zapnutím funguje jen ve Windows."
    try:
        _write(command())
    except OSError as e:
        return False, f"Zápis do registru se nepovedl: {e}"
    _remove_old_shortcut()
    return True, "HKCU\\" + RUN_KEY + "\\" + VALUE_NAME


def disable() -> tuple[bool, str]:
    _remove_old_shortcut()
    if winreg is None or _read() is None:
        return True, "Autostart nebyl zapnutý."
    try:
        _delete()
    except OSError as e:
        return False, str(e)
    return True, "HKCU\\" + RUN_KEY + "\\" + VALUE_NAME
