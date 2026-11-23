"""Hlavní smyčka: hlídá hru, čte obrazovku a posílá status do Discordu.

Používá ji režim s oknem (main.py --konzole) i běh na pozadí s ikonkou u hodin (pozadi.py).
Těžké věci (OCR, snímání obrazovky) se načtou až ve chvíli, kdy se spustí hra,
a po jejím zavření se zase uvolní, takže program bez hry skoro nic nežere.
"""

from __future__ import annotations

import gc
import logging
import threading
import time
from pathlib import Path
from typing import Callable

from paths import BUILTIN_DATA, DEBUG_DIR, IMAGE_CACHE, STATE, STATS, UPLOADS, WIKI_CACHE, ensure_data_dir

log = logging.getLogger("dbd")

INTERVAL = {"MENU": 1.5, "LOBBY": 1.2, "LOADING": 0.8, "MATCH": 1.5, "POSTGAME": 1.2, "OFF": 2.0}
RELEASE_AFTER = 90.0      # s bez hry -> uvolnit OCR a snímání obrazovky
DISCONNECT_AFTER = 10.0   # s bez hry -> odpojit se od Discordu

# Druhy stavu pro ikonku u hodin
WAIT, LIVE, NO_DISCORD, ERROR = "wait", "live", "nodiscord", "error"


class Runner:
    def __init__(self, cfg: dict, dry_run: bool = False, debug: bool = False,
                 stop: threading.Event | None = None,
                 on_status: Callable[[str, str], None] | None = None,
                 should_quit: Callable[[], bool] | None = None,
                 app_id: str | None = None) -> None:
        self.cfg = cfg
        self.dry_run = dry_run
        self.debug = debug
        self.stop = stop or threading.Event()
        self.on_status = on_status
        self.should_quit = should_quit
        self.app_id = app_id
        self._status: tuple[str, str] | None = None
        self.ocr = self.scanner = self.grabber = None

    # ---------------------------------------------------------------- stav
    def _report(self, kind: str, text: str) -> None:
        if self._status == (kind, text):
            return
        self._status = (kind, text)
        if self.on_status:
            try:
                self.on_status(kind, text)
            except Exception:
                log.debug("on_status selhal", exc_info=True)

    def _wait(self, seconds: float) -> bool:
        """Počkat; True = máme skončit."""
        if self.should_quit and self.should_quit():
            self.stop.set()
        return self.stop.wait(max(0.0, seconds))

    # ---------------------------------------------------------------- těžké části
    def _load_heavy(self) -> None:
        from capture import Grabber
        from detect import Scanner
        from ocr import Ocr

        if self.ocr is None:
            log.info("Načítám OCR (poprvé to chvíli trvá)...")
            self.ocr = Ocr(int(self.cfg.get("vlakna_ocr", 2) or 2))
            self.scanner = Scanner(self.ocr, self.catalog)
        if self.grabber is None:
            self.grabber = Grabber(str(self.cfg.get("snimani", "auto")))

    def _release_heavy(self) -> None:
        if self.ocr is None and self.grabber is None:
            return
        if self.ocr is not None and self.ocr.calls:
            log.debug("OCR: %d volání, průměr %.0f ms", self.ocr.calls, 1000 * self.ocr.seconds / self.ocr.calls)
        if self.grabber is not None:
            try:
                self.grabber.close()
            except Exception:
                pass
        self.ocr = self.scanner = self.grabber = None
        gc.collect()
        log.debug("Hra neběží -> OCR a snímání obrazovky uvolněno.")

    def _swap_catalog(self, data: dict) -> None:
        from catalog import Catalog

        try:
            cat = Catalog(data)
        except Exception as e:
            log.info("Nová data z wiki nejdou načíst (%s), zůstávám u starých.", e)
            return
        self.catalog = cat
        self.tracker.catalog = cat
        self.images.catalog = cat
        if self.scanner is not None:
            self.scanner.catalog = cat
        log.info("Seznam postav a map doplněn z wiki (%d postav, %d map).", len(cat.characters), len(cat.maps))

    # ---------------------------------------------------------------- běh
    def run(self) -> int:
        from capture import enable_dpi_awareness, find_game, find_window, game_alive, game_hidden, to_16x9
        from catalog import Catalog
        from images import Images, MapSnapshots, PrestigeBadges
        from presence import DiscordPresence
        from stats import Stats
        from tracker import OFF, Store, Tracker
        from wiki_data import WikiUpdater

        cfg, dry_run, debug = self.cfg, self.dry_run, self.debug
        enable_dpi_awareness()
        ensure_data_dir()
        self.wiki = WikiUpdater(BUILTIN_DATA, WIKI_CACHE,
                                enabled=bool(cfg.get("novinky_z_wiki", True)) and not dry_run)
        self.catalog = Catalog(self.wiki.data())
        store = Store(STATE)
        self.images = Images(self.app_id, cfg, offline=dry_run, cache_path=IMAGE_CACHE,
                             catalog=self.catalog)
        self.images.refresh(time.time())
        stats = Stats(STATS) if cfg.get("statistiky", True) else None
        if stats is not None and dry_run:
            stats.path = None  # nanečisto: statistiky ukázat, ale nic nezapisovat
        self.tracker = tracker = Tracker(self.catalog, store, cfg, self.images, stats)
        snapshots = MapSnapshots(UPLOADS, self.images, bool(cfg.get("ukladat_obrazky_map", False)))
        badges = PrestigeBadges(UPLOADS, self.images, bool(cfg.get("ukladat_odznaky_prestige", False)))
        self.discord = discord = DiscordPresence(self.app_id or "0", dry_run=dry_run)
        self.wiki.start()
        debug_dir = DEBUG_DIR
        saved = 0

        if tracker.character:
            log.info("Naposledy: %s (%s)", tracker.character.label(), tracker.role)
        log.info("Čekám na Dead by Daylight...")
        self._report(WAIT, "Čekám na Dead by Daylight")

        game, win = None, None
        hidden, size_logged = False, False
        next_game_check = next_win_check = 0.0
        gone_since: float | None = time.time()
        last_error = 0.0
        try:
            while not self.stop.is_set():
                now = time.time()
                try:
                    fresh = self.wiki.take()
                    if fresh is not None:
                        self._swap_catalog(fresh)
                    self.images.refresh(now)
                    if now >= next_game_check:
                        if game is None or not game_alive(game):
                            if game is not None:
                                log.info("Dead by Daylight se zavřel.")
                            game = find_game()
                            if game is not None:
                                log.info("Dead by Daylight běží.")
                                size_logged = False
                        next_game_check = now + (5.0 if game else 3.0)
                        if game is None:
                            win = None

                    # ------------------------------------------------ hra neběží
                    if game is None:
                        if gone_since is None:
                            gone_since = now
                        tracker.game_closed(now)
                        discord.set(None)
                        discord.tick(now)
                        if now - gone_since > DISCONNECT_AFTER:
                            discord.disconnect()
                        if now - gone_since > RELEASE_AFTER:
                            self._release_heavy()
                        self._report(WAIT, "Čekám na Dead by Daylight")
                        if self._wait(INTERVAL[OFF]):
                            break
                        continue
                    gone_since = None

                    # ------------------------------------------------ hra běží
                    self._load_heavy()
                    tracker.game_running(now, game.started_at)
                    if win is None or now >= next_win_check:
                        win = find_window(game.pids)
                        next_win_check = now + 5.0
                    if game_hidden(win, game.pids):
                        if not hidden:
                            hidden = True
                            log.info("Hra je schovaná za jiným oknem -> čtení obrazovky čeká. Přepni se do hry.")
                        discord.set(tracker.activity(now))
                        discord.tick(now)
                        self._report_activity(tracker, now, suffix=" (hra je schovaná)")
                        if self._wait(1.0):
                            break
                        continue
                    if hidden:
                        hidden = False
                        log.info("Hra je zase vidět, čtu obrazovku.")
                    frame = self.grabber.grab(win.rect if win else None)
                    if frame is None:
                        discord.tick(now)
                        if self._wait(2.0):
                            break
                        continue
                    if not size_logged:
                        size_logged = True
                        log.info("Čtu obrazovku: %dx%d (%s)%s", frame.shape[1], frame.shape[0],
                                 getattr(self.grabber, "backend", "?"),
                                 "" if win else ", okno hry nenalezeno -> celý hlavní monitor")
                    frame = to_16x9(frame)
                    obs = self.scanner.scan(frame, tracker.context(now), now)
                    if debug:
                        saved = self._debug_dump(obs, frame, debug_dir, saved)
                    tracker.update(obs, now)
                    if obs.header_badge is not None:
                        badges.save(obs.header_prestige, obs.header_badge, tracker.character)
                    if obs.board is not None and obs.board.mine is not None:
                        # Jen vlastní řádek: odznaky ostatních hráčů hra ukazuje ztlumené.
                        for ch, n, crop in obs.board.badges:
                            if ch == obs.board.mine and n == obs.board.my_prestige:
                                badges.save(n, crop, ch)
                    snapshots.tick(frame, tracker.phase, tracker.map,
                                   (now - tracker.match_start) if tracker.match_start else 0.0,
                                   tracker.match_start_exact)
                    discord.set(tracker.activity(now))
                    discord.tick(now)
                    self._report_activity(tracker, now)
                    spent = time.time() - now
                    if self._wait(max(0.2, INTERVAL.get(tracker.phase, 1.5) - spent)):
                        break
                except Exception:
                    # Jedna chyba (třeba odpojený monitor) nesmí shodit program na pozadí.
                    if now - last_error > 60:
                        log.exception("Chyba v hlavní smyčce, pokračuji")
                    last_error = now
                    self._report(ERROR, "Chyba – podrobnosti v log.txt")
                    if self._wait(3.0):
                        break
        finally:
            tracker.flush()
            self.wiki.stop()
            discord.close()
            self._release_heavy()
        return 0

    def _report_activity(self, tracker, now: float, suffix: str = "") -> None:
        act = tracker.activity(now) or {}
        parts = [p for p in (act.get("details"), act.get("state")) if p]
        text = " · ".join(parts) or "Dead by Daylight běží"
        if self.dry_run:
            kind = LIVE
        elif self.discord.connected:
            kind = LIVE
        else:
            kind = NO_DISCORD
            text += " (Discord neběží)"
        self._report(kind, text + suffix)

    @staticmethod
    def _debug_dump(obs, frame, debug_dir: Path, saved: int) -> int:
        for k, v in obs.debug.items():
            log.debug("   OCR %-10s %s", k, " | ".join(v))
        if (obs.title or obs.end_kind or obs.header_char or obs.header_unknown or obs.lobby_survivor) and saved < 300:
            try:
                import cv2

                debug_dir.mkdir(parents=True, exist_ok=True)
                what = "mapa" if obs.title else (obs.end_kind or "postava")
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ok:  # imencode + tofile zvládne i cestu s diakritikou
                    buf.tofile(str(debug_dir / f"{time.strftime('%H%M%S')}_{what}.jpg"))
                    saved += 1
            except Exception:
                pass
        return saved
