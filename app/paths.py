"""Kde co je.

Program (.exe nebo zdrojáky) jen čte svoje vestavěné soubory. Všechno, co si
vytváří sám (nastavení, log, stav, stažená data), patří do jedné složky
v %APPDATA%\\DbD Rich Presence, takže vedle .exe nic nepřibývá.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "DbD Rich Presence"
FROZEN = bool(getattr(sys, "frozen", False))

# Vestavěné soubory (jen ke čtení): dbd_data.json, ikona
if FROZEN:
    RES = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "app"
else:
    RES = Path(__file__).resolve().parent

BUILTIN_DATA = RES / "dbd_data.json"
ICON_PNG = RES / "ikona.png"
ICON_ICO = RES / "ikona.ico"


def _data_dir() -> Path:
    override = os.environ.get("DBD_RP_DATA")
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "dbd-rich-presence"


DATA = _data_dir()
CONFIG = DATA / "nastaveni.json"
LOG_FILE = DATA / "log.txt"
STATE = DATA / "stav.json"
IMAGE_CACHE = DATA / "obrazky_cache.json"
WIKI_CACHE = DATA / "dbd_data_wiki.json"
DEBUG_DIR = DATA / "debug"
UPLOADS = DATA / "obrazky_k_nahrani"


def ensure_data_dir() -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    return DATA
