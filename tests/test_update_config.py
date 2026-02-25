from chargeghost_evse.util.config import SimulationConfig


def test_simulation_config_persists_ignored_version(tmp_path, monkeypatch):
	from chargeghost_evse.util import config as cfg
	monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")

	c = SimulationConfig()
	c.ignored_version = "v0.2.0"
	c.save()

	reloaded = SimulationConfig.load()
	assert reloaded.ignored_version == "v0.2.0"
