"""Stav hry (menu / lobby / načítání / zápas / po zápase) a co ukázat v Discordu.

    MENU ──tlačítko PLAY──> LOBBY ──tlačítko zmizí po READY/CANCEL──> LOADING
      ^                       ^                                          │ karta s mapou
      │                       └────────── tlačítko je zpátky ────────────┤
      │                                                                  v
      └──────── nic dlouho ──────── POSTGAME <──── konec zápasu ──── MATCH
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from catalog import KILLER, SURVIVOR, Catalog, Character, MapMatch, compact
from detect import QUEUED, Observation, ScanContext
from images import Images

log = logging.getLogger("dbd")

OFF, MENU, LOBBY, LOADING, MATCH, POSTGAME = "OFF", "MENU", "LOBBY", "LOADING", "MATCH", "POSTGAME"

TEXTS = {
    "cs": {
        KILLER: "Killer", SURVIVOR: "Survivor",
        MENU: "V menu", LOBBY: "V lobby", "waiting": "Čeká na zápas",
        LOADING: "Načítá se zápas", MATCH: "V zápase", POSTGAME: "Po zápase",
    },
    "en": {
        KILLER: "Killer", SURVIVOR: "Survivor",
        MENU: "In the menus", LOBBY: "In the lobby", "waiting": "Waiting for a match",
        LOADING: "Loading into a match", MATCH: "In a match", POSTGAME: "After the match",
    },
}
PHASE_LOG = {OFF: "hra neběží", MENU: "v menu", LOBBY: "v lobby", LOADING: "načítá se zápas",
             MATCH: "v zápase", POSTGAME: "po zápase"}

BUTTON_GONE_AFTER = 3        # kolikrát po sobě tlačítko chybí, než to bereme vážně
LOADING_TIMEOUT = 150.0      # s; pak už určitě běží zápas, i když jsme nepřečetli mapu
LOADING_GUESS = 45.0         # s; odhad délky načítání, když mapu nepřečteme
POSTGAME_TIMEOUT = 25.0      # s bez obrazovky konce a bez lobby -> menu
MATCH_MAX = 3 * 3600.0


def _clip(text: str | None) -> str | None:
    if not text:
        return None
    text = text if len(text) <= 128 else text[:127] + "…"
    return text if len(text) >= 2 else text + " "


class Store:
    """Pamatuje si poslední postavy a herní jméno mezi spuštěními (stav.json)."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.data: dict = {}
        if path and path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, **values) -> None:
        changed = False
        for k, v in values.items():
            if self.data.get(k) != v:
                self.data[k] = v
                changed = True
        if changed and self.path:
            try:
                self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                log.debug("Nepodařilo se uložit stav: %s", e)


class Tracker:
    def __init__(self, catalog: Catalog, store: Store, config: dict, images: Images | None = None) -> None:
        self.catalog = catalog
        self.store = store
        self.texts = TEXTS.get(str(config.get("jazyk", "cs")).lower(), TEXTS["cs"])
        self.show_map = bool(config.get("ukazat_mapu", True))
        self.show_time = bool(config.get("ukazat_cas_zapasu", True))
        self.show_base = bool(config.get("ukazat_zakladni_postavu", True))
        self.show_prestige = bool(config.get("ukazat_prestige", True))
        self.prestige: dict[str, int] = {str(k): int(v) for k, v in (store.get("prestige") or {}).items()
                                         if isinstance(v, (int, float))}
        self.images = images if images is not None else Images(None, config, offline=True)
        fixed_name = str(config.get("jmeno_ve_hre") or "").strip()
        self.own_name: str | None = fixed_name or store.get("own_name")
        self._own_fixed = bool(fixed_name)
        self._own_votes: list[str] = []

        self.last: dict[str, Character | None] = {
            KILLER: catalog.character(store.get("last_killer"), KILLER),
            SURVIVOR: catalog.character(store.get("last_survivor"), SURVIVOR),
        }
        self.role: str | None = store.get("role") if store.get("role") in (KILLER, SURVIVOR) else None
        self.character: Character | None = self.last.get(self.role) if self.role else None

        self.phase = OFF
        self.phase_since = time.time()
        self.game_start: float | None = None
        self.button: str | None = None
        self.button_missing = 0
        self.loading_since: float | None = None
        self.match_start: float | None = None
        self.match_start_exact = False
        self.map: MapMatch | None = None
        self.end_seen_at = 0.0
        self.board_done = False
        self.lobby_survivor_done = False
        self.survivor_votes = 0
        self.match_lobby_votes = 0

    # ------------------------------------------------------------ helpers
    def _go(self, phase: str, now: float, why: str = "") -> None:
        if phase == self.phase:
            return
        old = self.phase
        self.phase, self.phase_since = phase, now
        if phase == LOBBY and old != LOBBY:
            self.lobby_survivor_done = False
            self.button_missing = 0
        if phase == LOADING:
            self.loading_since = now
            self.map = None
        if phase == POSTGAME:
            self.board_done = False
        if phase in (MENU, LOBBY, OFF):
            self.map = None
            self.match_start = None
        log.info("Stav: %s%s", PHASE_LOG[phase], f" ({why})" if why else "")

    def _start_match(self, now: float, exact: bool, start: float | None = None) -> None:
        self._go(MATCH, now)
        self.match_start = start if start is not None else now
        self.match_start_exact = exact

    def _set_char(self, c: Character, source: str) -> None:
        self.last[c.role] = c
        if c == self.character and c.role == self.role:
            return
        self.character, self.role = c, c.role
        log.info("Postava: %s (%s, %s)", c.label(), c.role, source)
        self.store.set(role=c.role, **{f"last_{c.role}": c.name})

    def _set_prestige(self, c: Character | None, value: int | None, source: str) -> None:
        if c is None or value is None:
            return
        key = c.base or c.name  # skin sdílí prestige se základní postavou
        if self.prestige.get(key) == value:
            return
        self.prestige[key] = value
        log.info("Prestige: %s = %d (%s)", key, value, source)
        self.store.set(prestige=dict(self.prestige))

    def current_prestige(self) -> int | None:
        c = self.character
        return self.prestige.get(c.base or c.name) if c else None

    def _set_role(self, role: str, source: str) -> None:
        if role == self.role:
            return
        self.role = role
        self.character = self.last.get(role)
        who = self.character.name if self.character else "postava zatím neznámá"
        log.info("Role: %s (%s) - %s", role, source, who)
        self.store.set(role=role)

    def _vote_own_name(self, name: str) -> None:
        if self._own_fixed:
            return
        self._own_votes = (self._own_votes + [name])[-3:]
        same = [n for n in self._own_votes if compact(n) == compact(name)]
        if len(same) >= 2 and (self.own_name is None or compact(self.own_name) != compact(name)):
            self.own_name = name
            log.info("Herní jméno: %s", name)
            self.store.set(own_name=name)

    # ------------------------------------------------------------ inputs
    def game_running(self, now: float, started_at: float | None) -> None:
        if self.phase == OFF:
            self.game_start = started_at or now
            self._go(MENU, now, "hra běží")

    def game_closed(self, now: float) -> None:
        if self.phase != OFF:
            self._go(OFF, now)
            self.game_start = None

    def context(self, now: float) -> ScanContext:
        return ScanContext(
            phase=self.phase,
            map_known=self.map is not None and self.map.map is not None,
            match_age=(now - self.match_start) if (self.phase == MATCH and self.match_start) else 0.0,
            own_name=self.own_name,
            want_lobby_survivor=self.role != KILLER and not self.lobby_survivor_done,
            want_board=not self.board_done,
        )

    def update(self, obs: Observation, now: float) -> None:
        # --- kdo jsem
        if obs.own_name:
            self._vote_own_name(obs.own_name)
        if obs.header_char:
            self._set_char(obs.header_char, "menu postav")
            self._set_prestige(obs.header_char, obs.header_prestige, "menu postav")
        elif obs.header_unknown:
            role = obs.header_role or self.role
            if role in (KILLER, SURVIVOR):
                c = self.catalog.make_custom(obs.header_unknown, role)
                self._set_char(c, "menu postav, není v seznamu")
                self._set_prestige(c, obs.header_prestige, "menu postav")
        if obs.lobby_killer:
            self.survivor_votes = 0
            self._set_char(obs.lobby_killer, "lobby")
        elif obs.survivor_hint:
            self.survivor_votes += 1
            if self.survivor_votes >= 3:
                self._set_role(SURVIVOR, "lobby")
        elif obs.button_read:
            self.survivor_votes = 0
        if obs.lobby_survivor:
            self.lobby_survivor_done = True
            self._set_char(obs.lobby_survivor, "lobby")
        if obs.board is not None and obs.board.mine is not None:
            self.board_done = True
            self._set_char(obs.board.mine, "scoreboard")
            self._set_prestige(obs.board.mine, obs.board.my_prestige, "scoreboard")

        # --- kde jsem
        if obs.end_kind:
            self.end_seen_at = now
            if self.phase not in (POSTGAME, OFF):
                self._go(POSTGAME, now, {"scoreboard": "scoreboard", "bloodpoints": "bloodpoints"}.get(obs.end_kind, "výsledek"))
            return

        if obs.title is not None and (obs.title.map or obs.title.confidence >= 0.4):
            if self.phase != MATCH:
                self._start_match(now, exact=True)
                self.map = obs.title
                log.info("Zápas začal, mapa: %s", obs.title.label() or "?")
            elif self.map is None or (self.map.map is None and obs.title.map):
                self.map = obs.title
                if not self.match_start_exact:
                    self.match_start, self.match_start_exact = now, True
                log.info("Mapa: %s", obs.title.label())
            return

        if obs.match_hint:
            # 'TAB MATCH DETAILS' vpravo nahoře = začátek zápasu (i když kartu s mapou nepřečteme)
            if self.phase in (MENU, LOBBY, LOADING):
                self._start_match(now, exact=True)
                log.info("Zápas začal (mapa zatím nepřečtená)")
            elif self.phase == MATCH and not self.match_start_exact:
                self.match_start, self.match_start_exact = now, True
            return

        if obs.button_read and obs.button is not None:
            if self.phase == MATCH:
                # Ze zápasu rovnou do lobby jen po odpojení. Musí to být jasné
                # (PLAY/READY dvakrát po sobě), ať ho nespustí třeba nastavení hry.
                if obs.button == "CANCEL":
                    return
                self.match_lobby_votes += 1
                if self.match_lobby_votes < 2:
                    return
            self.match_lobby_votes = 0
            self.button = obs.button
            self.button_missing = 0
            if self.phase != LOBBY:
                self._go(LOBBY, now)
            return
        if obs.button_read:
            self.match_lobby_votes = 0

        if self.phase == LOBBY and obs.button_read:
            self.button_missing += 1
            if self.button_missing >= BUTTON_GONE_AFTER:
                if self.button not in QUEUED:
                    self._go(MENU, now)
                elif obs.menu_hint is False:
                    self._go(LOADING, now, "tlačítko zmizelo")
                # menu_hint True/None: jsi ve frontě, jen v jiném menu (bloodweb apod.)
        elif self.phase == LOADING:
            if obs.menu_hint:
                self._go(LOBBY, now, "jen jiné menu")
            elif self.loading_since is not None and now - self.loading_since >= LOADING_TIMEOUT:
                self._start_match(now, exact=False, start=min(now, self.loading_since + LOADING_GUESS))
                log.info("Zápas asi běží (mapu se nepodařilo přečíst)")
        elif self.phase == POSTGAME:
            if obs.end_button is None and now - self.end_seen_at >= POSTGAME_TIMEOUT:
                self._go(MENU, now)
        elif self.phase == MATCH:
            if self.match_start and now - self.match_start > MATCH_MAX:
                self._go(MENU, now, "zápas trvá podezřele dlouho")

    # ------------------------------------------------------------ output
    def activity(self, now: float) -> dict | None:
        if self.phase == OFF:
            return None
        T = self.texts
        char_text = self.character.label(self.show_base) if self.character else None
        prestige = self.current_prestige() if self.show_prestige else None
        p_text = f"Prestige {prestige}" if prestige is not None else None
        role_text = T[self.role] if self.role else None
        who = f"{role_text}: {char_text}" if (role_text and char_text) else role_text
        map_text = self.map.label() if (self.map is not None and self.map.label()) else None
        start = self.game_start
        if self.phase == MATCH:
            details = who or T[MATCH]
            if self.show_map and map_text:
                state = map_text
            else:
                state = T[MATCH] if who else None
            start = self.match_start
        elif self.phase == LOBBY:
            details = who or T[LOBBY]
            state = T["waiting"] if self.button in QUEUED else T[LOBBY]
            if not who:
                details, state = state, None
            elif p_text:
                state = f"{state} · {p_text}"
        else:
            label = T[self.phase]
            if self.phase == MENU and who and p_text:
                label = f"{label} · {p_text}"
            details, state = (who, label) if who else (label, None)
        hover = f"{char_text} · {p_text}" if (char_text and p_text) else char_text
        img = self.images.pick(self.phase == MATCH and self.show_map, self.role, role_text,
                               self.character, hover, self.map, map_text,
                               prestige if self.character else None, p_text)
        act = {
            "details": _clip(details),
            "state": _clip(state),
            "start": int(start) if (start and self.show_time) else None,
            "large_image": img["large_image"],
            "large_text": _clip(img["large_text"]),
            "small_image": img["small_image"],
            "small_text": _clip(img["small_text"]),
        }
        return {k: v for k, v in act.items() if v is not None}
