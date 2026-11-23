"""Nastavení programu: %APPDATA%\\DbD Rich Presence\\nastaveni.json.

Když soubor chybí, vytvoří se s výchozími hodnotami. Chybějící položky se
doplní z výchozích, takže starší soubor nastavení vždycky funguje.
"""

from __future__ import annotations

import json
import logging
import os
import re

from paths import CONFIG, ensure_data_dir

log = logging.getLogger("dbd")

# Discord aplikace "Dead by Daylight" s nahranými odznaky prestige.
# Kdo chce vlastní, přepíše discord_application_id v nastavení.
DEFAULT_APP_ID = "1573821837052215356"

DEFAULTS: dict = {
    "discord_application_id": DEFAULT_APP_ID,
    "jazyk": "cs",
    "ukazat_mapu": True,
    "ukazat_cas_zapasu": True,
    "jmeno_ve_hre": "",
    "ukazat_zakladni_postavu": True,
    "ukazat_prestige": True,
    "statistiky": True,
    "ukazat_statistiky": True,
    "prestige_ikona": True,
    "velky_obrazek": "postava",
    "obrazky_z_wiki": True,
    "novinky_z_wiki": True,
    "obrazek": "",
    "obrazek_killer": "",
    "obrazek_survivor": "",
    "snimani": "auto",
    "vlakna_ocr": 2,
    "ukladat_odznaky_prestige": False,
    "ukladat_obrazky_map": False,
    "debug": False,
}


def load_config() -> tuple[dict, bool, str | None]:
    """(nastavení, vytvořeno_poprvé, chyba). Při chybě v souboru se použijí
    výchozí hodnoty a soubor se nepřepíše."""
    ensure_data_dir()
    if not CONFIG.exists():
        try:
            CONFIG.write_text(json.dumps(DEFAULTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            return dict(DEFAULTS), True, f"nastavení nejde uložit: {e}"
        return dict(DEFAULTS), True, None
    try:
        with open(CONFIG, encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("nečekaný obsah")
    except json.JSONDecodeError as e:
        return dict(DEFAULTS), False, f"řádek {e.lineno}: {e.msg}"
    except (OSError, ValueError) as e:
        return dict(DEFAULTS), False, str(e)
    cfg = dict(DEFAULTS)
    cfg.update(data)
    return cfg, False, None


def save_config(changes: dict) -> None:
    """Zapíše změny do nastaveni.json (ostatní položky nechá, jak jsou). Běh na pozadí
    si změnu sám všimne a nastavení načte znovu."""
    ensure_data_dir()
    data: dict = {}
    if CONFIG.exists():
        try:
            with open(CONFIG, encoding="utf-8-sig") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            data = {}
    if not data:
        data = dict(DEFAULTS)
    data.update(changes)
    tmp = CONFIG.with_name(CONFIG.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, CONFIG)


def app_id_from(cfg: dict) -> str:
    raw = str(cfg.get("discord_application_id", "")).strip()
    return raw if re.fullmatch(r"\d{15,22}", raw) else DEFAULT_APP_ID
