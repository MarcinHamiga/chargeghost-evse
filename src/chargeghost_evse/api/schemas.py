from __future__ import annotations

import enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from chargeghost_evse.util.config import BATTERY_CAPACITY_MAX, BATTERY_CAPACITY_MIN


class ConnectorStateEnum(str, enum.Enum):
    AVAILABLE = "Available"
    PREPARING = "Preparing"
    CHARGING = "Charging"
    SUSPENDED_EVSE = "SuspendedEVSE"
    SUSPENDED_EV = "SuspendedEV"
    FINISHING = "Finishing"
    RESERVED = "Reserved"
    UNAVAILABLE = "Unavailable"
    FAULTED = "Faulted"


class ConnectorInfo(BaseModel):
    id: int
    status: ConnectorStateEnum
    voltage: float
    current: float
    phase: int
    is_plugged_in: bool = False
    id_tag: Optional[str] = None


class SessionInfo(BaseModel):
    transaction_id: int
    connector_id: int
    energy_charged_wh: float
    state_of_charge: float
    start_time: float
    id_tag: Optional[str] = None
    is_charging: bool


class EnergyMeterInfo(BaseModel):
    reading_wh: float
    is_charging: bool


class SystemStatus(BaseModel):
    ocpp_connected: bool
    connectors: list[ConnectorInfo]
    active_sessions: list[SessionInfo]
    energy_meters: dict[int, EnergyMeterInfo]


class ActionResult(BaseModel):
    success: bool
    message: str
    details: Optional[dict[str, Any]] = None


class ConfigInfo(BaseModel):
    connection_url: str
    ocpp_id: str
    charge_point_model: str
    charge_point_vendor: str
    connectors: list[dict[str, Any]]
    skip_tls_verify: bool
    log_mode: str
    multi_evse_mode: bool
    ev_battery_capacity: float
    ocpp_version: str
    persist_message_queue: bool
    rfid_tag: Optional[str] = None


class ConfigUpdate(BaseModel):
	connection_url: Optional[str] = Field(default=None, min_length=1)
	ocpp_id: Optional[str] = None
	ocpp_password: Optional[str] = None
	charge_point_model: Optional[str] = None
	charge_point_vendor: Optional[str] = None
	skip_tls_verify: Optional[bool] = None
	log_mode: Optional[str] = None
	multi_evse_mode: Optional[bool] = None
	ev_battery_capacity: Optional[float] = Field(
		default=None,
		ge=BATTERY_CAPACITY_MIN,
		le=BATTERY_CAPACITY_MAX,
	)
	ocpp_version: Optional[str] = None
	rfid_tag: Optional[str] = None


class OcppConfigKeyInfo(BaseModel):
    key: str
    value: str
    readonly: bool
    default: Optional[str] = None
    description: str
    mandatory: bool
    category: str


class ConnectorCreateRequest(BaseModel):
    voltage: float = Field(default=230.0, ge=120.0, le=1000.0)
    current: float = Field(default=32.0, ge=6.0, le=150.0)
    phase: int = Field(default=1, ge=1, le=3)


class ConnectorUpdateRequest(BaseModel):
    voltage: Optional[float] = Field(default=None, ge=120.0, le=1000.0)
    current: Optional[float] = Field(default=None, ge=6.0, le=150.0)
    phase: Optional[int] = Field(default=None, ge=1, le=3)


class StoppedSessionResponse(BaseModel):
    transaction_id: int
    connector_id: int
    energy_charged_wh: float
    meter_stop: float
    reason: str
    id_tag: Optional[str] = None


class WSStateMessage(BaseModel):
    type: str
    timestamp: str
    data: dict
