"""DbD Rich Presence na pozadí: bez černého okna, s ikonkou u hodin.

    pythonw pozadi.py              spustit na pozadí (ikonka u hodin)
    pythonw pozadi.py --autostart  totéž, ale potichu, když už běží (zástupce v Po spuštění)
    python  pozadi.py --zapnout    zapnout spouštění se zapnutím Windows
    python  pozadi.py --vypnout    vypnout spouštění se zapnutím Windows
    python  pozadi.py --ukoncit    ukončit program běžící na pozadí

Pravým tlačítkem na ikonku: co program právě vidí, log, složka, autostart, ukončení.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
sys.path.insert(0, str(APP))

log = logging.getLogger("dbd")

COLORS = {"wait": (138, 143, 152), "live": (59, 165, 93), "nodiscord": (240, 160, 32), "error": (237, 66, 69)}


def _fix_streams() -> None:
    """pythonw.exe nemá konzoli: sys.stdout/stderr jsou None a print by spadl."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def icon_image(kind: str, size: int = 64):
    """Ikonka programu (generátor v červeném kruhu) s barevnou tečkou stavu vpravo dole."""
    from PIL import Image, ImageDraw

    img = None
    for name in ("aplikace.png", "killer.png"):
        try:
            img = Image.open(ROOT / "ikony" / name).convert("RGBA").resize((size, size), Image.LANCZOS)
            break
        except Exception:
            continue
    if img is None:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((2, 2, size - 3, size - 3), fill=(40, 12, 14, 255), outline=(178, 22, 32, 255), width=5)
    d = ImageDraw.Draw(img)
    r = size * 0.2
    cx = cy = size - r - 1
    d.ellipse((cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), fill=(20, 20, 22, 255))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=COLORS.get(kind, COLORS["wait"]) + (255,))
    return img


def _cli(args) -> int:
    """Pomocné příkazy pro .bat soubory (vypisují do konzole)."""
    import autostart
    from winutil import ask_running_instance_to_quit

    if args.zapnout:
        ok, info = autostart.enable()
        print("Autostart zapnut: " + info if ok else "Autostart se nepodařilo zapnout: " + info)
        return 0 if ok else 1
    if args.vypnout:
        ok, info = autostart.disable()
        print("Autostart vypnut." if ok else "Autostart se nepodařilo vypnout: " + info)
        return 0 if ok else 1
    if args.ukoncit:
        if ask_running_instance_to_quit():
            print("Program na pozadí dostal pokyn skončit.")
            return 0
        print("Na pozadí nic neběželo.")
        return 1
    return 0


def run_tray(autostarted: bool) -> int:
    from dbd_presence import LOG_FILE, app_id_from, load_config, setup_logging
    from runner import ERROR, NO_DISCORD, WAIT, Runner
    from winutil import QuitSignal, SingleInstance, message_box, open_path
    import autostart

    setup_logging(debug=False, to_file=True, console=False)
    try:
        # Musí být dřív, než vznikne jakékoli okno (ikonka u hodin), jinak by
        # při zvětšení písma ve Windows nesedělo, kde přesně je okno hry.
        from capture import enable_dpi_awareness

        enable_dpi_awareness()
    except Exception:
        pass
    try:
        cfg = load_config()
    except SystemExit:
        message_box("Soubor nastaveni.json má chybu (podrobnosti v log.txt).", error=True)
        return 2
    if cfg.get("debug"):
        log.setLevel(logging.DEBUG)
    app_id = app_id_from(cfg)
    if app_id is None:
        message_box("V souboru nastaveni.json chybí discord_application_id.\nPostup je v NAVOD.md (krok 1).", error=True)
        return 2

    lock = SingleInstance()
    if not lock.ok:
        if not autostarted:
            message_box("DbD Rich Presence už běží.\nIkonka je vpravo dole u hodin (případně pod šipkou ^).")
        return 0

    try:
        import pystray
    except ImportError:
        log.error("Chybí knihovna pystray (ikonka u hodin). Spusť zapnout_autostart.bat, doinstaluje ji.")
        message_box("Chybí knihovna pro ikonku u hodin.\nSpusť zapnout_autostart.bat, ten ji doinstaluje.", error=True)
        lock.release()
        return 1

    quit_signal = QuitSignal()
    stop = threading.Event()
    state = {"kind": WAIT, "text": "Spouštím..."}
    images = {k: icon_image(k) for k in COLORS}
    holder: dict = {}

    def on_status(kind: str, text: str) -> None:
        state["kind"], state["text"] = kind, text
        icon = holder.get("icon")
        if icon is None:
            return
        try:
            icon.icon = images.get(kind, images[WAIT])
            icon.title = ("DbD Rich Presence: " + text)[:120]
            icon.update_menu()
        except Exception:
            pass

    def worker() -> None:
        log.info("DbD Rich Presence běží na pozadí (ikonka u hodin).")
        while not stop.is_set():
            runner = Runner(cfg, stop=stop, on_status=on_status, should_quit=quit_signal.is_set, app_id=app_id)
            try:
                runner.run()
                break
            except Exception:
                log.exception("Program na pozadí spadl, za 30 s ho spustím znovu.")
                on_status(ERROR, "Chyba, za chvíli to zkusím znovu (podrobnosti v log.txt)")
                stop.wait(30)
        stop.set()
        log.info("DbD Rich Presence na pozadí končí.")
        icon = holder.get("icon")
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

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

    def quit_app(icon, item) -> None:
        stop.set()

    menu = pystray.Menu(
        pystray.MenuItem(lambda item: state["text"][:110], None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Otevřít log", lambda icon, item: open_path(LOG_FILE)),
        pystray.MenuItem("Otevřít složku programu", lambda icon, item: open_path(ROOT)),
        pystray.MenuItem("Spouštět se zapnutím Windows", toggle_autostart, checked=lambda item: autostart.is_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Ukončit", quit_app),
    )
    icon = pystray.Icon("dbd_rich_presence", images[WAIT], "DbD Rich Presence", menu)
    holder["icon"] = icon
    thread = threading.Thread(target=worker, name="runner", daemon=True)

    def setup(ic) -> None:
        ic.visible = True
        thread.start()
        if not autostarted:
            try:
                ic.notify("Běžím na pozadí. Až zapneš Dead by Daylight, ukážu to v Discordu.", "DbD Rich Presence")
            except Exception:
                pass

    try:
        icon.run(setup=setup)
    finally:
        stop.set()
        if thread.is_alive():
            thread.join(timeout=8)
        quit_signal.close()
        lock.release()
    return 0


def main(argv: list[str] | None = None) -> int:
    _fix_streams()
    ap = argparse.ArgumentParser(description="DbD Rich Presence na pozadí")
    ap.add_argument("--autostart", action="store_true", help="spuštěno se zapnutím Windows")
    ap.add_argument("--zapnout", action="store_true", help="zapnout spouštění se zapnutím Windows")
    ap.add_argument("--vypnout", action="store_true", help="vypnout spouštění se zapnutím Windows")
    ap.add_argument("--ukoncit", action="store_true", help="ukončit program běžící na pozadí")
    args = ap.parse_args(argv)
    if args.zapnout or args.vypnout or args.ukoncit:
        return _cli(args)
    return run_tray(args.autostart)


if __name__ == "__main__":
    sys.exit(main())
