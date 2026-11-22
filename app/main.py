"""Vstupní bod programu (i sestaveného DbD-Rich-Presence.exe).

Bez parametrů běží na pozadí s ikonkou u hodin (pozadi.py).
Ladicí režimy ze zdrojáků:  python main.py --konzole | --test X.png | --diagnostika
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEV = {"--konzole", "--test", "--prehrat", "--diagnostika", "--nanecisto", "--debug"}


def main() -> int:
    argv = sys.argv[1:]
    if any(a in DEV for a in argv):
        import dbd_presence
        from pozadi import fix_streams

        fix_streams()
        return dbd_presence.main([a for a in argv if a != "--konzole"])
    import pozadi

    return pozadi.main(argv)


if __name__ == "__main__":
    sys.exit(main())
