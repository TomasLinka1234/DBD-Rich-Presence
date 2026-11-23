"""API okna aplikace (bez skutečného okna): stav, statistiky, nastavení, aktualizace."""

import io
import json
import time

import config
import okno
import pytest
import stats as S
from catalog import KILLER, SURVIVOR


class FakeDiscord:
    connected = True


class FakeImages:
    def url_for(self, key):
        return None if not key else (key if key.startswith("https://") else f"https://cdn.example/{key}.png")

    def char_image(self, c):
        return "https://wiki.example/portret.png" if c else None


class FakeTracker:
    def __init__(self, st):
        self.stats = st


class FakeRunner:
    def __init__(self, st, catalog=None):
        self.tracker = FakeTracker(st)
        self.images = FakeImages()
        self.discord = FakeDiscord()
        self.catalog = catalog
        self.view = {"phase": "LOBBY", "game": True, "hidden": False, "activity": {
            "details": "Killer: The Trapper", "state": "V lobby · Prestige 6", "start": 1795449695,
            "large_image": "https://wiki.example/trapper.png", "large_text": "The Trapper",
            "small_image": "odznak_6", "small_text": "Prestige 6"}}


class FakeApp:
    def __init__(self, runner=None):
        self.runner = runner
        self.status = ("live", "Killer: The Trapper · V lobby")
        self.paused = False
        self.first_run_pending = True
        self.config_error = None
        self.pending_tab = "stats"
        self.window = None
        self.updates = okno.UpdateChecker("2.2.0")
        self.tray_refreshed = 0

    def set_paused(self, on):
        self.paused = on

    def refresh_tray(self):
        self.tray_refreshed += 1

    def hide_window(self):
        pass

    def quit(self):
        pass


@pytest.fixture()
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "nastaveni.json"
    monkeypatch.setattr(config, "CONFIG", path)
    monkeypatch.setattr(config, "ensure_data_dir", lambda: tmp_path)
    return path


def sample_stats(now):
    st = S.Stats(None)
    st.add(S.Match(now - 3000, now - 2400, KILLER, "The Trapper", map="Coal Tower", result="k4"))
    st.add(S.Match(now - 2000, now - 1400, SURVIVOR, "Meg Thomas", result="escaped"))
    return st


def test_state_for_home_page():
    now = time.time()
    api = okno.Api(FakeApp(FakeRunner(sample_stats(now))))
    st = api.state()
    assert st["game"] and st["discord"] and st["phase_text"] == "V lobby"
    assert st["activity"]["large"] == "https://wiki.example/trapper.png"
    assert st["activity"]["small"] == "https://cdn.example/odznak_6.png"
    assert st["first_run"] is True and st["goto"] == "stats"
    assert api.state()["goto"] is None                       # záložka se předá jen jednou
    assert st["today"] is not None and isinstance(st["recent"], list)
    json.dumps(st)                                           # musí jít poslat do JavaScriptu


def test_state_without_runner():
    st = okno.Api(FakeApp(None)).state()
    assert st["game"] is False and st["activity"] is None and st["discord"] is False


def test_pause_and_first_run(monkeypatch):
    import autostart

    calls = []
    monkeypatch.setattr(autostart, "enable", lambda: calls.append("on") or (True, "ok"))
    app = FakeApp(None)
    api = okno.Api(app)
    assert api.set_paused(True)["paused"] is True and app.paused
    assert api.first_run_answer(True)["first_run"] is False and calls == ["on"]


def test_dashboard_and_delete(base_data):
    from catalog import Catalog

    now = time.time()
    st = sample_stats(now)
    api = okno.Api(FakeApp(FakeRunner(st, Catalog(base_data))))
    d = api.dashboard("all", "all")
    assert d["total"]["matches"] == 2 and d["total"]["wins"] == 2
    assert {c["name"] for c in d["characters"]} == {"The Trapper", "Meg Thomas"}
    assert all(c["img"] == "https://wiki.example/portret.png" for c in d["characters"])
    assert api.dashboard("all", KILLER)["total"]["matches"] == 1
    victim = d["recent"][0]["id"]
    assert api.delete_match(victim) == {"ok": True}
    assert api.dashboard("all", "all")["total"]["matches"] == 1
    assert api.delete_match(victim) == {"ok": False}
    json.dumps(d)


def test_settings_roundtrip(cfg_file):
    api = okno.Api(FakeApp(None))
    s = api.settings()
    assert set(s["values"]) == set(okno.setting_items())
    assert all(k in config.DEFAULTS for k in okno.setting_items())
    r = api.save_settings({"ukazat_mapu": False, "jazyk": "en", "vlakna_ocr": 9, "jmeno_ve_hre": "  ScarsCZ ",
                           "neznama_polozka": 1})
    assert r["ok"] and set(r["changed"]) == {"ukazat_mapu", "jazyk", "vlakna_ocr", "jmeno_ve_hre"}
    saved = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert saved["ukazat_mapu"] is False and saved["jazyk"] == "en" and saved["vlakna_ocr"] == 4
    assert saved["jmeno_ve_hre"] == "ScarsCZ" and "neznama_polozka" not in saved
    bad = api.save_settings({"jazyk": "klingonsky", "discord_application_id": "abc"})
    assert not bad["ok"] and "jazyk" in bad["error"]
    assert json.loads(cfg_file.read_text(encoding="utf-8"))["jazyk"] == "en"
    assert api.reset_settings()["ok"]
    assert json.loads(cfg_file.read_text(encoding="utf-8"))["jazyk"] == "cs"


def test_saving_keeps_other_keys(cfg_file):
    cfg_file.write_text(json.dumps({"obrazek_killer": "muj_obrazek", "jazyk": "cs"}), encoding="utf-8")
    okno.Api(FakeApp(None)).save_settings({"jazyk": "en"})
    saved = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert saved == {"obrazek_killer": "muj_obrazek", "jazyk": "en"}


def test_empty_app_id_means_default(cfg_file):
    okno.Api(FakeApp(None)).save_settings({"discord_application_id": ""})
    assert json.loads(cfg_file.read_text(encoding="utf-8"))["discord_application_id"] == config.DEFAULT_APP_ID


def test_update_check(monkeypatch):
    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    payload = json.dumps({"tag_name": "v2.10.0", "html_url": "https://github.com/x/releases/tag/v2.10.0"}).encode()
    monkeypatch.setattr(okno.urllib.request, "urlopen", lambda req, timeout=0: Resp(payload))
    u = okno.UpdateChecker("2.9.3")
    info = u.check()
    assert info["newer"] is True and info["latest"] == "2.10.0"      # 2.10 > 2.9 (ne textově)
    assert okno.UpdateChecker("2.10.0").check()["newer"] is False

    def offline(req, timeout=0):
        raise OSError("offline")

    monkeypatch.setattr(okno.urllib.request, "urlopen", offline)
    assert "error" in okno.UpdateChecker("2.2.0").check()


def test_links_are_whitelisted(monkeypatch):
    import webbrowser

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    api = okno.Api(FakeApp(None))
    assert api.open_link("repo")["ok"] and opened == [okno.REPO_URL]
    assert api.open_link("https://evil.example")["ok"] is False and len(opened) == 1


def test_page_is_complete():
    html = okno.build_html()
    assert "{{" not in html and "data:image/png;base64," in html
    for page in ("home", "stats", "settings", "about"):
        assert f'id="page-{page}"' in html
    for name in ("state", "dashboard", "settings", "save_settings", "set_paused", "check_update", "delete_match",
                 "export_csv", "first_run_answer", "set_autostart", "open_link", "open_item", "clear_stats",
                 "reset_settings", "quit"):
        assert (f'"{name}"' in html or f"'{name}'" in html) and callable(getattr(okno.Api, name))
