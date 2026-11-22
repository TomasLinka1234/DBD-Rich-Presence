"""Spouštění se zapnutím Windows (klíč Run v HKEY_CURRENT_USER)."""

import os

import autostart
import pytest


@pytest.fixture()
def fake_registry(monkeypatch, tmp_path):
    store: dict[str, str] = {}
    monkeypatch.setattr(autostart, "winreg", object())          # „jsme na Windows“
    monkeypatch.setattr(autostart, "_read", lambda: store.get("v"))
    monkeypatch.setattr(autostart, "_write", lambda cmd: store.__setitem__("v", cmd))
    monkeypatch.setattr(autostart, "_delete", lambda: store.pop("v", None))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return store


def test_enable_disable(fake_registry):
    assert not autostart.is_enabled()
    ok, _ = autostart.enable()
    assert ok and autostart.is_enabled() and autostart.points_here()
    assert fake_registry["v"].endswith("--autostart")
    ok, _ = autostart.disable()
    assert ok and not autostart.is_enabled()


def test_moved_exe_is_detected(fake_registry):
    fake_registry["v"] = r'"D:\jinde\DbD-Rich-Presence.exe" --autostart'
    assert autostart.is_enabled() and not autostart.points_here()
    autostart.enable()
    assert autostart.points_here()


def test_old_shortcut_from_2_0_0_is_cleaned_up(fake_registry):
    link = autostart.old_shortcut()
    link.parent.mkdir(parents=True)
    link.write_bytes(b"L\0\0\0")
    assert autostart.is_enabled() and not autostart.points_here()
    autostart.enable()
    assert not link.exists() and autostart.points_here()


def test_without_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(autostart, "winreg", None)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    ok, msg = autostart.enable()
    assert not ok and "Windows" in msg
    assert autostart.disable()[0]


@pytest.mark.skipif(os.name != "nt", reason="skutečný registr jen ve Windows")
def test_real_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(autostart, "VALUE_NAME", "DbD Rich Presence (test)")   # nesahat na opravdové nastavení
    monkeypatch.setenv("APPDATA", str(tmp_path))
    try:
        assert autostart.enable()[0]
        assert autostart.is_enabled() and autostart.points_here()
    finally:
        autostart.disable()
    assert autostart._read() is None
