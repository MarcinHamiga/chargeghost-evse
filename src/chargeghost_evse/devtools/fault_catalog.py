from chargeghost_evse.devtools.fault_models import (
    FaultDefinition,
    FaultLifetime,
    FaultScope,
)

FAULT_CATALOG: dict[str, FaultDefinition] = {
    "forced_disconnect": FaultDefinition(
        fault_id="forced_disconnect",
        label="Forced Disconnect",
        scope=FaultScope.TRANSPORT,
        lifetime=FaultLifetime.ONE_SHOT,
    ),
    "delayed_reconnect": FaultDefinition(
        fault_id="delayed_reconnect",
        label="Delayed Reconnect",
        scope=FaultScope.TRANSPORT,
        lifetime=FaultLifetime.PERSISTENT,
        default_config={"delay_seconds": 30},
    ),
    "dropped_heartbeat": FaultDefinition(
        fault_id="dropped_heartbeat",
        label="Dropped Heartbeat",
        scope=FaultScope.TRANSPORT,
        lifetime=FaultLifetime.ONE_SHOT,
    ),
    "delayed_response": FaultDefinition(
        fault_id="delayed_response",
        label="Delayed Response",
        scope=FaultScope.PROTOCOL,
        lifetime=FaultLifetime.PERSISTENT,
        default_config={"delay_seconds": 5},
    ),
    "rejected_action": FaultDefinition(
        fault_id="rejected_action",
        label="Rejected Action",
        scope=FaultScope.PROTOCOL,
        lifetime=FaultLifetime.ONE_SHOT,
        default_config={"action": "RemoteStartTransaction"},
    ),
    "trigger_message_not_implemented": FaultDefinition(
        fault_id="trigger_message_not_implemented",
        label="TriggerMessage NotImplemented",
        scope=FaultScope.PROTOCOL,
        lifetime=FaultLifetime.ONE_SHOT,
    ),
    "frozen_meter": FaultDefinition(
        fault_id="frozen_meter",
        label="Frozen Meter",
        scope=FaultScope.METER,
        lifetime=FaultLifetime.PERSISTENT,
    ),
    "meter_jump": FaultDefinition(
        fault_id="meter_jump",
        label="Meter Jump",
        scope=FaultScope.METER,
        lifetime=FaultLifetime.ONE_SHOT,
        default_config={"amount_kwh": 10.0},
    ),
    "meter_reset": FaultDefinition(
        fault_id="meter_reset",
        label="Meter Reset",
        scope=FaultScope.METER,
        lifetime=FaultLifetime.ONE_SHOT,
    ),
    "status_flap": FaultDefinition(
        fault_id="status_flap",
        label="Status Flap",
        scope=FaultScope.STATE,
        lifetime=FaultLifetime.ONE_SHOT,
        default_config={"flap_count": 2},
    ),
}

FAULT_IDS: frozenset[str] = frozenset(FAULT_CATALOG.keys())


def get_fault_definition(fault_id: str) -> FaultDefinition:
    if fault_id not in FAULT_CATALOG:
        raise ValueError(f"Unknown fault ID: {fault_id}")
    return FAULT_CATALOG[fault_id]
