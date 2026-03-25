from dataclasses import dataclass, field
from typing import Callable, Optional

from ocpp.v16.enums import ConfigurationStatus

from chargeghost_evse.util.event import Event
from chargeghost_evse.util.helpers import parse_bool_string


@dataclass
class ConfigurationKey:
    key: str
    value: str
    readonly: bool
    default: Optional[str]
    description: str
    mandatory: bool = False
    category: str = "Core"
    value_provider: Optional[Callable[[], str]] = field(default=None, repr=False)

    def get_value(self) -> str:
        """Return dynamic value from provider if set, otherwise static value."""
        if self.value_provider is not None:
            return self.value_provider()
        return self.value


class ConfigurationKeyManager:
    def __init__(self) -> None:
        self._keys: dict[str, ConfigurationKey] = {}
        self.on_key_changed: Event = Event()

    def register_key(self, config_key: ConfigurationKey) -> None:
        """Register an additional configuration key."""
        self._keys[config_key.key] = config_key

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
            return int(config_key.get_value())
        except (TypeError, ValueError):
            return default

    def get_bool_value(self, key: str, default: bool = False) -> bool:
        config_key = self._keys.get(key)
        if config_key is None:
            return default
        return parse_bool_string(config_key.get_value())

    def initialize_defaults(self) -> None:
        self._keys = {
            "AllowOfflineTxForUnknownId": ConfigurationKey(
                key="AllowOfflineTxForUnknownId",
                value="false",
                readonly=False,
                default="false",
                description="Whether to allow offline transactions for unknown ID tags",
                mandatory=True,
                category="Core",
            ),
            "AuthorizationCacheEnabled": ConfigurationKey(
                key="AuthorizationCacheEnabled",
                value="true",
                readonly=False,
                default="true",
                description="Whether authorization cache is enabled",
                mandatory=True,
                category="Core",
            ),
            "AuthorizeRemoteTxRequests": ConfigurationKey(
                key="AuthorizeRemoteTxRequests",
                value="true",
                readonly=False,
                default="true",
                description="Whether to authorize remote transaction requests",
                mandatory=True,
                category="Core",
            ),
            "ChargeProfileMaxStackLevel": ConfigurationKey(
                key="ChargeProfileMaxStackLevel",
                value="5",
                readonly=True,
                default="5",
                description="Maximum stack level for charging profiles",
                mandatory=True,
                category="SmartCharging",
            ),
            "ChargingScheduleAllowedChargingRateUnit": ConfigurationKey(
                key="ChargingScheduleAllowedChargingRateUnit",
                value="Current,Power",
                readonly=True,
                default="Current,Power",
                description="Allowed charging rate units for charging schedules",
                mandatory=True,
                category="SmartCharging",
            ),
            "ChargingScheduleMaxPeriods": ConfigurationKey(
                key="ChargingScheduleMaxPeriods",
                value="10",
                readonly=True,
                default="10",
                description="Maximum number of periods in a charging schedule",
                mandatory=True,
                category="SmartCharging",
            ),
            "ClockAlignedDataInterval": ConfigurationKey(
                key="ClockAlignedDataInterval",
                value="0",
                readonly=False,
                default="0",
                description="Size of the interval in seconds for clock-aligned data (0=disabled)",
                mandatory=True,
                category="Core",
            ),
            "ConnectionTimeout": ConfigurationKey(
                key="ConnectionTimeout",
                value="30",
                readonly=False,
                default="30",
                description="Connection timeout in seconds",
                mandatory=True,
                category="Core",
            ),
            "ConnectorPhaseRotation": ConfigurationKey(
                key="ConnectorPhaseRotation",
                value="0.RST",
                readonly=False,
                default="0.RST",
                description="Phase rotation for connectors (e.g. 0.RST, 1.RST, 2.RTS)",
                mandatory=True,
                category="Core",
            ),
            "GetConfigurationMaxKeys": ConfigurationKey(
                key="GetConfigurationMaxKeys",
                value="50",
                readonly=True,
                default="50",
                description="Maximum number of configuration keys that can be retrieved in one request",
                mandatory=True,
                category="Core",
            ),
            "HeartbeatInterval": ConfigurationKey(
                key="HeartbeatInterval",
                value="300",
                readonly=False,
                default="300",
                description="Heartbeat interval in seconds (0 = disabled)",
                mandatory=True,
                category="Core",
            ),
            "LightIntensity": ConfigurationKey(
                key="LightIntensity",
                value="100",
                readonly=False,
                default="100",
                description="Intensity of the charge point light in percent",
                mandatory=False,
                category="Core",
            ),
            "LocalAuthListEnabled": ConfigurationKey(
                key="LocalAuthListEnabled",
                value="false",
                readonly=False,
                default="false",
                description="Whether local authorization list is enabled",
                mandatory=True,
                category="LocalAuthList",
            ),
            "LocalAuthListMaxLength": ConfigurationKey(
                key="LocalAuthListMaxLength",
                value="100",
                readonly=True,
                default="100",
                description="Maximum number of entries in local authorization list",
                mandatory=True,
                category="LocalAuthList",
            ),
            "LocalAuthorizeOffline": ConfigurationKey(
                key="LocalAuthorizeOffline",
                value="true",
                readonly=False,
                default="true",
                description="Whether to use local authorization list when offline",
                mandatory=True,
                category="LocalAuthList",
            ),
            "LocalPreAuthorize": ConfigurationKey(
                key="LocalPreAuthorize",
                value="false",
                readonly=False,
                default="false",
                description="Whether to use local authorization list before CSMS authorization",
                mandatory=True,
                category="LocalAuthList",
            ),
            "MaxChargingProfilesInstalled": ConfigurationKey(
                key="MaxChargingProfilesInstalled",
                value="20",
                readonly=True,
                default="20",
                description="Maximum number of charging profiles installed",
                mandatory=True,
                category="SmartCharging",
            ),
            "MeterValuesAlignedData": ConfigurationKey(
                key="MeterValuesAlignedData",
                value="Energy.Active.Import.Register",
                readonly=False,
                default="Energy.Active.Import.Register",
                description="Measurands to be included in clock-aligned meter values",
                mandatory=True,
                category="Core",
            ),
            "MeterValuesSampledData": ConfigurationKey(
                key="MeterValuesSampledData",
                value="Energy.Active.Import.Register",
                readonly=False,
                default="Energy.Active.Import.Register",
                description="Measurands to be included in sampled meter values",
                mandatory=True,
                category="Core",
            ),
            "MeterValueSampleInterval": ConfigurationKey(
                key="MeterValueSampleInterval",
                value="60",
                readonly=False,
                default="60",
                description="Interval for meter value sampling in seconds (0=disabled)",
                mandatory=True,
                category="Core",
            ),
            "NumberOfConnectors": ConfigurationKey(
                key="NumberOfConnectors",
                value="1",
                readonly=True,
                default="1",
                description="Number of connectors on this charge point",
                mandatory=True,
                category="Core",
            ),
            "ResetRetries": ConfigurationKey(
                key="ResetRetries",
                value="1",
                readonly=False,
                default="1",
                description="Number of retries for reset operation",
                mandatory=True,
                category="Core",
            ),
            "StopTransactionMaxLength": ConfigurationKey(
                key="StopTransactionMaxLength",
                value="10",
                readonly=True,
                default="10",
                description="Maximum number of meter values in a StopTransaction.req",
                mandatory=True,
                category="Core",
            ),
            "StopTransactionOnEVSideDisconnect": ConfigurationKey(
                key="StopTransactionOnEVSideDisconnect",
                value="true",
                readonly=False,
                default="true",
                description="Stop transaction when EV side disconnects",
                mandatory=True,
                category="Core",
            ),
            "StopTransactionOnInvalidId": ConfigurationKey(
                key="StopTransactionOnInvalidId",
                value="true",
                readonly=False,
                default="true",
                description="Stop transaction on invalid ID tag",
                mandatory=True,
                category="Core",
            ),
            "StopTxOnEVSideDisconnect": ConfigurationKey(
                key="StopTxOnEVSideDisconnect",
                value="true",
                readonly=False,
                default="true",
                description="Alias for StopTransactionOnEVSideDisconnect",
                mandatory=False,
                category="Core",
            ),
            "StopTxOnInvalidId": ConfigurationKey(
                key="StopTxOnInvalidId",
                value="true",
                readonly=False,
                default="true",
                description="Alias for StopTransactionOnInvalidId",
                mandatory=False,
                category="Core",
            ),
            "SupportedFeatureProfiles": ConfigurationKey(
                key="SupportedFeatureProfiles",
                value="Core,FirmwareManagement,LocalAuthListManagement,Reservation,RemoteTrigger,SmartCharging",
                readonly=True,
                default="Core,FirmwareManagement,LocalAuthListManagement,Reservation,RemoteTrigger,SmartCharging",
                description="List of supported OCPP feature profiles",
                mandatory=True,
                category="Core",
            ),
            "TransactionMessageAttempts": ConfigurationKey(
                key="TransactionMessageAttempts",
                value="3",
                readonly=False,
                default="3",
                description="Number of attempts to send transaction messages",
                mandatory=True,
                category="Core",
            ),
            "TransactionMessageRetryInterval": ConfigurationKey(
                key="TransactionMessageRetryInterval",
                value="10",
                readonly=False,
                default="10",
                description="Retry interval for transaction messages in seconds",
                mandatory=True,
                category="Core",
            ),
            "UnlockConnectorOnEVSideDisconnect": ConfigurationKey(
                key="UnlockConnectorOnEVSideDisconnect",
                value="true",
                readonly=False,
                default="true",
                description="Unlock connector when EV side disconnects",
                mandatory=True,
                category="Core",
            ),
            "WebSocketPingInterval": ConfigurationKey(
                key="WebSocketPingInterval",
                value="10",
                readonly=False,
                default="10",
                description="WebSocket ping interval in seconds",
                mandatory=False,
                category="Core",
            ),
        }
