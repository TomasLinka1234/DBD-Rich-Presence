"""Okno aplikace: Domů (živý náhled statusu), Statistiky, Nastavení, O aplikaci.

Vykresluje ho Microsoft Edge WebView2 (je ve Windows 11 i v aktuálních Windows 10)
přes knihovnu pywebview. Vzhled je v app/ui/index.html (HTML, CSS a JavaScript, nic
se nestahuje z internetu); s Pythonem mluví přes window.pywebview.api = třída Api.

Okno je jen pohled na běh na pozadí: zavřením se schová do ikonky u hodin a status
v Discordu jede dál. Úplně se aplikace ukončí z menu ikonky nebo tlačítkem v okně.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
import urllib.request
from pathlib import Path

from paths import CONFIG, DATA, ICON_ICO, ICON_PNG, LOG_FILE, RES, STATS
from version import VERSION

log = logging.getLogger("dbd")

REPO = "TomasLinka1234/DBD-Rich-Presence"
REPO_URL = f"https://github.com/{REPO}"
LINKS = {
    "repo": REPO_URL,
    "navod": f"{REPO_URL}/blob/main/NAVOD.md",
    "vydani": f"{REPO_URL}/releases/latest",
    "chyba": f"{REPO_URL}/issues/new",
    "bezpecnost": f"{REPO_URL}/blob/main/SECURITY.md",
    "webview2": "https://developer.microsoft.com/microsoft-edge/webview2/",
}
UPDATE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
UI_FILE = RES / "ui" / "index.html"
WINDOW_SIZE = (1120, 760)
MIN_SIZE = (960, 640)
SAVE_DIALOG = 30          # webview.FileDialog.SAVE

PHASE_TEXT = {"OFF": "Neběží", "MENU": "V menu", "LOBBY": "V lobby", "LOADING": "Načítá se zápas",
              "MATCH": "V zápase", "POSTGAME": "Po zápase"}

# Co jde nastavit v okně (zbytek nastaveni.json zůstává, jak je).
SETTINGS: list[dict] = [
    {"title": "Discord status", "items": [
        {"key": "jazyk", "type": "select", "label": "Jazyk statusu", "hint": "V jakém jazyce status uvidí kamarádi.",
         "options": [["cs", "Čeština"], ["en", "English"]]},
        {"key": "ukazat_mapu", "type": "bool", "label": "Ukazovat mapu", "hint": "V zápase název mapy a realmu."},
        {"key": "ukazat_cas_zapasu", "type": "bool", "label": "Ukazovat čas zápasu"},
        {"key": "ukazat_zakladni_postavu", "type": "bool", "label": "U skinu ukázat i základní postavu",
         "hint": "Třeba „Rize Kamishiro (The Ghoul)“."},
        {"key": "ukazat_prestige", "type": "bool", "label": "Prestige v textu statusu"},
        {"key": "prestige_ikona", "type": "bool", "label": "Odznak prestige v rohu obrázku"},
        {"key": "velky_obrazek", "type": "select", "label": "Velký obrázek",
         "options": [["postava", "Portrét postavy"], ["mapa", "Mapa"]]},
        {"key": "ukazat_statistiky", "type": "bool", "label": "Ukazovat statistiky",
         "hint": "Dnešní zápasy a výhry, výsledek po zápase a souhrn za postavu."},
    ]},
    {"title": "Statistiky", "items": [
        {"key": "statistiky", "type": "bool", "label": "Počítat odehrané zápasy",
         "hint": "Ukládá se jen u tebe v počítači (zapasy.jsonl)."},
    ]},
    {"title": "Data z DbD wiki", "items": [
        {"key": "obrazky_z_wiki", "type": "bool", "label": "Portréty postav a ikony map z wiki"},
        {"key": "novinky_z_wiki", "type": "bool", "label": "Nové postavy, mapy a skiny",
         "hint": "Jednou denně se podívá na DbD wiki."},
    ]},
    {"title": "Pokročilé", "advanced": True, "items": [
        {"key": "jmeno_ve_hre", "type": "text", "label": "Jméno ve hře", "max": 40,
         "hint": "Nech prázdné, program si ho zjistí sám.", "placeholder": "zjistí se samo"},
        {"key": "snimani", "type": "select", "label": "Snímání obrazovky",
         "options": [["auto", "Automaticky"], ["dxcam", "dxcam (rychlejší)"], ["mss", "mss (spolehlivější)"]]},
        {"key": "vlakna_ocr", "type": "int", "label": "Jádra pro čtení textu", "min": 1, "max": 4,
         "hint": "Když se hra seká, dej 1."},
        {"key": "discord_application_id", "type": "text", "label": "Discord Application ID", "max": 22,
         "hint": "Jen když chceš vlastní Discord aplikaci.", "pattern": "^[0-9]{15,22}$",
         "bad": "Application ID jsou jen číslice (15 až 22)."},
        {"key": "ukladat_odznaky_prestige", "type": "bool", "label": "Ukládat odznaky prestige k nahrání"},
        {"key": "ukladat_obrazky_map", "type": "bool", "label": "Ukládat obrázky map k nahrání"},
        {"key": "debug", "type": "bool", "label": "Ladicí režim",
         "hint": "Podrobný log a snímky obrazovky do složky debug."},
    ]},
]


def setting_items() -> dict[str, dict]:
    return {it["key"]: it for sec in SETTINGS for it in sec["items"]}


def clean_settings(values: dict, current: dict) -> tuple[dict, list[str]]:
    """Hodnoty z okna -> bezpečné hodnoty pro nastaveni.json. Neplatné se přeskočí."""
    from config import DEFAULT_APP_ID

    out, bad = dict(current), []
    items = setting_items()
    for key, value in (values or {}).items():
        it = items.get(key)
        if it is None:
            continue
        kind = it["type"]
        if kind == "bool":
            out[key] = bool(value)
        elif kind == "select":
            if str(value) in [o[0] for o in it["options"]]:
                out[key] = str(value)
            else:
                bad.append(key)
        elif kind == "int":
            try:
                out[key] = max(it["min"], min(it["max"], int(value)))
            except (TypeError, ValueError):
                bad.append(key)
        else:
            text = str(value if value is not None else "").strip()[: it.get("max", 100)]
            if key == "discord_application_id":
                if not text:
                    text = DEFAULT_APP_ID
                elif not re.fullmatch(it["pattern"].strip("^$"), text):
                    bad.append(key)
                    continue
            out[key] = text
    return out, bad


# ----------------------------------------------------------------- aktualizace
def version_tuple(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) if nums else (0,)


class UpdateChecker:
    """Jestli je na GitHubu novější vydání. Jen dotaz na api.github.com, nic se nestahuje."""

    EVERY = 6 * 3600.0

    def __init__(self, current: str = VERSION) -> None:
        self.current = current
        self.info: dict | None = None
        self._at = 0.0
        self._lock = threading.Lock()

    def check(self, force: bool = False) -> dict:
        with self._lock:
            if self.info is not None and not force and time.time() - self._at < self.EVERY:
                return self.info
            try:
                req = urllib.request.Request(UPDATE_URL, headers={
                    "User-Agent": f"DbD-Rich-Presence/{self.current}", "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                latest = str(data.get("tag_name") or "").lstrip("vV")
                self.info = {"current": self.current, "latest": latest,
                             "newer": version_tuple(latest) > version_tuple(self.current),
                             "url": str(data.get("html_url") or LINKS["vydani"])}
            except Exception as e:
                log.debug("Kontrola aktualizací selhala: %s", e)
                return {"error": "Nepodařilo se zjistit (jsi připojený k internetu?)"}
            self._at = time.time()
            return self.info


# ----------------------------------------------------------------- API pro okno
class Api:
    """Volá ho JavaScript v okně (window.pywebview.api.<metoda>). Každé volání běží ve vlastním vlákně."""

    def __init__(self, app) -> None:
        self._app = app

    # ---------------------------------------------------------- domů
    def state(self) -> dict:
        app = self._app
        r = app.runner
        view = dict(getattr(r, "view", None) or {"phase": "OFF", "game": False, "hidden": False, "activity": None})
        images = getattr(r, "images", None)
        discord = getattr(r, "discord", None)
        act = view.get("activity")
        preview = None
        if act:
            def url(key):
                if images is not None:
                    return images.url_for(key)
                return key if key and key.startswith("https://") else None

            preview = {"details": act.get("details"), "state": act.get("state"), "start": act.get("start"),
                       "large": url(act.get("large_image")), "large_text": act.get("large_text"),
                       "small": url(act.get("small_image")), "small_text": act.get("small_text")}
        from stats import game_day, match_dict, tally_dict, today_line

        stats = self._stats()
        now = time.time()
        today, recent = None, []
        if stats is not None:
            t = stats.today(now)
            today = {**tally_dict(t), "line": today_line(t)}
            day = game_day(now)
            recent = [match_dict(m) for m in reversed(stats.snapshot()) if game_day(m.start) == day][:4]
            for m in recent:
                m["img"] = self._portrait(m["base"] or m["character"])
        goto, app.pending_tab = app.pending_tab, None
        status_kind, status_text = app.status
        return {
            "version": VERSION, "status": {"kind": status_kind, "text": status_text},
            "phase": view.get("phase"), "phase_text": PHASE_TEXT.get(view.get("phase"), ""),
            "game": bool(view.get("game")), "hidden": bool(view.get("hidden")),
            "discord": bool(discord is not None and discord.connected),
            "paused": bool(app.paused), "activity": preview, "today": today, "recent": recent,
            "hero": self._hero(r, view),
            "first_run": bool(app.first_run_pending), "update": app.updates.info,
            "config_error": app.config_error, "goto": goto,
        }

    def _hero(self, r, view: dict) -> dict | None:
        """Velký panel na Domů: kdo, prestige, mapa, čas zápasu, portrét."""
        t = getattr(r, "tracker", None)
        if t is None or not view.get("game"):
            return None
        c = t.character
        mm = t.map
        return {"role": t.role, "character": c.name if c else None, "base": c.base if c else None,
                "prestige": t.current_prestige(),
                "map": mm.label() if (mm is not None and mm.label()) else None,
                "start": int(t.match_start) if (t.phase == "MATCH" and t.match_start) else None,
                "img": self._portrait_of(c)}

    def _portrait_of(self, c) -> str | None:
        images = getattr(self._app.runner, "images", None)
        if images is None or c is None:
            return None
        try:
            return images.url_for(images.char_image(c))
        except Exception:
            return None

    def _portrait(self, name: str | None) -> str | None:
        catalog = getattr(self._app.runner, "catalog", None)
        if not name or name == "?" or catalog is None:
            return None
        try:
            return self._portrait_of(catalog.character(name))
        except Exception:
            return None

    def set_paused(self, on: bool) -> dict:
        self._app.set_paused(bool(on))
        return self.state()

    def first_run_answer(self, autostart_on: bool) -> dict:
        import autostart

        if autostart_on:
            ok, info = autostart.enable()
            log.info("Autostart zapnut." if ok else f"Autostart se nepodařilo zapnout: {info}")
        self._app.first_run_pending = False
        return self.state()

    # ---------------------------------------------------------- statistiky
    def _stats(self):
        r = self._app.runner
        tracker = getattr(r, "tracker", None)
        if tracker is not None and tracker.stats is not None:
            return tracker.stats
        from stats import Stats

        return Stats(STATS) if STATS.exists() else None

    def dashboard(self, period: str = "week", role: str = "all") -> dict:
        from stats import dashboard

        stats = self._stats()
        data = dashboard(stats.snapshot() if stats else [], time.time(), period, role)
        cache: dict = {}

        def img(name):
            if name not in cache:
                cache[name] = self._portrait(name)
            return cache[name]

        for c in data["characters"]:
            c["img"] = img(c["name"])
        for m in data["recent"]:
            m["img"] = img(m["base"] or m["character"])
        return data

    def delete_match(self, match_id: int) -> dict:
        stats = self._stats()
        ok = bool(stats and stats.delete(int(match_id)))
        if ok:
            log.info("Zápas %s smazán ze statistik (z okna).", match_id)
        return {"ok": ok}

    def clear_stats(self) -> dict:
        stats = self._stats()
        if stats is not None:
            stats.clear()
        log.info("Statistiky smazány (z okna).")
        return {"ok": True}

    def export_csv(self) -> dict:
        from stats import to_csv

        window = self._app.window
        if window is None:
            return {"ok": False, "error": "Okno není připravené."}
        stats = self._stats()
        if stats is None or not stats.snapshot():
            return {"ok": False, "error": "Zatím nejsou žádné zápasy k exportu."}
        try:
            chosen = window.create_file_dialog(SAVE_DIALOG, save_filename="dbd-statistiky.csv",
                                               file_types=("CSV (*.csv)",))
        except Exception as e:
            return {"ok": False, "error": f"Okno pro uložení se nepodařilo otevřít: {e}"}
        if not chosen:
            return {"ok": False}
        path = Path(chosen if isinstance(chosen, str) else chosen[0])
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        try:
            path.write_text(to_csv(stats.snapshot()), encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": f"Nepodařilo se uložit: {e}"}
        return {"ok": True, "path": str(path)}

    # ---------------------------------------------------------- nastavení
    def settings(self) -> dict:
        import autostart
        import config

        cfg, _, error = config.load_config()
        return {"sections": SETTINGS, "values": {k: cfg.get(k) for k in setting_items()},
                "autostart": autostart.is_enabled(), "error": error}

    def save_settings(self, values: dict) -> dict:
        import config

        current, _, _ = config.load_config()
        cleaned, bad = clean_settings(values, current)
        changed = {k: cleaned[k] for k in setting_items() if cleaned.get(k) != current.get(k)}
        if changed:
            config.save_config(changed)
            log.info("Nastavení změněno v okně: %s", ", ".join(sorted(changed)))
        if bad:
            return {"ok": False, "error": "Některé hodnoty nejsou platné: " + ", ".join(bad)}
        return {"ok": True, "changed": sorted(changed)}

    def reset_settings(self) -> dict:
        import config

        defaults = {k: config.DEFAULTS[k] for k in setting_items() if k in config.DEFAULTS}
        config.save_config(defaults)
        log.info("Nastavení obnoveno na výchozí (z okna).")
        return {"ok": True}

    def set_autostart(self, on: bool) -> dict:
        import autostart

        ok, info = autostart.enable() if on else autostart.disable()
        log.info(("Autostart zapnut." if on else "Autostart vypnut.") if ok else f"Autostart: {info}")
        self._app.refresh_tray()
        return {"ok": ok, "on": autostart.is_enabled(), "info": info}

    # ---------------------------------------------------------- o aplikaci
    def check_update(self, force: bool = False) -> dict:
        return self._app.updates.check(bool(force))

    def open_link(self, name: str) -> dict:
        url = LINKS.get(str(name))
        if url:
            import webbrowser

            webbrowser.open(url)
        return {"ok": bool(url)}

    def open_item(self, what: str) -> dict:
        from winutil import open_path

        if what == "config":
            from pozadi import open_in_editor

            open_in_editor(CONFIG)
        elif what == "log":
            open_path(LOG_FILE)
        elif what == "data":
            open_path(DATA)
        else:
            return {"ok": False}
        return {"ok": True}

    def hide(self) -> None:
        self._app.hide_window()

    def quit(self) -> None:
        threading.Thread(target=self._app.quit, daemon=True).start()


# ----------------------------------------------------------------- okno
def build_html() -> str:
    html = UI_FILE.read_text(encoding="utf-8")
    return html.replace("{{LOGO}}", _logo_data_uri()).replace("{{VERSION}}", VERSION)


def _logo_data_uri(size: int = 160) -> str:
    """Logo zmenšené pro okno (stránka se předává jako text a velký obrázek by ji zbytečně nafoukl)."""
    try:
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.open(ICON_PNG).convert("RGBA").resize((size, size), Image.LANCZOS).save(buf, "PNG", optimize=True)
        data = buf.getvalue()
    except Exception:
        try:
            data = ICON_PNG.read_bytes()
        except OSError:
            return ""
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _dark_title_bar(window) -> None:
    """Tmavý horní pruh okna i při světlém motivu Windows (celá aplikace je tmavá)."""
    try:
        import ctypes

        hwnd = int(window.native.Handle.ToInt32())
        dwm = ctypes.windll.dwmapi
        for attr, value in ((20, 1), (35, 0x00100E0E), (36, 0x00E8EBEC)):   # tmavý režim, barva pruhu, barva textu
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        log.debug("Tmavý pruh okna nejde nastavit", exc_info=True)


def available() -> tuple[bool, str]:
    """Jde okno otevřít? (Windows + WebView2 + pywebview)"""
    if os.name != "nt" and not os.environ.get("DBD_RP_OKNO"):
        return False, "okno je jen pro Windows"
    from winutil import webview2_version

    if os.name == "nt" and not webview2_version():
        return False, "chybí Microsoft Edge WebView2 Runtime"
    try:
        import webview  # noqa: F401
    except Exception as e:
        return False, f"chybí knihovna pywebview ({e.__class__.__name__})"
    return True, ""


def run_window(app, hidden: bool) -> None:
    """Vytvoří okno a spustí smyčku GUI (blokuje hlavní vlákno, dokud se okno nezavře úplně)."""
    import webview

    window = webview.create_window(
        "DbD Rich Presence", html=build_html(), js_api=Api(app), width=WINDOW_SIZE[0], height=WINDOW_SIZE[1],
        min_size=MIN_SIZE, hidden=hidden, background_color="#0e0e10", text_select=False)
    app.window = window
    window.events.closing += app.on_window_closing
    if os.name == "nt":
        window.events.before_show += _dark_title_bar
    storage = DATA / "okno"
    storage.mkdir(parents=True, exist_ok=True)
    webview.start(gui=os.environ.get("DBD_RP_GUI", "edgechromium"), private_mode=False, storage_path=str(storage),
                  icon=str(ICON_ICO) if ICON_ICO.exists() else None)
