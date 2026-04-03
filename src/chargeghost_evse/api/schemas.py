from __future__ import annotations

import enum
from typing import Any, Literal, Optional

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


class FaultDefinitionInfo(BaseModel):
    fault_id: str
    label: str
    scope: str
    lifetime: str
    default_config: Optional[dict[str, Any]] = None


class FaultStateInfo(BaseModel):
    fault_id: str
    enabled: bool
    trigger_count: int
    config: Optional[dict[str, Any]] = None


class FaultEnableRequest(BaseModel):
    fault_id: str
    parameters: Optional[dict[str, Any]] = None
    count_limit: Optional[int] = None


class ScenarioStepInfo(BaseModel):
    kind: str
    label: str
    step_index: int
    action: Optional[str] = None
    condition: Optional[str] = None
    expected: Optional[Any] = None
    duration: Optional[float] = None
    fault_action: Optional[str] = None
    fault_id: Optional[str] = None
    message: Optional[str] = None


class ScenarioInfo(BaseModel):
    name: str
    description: str
    version: str
    step_count: int
    steps: list[ScenarioStepInfo]


class ScenarioLoadRequest(BaseModel):
    schema_version: str = "1.0"
    name: str = ""
    description: str = ""
    version: str = "1.0"
    defaults: Optional[dict[str, Any]] = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    metadata: Optional[dict[str, Any]] = None


class RunnerStatusResponse(BaseModel):
    state: str
    scenario_name: Optional[str] = None
    current_step_index: int = 0


class StepResultInfo(BaseModel):
    step_index: int
    kind: str
    label: str
    success: bool
    duration: float
    error_message: Optional[str] = None


class ScenarioReportInfo(BaseModel):
    scenario_name: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    success: bool
    failure_reason: Optional[str] = None
    failed_step_index: Optional[int] = None
    steps: list[StepResultInfo] = Field(default_factory=list)


class OcppConfigKeyUpdateRequest(BaseModel):
    key: str
    value: str


class ChargingSchedulePeriodInfo(BaseModel):
    start_period: int
    limit: float
    number_phases: Optional[int] = None


class ChargingScheduleInfo(BaseModel):
    charging_rate_unit: str
    charging_schedule_period: list[ChargingSchedulePeriodInfo] = Field(
        default_factory=list
    )
    duration: Optional[int] = None
    start_schedule: Optional[str] = None
    min_charging_rate: Optional[float] = None


class ChargingProfileInfo(BaseModel):
    charging_profile_id: int
    stack_level: int
    charging_profile_purpose: str
    charging_profile_kind: str
    charging_schedule: ChargingScheduleInfo
    transaction_id: Optional[int] = None
    recurrency_kind: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class ChargingProfileSetRequest(BaseModel):
    connector_id: int
    profile: dict[str, Any]


class ChargingProfileClearRequest(BaseModel):
    profile_id: Optional[int] = None
    connector_id: Optional[int] = None
    purpose: Optional[str] = None
    stack_level: Optional[int] = None


class CompositeScheduleRequest(BaseModel):
    connector_id: int
    duration: int


class CompositeSchedulePeriodInfo(BaseModel):
    start_period: int
    limit: float


class CompositeScheduleResponse(BaseModel):
    connector_id: int
    duration: int
    start_time: Optional[str] = None
    periods: list[CompositeSchedulePeriodInfo] = Field(default_factory=list)


class ReservationInfo(BaseModel):
    reservation_id: int
    connector_id: int
    id_tag: str
    expiry_date: str
    parent_id_tag: Optional[str] = None


class ReservationCreateRequest(BaseModel):
    connector_id: int
    reservation_id: int
    id_tag: str
    expiry_date: str
    parent_id_tag: Optional[str] = None


class VersionInfo(BaseModel):
    current_version: str
    latest_version: Optional[str] = None
    update_available: bool = False


class ReleaseInfoResponse(BaseModel):
    tag_name: str
    body: str
    published_at: str
    assets: list[dict[str, Any]] = Field(default_factory=list)


class DownloadProgressInfo(BaseModel):
    status: str
    progress: int = Field(ge=0, le=100)
    message: str


class SessionDetailInfo(BaseModel):
    transaction_id: int
    connector_id: int
    energy_charged_wh: float
    state_of_charge: float
    start_time: float
    max_energy: float
    is_charging: bool
    id_tag: Optional[str] = None


class TimelineEventInfo(BaseModel):
    event_id: int
    timestamp: str
    source: str
    direction: str
    event_type: str
    protocol_version: str
    action: str
    message_id: str
    connector_id: int
    transaction_id: int
    level: int
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_key: str = ""
    tags: list[str] = Field(default_factory=list)


class TimelineQueryParams(BaseModel):
    source: Optional[str] = None
    direction: Optional[str] = None
    event_type: Optional[str] = None
    action: Optional[str] = None
    limit: Optional[int] = None
    offset: Optional[int] = None
    connector_id: Optional[int] = None
    transaction_id: Optional[int] = None
    min_level: Optional[int] = None
    tags: Optional[list[str]] = None
    search: Optional[str] = None


class RawStartTransactionRequest(BaseModel):
    connector_id: int
    id_tag: str
    meter_start: Optional[int] = None
    timestamp: Optional[str] = None


class RawStopTransactionRequest(BaseModel):
    transaction_id: int
    meter_stop: Optional[int] = None
    timestamp: Optional[str] = None
    reason: Optional[str] = None


class StatusNotificationRequest(BaseModel):
    connector_id: int
    error_code: str = "NoError"
    status: str


class MeterValuesRequest(BaseModel):
    connector_id: int
    value: Optional[float] = None
    transaction_id: Optional[int] = None


class DataTransferRequest(BaseModel):
    vendor_id: str
    message_id: Optional[str] = None
    data: Optional[str] = None


class DiagnosticsStatusRequest(BaseModel):
    status: str


class FirmwareStatusRequest(BaseModel):
    status: str


class SecurityEventRequest(BaseModel):
    event_type: str
    timestamp: Optional[str] = None
    tech_info: Optional[str] = None


class LocalAuthListEntryInfo(BaseModel):
    id_tag: str
    id_tag_info: dict[str, Any]
    is_expired: bool
    authorization_status: str


class LocalAuthListInfo(BaseModel):
    version: int
    entry_count: int
    max_entries: int
    enabled: bool
    entries: list[LocalAuthListEntryInfo]


class LocalAuthListUpdateRequest(BaseModel):
    list_version: int
    entries: Optional[list[dict[str, Any]]] = None
    update_type: Literal["full", "differential"]


class FirmwareStatusInfo(BaseModel):
    status: Optional[str] = None
    location: Optional[str] = None
    retrieve_date: Optional[str] = None
    file_name: Optional[str] = None
    file_hash: Optional[str] = None


class DiagnosticsStatusInfo(BaseModel):
    status: Optional[str] = None
    location: Optional[str] = None


class FirmwareTriggerRequest(BaseModel):
    location: str
    retrieve_date: Optional[str] = None


class DiagnosticsTriggerRequest(BaseModel):
    location: str
    retries: int = 0
    retry_interval: int = 0


class AboutInfo(BaseModel):
    version: str
    description: str
    ocpp_versions: list[str]
    license: str
    features: list[str]
