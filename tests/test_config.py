import json
import logging
from pathlib import Path

import pytest

from chargeghost_evse.util import config as cfg_module
from chargeghost_evse.util.config import SimulationConfig


def test_load_logs_warning_on_corrupted_json(tmp_path, monkeypatch, caplog):
	"""A corrupted config file must log a warning, not fail silently."""
	config_file = tmp_path / "config.json"
	config_file.write_text("{ not valid json }")
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	with caplog.at_level(logging.WARNING):
		result = SimulationConfig.load()

	assert result is not None  # Falls back to defaults
	assert any("config" in r.message.lower() for r in caplog.records)


def test_save_is_atomic(tmp_path, monkeypatch):
	"""save() must write atomically (no partial file on interrupted write)."""
	config_file = tmp_path / "config.json"
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig()
	config.save()

	# No .tmp file should remain after successful save
	assert not (tmp_path / "config.json.tmp").exists()
	assert config_file.exists()
	data = json.loads(config_file.read_text())
	assert "connectors" in data


def test_num_connectors_field_removed(tmp_path, monkeypatch):
	"""num_connectors must not appear in saved JSON."""
	config_file = tmp_path / "config.json"
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig()
	config.save()

	data = json.loads(config_file.read_text())
	assert "num_connectors" not in data
