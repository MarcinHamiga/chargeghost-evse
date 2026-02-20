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
            "AllowOfflineTxForUnknownId": ConfigurationKey(
                key="AllowOfflineTxForUnknownId",
                value="false",
                readonly=False,
                default="false",
                description="Whether to allow offline transactions for unknown ID tags",
                mandatory=True,
            ),
            "AuthorizationCacheEnabled": ConfigurationKey(
                key="AuthorizationCacheEnabled",
                value="true",
                readonly=False,
                default="true",
                description="Whether authorization cache is enabled",
                mandatory=True,
            ),
            "AuthorizeRemoteTxRequests": ConfigurationKey(
                key="AuthorizeRemoteTxRequests",
                value="true",
                readonly=False,
                default="true",
                description="Whether to authorize remote transaction requests",
                mandatory=True,
            ),
            "ChargeProfileMaxStackLevel": ConfigurationKey(
                key="ChargeProfileMaxStackLevel",
                value="5",
                readonly=True,
                default="5",
                description="Maximum stack level for charging profiles",
                mandatory=True,
            ),
            "ChargingScheduleAllowedChargingRateUnit": ConfigurationKey(
                key="ChargingScheduleAllowedChargingRateUnit",
                value="Current,Power",
                readonly=True,
                default="Current,Power",
                description="Allowed charging rate units for charging schedules",
                mandatory=True,
            ),
            "ChargingScheduleMaxPeriods": ConfigurationKey(
                key="ChargingScheduleMaxPeriods",
                value="10",
                readonly=True,
                default="10",
                description="Maximum number of periods in a charging schedule",
                mandatory=True,
            ),
            "ClockAlignedDataInterval": ConfigurationKey(
                key="ClockAlignedDataInterval",
                value="0",
                readonly=False,
                default="0",
                description="Size of the interval in seconds for clock-aligned data (0=disabled)",
                mandatory=True,
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
                value="0.RST",
                readonly=False,
                default="0.RST",
                description="Phase rotation for connectors (e.g. 0.RST, 1.RST, 2.RTS)",
                mandatory=True,
            ),
            "GetConfigurationMaxKeys": ConfigurationKey(
                key="GetConfigurationMaxKeys",
                value="50",
                readonly=True,
                default="50",
                description="Maximum number of configuration keys that can be retrieved in one request",
                mandatory=True,
            ),
            "HeartbeatInterval": ConfigurationKey(
                key="HeartbeatInterval",
                value="300",
                readonly=False,
                default="300",
                description="Heartbeat interval in seconds (0 = disabled)",
                mandatory=True,
            ),
            "LightIntensity": ConfigurationKey(
                key="LightIntensity",
                value="100",
                readonly=False,
                default="100",
                description="Intensity of the charge point light in percent",
                mandatory=False,
            ),
            "LocalAuthListEnabled": ConfigurationKey(
                key="LocalAuthListEnabled",
                value="false",
                readonly=False,
                default="false",
                description="Whether local authorization list is enabled",
                mandatory=True,
            ),
            "LocalAuthListMaxLength": ConfigurationKey(
                key="LocalAuthListMaxLength",
                value="100",
                readonly=True,
                default="100",
                description="Maximum number of entries in local authorization list",
                mandatory=True,
            ),
            "LocalAuthorizeOffline": ConfigurationKey(
                key="LocalAuthorizeOffline",
                value="true",
                readonly=False,
                default="true",
                description="Whether to use local authorization list when offline",
                mandatory=True,
            ),
            "LocalPreAuthorize": ConfigurationKey(
                key="LocalPreAuthorize",
                value="false",
                readonly=False,
                default="false",
                description="Whether to use local authorization list before CSMS authorization",
                mandatory=True,
            ),
            "MaxChargingProfilesInstalled": ConfigurationKey(
                key="MaxChargingProfilesInstalled",
                value="20",
                readonly=True,
                default="20",
                description="Maximum number of charging profiles installed",
                mandatory=True,
            ),
            "MeterValuesAlignedData": ConfigurationKey(
                key="MeterValuesAlignedData",
                value="Energy.Active.Import.Register",
                readonly=False,
                default="Energy.Active.Import.Register",
                description="Measurands to be included in clock-aligned meter values",
                mandatory=True,
            ),
            "MeterValuesSampledData": ConfigurationKey(
                key="MeterValuesSampledData",
                value="Energy.Active.Import.Register",
                readonly=False,
                default="Energy.Active.Import.Register",
                description="Measurands to be included in sampled meter values",
                mandatory=True,
            ),
            "MeterValueSampleInterval": ConfigurationKey(
                key="MeterValueSampleInterval",
                value="60",
                readonly=False,
                default="60",
                description="Interval for meter value sampling in seconds (0=disabled)",
                mandatory=True,
            ),
            "NumberOfConnectors": ConfigurationKey(
                key="NumberOfConnectors",
                value="1",
                readonly=True,
                default="1",
                description="Number of connectors on this charge point",
                mandatory=True,
            ),
            "ResetRetries": ConfigurationKey(
                key="ResetRetries",
                value="1",
                readonly=False,
                default="1",
                description="Number of retries for reset operation",
                mandatory=True,
            ),
            "StopTransactionMaxLength": ConfigurationKey(
                key="StopTransactionMaxLength",
                value="10",
                readonly=True,
                default="10",
                description="Maximum number of meter values in a StopTransaction.req",
                mandatory=True,
            ),
            "StopTransactionOnEVSideDisconnect": ConfigurationKey(
                key="StopTransactionOnEVSideDisconnect",
                value="true",
                readonly=False,
                default="true",
                description="Stop transaction when EV side disconnects",
                mandatory=True,
            ),
            "StopTransactionOnInvalidId": ConfigurationKey(
                key="StopTransactionOnInvalidId",
                value="true",
                readonly=False,
                default="true",
                description="Stop transaction on invalid ID tag",
                mandatory=True,
            ),
            "StopTxOnEVSideDisconnect": ConfigurationKey(
                key="StopTxOnEVSideDisconnect",
                value="true",
                readonly=False,
                default="true",
                description="Alias for StopTransactionOnEVSideDisconnect",
                mandatory=False,
            ),
            "StopTxOnInvalidId": ConfigurationKey(
                key="StopTxOnInvalidId",
                value="true",
                readonly=False,
                default="true",
                description="Alias for StopTransactionOnInvalidId",
                mandatory=False,
            ),
            "SupportedFeatureProfiles": ConfigurationKey(
                key="SupportedFeatureProfiles",
                value="Core,FirmwareManagement,LocalAuthListManagement,RemoteTrigger",
                readonly=True,
                default="Core,FirmwareManagement,LocalAuthListManagement,RemoteTrigger",
                description="List of supported OCPP feature profiles",
                mandatory=True,
            ),
            "TransactionMessageAttempts": ConfigurationKey(
                key="TransactionMessageAttempts",
                value="3",
                readonly=False,
                default="3",
                description="Number of attempts to send transaction messages",
                mandatory=True,
            ),
            "TransactionMessageRetryInterval": ConfigurationKey(
                key="TransactionMessageRetryInterval",
                value="10",
                readonly=False,
                default="10",
                description="Retry interval for transaction messages in seconds",
                mandatory=True,
            ),
            "UnlockConnectorOnEVSideDisconnect": ConfigurationKey(
                key="UnlockConnectorOnEVSideDisconnect",
                value="true",
                readonly=False,
                default="true",
                description="Unlock connector when EV side disconnects",
                mandatory=True,
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

