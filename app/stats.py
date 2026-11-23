"""Statistiky odehraných zápasů.

Každý zápas je jeden řádek v %APPDATA%\\DbD Rich Presence\\zapasy.jsonl, třeba:
    {"start": 1795449695, "end": 1795450400, "role": "KILLER", "character": "The Krasue",
     "base": null, "map": "Rotten Fields", "realm": "Coldwind Farm", "result": "k4", "prestige": 6}

Výsledek se čte z obrazovky konce zápasu (Tally Screen):
    survivor  ESCAPED -> escaped, SACRIFICED -> sacrificed, DEAD / KILLED -> killed
    killer    MERCILESS KILLER -> k4, RUTHLESS KILLER -> k3, BRUTAL KILLER -> k2,
              THE ENTITY HUNGERS... (dřív ENTITY DISPLEASED) -> k01 (0-1 zabití)
    DISCONNECTED / ABANDONED -> left
Když se obrazovka konce nepřečte, zůstane výsledek None (nezjištěno) a do výher se nepočítá.

Výhra = útěk (survivor) nebo aspoň 3 zabití (killer).
Soubor je jen u tebe v počítači, nikam se neposílá.
"""

from __future__ import annotations

import html
import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from rapidfuzz import fuzz

from catalog import KILLER, SURVIVOR, compact

log = logging.getLogger("dbd")

DAY_START_HOUR = 4          # "dnes" začíná ve 4:00, ať se noční hraní po půlnoci nerozdělí
MIN_MATCH_SECONDS = 60.0    # kratší "zápasy" bez obrazovky konce jsou spíš omyl než zápas

SURVIVOR_RESULTS = ("escaped", "sacrificed", "killed")
KILLER_RESULTS = ("k4", "k3", "k2", "k01")
WINS = {"escaped", "k4", "k3"}
LOSSES = {"sacrificed", "killed", "left", "k2", "k01"}

RESULT_TEXT = {
    "cs": {"escaped": "Útěk", "sacrificed": "Obětování", "killed": "Smrt", "left": "Odpojení",
           "k4": "4 zabití", "k3": "3 zabití", "k2": "2 zabití", "k01": "0–1 zabití"},
    "en": {"escaped": "Escaped", "sacrificed": "Sacrificed", "killed": "Killed", "left": "Disconnected",
           "k4": "4 kills", "k3": "3 kills", "k2": "2 kills", "k01": "0–1 kills"},
}

# Nápisy na obrazovce konce zápasu. Killer nejdřív ('MERCILESS KILLER' obsahuje 'KILLE…')
# a celé tituly, ať se nesplete třeba kategorie bodů 'BRUTALITY' s 'BRUTAL KILLER'.
_KILLER_TITLES = (("MERCILESSKILLER", "k4"), ("RUTHLESSKILLER", "k3"), ("BRUTALKILLER", "k2"),
                  ("ENTITYHUNGERS", "k01"), ("ENTITYDISPLEASED", "k01"))
_SURVIVOR_WORDS = (("ESCAPED", "escaped"), ("SACRIFICED", "sacrificed"), ("KILLED", "killed"),
                   ("DEAD", "killed"), ("DISCONNECTED", "left"), ("ABANDONED", "left"))


def result_from_texts(texts: Iterable[str]) -> str | None:
    """Výsledek zápasu z textů přečtených vlevo nahoře na obrazovce konce zápasu."""
    lines = [c for c in (compact(t) for t in texts) if c]
    joined = "".join(lines)                    # OCR někdy rozdělí titul na dva řádky
    for phrase, res in _KILLER_TITLES:
        for c in (*lines, joined):
            if len(c) >= len(phrase) - 2 and fuzz.partial_ratio(phrase, c) >= 87:
                return res
    for c in lines:
        for word, res in _SURVIVOR_WORDS:
            if len(word) <= 4:
                if c == word:                       # krátké slovo: jen přesně ('DEAD')
                    return res
            elif fuzz.ratio(word, c) >= 85 or (word in c and len(c) <= len(word) + 8):
                return res                          # i 'SACRIFlCED', 'YOU ESCAPED'; ne 'KILLER'
    return None


def result_role(result: str | None) -> str | None:
    if result in KILLER_RESULTS:
        return KILLER
    if result in SURVIVOR_RESULTS:
        return SURVIVOR
    return None


# ----------------------------------------------------------------- záznam
@dataclass
class Match:
    start: float
    end: float
    role: str | None = None
    character: str | None = None
    base: str | None = None        # u skinu základní postava
    map: str | None = None
    realm: str | None = None
    result: str | None = None
    prestige: int | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def win(self) -> bool | None:
        if self.result in WINS:
            return True
        if self.result in LOSSES:
            return False
        return None

    @property
    def who(self) -> str | None:
        """Postava pro statistiky: skin se počítá k základní postavě (Rize -> The Ghoul)."""
        return self.base or self.character

    def to_json(self) -> str:
        d = asdict(self)
        d["start"], d["end"] = round(self.start), round(self.end)
        return json.dumps({k: v for k, v in d.items() if v is not None}, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> Match | None:
        try:
            m = cls(start=float(d["start"]), end=float(d["end"]))
        except (KeyError, TypeError, ValueError):
            return None
        for key in ("role", "character", "base", "map", "realm", "result"):
            v = d.get(key)
            setattr(m, key, str(v) if v is not None else None)
        p = d.get("prestige")
        m.prestige = int(p) if isinstance(p, (int, float)) else None
        return m


class Stats:
    """Seznam odehraných zápasů; nový zápas se připíše na konec souboru."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.matches: list[Match] = self._load(path) if path else []

    @staticmethod
    def _load(path: Path) -> list[Match]:
        if not path.exists():
            return []
        out = []
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        m = Match.from_dict(json.loads(line))
                    except ValueError:
                        m = None
                    if m is not None:
                        out.append(m)
        except OSError as e:
            log.warning("Statistiky nejdou načíst: %s", e)
        return out

    def add(self, m: Match) -> None:
        self.matches.append(m)
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(m.to_json() + "\n")
        except OSError as e:
            log.warning("Zápas se nepodařilo uložit do statistik: %s", e)

    def tally(self, keep: Callable[[Match], bool] = lambda m: True) -> Tally:
        t = Tally()
        for m in self.matches:
            if keep(m):
                t.add(m)
        return t

    def today(self, now: float, role: str | None = None) -> Tally:
        day = game_day(now)
        return self.tally(lambda m: game_day(m.start) == day and (role is None or m.role == role))

    def for_character(self, name: str | None) -> Tally:
        return self.tally(lambda m: name is not None and m.who == name)


@dataclass
class Tally:
    matches: int = 0
    seconds: float = 0.0
    wins: int = 0
    decided: int = 0                       # zápasy se známým výsledkem
    results: Counter = field(default_factory=Counter)

    def add(self, m: Match) -> None:
        self.matches += 1
        self.seconds += m.duration
        self.results[m.result or "?"] += 1
        if m.win is not None:
            self.decided += 1
            self.wins += int(m.win)

    @property
    def win_rate(self) -> float | None:
        return self.wins / self.decided if self.decided else None


def game_day(ts: float) -> date:
    return (datetime.fromtimestamp(ts) - timedelta(hours=DAY_START_HOUR)).date()


# ----------------------------------------------------------------- texty pro Discord
def plural(n: int, one: str, few: str, many: str) -> str:
    return one if n == 1 else few if 2 <= n <= 4 else many


def count_text(n: int, lang: str = "cs") -> str:
    if lang == "en":
        return f"{n} match" + ("" if n == 1 else "es")
    return f"{n} {plural(n, 'zápas', 'zápasy', 'zápasů')}"


def wins_text(n: int, lang: str = "cs") -> str:
    if lang == "en":
        return f"{n} win" + ("" if n == 1 else "s")
    return f"{n} {plural(n, 'výhra', 'výhry', 'výher')}"


def today_line(t: Tally, lang: str = "cs") -> str | None:
    """'Dnes 4 zápasy · 3 výhry'"""
    if not t.matches:
        return None
    head = ("Today: " if lang == "en" else "Dnes ") + count_text(t.matches, lang)
    return f"{head} · {wins_text(t.wins, lang)}" if t.decided else head


def character_line(t: Tally, lang: str = "cs") -> str | None:
    """'23 zápasů · 14 výher' (do popisku obrázku postavy)"""
    if not t.matches:
        return None
    return f"{count_text(t.matches, lang)} · {wins_text(t.wins, lang)}" if t.decided else count_text(t.matches, lang)


def result_text(result: str | None, lang: str = "cs") -> str | None:
    return RESULT_TEXT.get(lang, RESULT_TEXT["cs"]).get(result or "")


# ----------------------------------------------------------------- přehled (HTML)
def _dur(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _pct(t: Tally) -> str:
    return f"{round(100 * t.win_rate)} %" if t.win_rate is not None else "–"


def _esc(v) -> str:
    return html.escape(str(v)) if v not in (None, "") else "–"


def _group(matches: list[Match], key: Callable[[Match], str | None]) -> list[tuple[str, Tally]]:
    groups: dict[str, Tally] = {}
    for m in matches:
        k = key(m) or "?"
        groups.setdefault(k, Tally()).add(m)
    return sorted(groups.items(), key=lambda kv: (-kv[1].matches, kv[0]))


def _card(title: str, t: Tally) -> str:
    word = plural(t.matches, "zápas", "zápasy", "zápasů")
    return (f'<div class="card"><div class="k">{title}</div><div class="v">{t.matches}</div>'
            f'<div class="s">{word} · výhry {_pct(t)}<br>{_dur(t.seconds)}</div></div>')


def render_html(matches: list[Match], now: float) -> str:
    stats = Stats(None)
    stats.matches = sorted(matches, key=lambda m: m.start)
    today, week = game_day(now), game_day(now).isocalendar()[:2]
    t_today = stats.tally(lambda m: game_day(m.start) == today)
    t_week = stats.tally(lambda m: game_day(m.start).isocalendar()[:2] == week)
    t_all = stats.tally()
    surv = [m for m in stats.matches if m.role == SURVIVOR]
    kill = [m for m in stats.matches if m.role == KILLER]
    updated = datetime.fromtimestamp(now).strftime("%d. %m. %Y %H:%M")

    parts = [f"""<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Statistiky · DbD Rich Presence</title>
<style>
:root {{ color-scheme: dark; }}
body {{ margin: 0; background: #0f0f11; color: #e8e6e3; font: 15px/1.45 "Segoe UI", system-ui, sans-serif; }}
main {{ max-width: 1040px; margin: 0 auto; padding: 32px 20px 48px; }}
h1 {{ font-size: 26px; margin: 0 0 4px; letter-spacing: .5px; }}
h1 span {{ color: #d6293e; }}
h2 {{ font-size: 18px; margin: 36px 0 12px; padding-bottom: 6px; border-bottom: 1px solid #2a2a2f; }}
.sub {{ color: #8d8a86; margin: 0 0 24px; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }}
.card {{ background: #18181c; border: 1px solid #26262b; border-radius: 10px; padding: 14px 16px; }}
.card .k {{ color: #8d8a86; font-size: 13px; text-transform: uppercase; letter-spacing: .8px; }}
.card .v {{ font-size: 34px; font-weight: 600; margin: 2px 0; }}
.card .s {{ color: #b5b2ad; font-size: 13px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th, td {{ padding: 7px 10px; text-align: right; border-bottom: 1px solid #222227; white-space: nowrap; }}
th:first-child, td:first-child, .t {{ text-align: left; white-space: normal; }}
th {{ color: #8d8a86; font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: .6px; }}
tr:hover td {{ background: #16161a; }}
.win {{ color: #5fd38d; }} .loss {{ color: #e0606e; }} .unk {{ color: #77746f; }}
.empty {{ color: #8d8a86; background: #18181c; border-radius: 10px; padding: 20px; }}
footer {{ margin-top: 40px; color: #6f6c68; font-size: 12px; }}
</style></head><body><main>
<h1>Statistiky <span>Dead by Daylight</span></h1>
<p class="sub">Aktualizováno {updated} · {_esc(count_text(len(stats.matches)))} celkem</p>
"""]
    if not stats.matches:
        parts.append('<p class="empty">Zatím tu nic není. Odehraj zápas a statistiky se začnou plnit samy.</p>')
    else:
        parts.append('<div class="cards">' + _card("Dnes", t_today) + _card("Tento týden", t_week)
                     + _card("Celkem", t_all) + "</div>")

        if surv:
            ts = stats.tally(lambda m: m.role == SURVIVOR)
            parts.append(f"<h2>Survivor · {count_text(ts.matches)}, útěky {_pct(ts)}</h2>")
            parts.append("<table><tr><th>Postava</th><th>Zápasy</th><th>Útěk</th><th>Obětování</th><th>Smrt</th>"
                         "<th>Odpojení</th><th>?</th><th>Útěky</th><th>Čas</th></tr>")
            for name, t in _group(surv, lambda m: m.who):
                r = t.results
                parts.append(f"<tr><td>{_esc(name)}</td><td>{t.matches}</td><td>{r['escaped']}</td>"
                             f"<td>{r['sacrificed']}</td><td>{r['killed']}</td><td>{r['left']}</td><td>{r['?']}</td>"
                             f"<td>{_pct(t)}</td><td>{_dur(t.seconds)}</td></tr>")
            parts.append("</table>")

        if kill:
            tk = stats.tally(lambda m: m.role == KILLER)
            parts.append(f"<h2>Killer · {count_text(tk.matches)}, výhry (3+ zabití) {_pct(tk)}</h2>")
            parts.append("<table><tr><th>Postava</th><th>Zápasy</th><th>4K</th><th>3K</th><th>2K</th><th>0–1K</th>"
                         "<th>Odpojení</th><th>?</th><th>Výhry</th><th>Čas</th></tr>")
            for name, t in _group(kill, lambda m: m.who):
                r = t.results
                parts.append(f"<tr><td>{_esc(name)}</td><td>{t.matches}</td><td>{r['k4']}</td><td>{r['k3']}</td>"
                             f"<td>{r['k2']}</td><td>{r['k01']}</td><td>{r['left']}</td><td>{r['?']}</td>"
                             f"<td>{_pct(t)}</td><td>{_dur(t.seconds)}</td></tr>")
            parts.append("</table>")

        maps = _group(stats.matches, lambda m: f"{m.map} ({m.realm})" if (m.map and m.realm) else (m.map or m.realm))
        parts.append("<h2>Mapy</h2><table><tr><th>Mapa</th><th>Zápasy</th><th>Výhry</th><th>Průměrná délka</th></tr>")
        for name, t in maps:
            label = "nepřečtená" if name == "?" else name
            parts.append(f"<tr><td>{_esc(label)}</td><td>{t.matches}</td><td>{_pct(t)}</td>"
                         f"<td>{_dur(t.seconds / t.matches)}</td></tr>")
        parts.append("</table>")

        parts.append('<h2>Poslední zápasy</h2><table><tr><th>Kdy</th><th class="t">Role</th>'
                     '<th class="t">Postava</th><th class="t">Mapa</th><th>Délka</th><th>Výsledek</th></tr>')
        for m in reversed(stats.matches[-30:]):
            when = datetime.fromtimestamp(m.start).strftime("%d. %m. %H:%M")
            role = {KILLER: "Killer", SURVIVOR: "Survivor"}.get(m.role or "", "–")
            who = m.character if not m.base else f"{m.character} ({m.base})"
            cls = {True: "win", False: "loss"}.get(m.win, "unk")
            res = result_text(m.result) or "nezjištěno"
            parts.append(f'<tr><td>{when}</td><td class="t">{role}</td><td class="t">{_esc(who)}</td>'
                         f'<td class="t">{_esc(m.map)}</td><td>{_dur(m.duration)}</td><td class="{cls}">{_esc(res)}</td></tr>')
        parts.append("</table>")

    parts.append("<footer>Výhra = útěk (survivor) nebo aspoň 3 zabití (killer). "
                 "„?“ = výsledek se nepodařilo přečíst z obrazovky konce zápasu. "
                 "Data jsou jen u tebe v souboru zapasy.jsonl ve složce s daty programu.</footer>"
                 "</main></body></html>")
    return "\n".join(parts)


def write_report(matches: list[Match], out: Path, now: float) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(matches, now), encoding="utf-8")
    return out
