from dataclasses import dataclass
from typing import Optional

from ocpp.v16.enums import ConfigurationStatus

from chargeghost_evse.util.event import Event


@dataclass
class ConfigurationKey:
    key: str
    value: str
    readonly: bool
    default: Optional[str]
    description: str
    mandatory: bool = False


class ConfigurationKeyManager:
    def __init__(self) -> None:
        self._keys: dict[str, ConfigurationKey] = {}
        self.on_key_changed: Event = Event()

    def get_key(self, key: str) -> Optional[ConfigurationKey]:
        return self._keys.get(key)

    def get_all_keys(self) -> list[ConfigurationKey]:
        return list(self._keys.values())

    def set_key(self, key: str, value: str) -> ConfigurationStatus:
        config_key = self._keys.get(key)
        if config_key is None:
            return ConfigurationStatus.not_supported
        if config_key.readonly:
            return ConfigurationStatus.rejected
        config_key.value = value
        self.on_key_changed.emit(key_name=key, new_value=value)
        return ConfigurationStatus.accepted

    def get_int_value(self, key: str, default: int = 0) -> int:
        config_key = self._keys.get(key)
        if config_key is None:
            return default
        try:
            return int(config_key.value)
        except (TypeError, ValueError):
            return default

    def get_bool_value(self, key: str, default: bool = False) -> bool:
        config_key = self._keys.get(key)
        if config_key is None:
            return default
        value = config_key.value.lower()
        return value in ("true", "1", "yes", "on")

    def initialize_defaults(self) -> None:
        self._keys = {
            "AuthorizeRemoteTxRequests": ConfigurationKey(
                key="AuthorizeRemoteTxRequests",
                value="true",
                readonly=False,
                default="true",
                description="Whether to authorize remote transaction requests",
                mandatory=False,
            ),
            "ChargeProfileMaxStackLevel": ConfigurationKey(
                key="ChargeProfileMaxStackLevel",
                value="5",
                readonly=True,
                default="5",
                description="Maximum stack level for charging profiles",
                mandatory=False,
            ),
            "ChargingScheduleAllowedChargingRateUnit": ConfigurationKey(
                key="ChargingScheduleAllowedChargingRateUnit",
                value="Current,Power",
                readonly=True,
                default="Current,Power",
                description="Allowed charging rate units for charging schedules",
                mandatory=False,
            ),
            "ChargingScheduleMaxPeriods": ConfigurationKey(
                key="ChargingScheduleMaxPeriods",
                value="10",
                readonly=True,
                default="10",
                description="Maximum number of periods in a charging schedule",
                mandatory=False,
            ),
            "ClockAlignedDataInterval": ConfigurationKey(
                key="ClockAlignedDataInterval",
                value="900",
                readonly=False,
                default="900",
                description="Interval for clock-aligned meter value sampling in seconds (0=disabled, 900=15min)",
                mandatory=False,
            ),
            "ConnectionTimeout": ConfigurationKey(
                key="ConnectionTimeout",
                value="30",
                readonly=False,
                default="30",
                description="Connection timeout in seconds",
                mandatory=True,
            ),
            "ConnectorPhaseRotation": ConfigurationKey(
                key="ConnectorPhaseRotation",
                value="RST.RST",
                readonly=False,
                default="RST.RST",
                description="Phase rotation for connectors",
                mandatory=False,
            ),
            "HeartbeatInterval": ConfigurationKey(
                key="HeartbeatInterval",
                value="300",
                readonly=False,
                default="300",
                description="Heartbeat interval in seconds (0 = disabled)",
                mandatory=True,
            ),
            "LocalAuthListEnabled": ConfigurationKey(
                key="LocalAuthListEnabled",
                value="false",
                readonly=False,
                default="false",
                description="Whether local authorization list is enabled",
                mandatory=False,
            ),
            "LocalAuthListMaxLength": ConfigurationKey(
                key="LocalAuthListMaxLength",
                value="100",
                readonly=True,
                default="100",
                description="Maximum number of entries in local authorization list",
                mandatory=False,
            ),
            "MaxChargingProfilesInstalled": ConfigurationKey(
                key="MaxChargingProfilesInstalled",
                value="20",
                readonly=True,
                default="20",
                description="Maximum number of charging profiles installed",
                mandatory=False,
            ),
            "MeterValueSampleInterval": ConfigurationKey(
                key="MeterValueSampleInterval",
                value="60",
                readonly=False,
                default="60",
                description="Interval for meter value sampling in seconds",
                mandatory=False,
            ),
            "ResetRetries": ConfigurationKey(
                key="ResetRetries",
                value="0",
                readonly=False,
                default="0",
                description="Number of retries for reset operation",
                mandatory=True,
            ),
            "SendLocalListMaxLength": ConfigurationKey(
                key="SendLocalListMaxLength",
                value="20",
                readonly=True,
                default="20",
                description="Maximum entries in send local list",
                mandatory=False,
            ),
            "StopTransactionOnEVSideDisconnect": ConfigurationKey(
                key="StopTransactionOnEVSideDisconnect",
                value="true",
                readonly=False,
                default="true",
                description="Stop transaction when EV side disconnects",
                mandatory=True,
            ),
            "StopTxOnInvalidId": ConfigurationKey(
                key="StopTxOnInvalidId",
                value="true",
                readonly=False,
                default="true",
                description="Stop transaction on invalid ID tag",
                mandatory=False,
            ),
            "TransactionMessageAttempts": ConfigurationKey(
                key="TransactionMessageAttempts",
                value="3",
                readonly=False,
                default="3",
                description="Number of attempts to send transaction messages",
                mandatory=False,
            ),
            "TransactionMessageRetryInterval": ConfigurationKey(
                key="TransactionMessageRetryInterval",
                value="30",
                readonly=False,
                default="30",
                description="Retry interval for transaction messages in seconds",
                mandatory=False,
            ),
            "WebSocketPingInterval": ConfigurationKey(
                key="WebSocketPingInterval",
                value="10",
                readonly=False,
                default="10",
                description="WebSocket ping interval in seconds",
                mandatory=False,
            ),
        }
