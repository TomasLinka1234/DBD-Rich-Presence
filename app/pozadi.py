"""DbD Rich Presence na pozadí: bez okna, s ikonkou u hodin.

    DbD-Rich-Presence.exe              spustit (ikonka u hodin)
    DbD-Rich-Presence.exe --autostart  totéž, ale potichu, když už běží (spouští ho Windows po přihlášení)
    DbD-Rich-Presence.exe --ukoncit    ukončit program běžící na pozadí
    DbD-Rich-Presence.exe --statistiky otevřít přehled statistik v prohlížeči
    DbD-Rich-Presence.exe --self-test vysledek.json   kontrola sestaveného .exe

Pravým tlačítkem na ikonku: co program právě ukazuje, statistiky, nastavení,
log, spouštění s Windows a ukončení. Nastavení se po uložení samo načte znovu.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import CONFIG, DATA, FROZEN, ICON_PNG, LOG_FILE, ensure_data_dir  # noqa: E402

log = logging.getLogger("dbd")

COLORS = {"wait": (138, 143, 152), "live": (59, 165, 93), "nodiscord": (240, 160, 32), "error": (237, 66, 69)}


def fix_streams() -> None:
    """Program bez konzole: sys.stdout/stderr jsou None a print by spadl."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def icon_image(kind: str, size: int = 64):
    """Logo programu (generátor v červeném kruhu) s barevnou tečkou stavu vpravo dole."""
    from PIL import Image, ImageDraw

    try:
        img = Image.open(ICON_PNG).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((2, 2, size - 3, size - 3), fill=(40, 12, 14, 255), outline=(178, 22, 32, 255), width=5)
    d = ImageDraw.Draw(img)
    r = size * 0.2
    cx = cy = size - r - 1
    d.ellipse((cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), fill=(20, 20, 22, 255))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=COLORS.get(kind, COLORS["wait"]) + (255,))
    return img


def open_in_editor(path: Path) -> None:
    try:
        if os.name == "nt":
            subprocess.Popen(["notepad.exe", str(path)])
        else:
            from winutil import open_path

            open_path(path)
    except Exception:
        pass


def open_stats() -> Path:
    """Vytvoří přehled statistik (statistiky.html ve složce s daty) a otevře ho v prohlížeči."""
    import time

    from paths import STATS, STATS_HTML
    from stats import Stats, write_report
    from winutil import open_path

    out = write_report(Stats(STATS).matches, STATS_HTML, time.time())
    open_path(out)
    return out


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


# ======================================================================= aplikace
class App:
    """Běh na pozadí + ikonka u hodin + okno. Okno je jen pohled: zavřením se schová,
    status v Discordu jede dál. Úplně se aplikace ukončí z menu ikonky nebo tlačítkem v okně."""

    def __init__(self, cfg: dict, first_run: bool, autostarted: bool, config_error: str | None) -> None:
        from okno import UpdateChecker
        from runner import WAIT
        from winutil import QuitSignal, ShowSignal

        self.cfg = cfg
        self.autostarted = autostarted
        self.first_run_pending = first_run and not autostarted
        self.config_error = config_error
        self.status: tuple[str, str] = (WAIT, "Spouštím…")
        self.runner = None
        self.run_stop: threading.Event | None = None
        self.stop_all = threading.Event()
        self.quit_signal = QuitSignal()
        self.show_signal = ShowSignal()
        self.paused = False
        self.ui = False
        self.window = None
        self.quitting = False
        self.icon = None
        self.pending_tab: str | None = None
        self.updates = UpdateChecker()
        self.icons = {k: icon_image(k) for k in COLORS}
        self.worker_thread = threading.Thread(target=self._worker, name="runner", daemon=True)

    # ---------------------------------------------------------- běh na pozadí
    def _worker(self) -> None:
        import config
        from runner import ERROR, Runner

        log.info("DbD Rich Presence běží na pozadí. Data: %s", DATA)
        cfg_mtime = _mtime(CONFIG)
        while not self.stop_all.is_set():
            run_stop = threading.Event()
            self.run_stop = run_stop
            changed = {"cfg": False}

            def should_quit(changed=changed, cfg_mtime=cfg_mtime) -> bool:
                if self.stop_all.is_set() or self.quit_signal.is_set():
                    self.stop_all.set()
                    return True
                if _mtime(CONFIG) != cfg_mtime:
                    changed["cfg"] = True
                    return True
                return False

            runner = Runner(self.cfg, stop=run_stop, on_status=self.on_status, should_quit=should_quit,
                            app_id=config.app_id_from(self.cfg), paused=lambda: self.paused)
            self.runner = runner
            try:
                runner.run()
            except Exception:
                log.exception("Program na pozadí spadl, za 30 s ho spustím znovu.")
                self.on_status(ERROR, "Chyba, za chvíli to zkusím znovu (podrobnosti v logu)")
                self.stop_all.wait(30)
                continue
            if changed["cfg"] and not self.stop_all.is_set():
                cfg_mtime = _mtime(CONFIG)
                new_cfg, _, err = config.load_config()
                self.config_error = err
                if err:
                    log.error("Nastavení má chybu (%s), nechávám předchozí.", err)
                else:
                    self.cfg = new_cfg
                    log.info("Nastavení změněno, načítám ho znovu.")
                continue
            break
        self.stop_all.set()
        log.info("DbD Rich Presence končí.")
        self._close_ui()

    def on_status(self, kind: str, text: str) -> None:
        self.status = (kind, text)
        icon = self.icon
        if icon is None:
            return
        try:
            icon.icon = self.icons.get(kind, self.icons["wait"])
            icon.title = ("DbD Rich Presence: " + text)[:120]
            icon.update_menu()
        except Exception:
            pass

    def refresh_tray(self) -> None:
        if self.icon is not None:
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def set_paused(self, on: bool) -> None:
        if self.paused == on:
            return
        self.paused = on
        log.info("Status v Discordu %s.", "pozastaven" if on else "zase běží")
        self.refresh_tray()

    # ---------------------------------------------------------- okno
    def show_window(self, tab: str | None = None) -> None:
        if not self.ui or self.window is None:
            if tab == "settings":
                open_in_editor(CONFIG)
            else:
                self._open_stats_report()
            return
        if tab:
            self.pending_tab = tab
        w = self.window          # záložku si okno vyzvedne samo při dalším dotazu na stav (do 1 s)
        try:
            w.show()
            w.restore()
            w.on_top = True       # vytáhnout dopředu, i když je pod hrou
            w.on_top = False
        except Exception:
            log.debug("Okno nejde ukázat", exc_info=True)

    def hide_window(self) -> None:
        w = self.window
        if w is not None:
            try:
                w.hide()
            except Exception:
                pass

    def on_window_closing(self):
        """Křížek okna = schovat do ikonky (běh na pozadí pokračuje)."""
        if self.quitting:
            return None
        threading.Timer(0.01, self.hide_window).start()
        return False

    def _open_stats_report(self) -> None:
        try:
            open_stats()
        except Exception as e:
            from winutil import message_box

            log.exception("Přehled statistik se nepodařilo otevřít")
            message_box(f"Přehled statistik se nepodařilo otevřít:\n{e}", error=True)

    def _watch_show(self) -> None:
        """Druhé spuštění programu (třeba dvojklik na .exe) -> ukázat okno."""
        while not self.stop_all.is_set():
            if self.show_signal.wait(1.0) and not self.stop_all.is_set():
                log.info("Program spuštěn znovu -> ukazuji okno.")
                self.show_window()

    # ---------------------------------------------------------- konec
    def quit(self) -> None:
        self.quitting = True
        self.stop_all.set()
        if self.run_stop is not None:
            self.run_stop.set()
        self._close_ui()

    def _close_ui(self) -> None:
        self.quitting = True
        w, self.window = self.window, None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass
        icon = self.icon
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    # ---------------------------------------------------------- ikonka u hodin
    def _menu(self, pystray):
        import autostart
        from winutil import message_box, open_path

        def toggle_autostart(icon, item) -> None:
            if autostart.is_enabled():
                ok, info = autostart.disable()
                log.info("Autostart vypnut." if ok else f"Autostart se nepodařilo vypnout: {info}")
            else:
                ok, info = autostart.enable()
                log.info("Autostart zapnut." if ok else f"Autostart se nepodařilo zapnout: {info}")
                if not ok:
                    message_box("Spouštění se zapnutím Windows se nepodařilo zapnout:\n" + info, error=True)
            icon.update_menu()

        no_ui = lambda item: not self.ui  # noqa: E731
        return pystray.Menu(
            pystray.MenuItem(lambda item: self.status[1][:110], None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Otevřít", lambda icon, item: self.show_window(), default=True,
                             visible=lambda item: self.ui),
            pystray.MenuItem("Statistiky", lambda icon, item: self.show_window("stats")),
            pystray.MenuItem("Nastavení", lambda icon, item: self.show_window("settings")),
            pystray.MenuItem("Otevřít log", lambda icon, item: open_path(LOG_FILE), visible=no_ui),
            pystray.MenuItem("Otevřít složku s daty", lambda icon, item: open_path(DATA), visible=no_ui),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pozastavit status", lambda icon, item: self.set_paused(not self.paused),
                             checked=lambda item: self.paused),
            pystray.MenuItem("Spouštět se zapnutím Windows", toggle_autostart,
                             checked=lambda item: autostart.is_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Ukončit", lambda icon, item: self.quit()),
        )

    def run(self) -> int:
        import pystray

        from okno import available
        from runner import WAIT

        self.ui, why = available()
        if not self.ui:
            log.info("Okno aplikace nepůjde otevřít (%s), běžím jen s ikonkou u hodin.", why)
        self.icon = pystray.Icon("dbd_rich_presence", self.icons[WAIT], "DbD Rich Presence", self._menu(pystray))
        threading.Thread(target=self._watch_show, name="show", daemon=True).start()

        if self.ui:
            def tray_setup(ic) -> None:
                ic.visible = True

            tray = threading.Thread(target=self.icon.run, kwargs={"setup": tray_setup}, name="tray", daemon=True)
            tray.start()
            self.worker_thread.start()
            try:
                from okno import run_window

                run_window(self, hidden=self.autostarted)
            except Exception:
                log.exception("Okno aplikace nejde otevřít, běžím dál jen s ikonkou u hodin.")
                self.ui, self.window = False, None
                self.refresh_tray()
                while not self.stop_all.wait(1.0):
                    pass
            finally:
                self.quit()
                tray.join(timeout=5)
        else:
            def setup(ic) -> None:
                ic.visible = True
                self.worker_thread.start()
                if not self.autostarted:
                    try:
                        ic.notify("Běžím na pozadí. Až zapneš Dead by Daylight, ukážu to v Discordu.",
                                  "DbD Rich Presence")
                    except Exception:
                        pass

            try:
                self.icon.run(setup=setup)
            finally:
                self.quit()
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=8)
        self.quit_signal.close()
        self.show_signal.close()
        return 0


def run_tray(autostarted: bool) -> int:
    import autostart
    import config
    from dbd_presence import setup_logging
    from winutil import SingleInstance, ask_running_instance_to_show, ask_yes_no, message_box

    ensure_data_dir()
    setup_logging(debug=False, to_file=True, console=False)
    try:
        # Musí být dřív, než vznikne jakékoli okno (ikonka u hodin, okno aplikace), jinak by
        # při zvětšení písma ve Windows nesedělo, kde přesně je okno hry.
        from capture import enable_dpi_awareness

        enable_dpi_awareness()
    except Exception:
        pass

    lock = SingleInstance()
    if not lock.ok:
        if not autostarted and not ask_running_instance_to_show():
            message_box("DbD Rich Presence už běží.\nIkonka je vpravo dole u hodin (případně pod šipkou ^).")
        return 0

    cfg, first_run, error = config.load_config()
    if error:
        log.error("Nastavení má chybu (%s), používám výchozí hodnoty.", error)
    if cfg.get("debug"):
        log.setLevel(logging.DEBUG)

    try:
        import pystray  # noqa: F401
    except ImportError:
        log.error("Chybí knihovna pystray (ikonka u hodin).")
        message_box("Chybí knihovna pro ikonku u hodin (pystray).", error=True)
        lock.release()
        return 1

    from okno import available

    ui_ok, _ = available()
    if error and not ui_ok:
        message_box(f"Soubor s nastavením má chybu:\n{error}\n\nPoužívám výchozí hodnoty.\n{CONFIG}", error=True)
    if first_run and not autostarted and os.name == "nt" and not ui_ok:
        # Bez okna se zeptáme klasicky; s oknem se ptá uvítací karta na stránce Domů.
        if ask_yes_no("Spouštět DbD Rich Presence automaticky se zapnutím Windows?\n\n"
                      "Poběží na pozadí s ikonkou u hodin a sám počká, až zapneš Dead by Daylight. "
                      "Kdykoli to jde vypnout v menu ikonky."):
            ok, info = autostart.enable()
            log.info("Autostart zapnut." if ok else f"Autostart se nepodařilo zapnout: {info}")
        first_run = False
    elif autostart.is_enabled() and not autostart.points_here():
        # .exe se přesunul jinam (nebo je to zástupce z verze 2.0.0) -> ať se spouští tenhle
        ok, info = autostart.enable()
        log.info("Spouštění s Windows opraveno (program je teď jinde)." if ok else
                 f"Spouštění s Windows míří jinam a nejde opravit: {info}")

    app = App(cfg, first_run, autostarted, error)
    try:
        return app.run()
    finally:
        lock.release()


def self_test(out: str) -> int:
    """Ověří, že sestavené .exe má všechno potřebné (OCR modely, knihovny...).
    Výsledek zapíše jako JSON; návratový kód 0 = v pořádku."""
    import json
    import time
    import traceback

    res: dict = {"frozen": FROZEN, "steps": {}}

    def step(name: str, fn, required: bool = True) -> None:
        t = time.time()
        try:
            info = fn()
            res["steps"][name] = {"ok": True, "s": round(time.time() - t, 2), "info": info}
        except Exception:
            res["steps"][name] = {"ok": False, "required": required, "error": traceback.format_exc()[-1500:]}

    def catalog_check():
        from catalog import Catalog
        from paths import BUILTIN_DATA
        from wiki_data import WikiUpdater

        c = Catalog(WikiUpdater(BUILTIN_DATA, None, enabled=False).data())
        assert len(c.killers) >= 40 and len(c.maps) >= 40
        return f"{len(c.killers)} killerů, {len(c.survivors)} survivorů, {len(c.maps)} map"

    def ocr_check():
        import cv2
        import numpy as np

        from catalog import compact
        from ocr import Ocr

        img = np.full((160, 1100, 3), 28, np.uint8)
        cv2.putText(img, "THE TRAPPER", (30, 115), cv2.FONT_HERSHEY_SIMPLEX, 3.2, (255, 255, 255), 7, cv2.LINE_AA)
        text = " ".join(line.text for line in Ocr(1).read(img))
        assert "TRAPPER" in compact(text), text
        return text

    def wiki_check():
        import wiki_data

        t = wiki_data.lua_table('x = {{id = 1, name = "Trapper"}, -- c\n {id = 2, name = \'Wraith\'}}', "x")
        assert [e["name"] for e in wiki_data.seq(t)] == ["Trapper", "Wraith"]
        return "ok"

    def stats_check():
        from stats import Match, render_html, result_from_texts

        assert result_from_texts(["MATCH", "MERCILESS KILLER"]) == "k4"
        assert result_from_texts(["ESCAPED"]) == "escaped"
        now = time.time()
        page = render_html([Match(now - 600, now, "killer", "The Trapper", map="Coal Tower", result="k3")], now)
        assert "The Trapper" in page and "Coal Tower" in page
        return f"{len(page)} znaků"

    def tray_check():
        import pystray

        return [icon_image("live").size, pystray.Icon.__module__]

    def discord_check():
        import pypresence

        return pypresence.__version__

    def capture_check():
        import mss

        info = {"mss": getattr(mss, "__version__", "?")}
        try:
            import dxcam  # noqa: F401
            info["dxcam"] = "ok"
        except Exception as e:      # volitelné, bez něj se fotí přes mss
            info["dxcam"] = f"není: {e.__class__.__name__}"
        return info

    def window_check():
        """Skutečné okno aplikace: načte stránku, JavaScript zavolá Python (api.state) a zpátky."""
        import okno
        from winutil import webview2_version

        ok, why = okno.available()
        assert ok, why

        class FakeApp:
            runner = None
            status = ("wait", "self-test")
            paused = first_run_pending = False
            config_error = pending_tab = window = None
            updates = okno.UpdateChecker()

            def set_paused(self, on): self.paused = on  # noqa: E704
            def refresh_tray(self): pass  # noqa: E704
            def hide_window(self): pass  # noqa: E704
            def quit(self): pass  # noqa: E704

        import webview

        out: dict = {"webview2": webview2_version()}

        def probe(window):
            try:
                got, done = {}, threading.Event()
                window.evaluate_js("window.pywebview.api.state()", lambda r: (got.setdefault("s", r), done.set()))
                done.wait(30)
                out["api_version"] = (got.get("s") or {}).get("version")
                out["title"] = window.evaluate_js("document.title")
                out["pages"] = window.evaluate_js("document.querySelectorAll('.page').length")
                out["app"] = window.evaluate_js("typeof window.app")
            finally:
                window.destroy()

        watchdog = threading.Timer(120, lambda: os._exit(7))
        watchdog.daemon = True
        watchdog.start()
        w = webview.create_window("DbD Rich Presence (self-test)", html=okno.build_html(),
                                  js_api=okno.Api(FakeApp()), width=900, height=640)
        webview.start(probe, w, gui="edgechromium")
        watchdog.cancel()
        assert out.get("title") == "DbD Rich Presence" and out.get("pages") == 4, out
        assert out.get("app") == "object" and out.get("api_version"), out
        return out

    step("data", catalog_check)
    step("ocr", ocr_check)
    step("wiki", wiki_check)
    step("statistiky", stats_check)
    step("ikonka", tray_check)
    step("discord", discord_check)
    step("snimani", capture_check)
    if os.name == "nt":
        from winutil import webview2_version

        # okno až nakonec: smyčka GUI musí běžet v hlavním vlákně; bez WebView2 se nedá vyzkoušet
        step("okno", window_check, required=bool(webview2_version()))
    res["ok"] = all(s["ok"] for s in res["steps"].values() if s.get("required", True))
    Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if res["ok"] else 1


# ======================================================================= vstup
def main(argv: list[str] | None = None) -> int:
    fix_streams()
    ap = argparse.ArgumentParser(description="DbD Rich Presence")
    ap.add_argument("--autostart", action="store_true", help="spuštěno se zapnutím Windows")
    ap.add_argument("--zapnout", action="store_true", help="zapnout spouštění se zapnutím Windows")
    ap.add_argument("--vypnout", action="store_true", help="vypnout spouštění se zapnutím Windows")
    ap.add_argument("--ukoncit", action="store_true", help="ukončit program běžící na pozadí")
    ap.add_argument("--self-test", metavar="SOUBOR", help="kontrola sestaveného programu")
    ap.add_argument("--statistiky", action="store_true", help="otevřít přehled statistik v prohlížeči")
    args, _ = ap.parse_known_args(argv)
    if args.self_test:
        return self_test(args.self_test)
    if args.statistiky:
        print(open_stats())
        return 0
    if args.zapnout or args.vypnout:
        import autostart

        ok, info = autostart.enable() if args.zapnout else autostart.disable()
        print(("Hotovo: " if ok else "Nepovedlo se: ") + info)
        return 0 if ok else 1
    if args.ukoncit:
        from winutil import ask_running_instance_to_quit

        return 0 if ask_running_instance_to_quit() else 1
    return run_tray(args.autostart)


if __name__ == "__main__":
    sys.exit(main())
