"""Obrázky v Discordu.

Výchozí rozložení (jako u Fortnite): velký obrázek = portrét postavy, malá
kulatá ikonka v jeho rohu = mapa (v zápase) nebo killer/survivor (mimo zápas).

Portréty postav a ikony map se berou z Dead by Daylight Wiki (deadbydaylight.wiki.gg):
program si jednou zjistí adresu obrázku dané stránky (postava, skin, mapa)
a uloží ji do obrazky_cache.json. Discord pak obrázek zobrazí přímo z wiki.

Vlastní obrázky mají přednost: nahrávají se do tvé Discord aplikace
(Developer Portal -> Rich Presence -> Art Assets) pod jmény podle pravidla:

    killer, survivor               ikonky rolí (assets/ikony na GitHubu)
    rotten_fields, the_pale_rose   mapy  (malá písmena, mezery -> _, bez apostrofů)
    coldwind_farm                  realm (když chybí obrázek konkrétní mapy)
    the_ghoul, rize_kamishiro      postavy / skiny (nepovinné)
    odznak_1 … odznak_100          odznaky prestige (assets/odznaky na GitHubu)
    logo                           výchozí obrázek (nepovinné)

Program si seznam nahraných obrázků sám stahuje z Discordu (veřejný seznam
assetů aplikace), takže nikdy nepošle jméno obrázku, který neexistuje.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from catalog import KILLER, SURVIVOR, Character, MapMatch, slug

log = logging.getLogger("dbd")

ASSETS_URL = "https://discord.com/api/v10/oauth2/applications/{app_id}/assets"
MAX_KEY = 32
WIKI = "https://deadbydaylight.wiki.gg"
USER_AGENT = "DbD-Rich-Presence/1.2 (osobni Discord status; obrazky se nacitaji jen jednou a ukladaji)"


PRESTIGE_URL = "https://placehold.co/256x256/{bg}/{fg}/png?text={n}&font=oswald"


BADGES_URL = "https://github.com/TomasLinka1234/DBD-Rich-Presence/tree/main/assets/odznaky"
BADGE_PREFIX = "odznak_"   # starší sada se jmenovala prestige_<číslo>


def badge_key(n: int, c: Character | None = None) -> str:
    """Jméno odznaku v Art Assets. Odznak záleží jen na úrovni prestige
    (všechny postavy se stejnou prestige mají stejný odznak)."""
    return f"{BADGE_PREFIX}{n}"


def prestige_colors(n: int) -> tuple[str, str]:
    """Barva odznaku podle úrovně (zhruba jako ve hře)."""
    if n >= 100:
        return "6b1035", "ffffff"   # P100
    if n >= 75:
        return "a8801a", "ffffff"   # zlatý rámeček
    if n >= 50:
        return "8c949c", "111111"   # stříbrný
    if n >= 25:
        return "3d4148", "ffffff"   # tmavý
    return "8a4517", "ffffff"       # bronzový


def wiki_file_url(file: str | None) -> str | None:
    """Přímá adresa obrázku na wiki podle jména souboru (záloha, když dotaz na wiki nejde)."""
    return f"{WIKI}/images/{urllib.parse.quote(file)}" if file else None


def _http_get(url: str, limit: int | None = None, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(limit) if limit else resp.read()


class WikiImages:
    """Adresa hlavního obrázku stránky na DbD wiki (portrét postavy / ikona mapy).

    Každá stránka se zjišťuje jen jednou (pak je v obrazky_cache.json), na pozadí,
    takže hlavní smyčka nikdy nečeká na internet."""

    RETRY_MISSING = 7 * 86400.0   # stránku bez obrázku zkusit znovu za týden
    RETRY_ERROR = 600.0           # při chybě sítě za 10 minut

    def __init__(self, cache_path: Path | None, enabled: bool) -> None:
        self.enabled = enabled
        self.path = cache_path
        self.cache: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._pending: set[str] = set()
        self._failed_until: dict[str, float] = {}
        self._warned = False
        if cache_path and cache_path.exists():
            try:
                self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                self.cache = {}

    def get(self, title: str | None) -> str | None:
        if not self.enabled or not title:
            return None
        with self._lock:
            entry = self.cache.get(title)
            if entry is not None and (entry.get("url") or time.time() - entry.get("t", 0) < self.RETRY_MISSING):
                return entry.get("url")
            if title in self._pending or time.time() < self._failed_until.get(title, 0):
                return None
            self._pending.add(title)
        threading.Thread(target=self._fetch, args=(title,), daemon=True).start()
        return None

    @staticmethod
    def _good(url: str | None) -> str | None:
        if not url or not url.startswith("https://") or "/images/" not in url:
            return None
        low = url.lower()
        if "wiki.png" in low or "site-logo" in low or "favicon" in low:
            return None
        return url

    def _from_api(self, title: str) -> tuple[bool, str | None]:
        q = urllib.parse.urlencode({
            "action": "query", "format": "json", "formatversion": "2", "redirects": "1",
            "prop": "pageimages", "piprop": "original", "titles": title,
        })
        data = json.loads(_http_get(f"{WIKI}/api.php?{q}").decode("utf-8"))
        pages = (data.get("query") or {}).get("pages") or []
        if not pages:
            return True, None
        page = pages[0]
        if page.get("missing"):
            return True, None
        return True, self._good((page.get("original") or {}).get("source"))

    def _from_page(self, title: str) -> tuple[bool, str | None]:
        html = _http_get(f"{WIKI}/wiki/{urllib.parse.quote(title.replace(' ', '_'))}", limit=96_000)
        m = re.search(rb'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
        if not m:
            m = re.search(rb'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', html)
        url = m.group(1).decode("utf-8", "replace").replace("&amp;", "&") if m else None
        return True, self._good(url)

    def missing(self, title: str | None) -> bool:
        """Víme jistě, že stránka obrázek nemá (nebo neexistuje)?"""
        if not title:
            return True
        with self._lock:
            entry = self.cache.get(title)
            return entry is not None and not entry.get("url")

    def _fetch(self, title: str) -> None:
        url, answered = None, False
        for method in (self._from_api, self._from_page):
            try:
                ok, found = method(title)
                answered = answered or ok
                url = url or found
            except Exception as e:
                log.debug("Wiki (%s) pro '%s' selhala: %s", method.__name__, title, e)
            if url:
                break
        with self._lock:
            self._pending.discard(title)
            if answered or url:
                self.cache[title] = {"url": url, "t": time.time()}
                self._save()
            else:
                self._failed_until[title] = time.time() + self.RETRY_ERROR
                if not self._warned:
                    self._warned = True
                    log.info("Přesnou adresu obrázku na DbD wiki se nepodařilo zjistit, "
                             "používám známé názvy souborů (zkusím to znovu později).")
        if url:
            log.info("Obrázek z wiki: %s", title)

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            log.debug("obrazky_cache.json se nepodařilo uložit: %s", e)


class Images:
    REFRESH = 300.0  # s; nově nahrané obrázky se chytí do pár minut

    def __init__(self, app_id: str | None, cfg: dict, offline: bool = False,
                 cache_path: Path | None = None, catalog=None) -> None:
        self.app_id = app_id
        self.catalog = catalog
        self.offline = offline or not app_id
        self.available: set[str] | None = None
        self.wiki = WikiImages(cache_path, enabled=not offline and bool(cfg.get("obrazky_z_wiki", True)))
        self.layout = "mapa" if str(cfg.get("velky_obrazek", "postava")).strip().lower().startswith("map") else "postava"
        self._next = 0.0
        self._busy = False
        self._logged: frozenset[str] | None = None
        self._badge_hint = False

        def opt(key: str) -> str | None:
            v = str(cfg.get(key) or "").strip()
            return v or None

        self.cfg_logo = opt("obrazek")
        self.cfg_role = {KILLER: opt("obrazek_killer"), SURVIVOR: opt("obrazek_survivor")}
        self.prestige_on = bool(cfg.get("prestige_ikona", True))
        self.prestige_template = opt("prestige_obrazek_sablona") or PRESTIGE_URL

    # ------------------------------------------------------------ asset list
    def refresh(self, now: float) -> None:
        if self.offline or self._busy or now < self._next:
            return
        self._busy = True
        self._next = now + self.REFRESH
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self) -> None:
        try:
            req = urllib.request.Request(ASSETS_URL.format(app_id=self.app_id),
                                         headers={"User-Agent": "DbD-Rich-Presence/1.1"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            names = frozenset(str(a.get("name", "")).lower() for a in data if isinstance(a, dict) and a.get("name"))
            self.available = set(names)
            if names != self._logged:
                self._logged = names
                if names:
                    shown = ", ".join(sorted(names)[:12]) + (" …" if len(names) > 12 else "")
                    log.info("Obrázky v Discord aplikaci (%d): %s", len(names), shown)
                else:
                    log.info("V Discord aplikaci zatím nejsou žádné obrázky (Art Assets).")
            self._hint_badges(names)
        except Exception as e:
            log.debug("Seznam obrázků z Discordu se nepodařilo načíst: %s", e)
            self._next = time.time() + 60.0
        finally:
            self._busy = False

    def _hint_badges(self, names: frozenset[str]) -> None:
        """Jednou připomenout, když odznaky prestige v Art Assets chybí."""
        if self._badge_hint or not self.prestige_on:
            return
        missing = [n for n in range(1, 101) if badge_key(n) not in names]
        if not missing:
            return
        self._badge_hint = True
        if len(missing) == 100:
            old = any(f"prestige_{n}" in names for n in range(1, 101))
            log.info("Odznaky prestige (%s1 … %s100) nejsou v Art Assets tvé Discord aplikace. Stáhneš je z %s. "
                     "Do té doby se ukazují %s.", BADGE_PREFIX, BADGE_PREFIX, BADGES_URL,
                     "starší odznaky" if old else "jednoduché odznaky s číslem")
        else:
            shown = ", ".join(str(n) for n in missing[:10]) + (" …" if len(missing) > 10 else "")
            k = len(missing)
            word = "odznak" if k == 1 else "odznaky" if k < 5 else "odznaků"
            log.info("V Art Assets chybí %d %s prestige (%s). Stáhneš je z %s.", k, word, shown, BADGES_URL)

    # ------------------------------------------------------------ lookup
    def has(self, key: str | None) -> str | None:
        if not key:
            return None
        if key.startswith(("http://", "https://")):
            return key
        if self.available is None:
            return None
        k = key.lower()
        if k in self.available:
            return k
        if len(k) > MAX_KEY and k[:MAX_KEY] in self.available:
            return k[:MAX_KEY]
        return None

    def _configured(self, value: str | None) -> str | None:
        """Hodnota z nastaveni.json: odkaz https://… nebo jméno obrázku."""
        if not value:
            return None
        if value.startswith(("http://", "https://")) or self.available is None:
            return value
        return self.has(value)

    def role_icon(self, role: str | None) -> str | None:
        if role not in (KILLER, SURVIVOR):
            return None
        return self._configured(self.cfg_role.get(role)) or self.has(role)

    def logo(self) -> str | None:
        return self._configured(self.cfg_logo) or self.has("logo")

    def map_image(self, mm: MapMatch | None) -> str | None:
        """Vlastní obrázek (mapa, pak realm), jinak ikona mapy z wiki."""
        if mm is None:
            return None
        keys: list[str] = []
        for name in (mm.map, mm.realm):
            if name:
                keys.append(slug(name))
                if keys[-1].startswith("the_"):
                    keys.append(keys[-1][4:])
        for k in keys:
            got = self.has(k)
            if got:
                return got
        if not mm.map or not self.wiki.enabled:
            return None
        known = wiki_file_url(self.catalog.map_icon_file(mm.map)) if self.catalog else None
        return self.wiki.get(mm.map) or known

    def char_image(self, c: Character | None) -> str | None:
        """Vlastní obrázek postavy/skinu, jinak portrét z wiki (skin, pak základní postava)."""
        if c is None:
            return None
        for name in (c.name, c.base):
            if name:
                got = self.has(slug(name))
                if got:
                    return got
        if not self.wiki.enabled:
            return None
        # Přesná adresa z wiki (zjistí se jednou), mezitím / bez internetu známý soubor.
        url = self.wiki.get(c.name) or wiki_file_url(c.img)
        if not url and c.base:
            # Skin bez vlastního obrázku (nebo se ještě hledá) -> portrét základní postavy.
            base_file = self.catalog.portrait_file(c.base) if self.catalog else None
            base_url = self.wiki.get(c.base) if self.wiki.missing(c.name) else None
            url = base_url or wiki_file_url(base_file)
        return url

    def prestige_image(self, n: int | None, c: Character | None = None) -> str | None:
        """Odznak prestige: opravdový odznak nahraný v Art Assets ('prestige_6'),
        jinak vygenerovaný odznak s číslem."""
        if n is None or not self.prestige_on:
            return None
        keys = [badge_key(n), f"prestige_{n}", f"p{n}"]   # nová sada, pak starší jména
        if c is not None:
            keys.append(f"prestige_{n}_{slug(c.base or c.name)}")   # starší pojmenování
        for k in keys:
            got = self.has(k)
            if got:
                return got
        if self.offline:
            return None
        bg, fg = prestige_colors(n)
        try:
            return self.prestige_template.format(n=n, bg=bg, fg=fg)
        except Exception:
            return PRESTIGE_URL.format(n=n, bg=bg, fg=fg)

    def pick(self, in_match: bool, role: str | None, role_text: str | None,
             character: Character | None, char_text: str | None,
             mm: MapMatch | None, map_text: str | None,
             prestige: int | None = None, prestige_text: str | None = None) -> dict:
        role_img = self.role_icon(role)
        char_img = self.char_image(character)
        map_img = self.map_image(mm) if in_match else None
        prestige_img = self.prestige_image(prestige, character)
        logo = self.logo()
        cands_large: list[tuple[str | None, str | None]]
        if self.layout == "mapa":
            cands_large = [(map_img, map_text), (char_img, char_text), (logo, "Dead by Daylight"), (role_img, role_text)]
        else:
            cands_large = [(char_img, char_text), (logo, "Dead by Daylight"), (map_img, map_text), (role_img, role_text)]
        large, large_text = next(((i, t) for i, t in cands_large if i), (None, None))
        # Malá ikonka: v zápase mapa, mimo zápas prestige (jinak ikonka role).
        if self.layout == "mapa":
            cands_small = [(prestige_img, prestige_text), (role_img, role_text)]
        elif in_match:
            cands_small = [(map_img, map_text), (prestige_img, prestige_text), (role_img, role_text)]
        else:
            cands_small = [(prestige_img, prestige_text), (role_img, role_text)]
        small, small_text = next(((i, t) for i, t in cands_small if i and i != large), (None, None))
        if large is None:
            small, small_text = None, None
        return {"large_image": large, "large_text": large_text if large else None,
                "small_image": small, "small_text": small_text}


class MapSnapshots:
    """Uloží obrázek každé nové mapy (snímek ze začátku zápasu) do složky,
    odkud ho stačí nahrát do Discord aplikace. Text karty s mapou je vlevo
    dole, proto se bere čtverec z horní části středu obrazovky."""

    def __init__(self, folder: Path, images: Images, enabled: bool) -> None:
        self.folder = folder
        self.images = images
        self.enabled = enabled
        self.done: set[str] = set()
        self._hint = False

    @staticmethod
    def crop(frame):
        import cv2

        h, w = frame.shape[:2]
        top, bottom = int(0.06 * h), int(0.80 * h)
        side = min(bottom - top, w)
        left = max(0, w // 2 - side // 2)
        sq = frame[top:top + side, left:left + side]
        return cv2.resize(sq, (1024, 1024), interpolation=cv2.INTER_CUBIC)

    def tick(self, frame, phase: str, mm: MapMatch | None, match_age: float, exact: bool) -> None:
        if not self.enabled or phase != "MATCH" or mm is None or not mm.map or not exact:
            return
        key = slug(mm.map)
        if key in self.done:
            return
        if self.images.has(key):
            self.done.add(key)
            return
        path = self.folder / f"{key}.jpg"
        if path.exists():
            self.done.add(key)
            return
        if match_age < 2.5:
            return  # ať je po prolnutí z černé
        if match_age > 15:
            self.done.add(key)
            return
        try:
            import cv2

            img = self.crop(frame)
            if float(img.mean()) < 25:
                return  # ještě tma, zkusí se příště
            self.folder.mkdir(exist_ok=True)
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if ok:
                buf.tofile(str(path))
                log.info("Uložen obrázek mapy: obrazky_k_nahrani\\%s.jpg", key)
                if not self._hint:
                    self._hint = True
                    log.info("   -> nahraj ho v Discord Developer Portalu: Rich Presence -> Art Assets "
                             "(jméno nech '%s'). Příště se mapa ukáže v profilu.", key)
        except Exception as e:
            log.debug("Obrázek mapy se nepodařilo uložit: %s", e)
        self.done.add(key)


class PrestigeBadges:
    """Záloha pro odznaky prestige (zapíná se v nastavení): program odznak
    vyřízne přímo ze hry (menu postav, vlastní řádek ve scoreboardu)
    a uloží ho do složky obrazky_k_nahrani v datech programu.
    Po nahrání do Art Assets se v Discordu použije místo vygenerovaného odznaku.
    Nic se nikam neposílá."""

    def __init__(self, folder: Path, images: Images, enabled: bool) -> None:
        self.folder = folder
        self.images = images
        self.enabled = enabled
        self.done: set[str] = set()
        self._hint = False
        self.new_files = 0

    @staticmethod
    def render(badge):
        """Zvětšit na 512x512 a okolí kolečka udělat průhledné."""
        import cv2
        import numpy as np

        img = cv2.resize(badge, (512, 512), interpolation=cv2.INTER_CUBIC)
        yy, xx = np.mgrid[0:512, 0:512]
        dist = np.sqrt((xx - 255.5) ** 2 + (yy - 255.5) ** 2)
        alpha = np.clip((0.47 * 512 - dist) * 2.0, 0, 255).astype(np.uint8)  # měkký okraj
        return np.dstack([img, alpha])

    def save(self, n: int | None, badge, c: Character | None = None) -> None:
        if not self.enabled or n is None or badge is None:
            return
        key = badge_key(n, c)
        if key in self.done:
            return
        if self.images.has(key) or self.images.has(f"p{n}"):
            self.done.add(key)
            return
        path = self.folder / f"{key}.png"
        if path.exists():
            self.done.add(key)
            return
        try:
            import cv2

            self.folder.mkdir(exist_ok=True)
            ok, buf = cv2.imencode(".png", self.render(badge))
            if ok:
                buf.tofile(str(path))
                log.info("Uložen opravdový odznak prestige %d: obrazky_k_nahrani\\%s.png", n, key)
                self.new_files += 1
                if not self._hint:
                    self._hint = True
                    log.info("   -> nahraj ho v Discord Developer Portalu: Rich Presence -> Art Assets "
                             "(jméno nech '%s'). Pak se v Discordu ukáže místo vygenerovaného odznaku.", key)
        except Exception as e:
            log.debug("Odznak prestige se nepodařilo uložit: %s", e)
        self.done.add(key)

