"""Čtení Lua tabulek z datových modulů DbD wiki (bez internetu)."""

import pytest
import wiki_data as W
from conftest import ROOT

DATA = ROOT / "tests" / "data"


@pytest.fixture(scope="module")
def main_text() -> str:
    return (DATA / "Module_Datatable.lua").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def cos_text() -> str:
    return (DATA / "Module_Datatable_Cosmetics.lua").read_text(encoding="utf-8")


def test_killers_from_real_snippet(main_text):
    m = W.extract_main(main_text)
    assert [k["name"] for k in m["killers"]] == ["Trapper", "Wraith", "Hillbilly", "Nurse", "Shape"]


def test_survivors_keep_short_and_ingame_names(main_text):
    m = W.extract_main(main_text)
    names = [s["name"] for s in m["survivors"]]
    assert names[7] == 'William "Bill" Overbeck'
    assert "Élodie Rakoto" in names
    assert names[-1] == "Aestri Yazar & Baermar Uraz"
    tapp = next(s for s in m["survivors"] if s["id"] == 12)
    assert tapp["dbdName"] == "Detective Tapp"
    assert tapp["shortName"] == "David Tapp"


def test_realms_and_maps(main_text):
    m = W.extract_main(main_text)
    realms = [r["name"] for r in m["realms"]]
    assert realms[:3] == ["The MacMillan Estate", "Autohaven Wreckers", "Coldwind Farm"]
    assert "Léry's Memorial Institute" in realms
    assert m["maps"] == [
        {"id": 1, "name": "Coal Tower", "realm": 1},
        {"id": 2, "name": "Groaning Storehouse", "realm": 1},
        {"id": 6, "name": "Azarov's Resting Place", "realm": 2},
        {"id": 7, "name": "Blood Lodge", "realm": 2},
        {"id": 51, "name": "Hartshorne Mall", "realm": 22},
    ]


def test_cosmetics(cos_text):
    cos = W.extract_cosmetics(cos_text)["cos"]
    assert len(cos) == 14
    by_name = {c["name"]: c for c in cos}
    assert by_name["Good Gal"]["killer"] == 34
    assert by_name["Good Gal"]["realName"] == "Tiffany Valentine"
    assert "article" not in by_name["Good Gal"]
    assert by_name["Naughty Bear"]["article"] is False
    assert by_name["Naughty Bear"]["killer"] == 1
    assert by_name["Yellow Rabbit"]["realName"] == "William Afton"
    assert by_name["Tubarão"]["survivor"] == 36


def test_tricky_lua_syntax():
    src = ('x = { a = "q\\"x", [10] = 5, -3, 0x10, [[long\nstr]], b = f(1, {2}), '
           'c = "a" .. "b", d = {1, {2, 3}}, e = nil, --[[ komentář ]] g = true; }')
    t = W.lua_table(src, "x")
    assert t["a"] == 'q"x'
    assert t[10] == 5
    assert (t[1], t[2], t[3]) == (-3, 16, "long\nstr")
    assert t["b"] is None and t["c"] is None        # výrazy se přeskočí, nic se nespouští
    assert t["d"] == {1: 1, 2: {1: 2, 2: 3}}
    assert t["g"] is True and "e" in t


def test_missing_table_returns_none():
    assert W.lua_table("local y = 1", "x") is None


def test_garbage_does_not_crash():
    for junk in ["", "x = {", "x = { a = ", "x = {{{{{{", "x = { [ = ] }", "\x00\xff x = {1,2"]:
        try:
            W.lua_table(junk, "x")
        except W.LuaError:
            pass
