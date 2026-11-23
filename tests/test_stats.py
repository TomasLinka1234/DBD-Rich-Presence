"""Statistiky: výsledek z obrazovky konce, ukládání zápasů, souhrny a přehled."""

from datetime import datetime

import pytest
import stats as S
from catalog import KILLER, SURVIVOR

T0 = datetime(2026, 11, 23, 21, 0).timestamp()


@pytest.mark.parametrize("texts, want", [
    (["MATCH", "MERCILESS KILLER"], "k4"),
    (["MATCH RESULT", "RUTHLESS KILLER"], "k3"),
    (["BRUTAL KILLER"], "k2"),
    (["THE ENTITY HUNGERS..."], "k01"),
    (["ENTITY DISPLEASED"], "k01"),           # starší název
    (["MERCILESS", "KILLER"], "k4"),          # OCR rozdělí na dva řádky
    (["MERCILES5 KILLER"], "k4"),             # chyba OCR
    (["ESCAPED"], "escaped"),
    (["YOU ESCAPED!"], "escaped"),
    (["SACRIFlCED"], "sacrificed"),
    (["DEAD"], "killed"),
    (["KILLED"], "killed"),
    (["DISCONNECTED"], "left"),
])
def test_result_from_end_screen(texts, want):
    assert S.result_from_texts(texts) == want


@pytest.mark.parametrize("texts", [
    ["KILLER"], ["MATCH", "SCOREBOARD"], ["BLOODPOINTS"], ["DEADLINE"], ["THE TRAPPER"],
    ["MATCH", "BLOODPOINTS", "BRUTALITY", "DEVIOUSNESS", "HUNTER"], ["RUTHLESS"],
    ["ESCAPE THE TRIAL AND COMPLETE CHALLENGES"], ["CONTINUE"], [""], [],
])
def test_no_result_in_other_texts(texts):
    assert S.result_from_texts(texts) is None


def test_result_role():
    assert S.result_role("k3") == KILLER
    assert S.result_role("escaped") == SURVIVOR
    assert S.result_role("left") is None and S.result_role(None) is None


def test_win_definition():
    assert S.Match(0, 1, result="escaped").win is True
    assert S.Match(0, 1, result="k3").win is True
    assert S.Match(0, 1, result="k2").win is False
    assert S.Match(0, 1, result="sacrificed").win is False
    assert S.Match(0, 1, result=None).win is None


def test_save_and_load(tmp_path):
    path = tmp_path / "zapasy.jsonl"
    st = S.Stats(path)
    st.add(S.Match(T0, T0 + 600, KILLER, "The Trapper", map="Coal Tower", realm="The MacMillan Estate", result="k4"))
    st.add(S.Match(T0 + 900, T0 + 1500, SURVIVOR, "Rize Kamishiro", base="The Ghoul"))
    with open(path, "a", encoding="utf-8") as f:
        f.write("tohle není json\n{\"start\": \"x\"}\n\n")      # poškozený konec souboru nevadí
    again = S.Stats(path).matches
    assert len(again) == 2
    assert again[0].result == "k4" and again[0].map == "Coal Tower" and again[0].duration == 600
    assert again[1].who == "The Ghoul" and again[1].result is None


def test_stats_without_file_stay_in_memory():
    st = S.Stats(None)
    st.add(S.Match(T0, T0 + 60))
    assert len(st.matches) == 1


def test_game_day_starts_at_4am():
    assert S.game_day(datetime(2026, 11, 24, 1, 30).timestamp()).day == 23
    assert S.game_day(datetime(2026, 11, 24, 4, 30).timestamp()).day == 24


def _sample() -> S.Stats:
    st = S.Stats(None)
    day = 3600 * 24
    for i, (role, who, res) in enumerate([
        (KILLER, "The Trapper", "k4"), (KILLER, "The Trapper", "k2"), (SURVIVOR, "Meg Thomas", "escaped"),
        (SURVIVOR, "Meg Thomas", "sacrificed"), (SURVIVOR, "Meg Thomas", None),
    ]):
        st.add(S.Match(T0 + i * 700, T0 + i * 700 + 600, role, who, result=res))
    st.add(S.Match(T0 - 2 * day, T0 - 2 * day + 600, KILLER, "The Trapper", result="k3"))   # předevčírem
    return st


def test_today_and_character_tallies():
    st = _sample()
    t = st.today(T0 + 4000)
    assert (t.matches, t.wins, t.decided) == (5, 2, 4)
    assert st.today(T0 + 4000, KILLER).matches == 2
    trapper = st.for_character("The Trapper")
    assert (trapper.matches, trapper.wins) == (3, 2)
    assert st.today(T0 + 4000, SURVIVOR).results["?"] == 1


@pytest.mark.parametrize("n, wins, want", [
    (1, 1, "Dnes 1 zápas · 1 výhra"),
    (3, 2, "Dnes 3 zápasy · 2 výhry"),
    (5, 0, "Dnes 5 zápasů · 0 výher"),
    (22, 5, "Dnes 22 zápasů · 5 výher"),
])
def test_today_line_czech(n, wins, want):
    t = S.Tally(matches=n, wins=wins, decided=n)
    assert S.today_line(t) == want


def test_today_line_variants():
    assert S.today_line(S.Tally()) is None
    assert S.today_line(S.Tally(matches=2)) == "Dnes 2 zápasy"                 # výsledky nepřečtené
    assert S.today_line(S.Tally(matches=1, wins=1, decided=1), "en") == "Today: 1 match · 1 win"
    assert S.character_line(S.Tally(matches=23, wins=14, decided=20)) == "23 zápasů · 14 výher"


def test_report(tmp_path):
    st = _sample()
    st.add(S.Match(T0 + 5000, T0 + 5600, KILLER, "<script>alert(1)</script>", map="Coal Tower", result="k4"))
    page = S.render_html(st.matches, T0 + 6000)
    assert "<script>alert" not in page and "&lt;script&gt;" in page
    for text in ("The Trapper", "Meg Thomas", "Coal Tower", "Survivor", "Killer", "Poslední zápasy", "Útěk"):
        assert text in page
    out = S.write_report(st.matches, tmp_path / "statistiky.html", T0 + 6000)
    assert out.read_text(encoding="utf-8") == page


def test_empty_report():
    assert "Zatím tu nic není" in S.render_html([], T0)
