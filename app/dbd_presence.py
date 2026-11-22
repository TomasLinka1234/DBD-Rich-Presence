"""DbD Rich Presence: ukazuje v Discordu, koho hraješ v Dead by Daylight,
na jaké mapě a jak dlouho zápas běží.

Jak to funguje: program každou chvíli vyfotí obrazovku a přečte z ní text
(OCR): jméno postavy v menu, tlačítko PLAY/READY, název mapy na začátku
zápasu a obrazovku po zápase. Do hry nijak nezasahuje.

Spuštění:   python dbd_presence.py              (normální běh v okně)
            pythonw pozadi.py                   (na pozadí s ikonkou u hodin)
            python dbd_presence.py --test X.png (co program vidí na screenshotu)
            python dbd_presence.py --nanecisto  (bez Discordu, jen výpis)
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import re
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

from paths import BUILTIN_DATA, DEBUG_DIR, LOG_FILE, STATE, WIKI_CACHE, ensure_data_dir  # noqa: E402

log = logging.getLogger("dbd")

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


# --------------------------------------------------------------------- setup
def setup_logging(debug: bool, to_file: bool = True, console: bool = True) -> None:
    log.setLevel(logging.DEBUG if debug else logging.INFO)
    log.handlers.clear()
    if console and sys.stdout is not None:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
        log.addHandler(handler)
    if to_file:
        try:
            ensure_data_dir()
            fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
            log.addHandler(fh)
        except Exception:
            pass
    log.propagate = False


def load_config() -> dict:
    import config

    cfg, _, error = config.load_config()
    if error:
        log.error("Nastavení (%s) má chybu: %s. Používám výchozí hodnoty.", config.CONFIG, error)
    return cfg


def app_id_from(cfg: dict) -> str:
    import config

    return config.app_id_from(cfg)


def load_catalog():
    """Vestavěný seznam + to, co už se dřív stáhlo z wiki (bez internetu)."""
    from catalog import Catalog
    from wiki_data import WikiUpdater

    return Catalog(WikiUpdater(BUILTIN_DATA, WIKI_CACHE, enabled=False).data())


def imread(path: Path):
    """cv2.imread neumí cesty s diakritikou na Windows, tohle ano."""
    import cv2
    import numpy as np

    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def collect_images(items: list[str]) -> list[Path]:
    out: list[Path] = []
    for it in items:
        p = Path(it)
        if p.is_dir():
            out += sorted(q for q in p.iterdir() if q.suffix.lower() in IMAGE_EXT)
        elif p.suffix.lower() in IMAGE_EXT and p.exists():
            out.append(p)
    return out


# --------------------------------------------------------------------- modes
def run_test(items: list[str], cfg: dict) -> int:
    """Vypíše, co program na screenshotech přečte."""
    from capture import to_16x9
    from catalog import Catalog
    from detect import read_everything
    from ocr import Ocr
    from tracker import Store

    paths = collect_images(items)
    if not paths:
        log.error("Nenašel jsem žádné obrázky (png/jpg). Přetáhni screenshot na test_screenshotu.bat.")
        return 1
    catalog = load_catalog()
    own = str(cfg.get("jmeno_ve_hre") or "").strip() or Store(STATE).get("own_name")
    log.info("Načítám OCR...")
    ocr = Ocr(int(cfg.get("vlakna_ocr", 2) or 2))
    labels = {
        "tlacitko": "Tlačítko vpravo dole", "killer_pod_tlacitkem": "Killer pod tlačítkem",
        "survivor_ve_fronte": "Survivor ve frontě", "postava_v_zahlavi": "Postava v záhlaví",
        "role_v_zahlavi": "Záložka (role)", "prestige": "Prestige",
        "scoreboard_moje_prestige": "Moje prestige ve scoreboardu",
        "herni_jmeno": "Herní jméno (vpravo nahoře)", "survivor_v_lobby": "Survivor v lobby",
        "menu_vpravo_nahore": "Menu (měny vpravo nahoře)", "zacatek_zapasu": "Začátek zápasu (TAB MATCH DETAILS)",
        "mapa": "Mapa",
        "konec_zapasu_barva": "Červený nadpis", "konec_zapasu": "Obrazovka po zápase",
        "scoreboard_killer": "Killer ve scoreboardu", "scoreboard_moje_postava": "Moje postava ve scoreboardu",
    }
    for p in paths:
        img = imread(p)
        if img is None:
            log.error("%s: nejde otevřít", p.name)
            continue
        frame = to_16x9(img)
        ocr.forget()
        t0 = time.perf_counter()
        out = read_everything(ocr, frame, catalog, own)
        dt = time.perf_counter() - t0
        print(f"\n=== {p.name}  ({img.shape[1]}x{img.shape[0]}, {dt:.1f} s)")
        shown = False
        for k, v in out.items():
            if v not in (None, False):
                print(f"   {labels.get(k, k)}: {'ano' if v is True else v}")
                shown = True
        if not shown:
            print("   (nic z toho, co hledám)")
    return 0


def run_replay(items: list[str], cfg: dict, repeat: int) -> int:
    """Pustí sérii screenshotů jako by to byla živá hra (bez Discordu)."""
    from capture import to_16x9
    from catalog import Catalog
    from detect import Scanner
    from ocr import Ocr
    from presence import DiscordPresence
    from tracker import Store, Tracker

    paths = collect_images(items)
    if not paths:
        log.error("Žádné obrázky.")
        return 1
    catalog = load_catalog()
    ocr = Ocr(int(cfg.get("vlakna_ocr", 2) or 2))
    tracker = Tracker(catalog, Store(None), cfg)
    scanner = Scanner(ocr, catalog)
    discord = DiscordPresence("0", dry_run=True)
    discord.MIN_INTERVAL = 0.0
    t = 1_000_000.0
    tracker.game_running(t, t)
    last_hms = None
    for i, p in enumerate(paths):
        m = re.search(r"(\d{6})", p.stem)
        if m:
            hh, mm, ss = int(m.group(1)[:2]), int(m.group(1)[2:4]), int(m.group(1)[4:])
            hms = hh * 3600 + mm * 60 + ss
            if last_hms is not None and hms > last_hms:
                t += hms - last_hms - 1.5 * repeat
            last_hms = hms
        frame = to_16x9(imread(p))
        log.info("--- %s", p.name)
        for _ in range(repeat):
            obs = scanner.scan(frame, tracker.context(t), t)
            tracker.update(obs, t)
            discord.set(tracker.activity(t))
            discord.tick(t)
            t += 1.5
    return 0


def run_diagnostics(cfg: dict) -> int:
    """Vyfotí obrazovku oběma způsoby, uloží snímky do složky debug a vypíše,
    co na nich program přečetl. Na hledání chyb na konkrétním počítači."""
    import cv2

    from capture import Grabber, enable_dpi_awareness, find_game, find_window, game_hidden, to_16x9
    from catalog import Catalog
    from detect import read_everything
    from ocr import Ocr

    enable_dpi_awareness()
    catalog = load_catalog()
    own = str(cfg.get("jmeno_ve_hre") or "").strip() or None
    log.info("Načítám OCR...")
    ocr = Ocr(int(cfg.get("vlakna_ocr", 2) or 2))
    game = find_game()
    if game is None:
        log.error("Dead by Daylight neběží. Spusť hru, otevři lobby (nebo menu postav) a pusť diagnostiku znovu.")
        return 1
    win = find_window(game.pids)
    log.info("Hra běží (PID %s). Okno hry: %s", ",".join(map(str, sorted(game.pids))),
             f"{win.rect}{' (minimalizované)' if win and win.minimized else ''}" if win else "nenalezeno")
    log.info("Teď se do 8 sekund přepni do hry (do lobby nebo do menu postav) a nech ji v popředí ~15 s.")
    for i in range(8, 0, -1):
        print(f"   {i}...", flush=True)
        time.sleep(1)
    out_dir = DEBUG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    grabbers = {"dxcam": Grabber("dxcam"), "mss": Grabber("mss")}
    for n in range(1, 4):
        win = find_window(game.pids) or win
        log.info("--- snímek %d (hra v popředí: %s)", n, "ne" if game_hidden(win, game.pids) else "ano")
        for name, g in grabbers.items():
            try:
                frame = g.grab(win.rect if win else None)
            except Exception as e:
                frame = None
                log.info("   %s: chyba %s", name, e)
            if frame is None:
                log.info("   %s: nic nevyfotil", name)
                continue
            if g.backend != name:
                log.info("   %s: nejde, použil se %s", name, g.backend)
            small = cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                buf.tofile(str(out_dir / f"diag_{n}_{name}.jpg"))
            ocr.forget()
            seen = read_everything(ocr, to_16x9(frame), catalog, own)
            seen = {k: v for k, v in seen.items() if v not in (None, False)}
            log.info("   %s: %dx%d, jas %.0f -> %s", name, frame.shape[1], frame.shape[0],
                     float(frame[::8, ::8].mean()), seen or "nic nepřečteno")
        time.sleep(3)
    for g in grabbers.values():
        g.close()
    log.info("Hotovo. Snímky jsou v %s (diag_*.jpg). Pošli mi tento výpis, případně i ty snímky.", out_dir)
    return 0


def run_live(cfg: dict, dry_run: bool, debug: bool) -> int:
    import threading

    from runner import Runner
    from winutil import SingleInstance

    app_id = app_id_from(cfg)
    lock = SingleInstance()
    if not lock.ok:
        log.error("DbD Rich Presence už běží: buď na pozadí (ikonka vpravo dole u hodin), nebo v jiném okně.")
        log.error("Když ho chceš mít tady, ukonči ten druhý (ikonka: pravé tlačítko -> Ukončit).")
        return 3
    log.info("Nech toto okno otevřené (klidně minimalizované). Ukončení: zavři okno nebo Ctrl+C.")
    stop = threading.Event()
    try:
        return Runner(cfg, dry_run=dry_run, debug=debug, stop=stop, app_id=app_id).run()
    except KeyboardInterrupt:
        stop.set()
        log.info("Končím.")
        return 0
    finally:
        lock.release()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Discord Rich Presence pro Dead by Daylight")
    ap.add_argument("--test", nargs="+", metavar="OBRAZEK", help="jen vypiš, co je na screenshotech")
    ap.add_argument("--prehrat", nargs="+", metavar="OBRAZEK", help="přehraj sérii screenshotů jako živou hru")
    ap.add_argument("--opakovani", type=int, default=3, help="kolikrát každý snímek v --prehrat použít")
    ap.add_argument("--nanecisto", action="store_true", help="neposílat nic do Discordu, jen vypisovat")
    ap.add_argument("--debug", action="store_true", help="podrobný výpis + ukládání snímků do složky debug")
    ap.add_argument("--diagnostika", action="store_true", help="vyfotí obrazovku a vypíše, co na ní přečetl")
    args = ap.parse_args(argv)

    setup_logging(args.debug, to_file=not (args.test or args.prehrat))
    cfg = load_config()
    if args.debug or cfg.get("debug"):
        log.setLevel(logging.DEBUG)
    if args.test:
        return run_test(args.test, cfg)
    if args.prehrat:
        return run_replay(args.prehrat, cfg, max(1, args.opakovani))
    if args.diagnostika:
        return run_diagnostics(cfg)
    return run_live(cfg, args.nanecisto, args.debug or bool(cfg.get("debug")))


if __name__ == "__main__":
    sys.exit(main())
