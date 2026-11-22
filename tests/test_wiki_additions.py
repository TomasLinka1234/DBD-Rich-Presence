"""Doplňování nových postav, map a skinů z wiki do vestavěných dat."""

import copy
import time

import pytest
import wiki_data as W
from catalog import KILLER, SURVIVOR, Catalog


def test_real_wiki_has_nothing_new(base_data, wiki_snapshot):
    """Vestavěná data jsou aktuální: proti skutečné wiki nic nepřibude."""
    assert W.looks_ok(wiki_snapshot) == list(W.MINIMUM)
    add = W.additions(wiki_snapshot, base_data)
    assert W.count(add) == 0, W.describe(add)


@pytest.fixture()
def new_content(wiki_snapshot) -> dict:
    wiki = copy.deepcopy(wiki_snapshot)
    wiki["killers"].append({"id": 46, "name": "Wendigo"})
    wiki["survivors"].append({"id": 56, "name": 'Johnathan "JJ" Doe'})
    wiki["survivors"].append({"id": 57, "name": "Mara Vex", "dbdName": "Mara"})
    wiki["realms"].append({"id": 23, "name": "Frozen Pass"})
    wiki["maps"].append({"id": 52, "name": "Icebound Lodge", "realm": 23})
    wiki["maps"].append({"id": 53, "name": "Cinder Yard", "realm": 3})
    wiki["cos"].append({"name": "Snow Beast", "killer": 46, "survivor": None})
    wiki["cos"].append({"name": "Lumberjack Larry", "killer": 1, "survivor": None, "article": False})
    wiki["cos"].append({"name": "Ghost Girl", "killer": None, "survivor": 56, "realName": "Jo Doe"})
    return wiki


def test_new_entries_are_found(base_data, new_content):
    found = W.describe(W.additions(new_content, base_data))
    for want in ["killer The Wendigo", "survivor JJ Doe", "survivor Mara",
                 "mapa Icebound Lodge (Frozen Pass)", "mapa Cinder Yard (Coldwind Farm)",
                 "skin The Snow Beast (The Wendigo)", "skin Lumberjack Larry (The Trapper)",
                 "skin Ghost Girl (JJ Doe)"]:
        assert want in found


def test_merged_catalog_recognises_new_entries(base_data, new_content):
    merged = W.merge(base_data, W.additions(new_content, base_data))
    cat = Catalog(merged)
    assert len(cat.killers) == len(base_data["killers"]) + 1
    assert cat.match_character("THE WENDIGO", (KILLER,))[0].name == "The Wendigo"
    assert cat.match_character("JJ DOE", (SURVIVOR,))[0].name == "JJ Doe"
    assert cat.match_character("JOHNATHAN DOE", (SURVIVOR,))[0].name == "JJ Doe"
    skin = cat.match_character("THE SNOW BEAST", (KILLER,))[0]
    assert (skin.name, skin.base) == ("The Snow Beast", "The Wendigo")
    mm = cat.match_title_card(["ICEBOUND LODGE", "FROZEN PASS"])
    assert (mm.map, mm.realm) == ("Icebound Lodge", "Frozen Pass")
    assert cat.match_title_card(["CINDER YARD", "COLDWIND FARM"]).map == "Cinder Yard"


def test_merge_does_not_modify_base(base_data, new_content):
    before = copy.deepcopy(base_data)
    W.merge(base_data, W.additions(new_content, base_data))
    assert base_data == before


def test_updater_downloads_only_when_wiki_changes(tmp_path, monkeypatch, base_data, new_content):
    calls = []
    monkeypatch.setattr(W, "revisions", lambda titles: calls.append("rev") or {W.MAIN: 100, W.COSMETICS: 200})
    monkeypatch.setattr(W, "extract_main", lambda text: {k: new_content[k] for k in ("killers", "survivors", "realms", "maps")})
    monkeypatch.setattr(W, "extract_cosmetics", lambda text: {"cos": new_content["cos"]})
    monkeypatch.setattr(W, "raw_page", lambda title: calls.append(title) or "")

    from conftest import APP
    cache = tmp_path / "dbd_data_wiki.json"
    u = W.WikiUpdater(APP / "dbd_data.json", cache)
    assert u.due_in(time.time()) == 0
    assert u.check() is True
    assert calls == ["rev", W.MAIN, W.COSMETICS]
    fresh = u.take()
    assert fresh and any(k["name"] == "The Wendigo" for k in fresh["killers"])
    assert u.take() is None                       # vyzvedne se jen jednou

    calls.clear()
    assert u.check() is True
    assert calls == ["rev"]                       # revize stejná -> nic se nestahuje
    assert u.due_in(time.time()) > 19 * 3600     # další kontrola až zítra

    restarted = W.WikiUpdater(APP / "dbd_data.json", cache)
    assert any(k["name"] == "The Wendigo" for k in restarted.data()["killers"])   # funguje i offline


def test_updater_survives_network_error(tmp_path, monkeypatch):
    def offline(titles):
        raise OSError("offline")
    monkeypatch.setattr(W, "revisions", offline)
    from conftest import APP
    u = W.WikiUpdater(APP / "dbd_data.json", tmp_path / "c.json")
    assert u.check() is False
    assert 0 < u.due_in(time.time()) <= W.WikiUpdater.RETRY + 1
    assert u.data() == u.base


def test_disabled_updater_never_starts(tmp_path):
    from conftest import APP
    u = W.WikiUpdater(APP / "dbd_data.json", tmp_path / "c.json", enabled=False)
    u.start()
    assert u._thread is None
