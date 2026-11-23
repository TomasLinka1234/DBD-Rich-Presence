"""Průběh zápasu v trackeru -> záznam do statistik a texty v Discordu."""

from datetime import datetime

import pytest
from catalog import KILLER, SURVIVOR, Catalog, MapMatch
from detect import Observation
from stats import Match, Stats
from tracker import LOBBY, MATCH, MENU, POSTGAME, STATS_ROTATE, Store, Tracker

T0 = datetime(2026, 11, 23, 21, 0).timestamp()
COAL = MapMatch("The MacMillan Estate", "Coal Tower", 1.0)


@pytest.fixture()
def cat(base_data) -> Catalog:
    return Catalog(base_data)


class FakeImages:
    """Místo obrázků z Discordu: velký obrázek = portrét s popiskem postavy."""

    def pick(self, in_match, role, role_text, character, char_text, mm, map_text, prestige=None, p_text=None):
        return {"large_image": "portret", "large_text": char_text, "small_image": None, "small_text": None}


def make(cat, cfg=None, stats=True):
    st = Stats(None) if stats else None
    return Tracker(cat, Store(None), cfg or {}, FakeImages(), stats=st), st


def to_loading(t, cat, who, role, now):
    """Menu -> postava -> lobby ve frontě -> načítání."""
    t.game_running(now, None)
    t.update(Observation(header_char=cat.character(who, role)), now)
    t.update(Observation(button_read=True, button="READY"), now + 1)
    for i in range(3):
        t.update(Observation(button_read=True, button=None, menu_hint=False), now + 2 + i)


def play(t, cat, who, role, start, length, result="k4"):
    to_loading(t, cat, who, role, start - 30)
    t.update(Observation(title=COAL), start)
    assert t.phase == MATCH
    t.update(Observation(end_kind="result", end_result=result), start + length)
    assert t.phase == POSTGAME


def test_killer_match_is_recorded(cat):
    t, st = make(cat)
    play(t, cat, "The Trapper", KILLER, T0, 600)
    act = t.activity(T0 + 601)
    assert act["details"] == "Killer: The Trapper"
    assert act["state"] == "Po zápase · 4 zabití"
    assert st.matches == []                                    # uloží se až po odchodu z obrazovky konce
    t.update(Observation(button_read=True, button="PLAY"), T0 + 640)
    assert t.phase == LOBBY
    [m] = st.matches
    assert (m.role, m.character, m.map, m.realm, m.result) == (KILLER, "The Trapper", "Coal Tower",
                                                                "The MacMillan Estate", "k4")
    assert m.duration == 600


def test_survivor_escape_and_discord_texts(cat):
    t, st = make(cat)
    play(t, cat, "Meg Thomas", SURVIVOR, T0, 500, "escaped")
    assert t.activity(T0 + 501)["state"] == "Po zápase · Útěk"
    t.update(Observation(button_read=True, button="PLAY"), T0 + 520)
    assert st.matches[0].result == "escaped"
    even = (int(T0 // STATS_ROTATE) + 2) * STATS_ROTATE      # sudý úsek: normální status
    odd = even + STATS_ROTATE                                  # lichý úsek: statistiky
    assert t.activity(even + 1)["state"] == "V lobby"
    assert t.activity(odd + 1)["state"] == "Dnes 1 zápas · 1 výhra"
    assert "1 zápas · 1 výhra" in t.activity(even + 1)["large_text"]


def test_disconnect_is_counted_without_result(cat):
    t, st = make(cat)
    to_loading(t, cat, "The Trapper", KILLER, T0 - 30)
    t.update(Observation(title=COAL), T0)
    for i in range(2):                                         # ze zápasu rovnou do lobby = odpojení
        t.update(Observation(button_read=True, button="PLAY"), T0 + 300 + i)
    assert t.phase == LOBBY
    [m] = st.matches
    assert m.result is None and m.duration >= 300


def test_short_or_guessed_matches_are_not_counted(cat):
    t, st = make(cat)
    to_loading(t, cat, "The Trapper", KILLER, T0)
    t.update(Observation(button_read=True, button=None, menu_hint=False), T0 + 200)   # vypršelo načítání
    assert t.phase == MATCH and not t.match_start_exact
    for i in range(2):
        t.update(Observation(button_read=True, button="PLAY"), T0 + 600 + i)
    assert st.matches == []
    to_loading(t, cat, "The Trapper", KILLER, T0 + 700)
    t.update(Observation(title=COAL), T0 + 740)
    for i in range(2):
        t.update(Observation(button_read=True, button="PLAY"), T0 + 770 + i)               # 30 s
    assert st.matches == []


def test_game_closed_on_end_screen_still_saves(cat):
    t, st = make(cat)
    play(t, cat, "The Trapper", KILLER, T0, 600, "k3")
    t.game_closed(T0 + 650)
    assert [m.result for m in st.matches] == ["k3"]


def test_flush(cat):
    t, st = make(cat)
    play(t, cat, "The Trapper", KILLER, T0, 600, "k2")
    t.flush()
    assert len(st.matches) == 1
    t2, st2 = make(cat)
    to_loading(t2, cat, "The Trapper", KILLER, T0)
    t2.update(Observation(title=COAL), T0 + 30)
    t2.flush()                                                 # zápas ještě běží -> nepočítat
    assert st2.matches == []


def test_killer_title_fixes_wrong_role(cat):
    t, st = make(cat)
    t.update(Observation(header_char=cat.character("The Trapper", KILLER)), T0 - 100)
    play(t, cat, "Meg Thomas", SURVIVOR, T0, 600, "k4")
    assert t.role == KILLER
    t.update(Observation(button_read=True, button="PLAY"), T0 + 640)
    assert (st.matches[0].role, st.matches[0].character) == (KILLER, "The Trapper")


def test_spectating_after_death_is_one_match(cat):
    t, st = make(cat)
    play(t, cat, "Meg Thomas", SURVIVOR, T0, 400, "sacrificed")
    t.update(Observation(), T0 + 440)                          # divá se, obrazovka konce zmizela
    assert t.phase == MENU and len(st.matches) == 1
    t.update(Observation(end_kind="scoreboard"), T0 + 700)     # konec zápasu ostatních
    t.update(Observation(button_read=True, button="PLAY"), T0 + 720)
    assert len(st.matches) == 1


def test_stats_can_be_hidden_or_off(cat):
    t, st = make(cat, {"ukazat_statistiky": False})
    play(t, cat, "The Trapper", KILLER, T0, 600)
    assert t.activity(T0 + 601)["state"] == "Po zápase"
    t.update(Observation(button_read=True, button="PLAY"), T0 + 640)
    assert len(st.matches) == 1                                # počítá se dál, jen se neukazuje
    for s in range(4):
        assert "zápas" not in t.activity(T0 + 700 + s * STATS_ROTATE).get("state", "")
    t2, _ = make(cat, stats=False)
    play(t2, cat, "The Trapper", KILLER, T0, 600)
    t2.update(Observation(button_read=True, button="PLAY"), T0 + 640)
    assert t2.activity(T0 + 700)["details"] == "Killer: The Trapper"


def test_old_matches_shown_in_hover(cat):
    st = Stats(None)
    for i in range(5):
        st.add(Match(T0 - 86400 * 3 + i * 900, T0 - 86400 * 3 + i * 900 + 600, KILLER, "The Trapper", result="k4"))
    t = Tracker(cat, Store(None), {}, FakeImages(), stats=st)
    t.game_running(T0, None)
    t.update(Observation(header_char=cat.character("The Trapper", KILLER)), T0)
    act = t.activity(T0 + 1)
    assert act["state"] == "V menu"                            # dnes nic -> status beze změny
    assert act["large_text"].endswith("5 zápasů · 5 výher")
