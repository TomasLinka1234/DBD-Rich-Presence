"""Novinky z DbD wiki: nové killery, survivoři, mapy a skiny bez aktualizace programu.

Wiki má všechno v datových modulech (Lua tabulky):
    Module:Datatable            killers, survivors, realms, maps
    Module:Datatable/Cosmetics  cosChars = skiny, které mění jméno postavy (Rize Kamishiro...)

Program si je stáhne nejvýš jednou za den (a jen když se na wiki změnily),
vytáhne z nich jména a k vestavěnému dbd_data.json jen PŘIDÁ, co tam chybí.
Nic neubírá ani nepřepisuje, takže pokažená wiki nemůže rozbít rozpoznávání.
Výsledek je v app/dbd_data_wiki.json, aby byl k dispozici i bez internetu.
"""

from __future__ import annotations

import copy
import gzip
import json
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from catalog import compact

log = logging.getLogger("dbd")

WIKI = "https://deadbydaylight.wiki.gg"
USER_AGENT = "DbD-Rich-Presence/2.0 (osobni Discord status; data z wiki nejvys 1x denne)"
MAIN, COSMETICS = "Module:Datatable", "Module:Datatable/Cosmetics"
CACHE_VERSION = 1

# Pod tímhle počtem je stažená tabulka nejspíš rozbitá a nepoužije se.
MINIMUM = {"killers": 35, "survivors": 40, "realms": 15, "maps": 35, "cos": 40}


# =============================================================== Lua tabulky
class LuaError(ValueError):
    pass


_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<lcomment>--\[(?P<lceq>=*)\[.*?\](?P=lceq)\])
  | (?P<comment>--[^\n]*)
  | (?P<lstr>\[(?P<lseq>=*)\[.*?\](?P=lseq)\])
  | (?P<str>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')
  | (?P<num>0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\.\.\.|\.\.|==|~=|<=|>=|//|::|[-+*/%^#&~|<>=(){}\[\];:,.])
""", re.VERBOSE | re.DOTALL)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v",
            "\\": "\\", '"': '"', "'": "'", "\n": "\n"}


def _unescape(body: str) -> str:
    out, i = [], 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        nxt = body[i + 1] if i + 1 < len(body) else ""
        if nxt in _ESCAPES:
            out.append(_ESCAPES[nxt])
            i += 2
        elif nxt == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", body[i + 2:i + 4]):
            out.append(chr(int(body[i + 2:i + 4], 16)))
            i += 4
        elif nxt == "z":
            i += 2
            while i < len(body) and body[i].isspace():
                i += 1
        elif nxt == "u" and body[i + 2:i + 3] == "{" and "}" in body[i:]:
            end = body.index("}", i)
            out.append(chr(int(body[i + 3:end], 16)))
            i = end + 1
        elif nxt.isdigit():
            m = re.match(r"\d{1,3}", body[i + 1:])
            out.append(chr(int(m.group(0))))
            i += 1 + len(m.group(0))
        else:
            out.append(nxt)
            i += 2
    return "".join(out)


def _tokens(text: str, pos: int):
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:          # neznámý znak mimo řetězec -> přeskočit
            pos += 1
            continue
        pos = m.end()
        kind = m.lastgroup
        if kind in ("ws", "comment", "lcomment"):
            continue
        val = m.group(kind)
        if kind == "str":
            yield ("str", _unescape(val[1:-1]))
        elif kind == "lstr":
            eq = m.group("lseq")
            body = val[2 + len(eq):-(2 + len(eq))]
            yield ("str", body[1:] if body.startswith("\n") else body)
        elif kind == "num":
            if val[:2].lower() == "0x":
                yield ("num", int(val, 16))
            else:
                yield ("num", float(val) if re.search(r"[.eE]", val) else int(val))
        elif kind == "name":
            yield ("name", val)
        else:
            yield ("op", val)


class _Parser:
    """Rekurzivní parser jen pro literály tabulek. Cokoli jiného (volání funkcí,
    spojování řetězců...) přeskočí a hodnotu vrátí jako None."""

    def __init__(self, text: str, pos: int) -> None:
        self._gen = _tokens(text, pos)
        self._buf: list = []

    def _peek(self, k: int = 0):
        while len(self._buf) <= k:
            t = next(self._gen, None)
            if t is None:
                return None
            self._buf.append(t)
        return self._buf[k]

    def _next(self):
        t = self._peek(0)
        if t is not None:
            self._buf.pop(0)
        return t

    def _is(self, kind: str, val=None, k: int = 0) -> bool:
        t = self._peek(k)
        return t is not None and t[0] == kind and (val is None or t[1] == val)

    def table(self) -> dict:
        if not self._is("op", "{"):
            raise LuaError("čekal jsem '{'")
        self._next()
        tbl: dict = {}
        n = 0
        while True:
            if self._peek() is None:
                raise LuaError("neukončená tabulka")
            if self._is("op", "}"):
                self._next()
                return tbl
            if self._is("op", "["):                        # [key] = value
                self._next()
                key = self.value()
                if not self._is("op", "]"):
                    raise LuaError("čekal jsem ']'")
                self._next()
                if not self._is("op", "="):
                    raise LuaError("čekal jsem '='")
                self._next()
                tbl[key] = self.value()
            elif self._is("name") and self._is("op", "=", 1):  # name = value
                key = self._next()[1]
                self._next()
                tbl[key] = self.value()
            else:                                           # pozice
                n += 1
                tbl[n] = self.value()
            if not (self._is("op", ",") or self._is("op", ";") or self._is("op", "}")):
                self._skip_expr()                           # zbytek výrazu (a + b ...)
            if self._is("op", ",") or self._is("op", ";"):
                self._next()

    def value(self):
        t = self._peek()
        if t is None:
            raise LuaError("chybí hodnota")
        if t == ("op", "{"):
            return self.table()
        if t == ("op", "-") and self._is("num", k=1):
            self._next()
            return -self._next()[1]
        kind, val = t
        if kind in ("str", "num"):
            self._next()
            if self._is("op", ".."):
                self._skip_expr()
                return None
            return val
        if kind == "name" and val in ("true", "false", "nil"):
            self._next()
            return {"true": True, "false": False, "nil": None}[val]
        self._skip_expr()
        return None

    def _skip_expr(self) -> None:
        depth = 0
        while self._peek() is not None:
            kind, v = self._peek()
            if kind == "op":
                if v in ("{", "(", "["):
                    depth += 1
                elif v in ("}", ")", "]"):
                    if depth == 0:
                        return
                    depth -= 1
                elif v in (",", ";") and depth == 0:
                    return
            self._next()


def lua_table(text: str, name: str) -> dict | None:
    """Najde `name = {...}` (i `p.name = {...}`) a vrátí tabulku jako dict
    (pozice 1, 2, 3... jako int klíče, pojmenovaná pole jako str klíče)."""
    m = re.search(rf"^[ \t]*(?:local[ \t]+)?(?:p\.)?{re.escape(name)}[ \t]*=[ \t]*\{{", text, re.M)
    if not m:
        return None
    return _Parser(text, m.end() - 1).table()


def seq(tbl: dict | None) -> list:
    """Pozicové prvky tabulky v pořadí."""
    if not isinstance(tbl, dict):
        return []
    return [tbl[i] for i in sorted(k for k in tbl if isinstance(k, int))]


# =============================================================== extrakce
def _str(v) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() else None


def _int(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _section(text: str, key: str) -> list:
    try:
        return seq(lua_table(text, key))
    except Exception as e:           # jedna rozbitá tabulka nesmí shodit ostatní
        log.debug("Tabulku %s z wiki nejde přečíst: %s", key, e)
        return []


def extract_main(text: str) -> dict:
    out: dict = {}
    for key in ("killers", "survivors", "realms", "maps"):
        rows = []
        for e in _section(text, key):
            if not isinstance(e, dict) or _int(e.get("id")) is None or not _str(e.get("name")):
                continue
            row = {"id": _int(e["id"]), "name": _str(e["name"])}
            if key == "maps":
                row["realm"] = _int(e.get("realm"))
            if key == "survivors":
                # dbdName = jméno, jak ho ukazuje hra; shortName = běžná zkratka
                for extra in ("dbdName", "shortName"):
                    if _str(e.get(extra)):
                        row[extra] = _str(e[extra])
            rows.append(row)
        out[key] = rows
    return out


def extract_cosmetics(text: str) -> dict:
    rows = []
    for e in _section(text, "cosChars"):
        if not isinstance(e, dict) or not _str(e.get("name")):
            continue
        row = {"name": _str(e["name"]), "killer": _int(e.get("killer")), "survivor": _int(e.get("survivor"))}
        if e.get("article") is False:
            row["article"] = False
        real = _str(e.get("realName"))
        if real:
            real = _strip_parens(re.split(r"<br\s*/?>", real)[0])
            if real:
                row["realName"] = real
        if row["killer"] is None and row["survivor"] is None:
            continue
        rows.append(row)
    return {"cos": rows}


def looks_ok(wiki: dict) -> list[str]:
    """Které části stažených dat vypadají v pořádku."""
    return [k for k, n in MINIMUM.items() if len(wiki.get(k) or ()) >= n]


# =============================================================== porovnání s vestavěnými daty
def _strip_parens(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def survivor_variants(name: str) -> list[str]:
    """'Jeffrey "Jeff" Johansen' -> Jeff Johansen, Jeffrey Johansen...;
    'Detective David Tapp' -> David Tapp; 'A & B' -> A, B (řeší se zvlášť)."""
    name = _strip_parens(name)
    out: list[str] = []
    m = re.match(r'^(\S+)\s+["“]([^"”]+)["”]\s+(.+)$', name)
    if m:
        out += [f"{m.group(2)} {m.group(3)}", f"{m.group(1)} {m.group(3)}", name.replace('"', "")]
    else:
        out.append(name)
    for title in ("Detective ", "Officer ", "Doctor ", "Dr. ", "Captain "):
        if name.startswith(title):
            out.append(name[len(title):])
    if re.search(r"\b[A-Z]\.\s", name):                       # 'Ashley J. Williams'
        out.append(re.sub(r"\b[A-Z]\.\s", "", name))
    return list(dict.fromkeys(v for v in out if v))


def killer_title(name: str) -> str:
    return name if name.lower().startswith("the ") else f"The {name}"


class _Known:
    """Všechna jména a aliasy, která už program zná (kompaktní tvar)."""

    def __init__(self, entries: list[dict]) -> None:
        self.by_key: dict[str, str] = {}
        for e in entries:
            for n in (e["name"], *e.get("aliases", ())):
                self.add(n, e["name"])

    def add(self, variant: str, name: str) -> None:
        for v in (variant, variant[4:] if variant.lower().startswith("the ") else None):
            c = compact(v) if v else ""
            if len(c) >= 2:
                self.by_key.setdefault(c, name)

    def find(self, variants: list[str], fuzzy: float = 90.0) -> str | None:
        keys = [compact(v) for v in variants if v]
        for k in keys:
            if k in self.by_key:
                return self.by_key[k]
        try:
            from rapidfuzz import fuzz, process
        except ImportError:
            return None
        for k in keys:
            if len(k) < 8:
                continue
            hit = process.extractOne(k, list(self.by_key), scorer=fuzz.ratio, score_cutoff=fuzzy)
            if hit:
                return self.by_key[hit[0]]
        return None


def additions(wiki: dict, base: dict) -> dict:
    """Co z wiki ve vestavěných datech chybí (ve formátu dbd_data.json)."""
    add: dict = {"killers": [], "survivors": [], "outfits": [], "realms": [], "map_count": 0}
    usable = set(looks_ok(wiki))

    killers = _Known(base.get("killers", []))
    killer_by_id: dict[int, str] = {}
    if "killers" in usable:
        for k in wiki["killers"]:
            title = killer_title(k["name"])
            known = killers.find([title, k["name"]])
            if known is None:
                entry = {"name": title}
                if compact(k["name"]) != compact(title):
                    entry["aliases"] = [k["name"]]
                add["killers"].append(entry)
                killers.add(title, title)
                known = title
            killer_by_id[k["id"]] = known

    survivors = _Known(base.get("survivors", []))
    survivor_by_id: dict[int, str] = {}
    if "survivors" in usable:
        for s in wiki["survivors"]:
            parts = [p.strip() for p in re.split(r"\s+&\s+", _strip_parens(s["name"])) if p.strip()]
            first_known = None
            for i, part in enumerate(parts if len(parts) > 1 else [s["name"]]):
                variants = survivor_variants(part)
                if i == 0:
                    # Jméno ze hry (dbdName) má přednost, pak běžná zkratka.
                    variants = list(dict.fromkeys([x for x in (s.get("dbdName"), s.get("shortName")) if x] + variants))
                known = survivors.find(variants)
                if known is None:
                    entry = {"name": variants[0]}
                    rest = [v for v in variants[1:] if compact(v) != compact(variants[0])]
                    if rest:
                        entry["aliases"] = rest
                    add["survivors"].append(entry)
                    for v in variants:
                        survivors.add(v, variants[0])
                    known = variants[0]
                first_known = first_known or known
            survivor_by_id[s["id"]] = first_known

    everyone = _Known(base.get("killers", []) + base.get("survivors", []) + base.get("outfits", [])
                      + add["killers"] + add["survivors"])
    if "cos" in usable and killer_by_id and survivor_by_id:
        for c in wiki["cos"]:
            base_name = killer_by_id.get(c["killer"]) if c.get("killer") else survivor_by_id.get(c.get("survivor"))
            if not base_name:
                continue
            raw = c["name"]
            if c.get("killer") and c.get("article", True):
                name = killer_title(raw)
            else:
                name = raw
            variants = [name, raw]
            if c.get("realName"):
                variants.append(c["realName"])
            words = raw.split()
            if len(words) == 2 and c.get("survivor"):
                variants.append(f"{words[1]} {words[0]}")      # 'Shimizu Hinako' / 'Hinako Shimizu'
            if everyone.find(variants) is not None:
                continue
            entry = {"name": name, "base": base_name}
            aliases = [v for v in variants[1:] if compact(v) != compact(name)]
            if aliases:
                entry["aliases"] = list(dict.fromkeys(aliases))
            add["outfits"].append(entry)
            for v in variants:
                everyone.add(v, name)

    if "realms" in usable and "maps" in usable:
        realm_names = {r["id"]: r["name"] for r in wiki["realms"]}
        base_realms = {compact(r["name"]): r for r in base.get("realms", [])}
        for a in r_aliases(base.get("realms", [])):
            base_realms.setdefault(a[0], a[1])
        known_maps = {compact(m) for r in base.get("realms", []) for m in r.get("maps", ())}
        new_realms: dict[str, dict] = {}
        for m in wiki["maps"]:
            if compact(m["name"]) in known_maps or not m.get("realm") or m["realm"] not in realm_names:
                continue
            realm = realm_names[m["realm"]]
            key = compact(realm)
            target = new_realms.get(key)
            if target is None:
                existing = base_realms.get(key) or base_realms.get(compact(re.sub(r"^The ", "", realm)))
                target = {"name": existing["name"] if existing else realm, "maps": [], "new": existing is None}
                new_realms[key] = target
            target["maps"].append(m["name"])
            known_maps.add(compact(m["name"]))
            add["map_count"] += 1
        add["realms"] = list(new_realms.values())
    return add


def r_aliases(realms: list[dict]):
    for r in realms:
        for a in r.get("aliases", ()):
            yield compact(a), r


def merge(base: dict, add: dict) -> dict:
    """Vestavěná data + doplňky z wiki."""
    data = copy.deepcopy(base)
    data["killers"] = list(data.get("killers", [])) + [dict(k) for k in add.get("killers", [])]
    data["survivors"] = list(data.get("survivors", [])) + [dict(s) for s in add.get("survivors", [])]
    data["outfits"] = list(data.get("outfits", [])) + [dict(o) for o in add.get("outfits", [])]
    realms = data.setdefault("realms", [])
    for r in add.get("realms", []):
        target = next((x for x in realms if x["name"] == r["name"]), None)
        if target is None:
            realms.append({"name": r["name"], "maps": list(r["maps"])})
        else:
            target["maps"] = list(target.get("maps", [])) + [m for m in r["maps"] if m not in target.get("maps", [])]
    return data


def describe(add: dict) -> list[str]:
    out = [f"killer {k['name']}" for k in add.get("killers", [])]
    out += [f"survivor {s['name']}" for s in add.get("survivors", [])]
    for r in add.get("realms", []):
        out += [f"mapa {m} ({r['name']})" for m in r["maps"]]
    out += [f"skin {o['name']} ({o['base']})" for o in add.get("outfits", [])]
    return out


def count(add: dict) -> int:
    return len(add.get("killers", [])) + len(add.get("survivors", [])) + len(add.get("outfits", [])) + add.get("map_count", 0)


# =============================================================== stahování
def _get(url: str, timeout: float = 25.0, limit: int = 8_000_000) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(limit + 1)
        if len(data) > limit:
            raise ValueError("odpověď je podezřele velká")
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            data = gzip.decompress(data)
    return data


def revisions(titles: list[str]) -> dict[str, int]:
    q = urllib.parse.urlencode({"action": "query", "format": "json", "formatversion": "2",
                                "prop": "revisions", "rvprop": "ids", "titles": "|".join(titles)})
    data = json.loads(_get(f"{WIKI}/api.php?{q}").decode("utf-8"))
    out = {}
    for page in (data.get("query") or {}).get("pages") or []:
        revs = page.get("revisions") or []
        if revs and page.get("title"):
            out[page["title"]] = int(revs[0].get("revid") or 0)
    return out


def raw_page(title: str) -> str:
    q = urllib.parse.urlencode({"title": title, "action": "raw"})
    return _get(f"{WIKI}/index.php?{q}").decode("utf-8")


# =============================================================== aktualizace na pozadí
class WikiUpdater:
    """Jednou za den se podívá na wiki; když přibylo něco nového, připraví
    nová data pro Catalog. Hlavní smyčka si je vyzvedne přes take()."""

    MAX_AGE = 20 * 3600.0        # jak staré údaje stačí
    RETRY = 2 * 3600.0           # po chybě sítě zkusit znovu za 2 h

    def __init__(self, base_path: Path, cache_path: Path | None, enabled: bool = True) -> None:
        self.base_path = base_path
        self.cache_path = cache_path
        self.enabled = enabled
        with open(base_path, encoding="utf-8") as f:
            self.base = json.load(f)
        self.cache = self._load_cache()
        self._lock = threading.Lock()
        self._fresh: dict | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ---------------------------------------------------------- cache
    def _load_cache(self) -> dict:
        if not self.cache_path or not self.cache_path.exists():
            return {}
        try:
            c = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return c if isinstance(c, dict) and c.get("verze") == CACHE_VERSION else {}
        except Exception:
            return {}

    def _save_cache(self) -> None:
        if not self.cache_path:
            return
        try:
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.cache_path)
        except Exception as e:
            log.debug("dbd_data_wiki.json se nepodařilo uložit: %s", e)

    # ---------------------------------------------------------- data
    def additions(self) -> dict:
        wiki = self.cache.get("wiki") or {}
        try:
            return additions(wiki, self.base) if wiki else {}
        except Exception as e:
            log.debug("Doplňky z wiki se nepodařilo spočítat: %s", e)
            return {}

    def data(self) -> dict:
        """Vestavěná data + to, co už je stažené z wiki (i bez internetu)."""
        add = self.additions()
        return merge(self.base, add) if add else self.base

    def take(self) -> dict | None:
        """Nová data, pokud od posledního vyzvednutí něco přibylo."""
        with self._lock:
            fresh, self._fresh = self._fresh, None
        return fresh

    # ---------------------------------------------------------- vlákno
    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="wiki", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def due_in(self, now: float) -> float:
        last_ok = float(self.cache.get("zkontrolovano") or 0)
        last_err = float(self.cache.get("chyba") or 0)
        due = max(last_ok + self.MAX_AGE, last_err + self.RETRY)
        return max(0.0, due - now)

    def _loop(self) -> None:
        self._stop.wait(20.0)          # nezdržovat start programu
        while not self._stop.is_set():
            wait = self.due_in(time.time())
            if wait > 0:
                self._stop.wait(min(wait, 3600.0))
                continue
            self.check()

    def check(self) -> bool:
        """Jedno porovnání s wiki. True = podařilo se (ať už něco přibylo, nebo ne)."""
        before = describe(self.additions())
        try:
            revs = revisions([MAIN, COSMETICS])
            old_revs = self.cache.get("revize") or {}
            wiki = dict(self.cache.get("wiki") or {})
            got_any = False
            if revs.get(MAIN) != old_revs.get(MAIN) or "killers" not in wiki:
                wiki.update(extract_main(raw_page(MAIN)))
                got_any = True
            if revs.get(COSMETICS) != old_revs.get(COSMETICS) or "cos" not in wiki:
                wiki.update(extract_cosmetics(raw_page(COSMETICS)))
                got_any = True
            ok = looks_ok(wiki)
            if len(ok) < len(MINIMUM):
                bad = ", ".join(k for k in MINIMUM if k not in ok)
                log.info("Data z wiki vypadají neúplně (%s), nechávám je být.", bad)
            self.cache.update({"verze": CACHE_VERSION, "zkontrolovano": time.time(), "chyba": 0,
                               "revize": revs, "wiki": wiki})
            self._save_cache()
        except Exception as e:
            log.debug("Kontrola novinek na wiki selhala: %s", e)
            self.cache["chyba"] = time.time()
            self._save_cache()
            return False
        add = self.additions()
        new = [x for x in describe(add) if x not in before]
        if new:
            shown = ", ".join(new[:8]) + (f" a dalších {len(new) - 8}" if len(new) > 8 else "")
            log.info("Novinky z DbD wiki: %s", shown)
            with self._lock:
                self._fresh = merge(self.base, add)
        elif got_any:
            log.debug("Wiki: nic nového (%d doplňků už známých)", count(add))
        return True
