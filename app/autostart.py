"""Spouštění se zapnutím Windows: zástupce ve složce Po spuštění (Startup).

Zástupce spouští DbD-Rich-Presence.exe (u zdrojáků pythonw.exe s main.py).
Program pak běží neviditelně s ikonkou u hodin a sám čeká, až zapneš
Dead by Daylight. Nepotřebuje práva správce a jde kdykoli vypnout v menu ikonky.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path

from paths import FROZEN, ICON_ICO

APP = Path(__file__).resolve().parent
ROOT = APP.parent
SHORTCUT_NAME = "DbD Rich Presence.lnk"


def startup_folder() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path | None:
    folder = startup_folder()
    return folder / SHORTCUT_NAME if folder else None


def pythonw() -> Path:
    """pythonw.exe (bez okna) k Pythonu, který právě běží."""
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return cand if cand.exists() else exe


def target() -> tuple[Path, str, Path, str | None]:
    """(program, argumenty, pracovní složka, ikona) pro zástupce."""
    if FROZEN:
        exe = Path(sys.executable)
        return exe, "--autostart", exe.parent, f"{exe},0"
    args = '-X utf8 "' + str(APP / "main.py") + '" --autostart'
    return pythonw(), args, ROOT, (f"{ICON_ICO},0" if ICON_ICO.exists() else None)


def points_here() -> bool:
    """Míří zástupce na tenhle program? (po přesunutí .exe jinam ne)"""
    link = shortcut_path()
    if not link or not link.exists():
        return False
    try:
        r = _ps("(New-Object -ComObject WScript.Shell).CreateShortcut(" + _q(link) + ").TargetPath")
        return Path(r.stdout.strip()).resolve() == target()[0].resolve()
    except Exception:
        return True


def is_enabled() -> bool:
    p = shortcut_path()
    return bool(p and p.exists())


def _ps(script: str) -> subprocess.CompletedProcess:
    """PowerShell s příkazem v UTF-16 (zvládne diakritiku a mezery v cestách)."""
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-EncodedCommand", enc], capture_output=True, text=True, errors="replace",
                          timeout=60, creationflags=flags)


def _q(s: str | Path) -> str:
    """Řetězec pro PowerShell v jednoduchých uvozovkách."""
    return "'" + str(s).replace("'", "''") + "'"


def enable() -> tuple[bool, str]:
    link = shortcut_path()
    if link is None:
        return False, "Nenašel jsem složku Po spuštění (chybí proměnná APPDATA)."
    link.parent.mkdir(parents=True, exist_ok=True)
    prog, args, workdir, icon = target()
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "$sh = New-Object -ComObject WScript.Shell",
        "$s = $sh.CreateShortcut(" + _q(link) + ")",
        "$s.TargetPath = " + _q(prog),
        "$s.Arguments = " + _q(args),
        "$s.WorkingDirectory = " + _q(workdir),
        "$s.Description = 'DbD Rich Presence - Discord status pro Dead by Daylight'",
        "$s.WindowStyle = 7",
    ]
    if icon:
        lines.append("$s.IconLocation = " + _q(icon))
    lines.append("$s.Save()")
    script = "\n".join(lines)
    try:
        r = _ps(script)
    except Exception as e:
        return False, f"PowerShell nejde spustit: {e}"
    if r.returncode != 0 or not link.exists():
        return False, (r.stderr or r.stdout or "neznámá chyba").strip()[:400]
    return True, str(link)


def disable() -> tuple[bool, str]:
    link = shortcut_path()
    if link is None or not link.exists():
        return True, "Autostart nebyl zapnutý."
    try:
        link.unlink()
        return True, str(link)
    except Exception as e:
        return False, str(e)
