"""Co je zrovna na obrazovce: lobby, postava v záhlaví, karta s mapou, konec zápasu.

Všechny oblasti jsou v jednotkách VÝŠKY obrazu a měří se od levého/pravého
okraje nebo od středu. UI hry se škáluje s výškou okna a drží se okrajů,
takže to sedí na 1080p i 1440p. Oblasti jsou schválně velkorysé: RapidOCR si
text v nich najde sám, takže nevadí ani jiné nastavení velikosti UI ve hře.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from rapidfuzz import fuzz

from catalog import KILLER, SURVIVOR, Catalog, Character, MapMatch, compact, nice_case, norm, score
from ocr import Line, Ocr


@dataclass(frozen=True)
class Region:
    x0: float
    y0: float
    x1: float
    y1: float
    anchor: str = "left"  # left / right / center

    def rect(self, w: int, h: int) -> tuple[int, int, int, int]:
        if self.anchor == "left":
            l, r = self.x0 * h, self.x1 * h
        elif self.anchor == "right":
            l, r = w - self.x1 * h, w - self.x0 * h
        else:
            l, r = w / 2 + self.x0 * h, w / 2 + self.x1 * h

        def clamp(v: float, hi: int) -> int:
            return max(0, min(hi, round(v)))

        return clamp(l, w), clamp(self.y0 * h, h), clamp(r, w), clamp(self.y1 * h, h)

    def crop(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        l, t, r, b = self.rect(w, h)
        return frame[t:b, l:r]


# Tlačítko vpravo dole (PLAY / READY / CANCEL), pod ním killer, násobič, odhad času.
R_BUTTON = Region(0.03, 0.83, 0.66, 0.995, "right")
# Záhlaví vlevo nahoře v podstránkách lobby: 'THE JUDGMENT / CHARACTERS'
# a pod ním záložky 'ALL KILLERS' / 'ALL SURVIVORS' (podle nich se pozná role).
R_HEADER = Region(0.15, 0.01, 1.05, 0.20, "left")
HEADER_NAME_MAX_Y = 0.125  # jméno postavy je nad touto výškou (zbytek jsou záložky)
SUBPAGE_WORDS = ("CHARACTERS", "LOADOUT", "BLOODWEB", "CUSTOMIZATION", "CUSTOMIZATIONS", "OUTFITS", "PRESTIGE")
# Vpravo nahoře pod měnami je tvoje herní jméno.
R_OWN_NAME = Region(0.0, 0.025, 0.62, 0.125, "right")
# Survivor lobby: jména postav nad hlavami a pod nimi jména hráčů.
R_LOBBY_NAMES = Region(-0.75, 0.11, 0.75, 0.42, "center")
# Karta na začátku zápasu vlevo dole: mapa / čára / realm.
R_TITLE = Region(0.0, 0.74, 1.0, 0.96, "left")
# Konec zápasu vlevo nahoře: 'MATCH' + červený nadpis (SCOREBOARD, ESCAPED...).
R_END = Region(0.03, 0.06, 0.72, 0.33, "left")
# Řádky scoreboardu: 'POSTAVA  hráč'.
R_SCOREBOARD = Region(0.12, 0.20, 0.82, 0.76, "left")

BUTTON_WORDS = ("PLAY", "READY", "UNREADY", "CANCEL")
QUEUED = ("READY", "UNREADY", "CANCEL")
END_BUTTON_WORDS = ("CONTINUE", "SPECTATE")


# ----------------------------------------------------------------- readings
@dataclass(frozen=True)
class ButtonReading:
    word: str | None = None        # PLAY / READY / UNREADY / CANCEL
    end_word: str | None = None    # CONTINUE / SPECTATE (obrazovky po zápase)
    killer: Character | None = None
    texts: tuple[str, ...] = ()

    @property
    def survivor_hint(self) -> bool:
        """Ve frontě a pod tlačítkem není jméno killera -> hraješ survivora."""
        return self.word in QUEUED and self.killer is None


@dataclass(frozen=True)
class ScoreboardReading:
    rows: tuple[str, ...]
    killer: Character | None
    mine: Character | None
    my_prestige: int | None = None
    badges: tuple = ()   # (postava, prestige, výřez odznaku) pro každý přečtený řádek


def _texts(lines: list[Line]) -> tuple[str, ...]:
    return tuple(ln.text for ln in lines)


def read_button(ocr: Ocr, frame: np.ndarray, catalog: Catalog, now: float | None = None) -> ButtonReading:
    lines = ocr.read(R_BUTTON.crop(frame), key="button", now=now)
    word, word_s, end_word, end_s = None, 0.0, None, 0.0
    button_lines = set()
    for i, ln in enumerate(lines):
        for w in norm(ln.text).split():
            if len(w) < 4:
                continue
            for bw in BUTTON_WORDS:
                s = fuzz.ratio(w, bw)
                if s >= 80 and s > word_s:
                    word, word_s = bw, s
                    button_lines.add(i)
            for ew in END_BUTTON_WORDS:
                s = fuzz.ratio(w, ew)
                if s >= 80 and s > end_s:
                    end_word, end_s = ew, s
                    button_lines.add(i)
    killer, ks = None, 0.0
    if word is not None:
        for i, ln in enumerate(lines):
            if i in button_lines:
                continue
            k, s = catalog.match_character(ln.text, (KILLER,), "contains", 88)
            if k is not None and s > ks:
                killer, ks = k, s
    return ButtonReading(word, end_word, killer, _texts(lines))


@dataclass(frozen=True)
class HeaderReading:
    char: Character | None = None    # postava nebo skin ze seznamu
    unknown: str | None = None       # jméno, které v seznamu není (nový skin apod.)
    role_hint: str | None = None     # podle záložky ALL KILLERS / ALL SURVIVORS
    prestige: int | None = None      # číslo v odznaku vlevo od jména
    texts: tuple[str, ...] = ()
    badge: object = None             # výřez odznaku (obrázek), když se prestige přečetl


def read_badge_number(ocr: Ocr, crop: np.ndarray) -> int | None:
    return read_badge(ocr, crop)[0]


def read_badge(ocr: Ocr, crop: np.ndarray) -> tuple[int | None, tuple[float, float] | None]:
    """Číslo (prestige) v kulatém odznaku: vezme jen nejsvětlejší neutrální pixely
    (bílé číslice), zahodí pozadí odznaku i červený vykřičník a přečte to.
    Vrací (číslo, střed číslic ve výřezu)."""
    import cv2
    import re as _re

    if crop is None or crop.size == 0 or min(crop.shape[:2]) < 8:
        return None, None
    b, g, r = (crop[..., i].astype(np.int16) for i in range(3))
    mx = np.maximum(np.maximum(b, g), r)
    mn = np.minimum(np.minimum(b, g), r)
    thr = max(105.0, float(np.percentile(mn, 99.0)) - 40.0)
    mask = ((mn > thr) & (mx - mn < 60)).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(mask, 8)
    comps = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= 12]
    if not comps:
        return None, None
    H, W = mask.shape
    main = max(comps, key=lambda i: st[i, cv2.CC_STAT_AREA] - 0.5 * abs(cen[i][0] - W / 2) - 0.5 * abs(cen[i][1] - H / 2))
    mx0, my0, mw, mh = (int(v) for v in st[main, :4])
    keep = [main]
    for i in comps:
        if i == main:
            continue
        x, y, w, hh = (int(v) for v in st[i, :4])
        overlap = min(y + hh, my0 + mh) - max(y, my0)
        if overlap >= 0.6 * mh and hh >= 0.6 * mh and abs((x + w / 2) - (mx0 + mw / 2)) <= 2.2 * mh:
            keep.append(i)
    sel = np.isin(lab, keep)
    ys, xs = np.nonzero(sel)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    pad = max(4, (y1 - y0) // 3)
    out = np.full((y1 - y0 + 2 * pad, x1 - x0 + 2 * pad), 255, np.uint8)
    out[pad:pad + (y1 - y0), pad:pad + (x1 - x0)][sel[y0:y1, x0:x1]] = 0
    out = cv2.resize(out, None, fx=48 / out.shape[0], fy=48 / out.shape[0], interpolation=cv2.INTER_CUBIC)
    txt = ocr.rec_only(cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)).upper()
    digits = _re.sub(r"\D", "", txt.replace("O", "0").replace("I", "1").replace("L", "1"))
    center = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    if digits and len(digits) <= 3 and int(digits) <= 100:
        return int(digits), center
    return None, center


def _badge_in(ocr: Ocr, frame: np.ndarray, x0: float, y0: float, x1: float, y1: float,
              text_h: float) -> tuple[int | None, np.ndarray | None]:
    """Přečte odznak prestige v obdélníku (pixely snímku) a vrátí (číslo,
    čtvercový výřez celého odznaku tak, jak ho ukazuje hra)."""
    h, w = frame.shape[:2]
    x0, x1 = int(max(0, x0)), int(min(w, x1))
    y0, y1 = int(max(0, y0)), int(min(h, y1))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None, None
    value, center = read_badge(ocr, frame[y0:y1, x0:x1])
    badge = None
    if value is not None and center is not None:
        # Odznak má průměr zhruba 2,5-2,8x výšky písma vedle; střed = střed číslic.
        cx, cy = x0 + center[0], y0 + center[1]
        half = 1.6 * text_h
        bx0, bx1 = int(max(0, cx - half)), int(min(w, cx + half))
        by0, by1 = int(max(0, cy - half)), int(min(h, cy + half))
        if bx1 - bx0 >= 16 and by1 - by0 >= 16:
            badge = frame[by0:by1, bx0:bx1].copy()
    return value, badge


def _badge_left_of(ocr: Ocr, frame: np.ndarray, region: Region, name: Line) -> tuple[int | None, np.ndarray | None]:
    """Odznak prestige vlevo od jména v záhlaví (souřadnice jména jsou uvnitř výřezu `region`)."""
    h, w = frame.shape[:2]
    l, t, _, _ = region.rect(w, h)
    nx0, ny0, ny1 = l + name.x0, t + name.y0, t + name.y1
    return _badge_in(ocr, frame, nx0 - 0.085 * h, ny0 - 0.012 * h, nx0 - 0.008 * h, ny1 + 0.035 * h, ny1 - ny0)


def _prestige_near(lines: list[Line], name: Line, h: int) -> int | None:
    """Číslo prestige v kulatém odznaku vlevo od jména postavy."""
    best, best_h = None, 0.0
    for ln in lines:
        t = ln.text.strip().replace("O", "0").replace("o", "0")
        if not t.isdigit() or ln.score < 0.7:
            continue
        val = int(t)
        if not (0 <= val <= 100):
            continue
        if not (name.x0 - 0.16 * h <= ln.x1 <= name.x0 + 0.01 * h):
            continue
        if not (name.y0 - 0.035 * h <= ln.cy <= name.y1 + 0.045 * h):
            continue
        hgt = ln.y1 - ln.y0
        if hgt > best_h:
            best, best_h = val, hgt
    return best


def _clean_name(text: str) -> str | None:
    t = norm(text)
    words = t.split()
    letters = sum(ch.isalpha() for ch in t)
    if not (1 <= len(words) <= 5) or letters < 3 or letters < 0.7 * len(t.replace(" ", "")):
        return None
    if any(score(w, compact(t)) >= 85 for w in SUBPAGE_WORDS):
        return None
    return nice_case(t)


def read_header(ocr: Ocr, frame: np.ndarray, catalog: Catalog, now: float | None = None) -> HeaderReading:
    h = frame.shape[0]
    lines = ocr.read(R_HEADER.crop(frame), key="header", now=now)
    top_limit = (HEADER_NAME_MAX_Y - R_HEADER.y0) * h
    role_hint = None
    for ln in lines:
        c = compact(ln.text)
        if score("ALLKILLERS", c) >= 85:
            role_hint = KILLER
        elif score("ALLSURVIVORS", c) >= 85:
            role_hint = SURVIVOR
    top = [ln for ln in lines if ln.y1 <= top_limit]
    best, bs, best_ln = None, 0.0, None
    for ln in top:
        c, s = catalog.match_character(ln.text, (KILLER, SURVIVOR), "exact", 88)
        if c is not None and s > bs:
            best, bs, best_ln = c, s, ln
    if best is not None:
        prestige, badge = _badge_left_of(ocr, frame, R_HEADER, best_ln)
        if prestige is None:
            prestige = _prestige_near(lines, best_ln, h)
        return HeaderReading(best, None, role_hint, prestige, _texts(lines), badge)
    # Neznámé jméno: řádek těsně nad 'CHARACTERS' / 'LOADOUT'.
    for sub in top:
        c = compact(sub.text)
        if max(score(w, c) for w in SUBPAGE_WORDS) < 85:
            continue
        for ln in top:
            if ln is sub:
                continue
            gap = sub.y0 - ln.y1
            if -0.012 * h <= gap <= 0.03 * h and abs(ln.x0 - sub.x0) <= 0.03 * h:
                name = _clean_name(ln.text)
                if name:
                    prestige, badge = _badge_left_of(ocr, frame, R_HEADER, ln)
                    if prestige is None:
                        prestige = _prestige_near(lines, ln, h)
                    return HeaderReading(None, name, role_hint, prestige, _texts(lines), badge)
    return HeaderReading(None, None, role_hint, None, _texts(lines))


def read_own_name(ocr: Ocr, frame: np.ndarray, now: float | None = None) -> str | None:
    """Herní jméno vpravo nahoře pod měnami (nejnižší řádek s písmeny)."""
    lines = ocr.read(R_OWN_NAME.crop(frame), key="own", now=now)
    cands = []
    for ln in lines:
        c = compact(ln.text)
        letters = sum(ch.isalpha() for ch in c)
        if letters < 2 or "FPS" in c or "MATCHDETAILS" in c or c in ("TAB",):
            continue
        cands.append(ln)
    if not cands:
        return None
    name = max(cands, key=lambda ln: ln.y1).text.strip()
    return name if len(compact(name)) >= 2 else None


def read_top_right(ocr: Ocr, frame: np.ndarray, own_name: str | None, now: float | None = None) -> str | None:
    """Co je vpravo nahoře?
    'menu'  = měny / tvoje jméno (jsi v menu, třeba v bloodwebu)
    'match' = nápověda 'TAB MATCH DETAILS' (prvních pár sekund zápasu)
    None    = nic (načítání, zápas)"""
    lines = ocr.read(R_OWN_NAME.crop(frame), key="own", now=now)
    for ln in lines:
        c = compact(ln.text)
        if not c or "FPS" in c:
            continue
        if score("MATCHDETAILS", c, "contains") >= 85:
            return "match"
        if own_name and own_name_score(own_name, ln.text) >= 80:
            return "menu"
        digits = sum(ch.isdigit() for ch in c)
        if digits >= 3 and digits >= 0.6 * len(c):
            return "menu"
    return None


def read_menu_hint(ocr: Ocr, frame: np.ndarray, own_name: str | None, now: float | None = None) -> bool:
    return read_top_right(ocr, frame, own_name, now) == "menu"


def own_name_score(own: str, text: str) -> float:
    o, t = compact(own), compact(text)
    if not o or not t:
        return 0.0
    s = fuzz.ratio(o, t)
    if len(o) >= 5 and len(t) >= len(o):
        s = max(s, fuzz.partial_ratio(o, t))
    return float(s)


def read_lobby_survivor(ocr: Ocr, frame: np.ndarray, catalog: Catalog, own_name: str,
                        now: float | None = None) -> tuple[Character | None, tuple[str, ...]]:
    """Survivor lobby: najde tvoje jméno a postavu napsanou těsně nad ním."""
    h = frame.shape[0]
    lines = ocr.read(R_LOBBY_NAMES.crop(frame), key="lobbynames", now=now)
    best, bs = None, 0.0
    for mine in lines:
        ms = own_name_score(own_name, mine.text)
        if ms < 82:
            continue
        for ln in lines:
            if ln is mine:
                continue
            gap = mine.y0 - ln.y1
            if not (-0.012 * h <= gap <= 0.06 * h) or abs(ln.cx - mine.cx) > 0.12 * h:
                continue
            c, s = catalog.match_character(ln.text, (SURVIVOR,), "exact", 85)
            if c is not None and s + ms > bs:
                best, bs = c, s + ms
    return best, _texts(lines)


def read_title_card(ocr: Ocr, frame: np.ndarray, catalog: Catalog, strict: bool,
                    now: float | None = None) -> tuple[MapMatch | None, tuple[str, ...]]:
    lines = ocr.read(R_TITLE.crop(frame), key="title", now=now)
    texts = _texts(lines)
    return catalog.match_title_card(list(texts), strict=strict), texts


def end_gate(frame: np.ndarray) -> bool:
    """Levná kontrola bez OCR: je vlevo nahoře trochu čistě červené barvy?"""
    crop = R_END.crop(frame)
    if crop.size == 0:
        return False
    small = crop[::2, ::2]
    b = small[..., 0].astype(np.int16)
    g = small[..., 1].astype(np.int16)
    r = small[..., 2].astype(np.int16)
    red = float(((r > 150) & (g < 80) & (b < 80)).mean())
    return red >= 0.006


def read_end_screen(ocr: Ocr, frame: np.ndarray, now: float | None = None) -> tuple[str | None, tuple[str, ...]]:
    lines = ocr.read(R_END.crop(frame), key="end", now=now)
    texts = _texts(lines)
    comp = [compact(t) for t in texts]
    label = any(score("MATCH", c) >= 95 or score("MATCHRESULT", c) >= 85 for c in comp)
    board = max((score("SCOREBOARD", c) for c in comp), default=0.0)
    bp = max((score("BLOODPOINTS", c, "contains") for c in comp), default=0.0)
    if board >= 85 and (label or board >= 92):
        return "scoreboard", texts
    if bp >= 85 and (label or bp >= 92):
        return "bloodpoints", texts
    if label and any(sum(ch.isalpha() for ch in c) >= 5 and score("MATCH", c) < 95
                     and score("MATCHRESULT", c) < 85 for c in comp):
        return "result", texts
    return None, texts


def read_scoreboard(ocr: Ocr, frame: np.ndarray, catalog: Catalog, own_name: str | None,
                    now: float | None = None) -> ScoreboardReading:
    lines = ocr.read(R_SCOREBOARD.crop(frame), key="board", now=now)
    rows: list[tuple[Line, Character]] = []
    for ln in lines:
        c, s = catalog.match_character(ln.text, (KILLER, SURVIVOR), "prefix", 85)
        if c is not None:
            rows.append((ln, c))
    killer = next((c for _, c in rows if c.role == KILLER), None)
    mine, mine_ln = None, None
    if own_name:
        o = compact(own_name)
        scored = []
        for ln, c in rows:
            t = compact(ln.text)
            rest = t[len(compact(c.name)):]
            s = fuzz.ratio(o, rest) if rest else 0.0
            if len(o) >= 5:
                s = max(s, fuzz.partial_ratio(o, rest)) if len(rest) >= len(o) else s
            scored.append((float(s), c, ln))
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored and scored[0][0] >= 80 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 8):
            mine, mine_ln = scored[0][1], scored[0][2]
    # Odznak s prestige je u každého řádku vlevo pod jménem.
    h, w = frame.shape[:2]
    top = R_SCOREBOARD.rect(w, h)[1]
    badges, prestige = [], None
    for ln, c in rows:
        row_y1 = top + ln.y1
        value, crop = _badge_in(ocr, frame, 0.02 * h, row_y1 - 0.005 * h, 0.135 * h, row_y1 + 0.075 * h,
                                ln.y1 - ln.y0)
        if value is not None:
            badges.append((c, value, crop))
        if ln is mine_ln:
            prestige = value
    if mine is not None and prestige is None:
        row_y1 = top + mine_ln.y1
        badge = Region(0.02, (row_y1 - 0.005 * h) / h, 0.135, (row_y1 + 0.075 * h) / h, "left")
        for ln in ocr.read(badge.crop(frame), key=None, now=now):
            t = ln.text.strip().replace("O", "0").replace("o", "0")
            if t.isdigit() and 0 <= int(t) <= 100:
                prestige = int(t)
                break
    return ScoreboardReading(tuple(ln.text for ln, _ in rows), killer, mine, prestige, tuple(badges))


# ----------------------------------------------------------------- scanner
@dataclass
class ScanContext:
    """Co scanner potřebuje vědět o stavu hry, aby nečetl zbytečně."""
    phase: str = "MENU"
    map_known: bool = False
    match_age: float = 0.0
    own_name: str | None = None
    want_lobby_survivor: bool = False
    want_board: bool = False


@dataclass
class Observation:
    button_read: bool = False
    button: str | None = None
    end_button: str | None = None
    lobby_killer: Character | None = None
    survivor_hint: bool = False
    header_char: Character | None = None
    header_unknown: str | None = None
    header_role: str | None = None
    header_prestige: int | None = None
    header_badge: object = None
    own_name: str | None = None
    lobby_survivor: Character | None = None
    menu_hint: bool | None = None
    match_hint: bool = False
    title: MapMatch | None = None
    end_kind: str | None = None
    board: ScoreboardReading | None = None
    debug: dict[str, tuple[str, ...]] = field(default_factory=dict)


class Scanner:
    """Rozhoduje, co a jak často číst, aby OCR nebralo hře výkon."""

    def __init__(self, ocr: Ocr, catalog: Catalog) -> None:
        self.ocr = ocr
        self.catalog = catalog
        self._last: dict[str, float] = {}

    def _due(self, name: str, now: float, every: float) -> bool:
        if now - self._last.get(name, -1e9) >= every:
            self._last[name] = now
            return True
        return False

    def scan(self, frame: np.ndarray, ctx: ScanContext, now: float) -> Observation:
        obs = Observation()
        ph = ctx.phase
        cat, ocr = self.catalog, self.ocr
        h, w = frame.shape[:2]
        if h > 1100:  # 1440p / 4K: zmenšit na 1080p, OCR je pak rychlejší a funguje stejně
            import cv2

            frame = cv2.resize(frame, (round(w * 1080 / h), 1080), interpolation=cv2.INTER_AREA)

        # Tlačítko lobby. V zápase stačí občas (návrat do lobby po odpojení).
        if self._due("button", now, 6.0 if ph == "MATCH" else 0.0):
            b = read_button(ocr, frame, cat, now)
            obs.button_read = True
            obs.button, obs.end_button = b.word, b.end_word
            obs.lobby_killer, obs.survivor_hint = b.killer, b.survivor_hint
            obs.debug["button"] = b.texts
        lobby = obs.button is not None

        # Konec zápasu: levná kontrola barvy, OCR jen když tam něco červeného je.
        # (Když je vidět tlačítko lobby, konec zápasu to být nemůže.)
        if not lobby and self._due("end", now, 2.5 if ph == "MATCH" else 1.0) and end_gate(frame):
            obs.end_kind, obs.debug["end"] = read_end_screen(ocr, frame, now)

        own = ctx.own_name
        if lobby or obs.end_kind == "scoreboard":
            if not own and self._due("own", now, 4.0):
                obs.own_name = read_own_name(ocr, frame, now)
                own = obs.own_name or own
        if lobby:
            if self._due("header", now, 2.0):
                hr = read_header(ocr, frame, cat, now)
                obs.header_char, obs.header_unknown, obs.header_role = hr.char, hr.unknown, hr.role_hint
                obs.header_prestige, obs.header_badge = hr.prestige, hr.badge
                obs.debug["header"] = hr.texts
            if ((ctx.want_lobby_survivor or obs.survivor_hint) and obs.button in QUEUED and own
                    and self._due("lobbynames", now, 3.0)):
                obs.lobby_survivor, obs.debug["lobbynames"] = read_lobby_survivor(ocr, frame, cat, own, now)

        # Vpravo nahoře: měny (= jen jiné menu) nebo 'TAB MATCH DETAILS' (= začal zápas)?
        if (obs.button_read and not lobby and obs.end_kind is None and ph in ("LOBBY", "LOADING", "MENU")
                and self._due("topright", now, 2.5 if ph == "MENU" else 0.0)):
            where = read_top_right(ocr, frame, own, now)
            obs.menu_hint = where == "menu"
            obs.match_hint = where == "match"

        # Karta s mapou na začátku zápasu.
        if not lobby and obs.end_kind is None:
            every, strict = None, False
            if ph in ("LOADING", "LOBBY"):
                every = 0.0
            elif ph == "MATCH" and not ctx.map_known and ctx.match_age < 150:
                every = 0.8 if ctx.match_age < 25 else 3.0
            elif ph in ("MENU", "POSTGAME"):
                every, strict = 2.5, True
            if every is not None and self._due("title", now, every):
                obs.title, obs.debug["title"] = read_title_card(ocr, frame, cat, strict, now)

        if obs.end_kind == "scoreboard" and ctx.want_board and self._due("board", now, 1.5):
            obs.board = read_scoreboard(ocr, frame, cat, own, now)
            obs.debug["board"] = obs.board.rows
        return obs


def read_everything(ocr: Ocr, frame: np.ndarray, catalog: Catalog, own_name: str | None = None) -> dict:
    """Testovací režim: přečte všechno najednou (bez plánování)."""
    out: dict = {}
    b = read_button(ocr, frame, catalog)
    out["tlacitko"] = b.word or b.end_word
    out["killer_pod_tlacitkem"] = b.killer.label() if b.killer else None
    out["survivor_ve_fronte"] = b.survivor_hint
    hr = read_header(ocr, frame, catalog)
    out["postava_v_zahlavi"] = hr.char.label() if hr.char else (f"{hr.unknown} (není v seznamu)" if hr.unknown else None)
    out["role_v_zahlavi"] = hr.role_hint
    out["prestige"] = hr.prestige
    seen = read_own_name(ocr, frame)
    out["herni_jmeno"] = seen
    name = own_name or seen
    if name:
        s, _ = read_lobby_survivor(ocr, frame, catalog, name)
        out["survivor_v_lobby"] = s.label() if s else None
    where = read_top_right(ocr, frame, name)
    out["menu_vpravo_nahore"] = where == "menu"
    out["zacatek_zapasu"] = where == "match"
    m, _ = read_title_card(ocr, frame, catalog, strict=False)
    out["mapa"] = m.label() if m else None
    out["konec_zapasu_barva"] = end_gate(frame)
    kind, _ = read_end_screen(ocr, frame)
    out["konec_zapasu"] = kind
    if kind == "scoreboard":
        sb = read_scoreboard(ocr, frame, catalog, name)
        out["scoreboard_killer"] = sb.killer.label() if sb.killer else None
        out["scoreboard_moje_postava"] = sb.mine.label() if sb.mine else None
        out["scoreboard_moje_prestige"] = sb.my_prestige
    return out
