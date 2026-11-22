"""Odznaky prestige: jména obrázků a soubory v repozitáři."""

from conftest import ROOT
from images import badge_key


def test_badge_key():
    assert badge_key(1) == "odznak_1"
    assert badge_key(100) == "odznak_100"


def test_all_badges_are_in_repo():
    folder = ROOT / "assets" / "odznaky"
    missing = [n for n in range(1, 101) if not (folder / f"odznak_{n}.png").is_file()]
    assert not missing


def test_badges_are_real_png():
    folder = ROOT / "assets" / "odznaky"
    for n in (1, 50, 100):
        assert (folder / f"odznak_{n}.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
