# OCPP 1.6J Implementation Status - ChargeGhost EVSE

This document outlines the current state of OCPP 1.6J compliance for the ChargeGhost EVSE simulator. It serves as a roadmap for future development to achieve full protocol compliance.

## 1. Feature Profile Progress

| Profile | Status | Description |
| :--- | :--- | :--- |
| **Core** | Partial | Basic charging loop and heartbeat are implemented. Administrative commands like Reset and UnlockConnector are missing. |
| **Firmware Management** | Implemented | Simulated diagnostics upload and firmware updates. |
| **Local Auth List** | Implemented | Full support for local authorization lists, caching, and list updates. |
| **Smart Charging** | Missing | No support for charging profiles or load balancing. |
| **Reservation** | Missing | No support for connector reservations. |
| **Remote Trigger** | Missing | No support for Central System triggered messages. |

---

## 2. Detailed Unimplemented Messages

### Core Profile
- [ ] **ChangeAvailability**: Allows CS to set a connector (or the whole CP) to `Inoperative` or `Operative`.
- [x] **ChangeConfiguration**: Critical for updating system settings (e.g., `HeartbeatInterval`, `ConnectionTimeout`).
- [x] **GetConfiguration**: Allows the CS to retrieve current configuration key values.
- [ ] **Reset**: Support for `Soft` (application restart) and `Hard` (reboot) reset commands.
- [ ] **ClearCache**: Command to clear the local authorization cache.
- [ ] **UnlockConnector**: Remote command to release the locking mechanism on a connector.
- [ ] **DataTransfer**: Generic message for vendor-specific extensions.

### Firmware Management Profile
- [x] **GetDiagnostics**: Request for the CP to upload log files to a specified location. (Simulated)
- [x] **DiagnosticsStatusNotification**: Reporting the progress/status of a log upload.
- [x] **UpdateFirmware**: Command to download and install a firmware image from a URI. (Simulated)
- [x] **FirmwareStatusNotification**: Reporting stages: `Downloading`, `Downloaded`, `Installing`, `Installed`, `InstallationFailed`.

### Smart Charging Profile
- [ ] **SetChargingProfile**: Receiving and enforcing complex charging schedules (Power/Current limits over time).
- [ ] **ClearChargingProfile**: Removing active or scheduled charging constraints.
- [ ] **GetCompositeSchedule**: Calculating the effective charging limit for a specific time window.

### Reservation Profile
- [ ] **ReserveNow**: Reserving a connector for a specific `idTag` until an `expiryDate`.
- [ ] **CancelReservation**: Releasing a previously held reservation.

### Local Auth List Management Profile
- [x] **SendLocalList**: Receiving a batch of authorized tags for offline operation.
- [x] **GetLocalListVersion**: Querying the version of the currently stored local list.

### Remote Trigger Profile
- [ ] **TriggerMessage**: CS request for the CP to send a specific message immediately (e.g., `Heartbeat`, `StatusNotification`, `MeterValues`).

---

## 3. Configuration Keys

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

## 4. Architectural & Infrastructure Gaps

### Persistence Layer
- [ ] **Configuration Store**: Persistent storage (JSON/SQLite) to retain OCPP configuration keys across restarts.
- [ ] **Transaction Persistence**: Ability to recover an ongoing transaction and its meter values if the process crashes or restarts.
- [ ] **Log Storage**: Local buffering of events for `GetDiagnostics`.

### Security
- [ ] **TLS Certificate Management**: Mechanisms to rotate certificates via OCPP.
- [ ] **SecurityEventNotification**: Reporting security-related events (e.g., failed logins, invalid certificates).
- [ ] **OCPP 1.6 Security Whitepaper**: Full implementation of the three security profiles (Unsecured, TLS with Basic Auth, TLS with Client Side Certificates).

### Logic & Robustness
- [ ] **Message Queuing (Offline)**: Buffering mandatory messages (like `MeterValues`, `StopTransaction`) when the connection is lost and re-sending them upon reconnection.
- [ ] **CallError Handling**: Gracefully handling error responses from the Central System for all message types.
- [ ] **State Machine Validation**: Ensuring strict adherence to connector states (e.g., not allowing a transaction to start if the connector is `Faulted` or `Inoperative`).
