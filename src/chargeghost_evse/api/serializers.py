from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional, cast

from chargeghost_evse.devtools.timeline_models import TimelineEvent
from chargeghost_evse.engine.connector import Connector
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.engine.energy_meter import EnergyMeter
from chargeghost_evse.engine.session import Session
from chargeghost_evse.ocpp_adapter.firmware_manager import FirmwareManager
from chargeghost_evse.ocpp_adapter.local_auth_list import LocalAuthListManager
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


def serialize_timeline_event(event: TimelineEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "source": event.source,
        "direction": event.direction,
        "event_type": event.event_type,
        "protocol_version": event.protocol_version,
        "action": event.action,
        "message_id": event.message_id,
        "connector_id": event.connector_id,
        "transaction_id": event.transaction_id,
        "level": event.level,
        "summary": event.summary,
        "payload": event.payload,
        "correlation_key": event.correlation_key,
        "tags": event.tags,
    }


def serialize_local_auth_list(manager: LocalAuthListManager) -> dict[str, Any]:
    entries = [
        _serialize_local_auth_entry_info(entry) for entry in manager._entries.values()
    ]
    return {
        "version": manager.version,
        "enabled": manager.enabled,
        "entry_count": manager.entry_count,
        "max_entries": manager.max_entries,
        "entries": entries,
    }


def serialize_local_auth_entry(
    manager: LocalAuthListManager, id_tag: str
) -> Optional[dict[str, Any]]:
    entry = manager._entries.get(id_tag)
    if entry is None:
        return None
    return {
        "version": manager.version,
        "enabled": manager.enabled,
        "entry_count": 1,
        "max_entries": manager.max_entries,
        "entries": [_serialize_local_auth_entry_info(entry)],
    }


def _serialize_local_auth_entry_info(entry: Any) -> dict[str, Any]:
    return {
        "id_tag": entry.id_tag,
        "id_tag_info": entry.id_tag_info,
        "is_expired": entry.is_expired(),
        "authorization_status": entry.get_authorization_status().value,
    }


def serialize_firmware_status(manager: FirmwareManager) -> dict[str, Any]:
    task = manager.firmware_task
    return {
        "status": manager.get_firmware_status().value,
        "location": task.location if task else None,
        "retrieve_date": task.retrieve_date.isoformat()
        if task and task.retrieve_date
        else None,
        "retries": task.retries if task else 0,
        "retry_interval": task.retry_interval if task else 0,
        "file_name": task.file_name if task else None,
        "file_hash": task.file_hash if task else None,
    }


def serialize_diagnostics_status(manager: FirmwareManager) -> dict[str, Any]:
    task = manager.diagnostics_task
    return {
        "status": manager.get_diagnostics_status().value,
        "location": task.location if task else None,
        "start_time": task.start_time.isoformat() if task and task.start_time else None,
        "stop_time": task.stop_time.isoformat() if task and task.stop_time else None,
        "retries": task.retries if task else 0,
        "retry_interval": task.retry_interval if task else 0,
    }
