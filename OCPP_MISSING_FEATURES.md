# OCPP 1.6J Implementation Status - ChargeGhost EVSE

This document outlines the current state of OCPP 1.6J compliance for the ChargeGhost EVSE simulator. It serves as a roadmap for future development to achieve full protocol compliance.

## 1. Feature Profile Progress

| Profile | Status | Description |
| :--- | :--- | :--- |
| **Core** | Partial | Basic charging loop, heartbeat, transaction management, remote reset, ChangeAvailability, and UnlockConnector are implemented. ClearCache and DataTransfer are still missing. |
| **Firmware Management** | Implemented | Full support for diagnostics upload and firmware updates with complete status reporting. |
| **Local Auth List** | Implemented | Full support for local authorization lists, caching, and list updates. |
| **Smart Charging** | Implemented | Full support for SetChargingProfile, ClearChargingProfile, and GetCompositeSchedule with all profile purposes (ChargePointMaxProfile, TxDefaultProfile, TxProfile) and schedule kinds (Absolute, Recurring, Relative). |
| **Reservation** | Missing | No support for connector reservations (ReserveNow, CancelReservation). |
| **Remote Trigger** | Missing | No support for Central System triggered messages (TriggerMessage). |

---

## 2. Implemented Messages

### Inbound Messages (Central System → Charge Point)

**Core Profile**
- [x] **RemoteStartTransaction**: Start a transaction on a connector with an ID tag.
- [x] **RemoteStopTransaction**: Stop an active transaction on a connector.
- [x] **Reset**: Trigger a Soft (application restart) or Hard (reboot) reset.
- [x] **ChangeConfiguration**: Update OCPP configuration keys.
- [x] **GetConfiguration**: Retrieve OCPP configuration key values.

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

**Firmware Management Profile**
- [x] **DiagnosticsStatusNotification**: Report progress of diagnostics upload (Uploading, Uploaded, UploadFailed).
- [x] **FirmwareStatusNotification**: Report firmware update progress (Downloading, Downloaded, Installing, Installed, InstallationFailed).

---

## 3. Missing Messages

### Inbound Messages Not Yet Implemented

**Core Profile**
- [x] **ChangeAvailability**: Set a connector (or entire Charge Point) to Inoperative or Operative.
- [ ] **ClearCache**: Clear the local authorization cache.
- [x] **UnlockConnector**: Remotely unlock a connector's physical lock.
- [ ] **DataTransfer**: Generic message for vendor-specific extensions.

**Reservation Profile**
- [ ] **ReserveNow**: Reserve a connector for a specific `idTag` until an `expiryDate`.
- [ ] **CancelReservation**: Cancel a previously made reservation.

**Remote Trigger Profile**
- [ ] **TriggerMessage**: Request the Charge Point to send a specific message immediately (e.g., Heartbeat, StatusNotification, MeterValues).

### Outbound Messages Not Yet Implemented

**Security Profile**
- [ ] **SecurityEventNotification**: Report security-related events (e.g., failed authentication, invalid certificates, unauthorized access attempts).

---

## 4. Configuration Keys

OCPP 1.6 defines mandatory and optional configuration keys. The following are implemented with GUI support:

### Implemented Mandatory Keys
| Key | Default | Description |
| :--- | :--- | :--- |
| `ConnectionTimeout` | 30 | Connection timeout in seconds |
| `HeartbeatInterval` | 300 | Heartbeat interval in seconds (0 = disabled) |
| `ResetRetries` | 0 | Number of retries for reset operation |
| `StopTransactionOnEVSideDisconnect` | true | Stop transaction when EV side disconnects |

### Implemented Optional Keys
| Key | Default | Description |
| :--- | :--- | :--- |
| `AuthorizeRemoteTxRequests` | true | Whether to authorize remote transaction requests |
| `ClockAlignedDataInterval` | 900 | Interval for clock-aligned meter value sampling (0=disabled) |
| `ConnectorPhaseRotation` | RST.RST | Phase rotation for connectors |
| `LocalAuthListEnabled` | false | Whether local authorization list is enabled |
| `MeterValueSampleInterval` | 60 | Interval for meter value sampling in seconds |
| `StopTxOnInvalidId` | true | Stop transaction on invalid ID tag |
| `TransactionMessageAttempts` | 3 | Number of attempts to send transaction messages |
| `TransactionMessageRetryInterval` | 30 | Retry interval for transaction messages in seconds |
| `WebSocketPingInterval` | 10 | WebSocket ping interval in seconds |

### Read-Only Keys (Device Capabilities)
| Key | Default | Description |
| :--- | :--- | :--- |
| `ChargeProfileMaxStackLevel` | 5 | Maximum stack level for charging profiles |
| `ChargingScheduleAllowedChargingRateUnit` | Current,Power | Allowed charging rate units |
| `ChargingScheduleMaxPeriods` | 10 | Maximum periods in a charging schedule |
| `LocalAuthListMaxLength` | 100 | Maximum entries in local authorization list |
| `MaxChargingProfilesInstalled` | 20 | Maximum charging profiles installed |
| `SendLocalListMaxLength` | 20 | Maximum entries in send local list |

### Missing Configuration Keys
- [ ] **GetProfileIds**: List of installed charging profile IDs
- [ ] **ChargingRateUnit**: Default charging rate unit
- [ ] **NumberOfConnectors**: Number of physical connectors

---

## 5. Architectural & Infrastructure Gaps

### Persistence Layer
- [ ] **Configuration Store**: Persistent storage (JSON/SQLite) to retain OCPP configuration keys across restarts.
- [ ] **Transaction Persistence**: Ability to recover an ongoing transaction and its meter values if the process crashes or restarts.
- [ ] **Log Storage**: Local buffering of events for `GetDiagnostics`.

### Security
- [ ] **TLS Certificate Management**: Mechanisms to rotate certificates via OCPP.
- [ ] **SecurityEventNotification**: Reporting security-related events (e.g., failed logins, invalid certificates).
- [ ] **OCPP 1.6 Security Whitepaper**: Full implementation of the three security profiles (Unsecured, TLS with Basic Auth, TLS with Client Side Certificates).

### Logic & Robustness
- [x] **Message Queuing (Offline)**: Buffering mandatory messages (like `MeterValues`, `StopTransaction`) when the connection is lost and re-sending them upon reconnection.
- [x] **CallError Handling**: Gracefully handling error responses from the Central System for all message types.
- [x] **State Machine Validation**: Ensuring strict adherence to connector states (e.g., not allowing a transaction to start if the connector is `Faulted` or `Inoperative`).

---

## 6. Summary Statistics

- **Inbound Messages**: 13 of 19 implemented (68%)
- **Outbound Messages**: 9 of 10 implemented (90%)
- **Feature Profiles**: 4 of 6 implemented (67%)
- **Configuration Keys**: 16 of 19 implemented (84%)

**Last Updated**: March 10, 2026
