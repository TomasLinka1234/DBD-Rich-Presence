"""Společné nastavení testů.

Testy nikdy nesahají na skutečnou složku s daty (%APPDATA%) ani na internet:
DBD_RP_DATA míří do dočasné složky a síťové funkce se v testech nahrazují.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
os.environ.setdefault("DBD_RP_DATA", tempfile.mkdtemp(prefix="dbd-rp-test-"))
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


@pytest.fixture(scope="session")
def base_data() -> dict:
    with open(APP / "dbd_data.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def wiki_snapshot() -> dict:
    """Celá data z wiki (postavy, realmy, mapy, skiny) ve stavu z 22. 11. 2026."""
    with open(ROOT / "tests" / "data" / "wiki_2026-11-22.json", encoding="utf-8") as f:
        return json.load(f)
