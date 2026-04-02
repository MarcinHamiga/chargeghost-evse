import json
import logging
from pathlib import Path

import pytest

from chargeghost_evse.util import config as cfg_module
from chargeghost_evse.util.config import (
    BATTERY_CAPACITY_DEFAULT,
    BATTERY_CAPACITY_MAX,
    BATTERY_CAPACITY_MIN,
    SimulationConfig,
)


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


def test_log_mode_shallow_deep_values(tmp_path, monkeypatch):
	"""log_mode must accept 'shallow' and 'deep' values."""
	config_file = tmp_path / "config.json"
	config_file.write_text(json.dumps({"log_mode": "deep"}))
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig.load()
	assert config.log_mode == "deep"


def test_log_mode_backward_compat_compact(tmp_path, monkeypatch):
	"""Old 'compact' value must be migrated to 'shallow'."""
	config_file = tmp_path / "config.json"
	config_file.write_text(json.dumps({"log_mode": "compact"}))
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig.load()
	assert config.log_mode == "shallow"


def test_log_mode_backward_compat_verbose(tmp_path, monkeypatch):
	"""Old 'verbose' value must be migrated to 'deep'."""
	config_file = tmp_path / "config.json"
	config_file.write_text(json.dumps({"log_mode": "verbose"}))
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig.load()
	assert config.log_mode == "deep"


def test_log_mode_default_is_shallow():
	"""Default log_mode must be 'shallow'."""
	config = SimulationConfig()
	assert config.log_mode == "shallow"


def test_log_mode_unknown_value_defaults_to_shallow(tmp_path, monkeypatch):
	"""Unknown log_mode values must default to 'shallow'."""
	config_file = tmp_path / "config.json"
	config_file.write_text(json.dumps({"log_mode": "garbage"}))
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig.load()
	assert config.log_mode == "shallow"


def test_battery_capacity_default():
	"""SimulationConfig must default ev_battery_capacity to 55.0 kWh."""
	config = SimulationConfig()
	assert config.ev_battery_capacity == BATTERY_CAPACITY_DEFAULT


def test_battery_capacity_save_load(tmp_path, monkeypatch):
	"""Battery capacity must persist through save/load cycle."""
	config_file = tmp_path / "config.json"
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig()
	config.ev_battery_capacity = 75.0
	config.save()

	loaded = SimulationConfig.load()
	assert loaded.ev_battery_capacity == 75.0


def test_battery_capacity_in_json_output(tmp_path, monkeypatch):
	"""ev_battery_capacity key must appear in saved JSON."""
	config_file = tmp_path / "config.json"
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig()
	config.ev_battery_capacity = 100.0
	config.save()

	data = json.loads(config_file.read_text())
	assert "ev_battery_capacity" in data
	assert data["ev_battery_capacity"] == 100.0


def test_battery_capacity_clamped_on_load(tmp_path, monkeypatch):
	"""Out-of-range battery capacity must be clamped on load."""
	config_file = tmp_path / "config.json"
	config_file.write_text(json.dumps({"ev_battery_capacity": 9999.0}))
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig.load()
	assert config.ev_battery_capacity == BATTERY_CAPACITY_MAX


def test_battery_capacity_clamped_below_min_on_load(tmp_path, monkeypatch):
	"""Battery capacity below minimum must be clamped on load."""
	config_file = tmp_path / "config.json"
	config_file.write_text(json.dumps({"ev_battery_capacity": -5.0}))
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig.load()
	assert config.ev_battery_capacity == BATTERY_CAPACITY_MIN


def test_battery_capacity_missing_uses_default(tmp_path, monkeypatch):
	"""Missing ev_battery_capacity in JSON must use the default."""
	config_file = tmp_path / "config.json"
	config_file.write_text(json.dumps({}))
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig.load()
	assert config.ev_battery_capacity == BATTERY_CAPACITY_DEFAULT
