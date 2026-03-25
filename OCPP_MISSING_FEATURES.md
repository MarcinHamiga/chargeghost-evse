# OCPP 1.6J Implementation Status - ChargeGhost EVSE

This document outlines the current state of OCPP 1.6J compliance for the ChargeGhost EVSE simulator. It serves as a roadmap for future development to achieve full protocol compliance.

## 1. Feature Profile Progress

| Profile | Status | Description |
| :--- | :--- | :--- |
| **Core** | Implemented | Full support: BootNotification, Heartbeat, StatusNotification, Authorize, StartTransaction, StopTransaction, MeterValues, RemoteStart/Stop, Reset, ChangeAvailability, UnlockConnector, ChangeConfiguration, GetConfiguration, ClearCache, DataTransfer. |
| **Firmware Management** | Implemented | Full support for diagnostics upload and firmware updates with complete status reporting. |
| **Local Auth List** | Implemented | Full support for local authorization lists, caching, and list updates. |
| **Smart Charging** | Implemented | Full support for SetChargingProfile, ClearChargingProfile, and GetCompositeSchedule with all profile purposes (ChargePointMaxProfile, TxDefaultProfile, TxProfile) and schedule kinds (Absolute, Recurring, Relative). |
| **Reservation** | Implemented | Full support for ReserveNow and CancelReservation with expiry management. |
| **Remote Trigger** | Implemented | Full support for TriggerMessage (Heartbeat, StatusNotification, MeterValues, BootNotification, DiagnosticsStatusNotification, FirmwareStatusNotification). |

---

## 2. Implemented Messages

### Inbound Messages (Central System → Charge Point)

**Core Profile**
- [x] **RemoteStartTransaction**: Start a transaction on a connector with an ID tag.
- [x] **RemoteStopTransaction**: Stop an active transaction on a connector.
- [x] **Reset**: Trigger a Soft (application restart) or Hard (reboot) reset.
- [x] **ChangeConfiguration**: Update OCPP configuration keys.
- [x] **GetConfiguration**: Retrieve OCPP configuration key values.
- [x] **ChangeAvailability**: Set a connector (or entire Charge Point) to Inoperative or Operative.
- [x] **UnlockConnector**: Remotely unlock a connector's physical lock.
- [x] **ClearCache**: Clear the in-memory authorization cache.
- [x] **DataTransfer**: Generic message for vendor-specific extensions.

**Reservation Profile**
- [x] **ReserveNow**: Reserve a connector for a specific `idTag` until an `expiryDate`.
- [x] **CancelReservation**: Cancel a previously made reservation.

**Remote Trigger Profile**
- [x] **TriggerMessage**: Request the Charge Point to send a specific message immediately.

**Firmware Management Profile**
- [x] **GetDiagnostics**: Request diagnostics log file upload (simulated).
- [x] **UpdateFirmware**: Request firmware download and installation (simulated).

**Local Auth List Management Profile**
- [x] **SendLocalList**: Receive and store authorized ID tags for offline operation.
- [x] **GetLocalListVersion**: Query the version of the current local authorization list.

**Smart Charging Profile**
- [x] **SetChargingProfile**: Receive and enforce charging schedules with power/current limits over time.
- [x] **ClearChargingProfile**: Remove active or scheduled charging constraints.
- [x] **GetCompositeSchedule**: Calculate the effective charging limit for a specific time window.

### Outbound Messages (Charge Point → Central System)

**Core Profile**
- [x] **BootNotification**: Announce system startup and device information.
- [x] **Heartbeat**: Send periodic keep-alive messages.
- [x] **Authorize**: Request authorization for an ID tag before transaction start.
- [x] **StartTransaction**: Report transaction initiation with meter value.
- [x] **StopTransaction**: Report transaction termination with final meter value.
- [x] **StatusNotification**: Report connector status changes.
- [x] **MeterValues**: Send periodic or on-demand meter readings.
- [x] **DataTransfer**: Send vendor-specific data to the Central System.

**Firmware Management Profile**
- [x] **DiagnosticsStatusNotification**: Report progress of diagnostics upload.
- [x] **FirmwareStatusNotification**: Report firmware update progress.

**Security Extension**
- [x] **SecurityEventNotification**: Report security-related events (e.g., failed authentication).

---

## 3. Configuration Keys

OCPP 1.6 defines mandatory and optional configuration keys. All relevant keys are implemented:

### Implemented Mandatory Keys
| Key | Default | Description |
| :--- | :--- | :--- |
| `AllowOfflineTxForUnknownId` | false | Whether to allow offline transactions for unknown ID tags |
| `AuthorizationCacheEnabled` | true | Whether authorization cache is enabled |
| `AuthorizeRemoteTxRequests` | true | Whether to authorize remote transaction requests |
| `ClockAlignedDataInterval` | 0 | Interval for clock-aligned meter value sampling (0=disabled) |
| `ConnectionTimeout` | 30 | Connection timeout in seconds |
| `ConnectorPhaseRotation` | 0.RST | Phase rotation for connectors |
| `GetConfigurationMaxKeys` | 50 | Maximum configuration keys per request |
| `HeartbeatInterval` | 300 | Heartbeat interval in seconds (0 = disabled) |
| `LocalAuthListEnabled` | false | Whether local authorization list is enabled |
| `LocalAuthorizeOffline` | true | Whether to use local auth list when offline |
| `LocalPreAuthorize` | false | Whether to check local auth list before CSMS |
| `MeterValuesAlignedData` | Energy.Active.Import.Register | Measurands for clock-aligned meter values |
| `MeterValuesSampledData` | Energy.Active.Import.Register | Measurands for sampled meter values |
| `MeterValueSampleInterval` | 60 | Interval for meter value sampling in seconds |
| `NumberOfConnectors` | 1 | Number of connectors on this charge point |
| `ResetRetries` | 1 | Number of retries for reset operation |
| `StopTransactionOnEVSideDisconnect` | true | Stop transaction when EV side disconnects |
| `StopTransactionOnInvalidId` | true | Stop transaction on invalid ID tag |
| `SupportedFeatureProfiles` | (all 6) | List of supported OCPP feature profiles |
| `TransactionMessageAttempts` | 3 | Number of attempts to send transaction messages |
| `TransactionMessageRetryInterval` | 10 | Retry interval for transaction messages in seconds |
| `UnlockConnectorOnEVSideDisconnect` | true | Unlock connector when EV side disconnects |

### Read-Only Keys (Device Capabilities)
| Key | Default | Description |
| :--- | :--- | :--- |
| `ChargeProfileMaxStackLevel` | 5 | Maximum stack level for charging profiles |
| `ChargingScheduleAllowedChargingRateUnit` | Current,Power | Allowed charging rate units |
| `ChargingScheduleMaxPeriods` | 10 | Maximum periods in a charging schedule |
| `GetProfileIds` | (dynamic) | Comma-separated list of installed charging profile IDs |
| `LocalAuthListMaxLength` | 100 | Maximum entries in local authorization list |
| `MaxChargingProfilesInstalled` | 20 | Maximum charging profiles installed |
| `SendLocalListMaxLength` | 20 | Maximum entries in send local list |
| `StopTransactionMaxLength` | 10 | Maximum meter values in a StopTransaction |

### Optional Keys
| Key | Default | Description |
| :--- | :--- | :--- |
| `LightIntensity` | 100 | Intensity of the charge point light in percent |
| `WebSocketPingInterval` | 10 | WebSocket ping interval in seconds |

---

## 4. Architectural & Infrastructure Gaps

### Persistence Layer
- [ ] **Configuration Store**: Persistent storage (JSON/SQLite) to retain OCPP configuration keys across restarts.
- [ ] **Transaction Persistence**: Ability to recover an ongoing transaction and its meter values if the process crashes or restarts.
- [ ] **Log Storage**: Local buffering of events for `GetDiagnostics`.

### Security
- [ ] **TLS Certificate Management**: Mechanisms to rotate certificates via OCPP.
- [ ] **OCPP 1.6 Security Whitepaper**: Full implementation of the three security profiles (Unsecured, TLS with Basic Auth, TLS with Client Side Certificates).

### Logic & Robustness
- [x] **Message Queuing (Offline)**: Buffering mandatory messages when the connection is lost and re-sending them upon reconnection.
- [x] **CallError Handling**: Gracefully handling error responses from the Central System for all message types.
- [x] **State Machine Validation**: Ensuring strict adherence to connector states.

---

## 5. Summary Statistics

- **Inbound Messages**: 19 of 19 implemented (100%)
- **Outbound Messages**: 10 of 10 implemented (100%)
- **Feature Profiles**: 6 of 6 implemented (100%)
- **Configuration Keys**: All mandatory and optional keys implemented

**Last Updated**: March 19, 2026
