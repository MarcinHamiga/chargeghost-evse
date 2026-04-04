# OCPP 2.0.1 Implementation Plan — ChargeGhost EVSE

## Current State

**Already implemented** (6 inbound, 8 outbound handlers):
- Inbound: `RequestStartTransaction`, `RequestStopTransaction`, `TriggerMessage`, `ChangeAvailability`, `UnlockConnector`, `Reset`
- Outbound: `BootNotification`, `Heartbeat`, `StatusNotification`, `Authorize`, `TransactionEvent(Started/Updated/Ended)`, `MeterValues`
- Supporting: `TransactionManagerV201`, status/reason/context mapping dicts, bridge V201 path dispatch

**Gap**: 37 additional Core messages, full device model, V201-specific managers, enhanced smart charging, variable monitoring, display messages, tariff/cost, reservations enhancement, and diagnostics restructuring.

---

## Architecture Principles

1. **Parallel paths, not replacement** — All V201 code lives alongside V16. The bridge dispatches based on `_is_v201()`. Existing V16 code is never modified.
2. **Versioned managers** — New `*V201` manager classes use native OCPP 2.0.1 datatypes. Shared logic extracted to abstract bases where natural.
3. **Full device model** — New `device_model/` package implements the Component -> Variable tree, `NotifyReport` reporting, and variable monitoring.
4. **Engine stays protocol-agnostic** — The Engine continues to manage Connectors/Sessions without OCPP version awareness. The adapter/bridge layers handle all protocol translation.

---

## Phase 1 — Transaction Lifecycle & Smart Charging

**Goal**: Full OCPP 2.0.1 transaction fidelity and smart charging parity with V16.

### 1.1 Enhanced TransactionEvent

**Files**: `ocpp_adapter/v201_adapter.py`, `ocpp_adapter/transaction_manager_v201.py`, `engine/session.py`

- **UUID transaction IDs** — `TransactionManagerV201.begin_transaction()` generates `uuid4()` strings instead of sequential integers
- **Configurable TxStartStopPoint** — New `TxStartStopPointConfig` in the adapter/engine that controls which physical events trigger `TransactionEvent(Started)` (e.g., `EVConnected` vs `EnergyTransfer` vs `Authorized`)
- **Full trigger reason mapping** — Map all 14 `TriggerReasonEnumType` values from engine events:
  - `cable_plugged_in` -> `CablePluggedIn`
  - `authorized` -> `Authorized`
  - `charging_state_changed` -> `ChargingStateChanged` (SUSPENDED_EV/CHARGING transitions)
  - `charging_rate_changed` -> `ChargingRateChanged` (profile limit change)
  - `meter_value_periodic` / `meter_value_clock` -> `MeterValuePeriodic` / `MeterValueClock`
  - `ev_departed` -> `EVDeparted`
  - `stop_requested` -> `StopRequested`
  - `de_authorized` -> `DeAuthorized`
  - `energy_limit_reached` -> `EnergyLimitReached`
  - `trigger` -> `Trigger`
  - `unlock_command` -> `UnlockCommand`
- **Charging state in TransactionEvent(Updated)** — Map `ConnectorState` to `ChargingStateEnumType`:
  - `CHARGING` -> `Charging`, `SUSPENDED_EV` -> `SuspendedEV`, `SUSPENDED_EVSE` -> `SuspendedEVSE`
- **Embedded meter values** — All periodic meter values during a transaction go into `TransactionEvent(Updated).meter_value` instead of standalone `MeterValues`
- **Response handling** — Process `TransactionEvent` response fields: `total_cost`, `charging_priority`, `id_token_info`, `updated_personal_message`
- **Offline sequence tracking** — `TransactionManagerV201` persists pending seq_no state for offline replay

**Tests**: `test_v201_transactions.py` expanded, new `test_v201_tx_start_stop_points.py`

### 1.2 Smart Charging V201

**Files**: New `ocpp_adapter/charging_profile_manager_v201.py`

- **`ChargingProfileManagerV201`** — New class with:
  - **Multi-schedule tuples** — `ChargingProfileType` with array of `ChargingScheduleType` (each with `id`, `chargingRateUnit`, periods). Most restrictive across all schedules wins.
  - **EVSE targeting** — Profiles target `evse_id` instead of `connector_id`
  - **New purpose**: `ChargingStationExternalConstraints` — grid operator limits
  - **Source tracking** — `ChargingLimitSourceEnumType` (CSO, EMS, SO, Other)
  - **Composite schedule calculation** — Stack level + purpose precedence, same logic as V16 but with multi-schedule aggregation
- **Inbound handlers**:
  - `SetChargingProfile` — Install profile with EVSE targeting, enhanced validation
  - `ClearChargingProfile` — With `charging_profile_criteria` filter
  - `GetChargingProfiles` — Async query returning `ReportChargingProfiles`
  - `GetCompositeSchedule` — Returns `CompositeScheduleType` with period details
- **Outbound handlers**:
  - `send_report_charging_profiles()` — Async delivery with `tbc` pagination
  - `send_notify_charging_limit()` — Report EMS/local limits
  - `send_cleared_charging_limit()` — Report limit removal
- **Bridge integration** — `get_limit` callback wired to `ChargingProfileManagerV201.get_composite_limit()`

**Tests**: New `test_charging_profile_manager_v201.py`

### 1.3 Enhanced StatusNotification

**Files**: `ocpp_adapter/v201_adapter.py`, `engine/connector.py`

- **5-state model** — Map the 9-state `ConnectorState` (V16) down to 5 `ConnectorStatusEnumType` values (already partially done in `_STATUS_MAP`)
- **Transaction state via TransactionEvent** — Charging/suspended states reported through `TransactionEvent(Updated).charging_state`, not `StatusNotification`
- **Fault via NotifyEvent** — `FAULTED` status also triggers `NotifyEvent` with fault details

---

## Phase 2 — Device Model & Configuration

**Goal**: Full Component -> Variable tree, `GetVariables`/`SetVariables`, device model reporting, variable monitoring.

### 2.1 Device Model Package

**Files**: New `ocpp_adapter/device_model/` package

```
device_model/
    __init__.py
    device_model.py          # ChargingStationDeviceModel class
    component.py             # Component, EVSEComponent, ConnectorComponent
    variable.py              # Variable, VariableAttribute, VariableCharacteristics
    report_builder.py        # Builds NotifyReport payloads from device model
    monitoring/
        __init__.py
        monitor.py           # VariableMonitor (threshold, periodic, delta)
        monitor_manager.py   # SetVariableMonitoring, ClearVariableMonitoring, etc.
```

- **`ChargingStationDeviceModel`** — Holds the component-variable tree. Initialized with:
  - `Controller` components: `TxCtrlr`, `SmartChargingCtrlr`, `AuthCtrlr`, `OCPPCommCtrlr`, `TariffCostCtrlr`, `SampledDataCtrlr`
  - Physical components: `Connector`, `EVSE`, `Meter`, `TemperatureSensor`, `AcDcConverter`
  - Each component declares `Variable`s with `Mutability`, `Attribute` (Actual/Target/MinSet/MaxSet), data type, and default value
- **`EVSEComponent`** — Wraps EVSE ID + child `ConnectorComponent`s. Maps to engine's `Connector` concept.
- **Report builder** — Generates `NotifyReport` payloads for `GetBaseReport` and `GetReport` requests with `tbc` pagination

### 2.2 GetVariables / SetVariables Handlers

**Files**: `ocpp_adapter/v201_adapter.py`, `ocpp_adapter/device_model/`

- **`on_get_variables()`** — Accept `GetVariableDataType[]`, resolve each against device model, return `GetVariableResultType[]` with `AttributeEnumType` support
- **`on_set_variables()`** — Accept `SetVariableDataType[]`, write to device model, return `SetVariableResultType[]`. Validates mutability. Triggers `on_key_changed`-equivalent events for bridge consumption.
- **Replace `ConfigurationKeyManager`** — V201 adapter uses device model instead of flat key-value store. The bridge detects which manager the adapter exposes.

### 2.3 Variable Monitoring

**Files**: `ocpp_adapter/device_model/monitoring/`

- **`MonitorManager`** — Manages `SetMonitoringDataType` entries with:
  - `UpperThreshold` / `LowerThreshold` — fires `NotifyEvent` when value crosses
  - `Delta` — fires when value changes by configured amount
  - `Periodic` / `PeriodicClockAligned` — fires at intervals
- **Handlers**:
  - `on_set_variable_monitoring()` — Install monitors
  - `on_clear_variable_monitoring()` — Remove by ID
  - `on_get_monitoring_report()` — Returns `NotifyMonitoringReport`
  - `on_set_monitoring_base()` — Set baseline (AllMonitoring, FactoryDefault, HardWiredOnly)
  - `on_set_monitoring_level()` — Set severity filter
- **Evaluation loop** — Integrated with the bridge's meter-values polling thread. Each tick evaluates active monitors and queues `NotifyEvent` sends for threshold breaches.

**Tests**: `test_device_model.py`, `test_v201_variables.py`, `test_v201_monitoring.py`

---

## Phase 3 — Reservations, Local Auth, Display, Data Transfer

### 3.1 Enhanced Reservations

**Files**: `ocpp_adapter/v201_adapter.py`, `engine/reservation.py`

- **`on_reserve_now()`** — Accepts `evse_id`, `connector_type`, `group_id_token`, `reservation_id`
- **`on_cancel_reservation()`** — Largely unchanged, uses `reservation_id`
- **`send_reservation_status_update()`** — New outbound for `Expired`/`Removed` notifications
- **Engine changes** — `Reservation` dataclass gains `connector_type`, `group_id_tag` fields (with V16 compatibility)
- **Expiry loop** — Bridge checks reservation expiry and sends `ReservationStatusUpdate(expired)`

### 3.2 Local Auth List V201

**Files**: New `ocpp_adapter/local_auth_list_v201.py`

- **`LocalAuthListManagerV201`** — Same core logic as V16 but uses OCPP 2.0.1 `AuthorizationData` with `IdTokenType` instead of flat `idTag` strings
- **Handlers**:
  - `on_get_local_list_version()` — Return version
  - `on_send_local_list()` — Differential/Full update with V201 `AuthorizationData[]`
- **`on_clear_cache()`** — Clears `AuthorizationCacheManager` (shared)

### 3.3 Display Messages

**Files**: `ocpp_adapter/v201_adapter.py`

- **`on_set_display_message()`** — Store `MessageInfoType` with priority, state filter, transaction ID
- **`on_get_display_messages()`** — Return stored messages
- **`on_clear_display_message()`** — Remove by ID
- **`send_notify_display_messages()`** — Async delivery
- **UI integration** — `QtSignalBridge` emits signal for UI to show/update messages

### 3.4 Data Transfer

**Files**: `ocpp_adapter/v201_adapter.py`

- **`on_data_transfer()`** — Largely identical to V16, uses V201 `DataTransferStatus`
- **`send_data_transfer()`** — Outbound vendor-specific data

### 3.5 GetTransactionStatus

**Files**: `ocpp_adapter/v201_adapter.py`

- **`on_get_transaction_status()`** — Returns whether messages are queued for a given `transaction_id`

---

## Phase 4 — Firmware, Diagnostics, Events

### 4.1 Firmware Manager V201

**Files**: New `ocpp_adapter/firmware_manager_v201.py`

- **`FirmwareManagerV201`** — Enhanced firmware lifecycle:
  - `UpdateFirmware` with `FirmwareType` (signing_certificate, signature, install_date_time)
  - Wait for `retrieve_date_time`, download, verify signature, install
  - `PublishFirmware` support for local controller scenarios
- **Handlers**:
  - `on_update_firmware()` — Schedule firmware update with signature verification
  - `on_publish_firmware()` — Publish firmware locally
  - `on_unpublish_firmware()` — Remove published firmware
- **Outbound**:
  - `send_firmware_status_notification()` — V201 status (expanded statuses)
  - `send_publish_firmware_status_notification()` — Publish progress

### 4.2 Diagnostics -> GetLog

**Files**: `ocpp_adapter/firmware_manager_v201.py`

- **`on_get_log()`** — Replaces `GetDiagnostics`. Supports `DiagnosticsLog` and `SecurityLog` types
- **`send_log_status_notification()`** — Replaces `DiagnosticsStatusNotification`

### 4.3 NotifyEvent

**Files**: `ocpp_adapter/v201_adapter.py`

- **`send_notify_event()`** — Report events/errors/alerts with `EventDataType` (component, variable, actual_value, event_notification, severity)
- **Fault reporting** — `ConnectorState.FAULTED` -> `NotifyEvent` with fault code and severity
- **Monitor breaches** — Variable monitor threshold crossings -> `NotifyEvent`

---

## Phase 5 — Tariff/Cost & Security Events

### 5.1 Tariff & Cost

**Files**: `ocpp_adapter/v201_adapter.py`

- **Process `CostUpdated`** — Inbound from CSMS: `transaction_id`, `total_cost`, `currency`
- **`TransactionEvent` response** — Handle `total_cost` in started/updated responses
- **`send_customer_information()`** — If `CustomerInformation` is requested
- **TariffCostCtrlr variables** — Exposed via device model

### 5.2 Security Event Notification

**Files**: `ocpp_adapter/v201_adapter.py`

- **`send_security_event_notification()`** — Already partially present in V16, port to V201 format
- **Security events**: authentication failures, firmware tampering, reset events, configuration changes

---

## Phase 6 — Bridge Integration & UI

### 6.1 Bridge V201 Path Expansion

**Files**: `bridge/bridge.py`

- **Meter values routing** — During transaction: embedded in `TransactionEvent(Updated)`. Outside transaction: standalone `MeterValues`
- **Event subscriptions** — New engine events (if any) wired to V201-specific sends
- **Message queue awareness** — V201 message types (`TransactionEventStarted`, `TransactionEventEnded`, `TransactionEventUpdated`) in offline queue drain
- **ChargingProfileManager injection** — Bridge wires `get_limit` to `ChargingProfileManagerV201` when V201 active
- **Device model sync** — Engine state changes reflected in device model variables

### 6.2 UI Updates

**Files**: `ui/bridge.py`, `ui/widgets/`

- **Device model panel** — Display component-variable tree
- **Display message widget** — Show active CSMS display messages
- **Tariff/cost display** — Show running cost during transaction
- **Charging state display** — V201 `ChargingStateEnumType` in connector status
- **Event log** — Show `NotifyEvent` entries in timeline

---

## Phase 7 — Testing & Validation

### 7.1 Unit Tests

New test files (one per feature area):

| Test File | Scope |
|---|---|
| `test_v201_tx_start_stop_points.py` | Configurable start/stop points, all trigger reasons |
| `test_charging_profile_manager_v201.py` | Multi-schedule, EVSE targeting, external constraints |
| `test_v201_device_model.py` | Component-variable tree, report generation |
| `test_v201_variables.py` | GetVariables/SetVariables |
| `test_v201_monitoring.py` | Variable monitors, threshold breaches |
| `test_v201_reservations.py` | Enhanced reservations, status updates |
| `test_v201_local_auth.py` | V201 local auth list |
| `test_v201_display_messages.py` | Set/Get/Clear display messages |
| `test_v201_firmware.py` | V201 firmware lifecycle, signed updates |
| `test_v201_diagnostics.py` | GetLog (diagnostics + security logs) |
| `test_v201_events.py` | NotifyEvent generation |
| `test_v201_tariff_cost.py` | CostUpdated, total_cost in TransactionEvent |
| `test_v201_data_transfer.py` | V201 data transfer |
| `test_v201_transaction_status.py` | GetTransactionStatus |

### 7.2 Integration Tests

- Full transaction lifecycle: BootNotification -> Authorize -> Started -> Updated(periodic) -> Updated(state change) -> Ended
- Smart charging: SetChargingProfile -> composite limit -> rate change event
- Offline resilience: Disconnect during transaction -> queue -> reconnect -> replay
- Multi-EVSE: Parallel transactions with independent profiles

---

## File Map Summary

### New Files

```
src/chargeghost_evse/ocpp_adapter/
    charging_profile_manager_v201.py    (~800 lines)
    local_auth_list_v201.py             (~300 lines)
    firmware_manager_v201.py            (~400 lines)
    auth_cache_v201.py                  (~80 lines)
    device_model/
        __init__.py
        device_model.py                 (~500 lines)
        component.py                    (~200 lines)
        variable.py                     (~250 lines)
        report_builder.py               (~300 lines)
        monitoring/
            __init__.py
            monitor.py                  (~150 lines)
            monitor_manager.py          (~400 lines)
```

### Modified Files

| File | Changes |
|---|---|
| `v201_adapter.py` | +29 inbound handlers, +12 outbound methods (~2500 additional lines) |
| `transaction_manager_v201.py` | UUID generation, offline persistence |
| `bridge/bridge.py` | V201 dispatch paths for all new messages, meter routing |
| `engine/session.py` | `transaction_id` typed as `int or str` for UUID support |
| `engine/reservation.py` | New fields: `connector_type`, `group_id_tag` |
| `engine/connector.py` | Optional V201 charging state mapping |
| `ui/bridge.py` | New Qt signals for display messages, cost, events |
| `ocpp_adapter/__init__.py` | Export new V201 classes |

### Estimated Effort

| Phase | New Lines | Tests | Complexity |
|---|---|---|---|
| Phase 1: Transactions + Smart Charging | ~1,200 | ~600 | High |
| Phase 2: Device Model + Variables | ~1,800 | ~500 | High |
| Phase 3: Reservations, Auth, Display, Data | ~800 | ~400 | Medium |
| Phase 4: Firmware, Diagnostics, Events | ~600 | ~300 | Medium |
| Phase 5: Tariff/Cost + Security | ~300 | ~150 | Low |
| Phase 6: Bridge + UI | ~500 | ~200 | Medium |
| Phase 7: Testing | — | ~800 | — |
| **Total** | **~5,200** | **~2,950** | |

---

## Execution Order

Phases 1-2 are the foundation (everything else depends on them). Within each phase, the adapter handlers should be implemented first, then bridge wiring, then tests. The recommended order:

1. **Phase 1.1** — TransactionEvent enhancements (touches core path)
2. **Phase 1.2** — Smart Charging V201 (can be parallel with 1.3)
3. **Phase 1.3** — Enhanced StatusNotification
4. **Phase 2.1** — Device model package
5. **Phase 2.2** — GetVariables/SetVariables
6. **Phase 2.3** — Variable monitoring
7. **Phase 3** — Reservations, auth, display, data transfer (can be parallelized by subagent)
8. **Phase 4** — Firmware, diagnostics, events
9. **Phase 5** — Tariff/cost + security events
10. **Phase 6** — Bridge integration + UI
11. **Phase 7** — Full test suite validation
