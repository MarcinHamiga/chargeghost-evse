from __future__ import annotations

from unittest.mock import MagicMock, patch

from chargeghost_evse.api.runtime import (
    ConfigSaveResult,
    SimulationRuntime,
)
from chargeghost_evse.util.config import ConnectorConfig, SimulationConfig


def _make_config(**overrides) -> SimulationConfig:
    defaults = dict(
        connection_url="wss://localhost:3000/CP_1",
        ocpp_id="CP_Test",
        connectors=[ConnectorConfig()],
        ev_battery_capacity=55.0,
    )
    defaults.update(overrides)
    return SimulationConfig(**defaults)


@patch("chargeghost_evse.api.runtime.Bridge")
def _make_runtime(mock_bridge_cls, **config_overrides) -> SimulationRuntime:
    config = _make_config(**config_overrides)
    mock_bridge_instance = MagicMock()
    mock_bridge_cls.return_value = mock_bridge_instance
    runtime = SimulationRuntime(config=config)
    return runtime


class TestSimulationRuntime:
    def test_builds_engine_from_config(self) -> None:
        with patch("chargeghost_evse.api.runtime.Bridge") as mock_bridge_cls:
            mock_bridge_cls.return_value = MagicMock()
            config = _make_config(
                connectors=[ConnectorConfig(), ConnectorConfig(voltage=400.0)],
                ev_battery_capacity=75.0,
            )
            runtime = SimulationRuntime(config=config)

            assert len(runtime.engine.connectors) == 2
            assert runtime.engine.ev_battery_capacity == 75000.0

    def test_start_and_stop_lifecycle(self) -> None:
        runtime = _make_runtime()

        assert runtime.is_running is False

        runtime.start()
        assert runtime.is_running is True

        runtime.stop()
        assert runtime.is_running is False

    async def test_call_dispatches_to_thread(self) -> None:
        runtime = _make_runtime()
        runtime.start()

        result = await runtime.call(lambda: 42)

        assert result == 42
        runtime.stop()

    async def test_snapshot_returns_engine_state(self) -> None:
        runtime = _make_runtime()
        runtime.start()

        snap = await runtime.snapshot()

        assert "connectors" in snap
        assert "sessions" in snap
        assert "energy_meters" in snap
        assert len(snap["connectors"]) == 1
        runtime.stop()

    def test_apply_config_patch_noop(self) -> None:
        runtime = _make_runtime()
        current_url = runtime.config.connection_url

        result = runtime._apply_config_patch_sync({"connection_url": current_url})

        assert result.action == "no-op"
        assert result.changed_fields == []

    def test_apply_config_patch_bridge_restart(self) -> None:
        runtime = _make_runtime()

        result = runtime._apply_config_patch_sync(
            {"connection_url": "wss://new-host:4000/CP_1"}
        )

        assert result.action == "bridge_restart_required"
        assert "connection_url" in result.changed_fields
        assert runtime.config.connection_url == "wss://new-host:4000/CP_1"

    def test_apply_config_patch_runtime_rebuild(self) -> None:
        runtime = _make_runtime()

        result = runtime._apply_config_patch_sync({"multi_evse_mode": True})

        assert result.action == "runtime_rebuild_required"
        assert "multi_evse_mode" in result.changed_fields
        assert runtime.config.multi_evse_mode is True

    def test_save_config(self) -> None:
        runtime = _make_runtime()
        runtime.config.save = MagicMock()

        result = runtime._save_config_sync()

        assert isinstance(result, ConfigSaveResult)
        assert result.saved is True
        runtime.config.save.assert_called_once()

    def test_restart_bridge(self) -> None:
        with patch("chargeghost_evse.api.runtime.Bridge") as mock_bridge_cls:
            first_bridge = MagicMock()
            second_bridge = MagicMock()
            mock_bridge_cls.side_effect = [first_bridge, second_bridge]
            config = _make_config()
            runtime = SimulationRuntime(config=config)

            old_bridge = runtime.bridge
            runtime.restart_bridge()

            old_bridge.shutdown.assert_called_once()
            assert runtime.bridge is second_bridge

    def test_rebuild_runtime(self) -> None:
        with patch("chargeghost_evse.api.runtime.Bridge") as mock_bridge_cls:
            first_bridge = MagicMock()
            second_bridge = MagicMock()
            mock_bridge_cls.side_effect = [first_bridge, second_bridge]
            config = _make_config()
            runtime = SimulationRuntime(config=config)

            old_engine = runtime.engine
            runtime.rebuild_runtime()

            old_bridge = first_bridge
            old_bridge.shutdown.assert_called_once()
            assert runtime.engine is not old_engine

    def test_properties_expose_internal_state(self) -> None:
        runtime = _make_runtime()

        assert runtime.engine is not None
        assert runtime.controller is not None
        assert runtime.config is not None
        assert isinstance(runtime.config, SimulationConfig)

    def test_get_ocpp_config_keys_returns_empty_when_no_bridge(self) -> None:
        runtime = _make_runtime(connection_url="")
        assert runtime.bridge is None
        assert runtime.get_ocpp_config_keys() == []

    def test_get_ocpp_config_keys_returns_empty_when_no_runner(self) -> None:
        with patch("chargeghost_evse.api.runtime.Bridge") as mock_bridge_cls:
            mock_bridge = MagicMock()
            mock_bridge.runner = None
            mock_bridge_cls.return_value = mock_bridge
            config = _make_config()
            runtime = SimulationRuntime(config=config)

            assert runtime.get_ocpp_config_keys() == []

    def test_get_ocpp_config_keys_returns_keys(self) -> None:
        with patch("chargeghost_evse.api.runtime.Bridge") as mock_bridge_cls:
            mock_bridge = MagicMock()
            mock_key = MagicMock()
            mock_key.key = "HeartbeatInterval"
            mock_key.value = "300"
            mock_key.readonly = False
            mock_bridge.runner.adapter.config_manager.get_all_keys.return_value = [
                mock_key
            ]
            mock_bridge_cls.return_value = mock_bridge
            config = _make_config()
            runtime = SimulationRuntime(config=config)

            keys = runtime.get_ocpp_config_keys()
            assert len(keys) == 1
            assert keys[0]["key"] == "HeartbeatInterval"
            assert keys[0]["value"] == "300"
            assert keys[0]["readonly"] is False
