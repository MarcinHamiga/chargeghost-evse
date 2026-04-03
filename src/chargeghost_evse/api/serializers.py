from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional, cast

from chargeghost_evse.engine.connector import Connector
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.engine.energy_meter import EnergyMeter
from chargeghost_evse.engine.session import Session
from chargeghost_evse.util.config import SimulationConfig


def create_ws_message(message_type: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": message_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def serialize_connector(connector: Connector) -> dict[str, Any]:
    return {
        "id": connector.id,
        "status": connector.status.value,
        "voltage": connector.voltage,
        "current": connector.current,
        "phase": connector.phase,
        "is_plugged_in": connector.is_plugged_in,
        "id_tag": connector.id_tag,
    }


def serialize_session(
    session: Session, meter: Optional[EnergyMeter] = None
) -> dict[str, Any]:
    return {
        "transaction_id": session.transaction_id,
        "connector_id": session.connector_id,
        "energy_charged_wh": round(session.energy_charged, 2),
        "state_of_charge": round(session.state_of_charge, 1),
        "start_time": session.start_time,
        "id_tag": session.id_tag,
        "is_charging": meter.is_charging if meter else False,
    }


def serialize_stopped_session(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "transaction_id": data["transaction_id"],
        "connector_id": data["connector_id"],
        "energy_charged_wh": round(data["energy_charged"], 2),
        "meter_stop": round(data["meter_stop"], 2),
        "reason": data["reason"],
        "id_tag": data.get("id_tag"),
    }


def serialize_system_status(
    engine: Engine,
    bridge: Optional[Any] = None,
    start_time: Optional[float] = None,
) -> dict[str, Any]:
    connectors = [serialize_connector(c) for c in engine.connectors]
    sessions = []
    for connector in engine.connectors:
        session = engine.get_session(connector.id)
        if session is not None:
            meter = engine.get_energy_meter(connector.id)
            sessions.append(serialize_session(session, meter))

    energy_meters = {}
    for c in engine.connectors:
        meter = engine.get_energy_meter(c.id)
        energy_meters[str(c.id)] = {
            "reading_wh": round(meter.get_meter_reading(), 2),
            "is_charging": meter.is_charging,
        }

    ocpp_connected = False
    if bridge is not None:
        ocpp_connected = getattr(
            getattr(bridge, "runner", bridge), "is_connected", False
        )

    result: dict[str, Any] = {
        "ocpp_connected": ocpp_connected,
        "connectors": connectors,
        "active_sessions": sessions,
        "energy_meters": energy_meters,
    }
    if start_time is not None:
        result["uptime_seconds"] = round(time.monotonic() - start_time, 1)
    return result


def serialize_config(config: SimulationConfig) -> dict[str, Any]:
    return {
        "connection_url": config.connection_url,
        "ocpp_id": config.ocpp_id,
        "charge_point_model": config.charge_point_model,
        "charge_point_vendor": config.charge_point_vendor,
        "connectors": [c.to_dict() for c in config.connectors],
        "skip_tls_verify": config.skip_tls_verify,
        "log_mode": config.log_mode,
        "multi_evse_mode": config.multi_evse_mode,
        "ev_battery_capacity": config.ev_battery_capacity,
        "ocpp_version": config.ocpp_version,
        "persist_message_queue": config.persist_message_queue,
        "rfid_tag": config.rfid_tag,
    }


def serialize_full_state(
    engine: Engine,
    bridge: Optional[Any] = None,
) -> dict[str, Any]:
    active_sessions = []
    for connector in engine.connectors:
        session = engine.get_session(connector.id)
        if session is None:
            continue
        active_sessions.append(
            serialize_session(
                cast(Session, session), engine.get_energy_meter(connector.id)
            )
        )

    return {
        "connectors": [
            serialize_connector(connector) for connector in engine.connectors
        ],
        "active_sessions": active_sessions,
        "ocpp_connected": (
            getattr(getattr(bridge, "runner", bridge), "is_connected", False)
            if bridge
            else False
        ),
    }
