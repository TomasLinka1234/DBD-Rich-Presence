"""Seznam postav a map a porovnávání textu z OCR s nimi (fuzzy matching).

Všechna porovnávání běží nad "kompaktním" tvarem textu: velká písmena, bez
diakritiky, bez mezer a interpunkce. OCR totiž občas spojí slova
('JILLVALENTINE') nebo vynechá apostrof ('TRICKSTERS DELUSION').
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

KILLER = "killer"
SURVIVOR = "survivor"


def norm(text: str) -> str:
    """'Léry’s Memorial' -> "LERY'S MEMORIAL"; smetí z OCR zmizí."""
    text = re.sub(r"[’‘`´]", "'", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()
    text = re.sub(r"[^A-Z0-9']+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact(text: str) -> str:
    """Jen písmena a číslice: "TRICKSTER'S DELUSION" -> 'TRICKSTERSDELUSION'."""
    return re.sub(r"[^A-Z0-9]", "", norm(text))


def slug(text: str) -> str:
    """Název obrázku v Discordu: 'Trickster's Delusion' -> 'tricksters_delusion'."""
    text = re.sub(r"[’‘`´']", "", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def nice_case(text: str) -> str:
    """'RIZE KAMISHIRO' -> 'Rize Kamishiro' (pro jména, která neznáme ze seznamu)."""
    return " ".join(w[:1].upper() + w[1:].lower() for w in text.split())


def score(key: str, text: str, mode: str = "exact") -> float:
    """0-100: jak dobře kompaktní `key` sedí na kompaktní `text`.

    exact    - řádek je přesně to jméno (záhlaví, název mapy)
    prefix   - řádek jménem začíná (scoreboard: 'KATE DENSON hracske_jmeno')
    contains - jméno je kdekoli v řádku ('THE HILLBILLY 1:04 EST. 2:27')
    """
    if not key or not text:
        return 0.0
    if mode == "exact" or len(text) < len(key) or (mode == "contains" and len(key) < 6):
        s = fuzz.ratio(key, text)
    elif mode == "prefix":
        s = fuzz.partial_ratio(key, text[: len(key) + 3])
    else:
        s = fuzz.partial_ratio(key, text)
    # Krátká jména ('THEPIG', 'ELEVEN') musí sedět skoro přesně, jinak by se
    # chytala na náhodné kousky textu.
    if len(key) <= 7 and s < 95:
        return 0.0
    return float(s)


@dataclass(frozen=True)
class Character:
    name: str
    role: str  # KILLER / SURVIVOR
    keys: tuple[str, ...]
    base: str | None = None   # u skinu: základní postava ('Rize Kamishiro' -> 'The Ghoul')
    custom: bool = False      # jméno přečtené ze hry, které není v seznamu
    img: str | None = None    # soubor portrétu na DbD wiki

    def label(self, show_base: bool = True) -> str:
        return f"{self.name} ({self.base})" if (self.base and show_base) else self.name


@dataclass(frozen=True)
class GameMap:
    name: str
    realm: str
    keys: tuple[str, ...]
    img: str | None = None    # soubor ikony mapy na DbD wiki


@dataclass(frozen=True)
class Realm:
    name: str
    keys: tuple[str, ...]
    maps: tuple[GameMap, ...]


@dataclass(frozen=True)
class MapMatch:
    realm: str | None
    map: str | None
    confidence: float  # 0..1

    def label(self) -> str:
        if self.map and self.realm:
            return f"{self.map} ({self.realm})"
        return self.map or self.realm or ""


def _keys(name: str, aliases: list[str] | tuple[str, ...] = ()) -> tuple[str, ...]:
    keys: list[str] = []
    for n in (name, *aliases):
        c = compact(n)
        if c and c not in keys:
            keys.append(c)
        # 'The MacMillan Estate' se může na kartě objevit i bez 'The'.
        if n.lower().startswith("the "):
            c2 = compact(n[4:])
            if len(c2) >= 8 and c2 not in keys:
                keys.append(c2)
    return tuple(keys)


class Catalog:
    def __init__(self, data: dict) -> None:
        portraits: dict = data.get("portraits", {}) or {}
        icons: dict = data.get("map_icons", {}) or {}
        self.killers = tuple(Character(k["name"], KILLER, _keys(k["name"], k.get("aliases", ())),
                                       img=portraits.get(k["name"]))
                             for k in data["killers"])
        self.survivors = tuple(Character(s["name"], SURVIVOR, _keys(s["name"], s.get("aliases", ())),
                                         img=portraits.get(s["name"]))
                               for s in data["survivors"])
        base_role = {c.name: c.role for c in self.killers + self.survivors}
        self.outfits = tuple(
            Character(o["name"], base_role[o["base"]], _keys(o["name"], o.get("aliases", ())), base=o["base"],
                      img=portraits.get(o["name"]))
            for o in data.get("outfits", ()) if o.get("base") in base_role)
        realms = []
        for r in data["realms"]:
            maps = tuple(GameMap(m, r["name"], _keys(m), img=icons.get(m)) for m in r["maps"])
            realms.append(Realm(r["name"], _keys(r["name"], r.get("aliases", ())), maps))
        self.realms = tuple(realms)
        self.maps = tuple(m for r in self.realms for m in r.maps)
        self.characters = self.killers + self.survivors + self.outfits
        self._by_name = {c.name: c for c in self.characters}
        self._map_by_name = {m.name: m for m in self.maps}

    def portrait_file(self, name: str | None) -> str | None:
        c = self._by_name.get(name) if name else None
        return c.img if c else None

    def map_icon_file(self, name: str | None) -> str | None:
        m = self._map_by_name.get(name) if name else None
        return m.img if m else None

    @classmethod
    def load(cls, path: Path) -> "Catalog":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def character(self, name: str | None, role: str | None = None) -> Character | None:
        """Postava podle jména. Neznámé jméno (třeba nový skin) se vytvoří, když známe roli."""
        if not name:
            return None
        c = self._by_name.get(name)
        if c is None and role in (KILLER, SURVIVOR):
            c = self.make_custom(name, role)
        return c

    def make_custom(self, name: str, role: str) -> Character:
        known = self._by_name.get(name)
        if known is not None:
            return known
        return Character(name, role, _keys(name), custom=True)

    # ---------------------------------------------------------------- matching
    @staticmethod
    def _best(items, text: str, mode: str) -> tuple[object | None, float, float]:
        """(nejlepší položka, skóre, skóre druhé nejlepší jiné položky)."""
        t = compact(text)
        best, best_s, best_len, runner = None, 0.0, 0, 0.0
        for item in items:
            item_s, item_len = 0.0, 0
            for k in item.keys:
                s = score(k, t, mode)
                if s > item_s or (s == item_s and len(k) > item_len):
                    item_s, item_len = s, len(k)
            # Shoda: vyšší skóre, při rovnosti delší jméno ('...EAST WING' > '...STATION').
            if item_s > best_s or (item_s == best_s and item_s > 0 and item_len > best_len):
                if best is not None:
                    runner = max(runner, best_s)
                best, best_s, best_len = item, item_s, item_len
            else:
                runner = max(runner, item_s)
        return best, best_s, runner

    def match_character(self, text: str, roles: tuple[str, ...] = (KILLER, SURVIVOR),
                        mode: str = "exact", min_score: float = 88) -> tuple[Character | None, float]:
        items = [c for c in self.characters if c.role in roles]
        best, s, _ = self._best(items, text, mode)
        return (best, s) if best is not None and s >= min_score else (None, s)

    def match_title_card(self, texts: list[str], strict: bool = False) -> MapMatch | None:
        """Řádky z levého dolního rohu na začátku zápasu -> mapa.

        Karta vypadá takhle:  THE PALE ROSE        (mapa, výrazně)
                              ───────────────
                              BACKWATER SWAMP      (realm, slaběji)
        strict=True: vyžaduje silnější důkaz (když nevíme, že se načítá zápas).
        """
        lines = [t for t in texts if len(compact(t)) >= 4]
        if not lines:
            return None
        realm, rs = None, 0.0
        for t in lines:
            r, s, _ = self._best(self.realms, t, "exact")
            if r is not None and s > rs:
                realm, rs = r, s
        if realm is not None and rs >= 85:
            m, ms = None, 0.0
            for t in lines:
                cand, s, _ = self._best(realm.maps, t, "exact")
                if cand is not None and s > ms:
                    m, ms = cand, s
            if m is not None and ms >= 70:
                return MapMatch(realm.name, m.name, (rs + ms) / 200)
            if len(realm.maps) == 1:
                return MapMatch(realm.name, realm.maps[0].name, 0.9 * rs / 100)
            if not strict:
                return MapMatch(realm.name, None, 0.5 * rs / 100)
            return None
        best, bs, brun = None, 0.0, 0.0
        for t in lines:
            m, s, run = self._best(self.maps, t, "exact")
            if m is not None and s > bs:
                best, bs, brun = m, s, run
        need = 92 if strict else 88
        if best is not None and bs >= need and (bs - brun >= 5 or bs >= 97):
            return MapMatch(best.realm, best.name, 0.9 * bs / 100)
        return None
