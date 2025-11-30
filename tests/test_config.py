import json
import os
from pathlib import Path

import pytest

from fimpad import config


def _use_temp_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    app_dir = tmp_path / "confdir"
    cfg_path = app_dir / "config.json"
    monkeypatch.setattr(config, "APP_DIR", str(app_dir))
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    return app_dir


def test_save_config_writes_atomically(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_dir = _use_temp_config(monkeypatch, tmp_path)
    cfg_path = Path(config.CONFIG_PATH)

    payload = {"value": 1}
    config.save_config(payload)

    assert cfg_path.exists()
    with cfg_path.open(encoding="utf-8") as f:
        assert json.load(f) == payload

    assert not list(app_dir.glob("config.*.tmp"))


def test_save_config_restores_on_replace_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app_dir = _use_temp_config(monkeypatch, tmp_path)
    cfg_path = Path(config.CONFIG_PATH)
    app_dir.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"original": True}), encoding="utf-8")

    def _fail_replace(src: str, dst: str) -> None:  # pragma: no cover - behavior asserted
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", _fail_replace)

    with pytest.raises(config.ConfigSaveError):
        config.save_config({"original": False})

    with cfg_path.open(encoding="utf-8") as f:
        assert json.load(f) == {"original": True}

    assert not list(app_dir.glob("config.*.tmp"))


def test_load_config_backs_up_corrupt_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app_dir = _use_temp_config(monkeypatch, tmp_path)
    cfg_path = Path(config.CONFIG_PATH)
    app_dir.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("{not:json", encoding="utf-8")

    loaded = config.load_config()

    assert loaded == config.DEFAULTS
    backups = sorted(app_dir.glob("config.json.corrupt-*"))
    assert backups, "corrupt config should be preserved"
    assert backups[0].read_text(encoding="utf-8") == "{not:json"

    with cfg_path.open(encoding="utf-8") as f:
        assert json.load(f) == config.DEFAULTS


def test_load_config_recovers_non_object(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app_dir = _use_temp_config(monkeypatch, tmp_path)
    cfg_path = Path(config.CONFIG_PATH)
    app_dir.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("[]", encoding="utf-8")

    loaded = config.load_config()

    assert loaded == config.DEFAULTS
    backups = sorted(app_dir.glob("config.json.corrupt-*"))
    assert backups, "non-object config should be backed up"
    assert backups[0].read_text(encoding="utf-8") == "[]"

    with cfg_path.open(encoding="utf-8") as f:
        assert json.load(f) == config.DEFAULTS
