from __future__ import annotations

import time
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from chargeghost_evse.api.serializers import (
    create_ws_message,
    serialize_config,
    serialize_connector,
    serialize_full_state,
    serialize_session,
    serialize_stopped_session,
    serialize_system_status,
)
from chargeghost_evse.util.config import ConnectorConfig, SimulationConfig


def _make_connector(
    connector_id: int,
    *,
    status: str = "Available",
    voltage: float = 230.0,
    current: float = 32.0,
    phase: int = 1,
    is_plugged_in: bool = False,
    id_tag: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=connector_id,
        status=SimpleNamespace(value=status),
        voltage=voltage,
        current=current,
        phase=phase,
        is_plugged_in=is_plugged_in,
        id_tag=id_tag,
    )


def _make_session(
    transaction_id: int,
    connector_id: int,
    *,
    energy_charged: float = 1234.56,
    state_of_charge: float = 67.8,
    start_time: float = 1710000000.0,
    id_tag: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        transaction_id=transaction_id,
        connector_id=connector_id,
        energy_charged=energy_charged,
        state_of_charge=state_of_charge,
        start_time=start_time,
        id_tag=id_tag,
    )


def _make_meter(*, reading_wh: float = 0.0, is_charging: bool = False) -> MagicMock:
    return MagicMock(
        get_meter_reading=MagicMock(return_value=reading_wh),
        is_charging=is_charging,
    )


def _make_engine(
    *,
    connectors: list[SimpleNamespace] | None = None,
    sessions: dict[int, SimpleNamespace] | None = None,
    meters: dict[int, MagicMock] | None = None,
) -> MagicMock:
    engine = MagicMock()
    engine.connectors = connectors or []
    engine.get_session.side_effect = lambda cid: (sessions or {}).get(cid)
    engine.get_energy_meter.side_effect = lambda cid: (meters or {}).get(
        cid, _make_meter()
    )
    return engine


class TestCreateWsMessage:
    def test_creates_envelope_with_type_timestamp_data(self) -> None:
        data = {"foo": "bar"}
        result = create_ws_message("tick", data)

        assert result["type"] == "tick"
        assert result["data"] == data
        ts = result["timestamp"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None

    def test_different_message_types(self) -> None:
        for msg_type in ("state_snapshot", "tick", "error", "custom_event"):
            result = create_ws_message(msg_type, {})
            assert result["type"] == msg_type


class TestSerializeConnector:
    def test_serializes_all_fields(self) -> None:
        connector = _make_connector(
            3,
            status="Charging",
            voltage=400.0,
            current=16.0,
            phase=3,
            is_plugged_in=True,
            id_tag="TAG1",
        )
        result = serialize_connector(connector)

        assert result == {
            "id": 3,
            "status": "Charging",
            "voltage": 400.0,
            "current": 16.0,
            "phase": 3,
            "is_plugged_in": True,
            "id_tag": "TAG1",
        }

    def test_status_is_string_value(self) -> None:
        connector = _make_connector(1, status="Preparing")
        result = serialize_connector(connector)

        assert result["status"] == "Preparing"
        assert isinstance(result["status"], str)


class TestSerializeSession:
    def test_serializes_with_meter(self) -> None:
        session = _make_session(42, 2, energy_charged=999.999, state_of_charge=50.25)
        meter = _make_meter(is_charging=True)
        result = serialize_session(session, meter)

        assert result == {
            "transaction_id": 42,
            "connector_id": 2,
            "energy_charged_wh": 1000.0,
            "state_of_charge": 50.2,
            "start_time": 1710000000.0,
            "id_tag": None,
            "is_charging": True,
        }

    def test_serializes_without_meter(self) -> None:
        session = _make_session(10, 1, energy_charged=0.0, state_of_charge=0.0)
        result = serialize_session(session)

        assert result["is_charging"] is False


class TestSerializeStoppedSession:
    def test_serializes_stopped_session_data(self) -> None:
        data = {
            "transaction_id": 55,
            "connector_id": 2,
            "energy_charged": 321.987,
            "meter_stop": 654.321,
            "reason": "Local",
            "id_tag": "STOP-TAG",
        }
        result = serialize_stopped_session(data)

        assert result == {
            "transaction_id": 55,
            "connector_id": 2,
            "energy_charged_wh": 321.99,
            "meter_stop": 654.32,
            "reason": "Local",
            "id_tag": "STOP-TAG",
        }

    def test_handles_optional_id_tag(self) -> None:
        data = {
            "transaction_id": 10,
            "connector_id": 1,
            "energy_charged": 100.0,
            "meter_stop": 200.0,
            "reason": "Remote",
        }
        result = serialize_stopped_session(data)

        assert result["id_tag"] is None


class TestSerializeSystemStatus:
    def test_with_no_bridge(self) -> None:
        engine = _make_engine()
        result = serialize_system_status(engine)

        assert result["ocpp_connected"] is False

    def test_with_connected_bridge(self) -> None:
        engine = _make_engine()
        bridge = MagicMock()
        bridge.runner.is_connected = True
        result = serialize_system_status(engine, bridge=bridge)

        assert result["ocpp_connected"] is True

    def test_with_start_time(self) -> None:
        engine = _make_engine()
        start = time.monotonic() - 10.0
        result = serialize_system_status(engine, start_time=start)

        assert "uptime_seconds" in result
        assert result["uptime_seconds"] >= 9.0


class TestSerializeConfig:
    def test_serializes_all_config_fields(self) -> None:
        config = SimulationConfig(
            connection_url="wss://example.com/CP_1",
            ocpp_id="CP_1",
            charge_point_model="ModelX",
            charge_point_vendor="VendorY",
            connectors=[ConnectorConfig()],
            skip_tls_verify=True,
            log_mode="deep",
            multi_evse_mode=True,
            ev_battery_capacity=75.0,
            ocpp_version="1.6",
            persist_message_queue=True,
            rfid_tag="TAG456",
        )
        result = serialize_config(config)

        assert result["connection_url"] == "wss://example.com/CP_1"
        assert result["ocpp_id"] == "CP_1"
        assert result["charge_point_model"] == "ModelX"
        assert result["charge_point_vendor"] == "VendorY"
        assert result["skip_tls_verify"] is True
        assert result["log_mode"] == "deep"
        assert result["multi_evse_mode"] is True
        assert result["ev_battery_capacity"] == 75.0
        assert result["ocpp_version"] == "1.6"
        assert result["persist_message_queue"] is True
        assert result["rfid_tag"] == "TAG456"

    def test_connectors_serialized_as_dicts(self) -> None:
        config = SimulationConfig(
            connectors=[
                ConnectorConfig(voltage=400.0, current=16.0, phase=3),
            ]
        )
        result = serialize_config(config)

        assert result["connectors"] == [{"voltage": 400.0, "current": 16.0, "phase": 3}]


class TestSerializeFullState:
    def test_with_no_sessions(self) -> None:
        connector = _make_connector(1)
        engine = _make_engine(connectors=[connector])
        result = serialize_full_state(engine)

        assert result["active_sessions"] == []
        assert result["connectors"] == [serialize_connector(connector)]
        assert result["ocpp_connected"] is False

    def test_with_active_session(self) -> None:
        connector = _make_connector(1, status="Charging")
        session = _make_session(5, 1, id_tag="TAG")
        meter = _make_meter(is_charging=True)
        engine = _make_engine(
            connectors=[connector],
            sessions={1: session},
            meters={1: meter},
        )
        result = serialize_full_state(engine)

        assert len(result["active_sessions"]) == 1
        assert result["active_sessions"][0]["transaction_id"] == 5
        assert result["active_sessions"][0]["connector_id"] == 1
        assert result["active_sessions"][0]["is_charging"] is True
        assert result["active_sessions"][0]["id_tag"] == "TAG"
