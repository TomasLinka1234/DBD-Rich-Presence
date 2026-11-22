"""DbD Rich Presence na pozadí: bez okna, s ikonkou u hodin.

    DbD-Rich-Presence.exe              spustit (ikonka u hodin)
    DbD-Rich-Presence.exe --autostart  totéž, ale potichu, když už běží (zástupce v Po spuštění)
    DbD-Rich-Presence.exe --ukoncit    ukončit program běžící na pozadí
    DbD-Rich-Presence.exe --self-test vysledek.json   kontrola sestaveného .exe

Pravým tlačítkem na ikonku: co program právě ukazuje, nastavení, log,
spouštění s Windows a ukončení. Nastavení se po uložení samo načte znovu.
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


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


# ======================================================================= tray
def run_tray(autostarted: bool) -> int:
    import autostart
    import config
    from dbd_presence import setup_logging
    from runner import ERROR, WAIT, Runner
    from winutil import QuitSignal, SingleInstance, ask_yes_no, message_box, open_path

    ensure_data_dir()
    setup_logging(debug=False, to_file=True, console=False)
    try:
        # Musí být dřív, než vznikne jakékoli okno (ikonka u hodin), jinak by
        # při zvětšení písma ve Windows nesedělo, kde přesně je okno hry.
        from capture import enable_dpi_awareness

        enable_dpi_awareness()
    except Exception:
        pass

    lock = SingleInstance()
    if not lock.ok:
        if not autostarted:
            message_box("DbD Rich Presence už běží.\nIkonka je vpravo dole u hodin (případně pod šipkou ^).")
        return 0

    cfg, first_run, error = config.load_config()
    if error:
        log.error("Nastavení má chybu (%s), používám výchozí hodnoty.", error)
        message_box(f"Soubor s nastavením má chybu:\n{error}\n\nPoužívám výchozí hodnoty.\n{CONFIG}", error=True)
    if cfg.get("debug"):
        log.setLevel(logging.DEBUG)

    try:
        import pystray
    except ImportError:
        log.error("Chybí knihovna pystray (ikonka u hodin).")
        message_box("Chybí knihovna pro ikonku u hodin (pystray).", error=True)
        lock.release()
        return 1

    if first_run and not autostarted and os.name == "nt":
        if ask_yes_no("Spouštět DbD Rich Presence automaticky se zapnutím Windows?\n\n"
                      "Poběží na pozadí s ikonkou u hodin a sám počká, až zapneš Dead by Daylight. "
                      "Kdykoli to jde vypnout v menu ikonky."):
            ok, info = autostart.enable()
            log.info("Autostart zapnut." if ok else f"Autostart se nepodařilo zapnout: {info}")
    elif not autostarted and autostart.is_enabled():
        # .exe se mohl přesunout jinam -> opravit zástupce, ať míří sem
        def fix_link() -> None:
            if not autostart.points_here():
                ok, _ = autostart.enable()
                log.info("Zástupce pro spouštění s Windows opraven (program je teď jinde)." if ok else
                         "Zástupce pro spouštění s Windows míří jinam a nejde opravit.")
        threading.Thread(target=fix_link, daemon=True).start()

    quit_signal = QuitSignal()
    stop_all = threading.Event()
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
        nonlocal cfg
        log.info("DbD Rich Presence běží na pozadí (ikonka u hodin). Data: %s", DATA)
        cfg_mtime = _mtime(CONFIG)
        while not stop_all.is_set():
            run_stop = threading.Event()
            holder["run_stop"] = run_stop
            changed = {"cfg": False}

            def should_quit() -> bool:
                if stop_all.is_set() or quit_signal.is_set():
                    stop_all.set()
                    return True
                if _mtime(CONFIG) != cfg_mtime:
                    changed["cfg"] = True
                    return True
                return False

            runner = Runner(cfg, stop=run_stop, on_status=on_status, should_quit=should_quit,
                            app_id=config.app_id_from(cfg))
            try:
                runner.run()
            except Exception:
                log.exception("Program na pozadí spadl, za 30 s ho spustím znovu.")
                on_status(ERROR, "Chyba, za chvíli to zkusím znovu (podrobnosti v logu)")
                stop_all.wait(30)
                continue
            if changed["cfg"] and not stop_all.is_set():
                cfg_mtime = _mtime(CONFIG)
                new_cfg, _, err = config.load_config()
                if err:
                    log.error("Nastavení má chybu (%s), nechávám předchozí.", err)
                else:
                    cfg = new_cfg
                    log.info("Nastavení změněno, načítám ho znovu.")
                continue
            break
        stop_all.set()
        log.info("DbD Rich Presence končí.")
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
        stop_all.set()
        rs = holder.get("run_stop")
        if rs is not None:
            rs.set()

    menu = pystray.Menu(
        pystray.MenuItem(lambda item: state["text"][:110], None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Nastavení", lambda icon, item: open_in_editor(CONFIG)),
        pystray.MenuItem("Otevřít log", lambda icon, item: open_path(LOG_FILE)),
        pystray.MenuItem("Otevřít složku s daty", lambda icon, item: open_path(DATA)),
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
        quit_app(None, None)
        if thread.is_alive():
            thread.join(timeout=8)
        quit_signal.close()
        lock.release()
    return 0


# ======================================================================= self-test
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

    step("data", catalog_check)
    step("ocr", ocr_check)
    step("wiki", wiki_check)
    step("ikonka", tray_check)
    step("discord", discord_check)
    step("snimani", capture_check)
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
    args, _ = ap.parse_known_args(argv)
    if args.self_test:
        return self_test(args.self_test)
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
