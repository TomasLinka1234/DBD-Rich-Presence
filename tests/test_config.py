"""Nastavení: výchozí hodnoty, doplnění chybějících položek, chybný soubor."""

import json

import config
import pytest


@pytest.fixture()
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "nastaveni.json"
    monkeypatch.setattr(config, "CONFIG", path)
    monkeypatch.setattr(config, "ensure_data_dir", lambda: tmp_path)
    return path


def test_first_run_creates_defaults(cfg_file):
    cfg, created, err = config.load_config()
    assert created and err is None
    assert cfg == config.DEFAULTS
    assert json.loads(cfg_file.read_text(encoding="utf-8")) == config.DEFAULTS


def test_missing_keys_are_filled_in(cfg_file):
    cfg_file.write_text(json.dumps({"jmeno_ve_hre": "ScarsCZ", "ukazat_mapu": False}), encoding="utf-8")
    cfg, created, err = config.load_config()
    assert not created and err is None
    assert cfg["jmeno_ve_hre"] == "ScarsCZ" and cfg["ukazat_mapu"] is False
    assert cfg["jazyk"] == config.DEFAULTS["jazyk"]


def test_broken_file_is_not_overwritten(cfg_file):
    cfg_file.write_text('{"jazyk": "cs",,}', encoding="utf-8")
    cfg, created, err = config.load_config()
    assert err and "řádek 1" in err
    assert cfg == config.DEFAULTS
    assert cfg_file.read_text(encoding="utf-8") == '{"jazyk": "cs",,}'


def test_bom_is_accepted(cfg_file):
    cfg_file.write_text('﻿{"jazyk": "en"}', encoding="utf-8")
    cfg, _, err = config.load_config()
    assert err is None and cfg["jazyk"] == "en"


@pytest.mark.parametrize("value, want", [
    ("123456789012345678", "123456789012345678"),
    (" 123456789012345678 ", "123456789012345678"),
    ("", config.DEFAULT_APP_ID),
    ("abc", config.DEFAULT_APP_ID),
    (None, config.DEFAULT_APP_ID),
])
def test_app_id(value, want):
    assert config.app_id_from({"discord_application_id": value}) == want
