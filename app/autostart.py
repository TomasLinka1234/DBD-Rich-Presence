"""Spouštění se zapnutím Windows: zástupce ve složce Po spuštění (Startup).

Zástupce spouští pythonw.exe (bez černého okna) s app/pozadi.py. Program pak
běží neviditelně s ikonkou u hodin a sám čeká, až zapneš Dead by Daylight.
Nepotřebuje práva správce a jde kdykoli smazat (vypnout_autostart.bat).
"""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

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
    """pythonw.exe z .venv programu (bez okna); záložně ten, co právě běží."""
    venv = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if venv.exists():
        return venv
    import sys

    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return cand if cand.exists() else exe


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
    icon = ROOT / "ikony" / "aplikace.ico"
    args = '-X utf8 "' + str(APP / "pozadi.py") + '" --autostart'
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "$sh = New-Object -ComObject WScript.Shell",
        "$s = $sh.CreateShortcut(" + _q(link) + ")",
        "$s.TargetPath = " + _q(pythonw()),
        "$s.Arguments = " + _q(args),
        "$s.WorkingDirectory = " + _q(ROOT),
        "$s.Description = 'DbD Rich Presence - Discord status pro Dead by Daylight'",
        "$s.WindowStyle = 7",
    ]
    if icon.exists():
        lines.append("$s.IconLocation = " + _q(str(icon) + ",0"))
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
