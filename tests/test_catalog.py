"""Rozpoznávání jmen postav a map z textu přečteného ze hry."""

import pytest
from catalog import KILLER, SURVIVOR, Catalog, compact, norm


@pytest.fixture(scope="module")
def cat(base_data) -> Catalog:
    return Catalog(base_data)


def test_bundled_data_is_complete(base_data):
    assert len(base_data["killers"]) >= 40
    assert len(base_data["survivors"]) >= 50
    names = [k["name"] for k in base_data["killers"]]
    assert len(names) == len(set(names)), "duplicitní killer"


def test_normalisation():
    assert compact("Léry's Memorial Institute") == compact("LERYS MEMORIAL INSTITUTE")
    assert norm("  The   Trapper ") == norm("the trapper")


@pytest.mark.parametrize("text, want", [
    ("THE TRAPPER", "The Trapper"),
    ("THE TRAPPFR", "The Trapper"),       # typická chyba OCR
    ("THE NURSE", "The Nurse"),
])
def test_killer_names(cat, text, want):
    c, score = cat.match_character(text, (KILLER,))
    assert c is not None and c.name == want, (text, score)


def test_survivor_name(cat):
    c, _ = cat.match_character("DWIGHT FAIRFIELD", (SURVIVOR,))
    assert c is not None and c.name == "Dwight Fairfield"


def test_random_text_is_not_a_character(cat):
    for junk in ["READY", "PLAY", "BLOODWEB", "12345", "XQZW"]:
        assert cat.match_character(junk)[0] is None, junk


def test_skin_points_to_base_character(cat):
    skins = [c for c in cat.characters if c.base]
    assert skins, "ve vestavěných datech nejsou skiny"
    s = skins[0]
    found, _ = cat.match_character(s.name.upper(), (s.role,))
    assert found is not None and found.base == s.base


def test_title_card(cat):
    mm = cat.match_title_card(["COAL TOWER", "THE MACMILLAN ESTATE"])
    assert mm is not None and mm.map == "Coal Tower" and mm.realm == "The MacMillan Estate"
    assert mm.label() == "Coal Tower (The MacMillan Estate)"


def test_title_card_ignores_noise(cat):
    assert cat.match_title_card(["", "OK", "LOADING"]) is None
