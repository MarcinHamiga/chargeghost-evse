# OCPP 2.0.1 Dual-Stack Support Implementation Plan

**Goal:** Add full OCPP 2.0.1 support to ChargeGhost EVSE while keeping existing OCPP 1.6J support intact and selectable at runtime via configuration.

**Architecture:** Keep the existing four-layer split. The `Engine` remains protocol-agnostic domain logic. The `Bridge` becomes version-aware only at the adapter boundary. Version-specific OCPP behavior lives in separate adapter implementations with a shared base contract.

**Tech Stack:** Python 3.14, PySide6, `ocpp` v2.1.0, `websockets`, `asyncio`, `dataclasses`, `pytest`, `ruff`, `mypy`

**Important constraint:** This is not a migration plan. OCPP 1.6J remains supported and unchanged for existing users. OCPP 2.0.1 is added alongside it as a second protocol mode.

---

## Scope and Success Criteria

- Add protocol selection to configuration and UI.
- Keep the current OCPP 1.6J path stable.
- Add a new OCPP 2.0.1 adapter using the installed `ocpp.v201` support.
- Implement full OCPP 2.0.1 feature coverage in grouped milestones, not only a minimal core profile.
- Preserve the current engine simulation model unless a protocol concept cannot be represented without a new domain abstraction.

Success means:

- A user can choose `OCPP 1.6J` or `OCPP 2.0.1` in settings.
- The bridge connects with the correct WebSocket subprotocol: `ocpp1.6` or `ocpp2.0.1`.
- Existing OCPP 1.6J tests still pass.
- New OCPP 2.0.1 tests cover the full supported message surface for the simulator.
- The simulator can interoperate with both 1.6J and 2.0.1 CSMS implementations without code changes between runs.

## Target OCPP 2.0.1 Operation Surface

The implementation target is the full OCPP 2.0.1 action set exposed by the installed `ocpp.v201`
library, delivered in grouped milestones rather than one large change.

### Core and transaction flow

- `Authorize`
- `BootNotification`
- `Heartbeat`
- `MeterValues`
- `StatusNotification`
- `TransactionEvent`
- `GetTransactionStatus`
- `TriggerMessage`
- `DataTransfer`
- `SecurityEventNotification`

### Remote control and station control

- `RequestStartTransaction`
- `RequestStopTransaction`
- `ChangeAvailability`
- `UnlockConnector`
- `Reset`

### Smart charging

- `SetChargingProfile`
- `ClearChargingProfile`
- `GetChargingProfiles`
- `ReportChargingProfiles`
- `GetCompositeSchedule`
- `NotifyChargingLimit`
- `ClearedChargingLimit`
- `NotifyEVChargingNeeds`
- `NotifyEVChargingSchedule`

### Device model and reporting

- `GetVariables`
- `SetVariables`
- `GetBaseReport`
- `GetReport`
- `NotifyReport`

### Monitoring

- `SetVariableMonitoring`
- `ClearVariableMonitoring`
- `GetMonitoringReport`
- `NotifyMonitoringReport`
- `SetMonitoringBase`
- `SetMonitoringLevel`

### Reservations and local authorization

- `ReserveNow`
- `CancelReservation`
- `ReservationStatusUpdate`
- `SendLocalList`
- `GetLocalListVersion`
- `ClearCache`

### Firmware and logs

- `UpdateFirmware`
- `FirmwareStatusNotification`
- `GetLog`
- `LogStatusNotification`
- `PublishFirmware`
- `UnpublishFirmware`
- `PublishFirmwareStatusNotification`

### Certificates and security credentials

- `InstallCertificate`
- `DeleteCertificate`
- `GetInstalledCertificateIds`
- `SignCertificate`
- `CertificateSigned`
- `GetCertificateStatus`
- `Get15118EVCertificate`

### Display and customer information

- `SetDisplayMessage`
- `GetDisplayMessages`
- `ClearDisplayMessage`
- `NotifyDisplayMessages`
- `CustomerInformation`
- `NotifyCustomerInformation`
- `CostUpdated`

### Network profile

- `SetNetworkProfile`

---

## Architectural Decisions

### 1. Version selection is explicit

Add `ocpp_version` to `SimulationConfig` and surface it in the UI settings.

- Allowed values: `"1.6"`, `"2.0.1"`
- Default remains `"1.6"` to preserve current behavior.
- No auto-negotiation in the first pass.

### 2. Shared base adapter plus versioned subclasses

Introduce a common adapter contract:

- `BaseAdapter`: shared events, common callbacks, logging helpers, registration state, offline queue hooks, shared utility methods.
- `V16Adapter`: existing behavior moved from the current `adapter.py` with minimal semantic change.
- `V201Adapter`: new OCPP 2.0.1 implementation.

### 3. Engine stays protocol-neutral

The engine should not become an OCPP 2.0.1 protocol handler.

- Keep session, connector, reservation, metering, and availability in the engine.
- Add only the extra domain abstractions needed to represent 2.0.1 concepts cleanly.
- Translate protocol-specific payloads in adapters and bridge helpers.

### 4. One EVSE per connector in OCPP 2.0.1 mode

The current simulator already models connectors as the main charging units. For OCPP 2.0.1:

- Map `evseId == connector.id`
- Treat each simulated connector as one EVSE with one connector
- Keep connector `0` / station-wide status concepts in adapter logic where needed

This avoids unnecessary domain churn and fits the current simulator architecture.

---

## Target File Layout

Create or refactor toward this structure:

- `src/chargeghost_evse/ocpp_adapter/base_adapter.py`
- `src/chargeghost_evse/ocpp_adapter/v16_adapter.py`
- `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- `src/chargeghost_evse/ocpp_adapter/transaction_manager_v201.py`
- `src/chargeghost_evse/ocpp_adapter/component_registry_v201.py`
- `src/chargeghost_evse/ocpp_adapter/variable_monitor_v201.py`
- `src/chargeghost_evse/ocpp_adapter/certificate_manager_v201.py`
- `src/chargeghost_evse/ocpp_adapter/display_manager_v201.py`
- `src/chargeghost_evse/ocpp_adapter/customer_info_manager_v201.py`
- `src/chargeghost_evse/ocpp_adapter/event_manager_v201.py`
- `src/chargeghost_evse/ocpp_adapter/network_profile_manager_v201.py`
- `src/chargeghost_evse/ocpp_adapter/firmware_manager_v201.py`

The current `src/chargeghost_evse/ocpp_adapter/adapter.py` can either become a thin compatibility import or be renamed once all imports are updated.

---

## Phase 1: Version Selection and Adapter Factory — DONE

### Task 1: Add protocol selection to configuration — DONE

**Files:**
- Modify: `src/chargeghost_evse/util/config.py`
- Test: `tests/test_config.py`
- Test: `tests/test_app_settings.py`

Add:

- `ocpp_version: Literal["1.6", "2.0.1"] = "1.6"`
- load/save support in `SimulationConfig`
- backward-compatible defaulting when the field is absent

Done when:

- Saved configs persist the selected protocol version.
- Older configs load without changes.

### Task 2: Add protocol selection to UI — DONE

**Files:**
- Modify: `src/chargeghost_evse/ui/widgets/settings_panel.py`
- Test: `tests/test_ui_widgets.py`
- Test: `tests/test_app_settings.py`

Add a settings control for protocol version.

Done when:

- Users can switch between `OCPP 1.6J` and `OCPP 2.0.1`.
- Existing settings behavior remains intact.

### Task 3: Make the bridge version-aware at adapter creation time — DONE

**Files:**
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Test: `tests/test_bridge_inject.py`

Refactor `AsyncRunner` so it:

- chooses subprotocol `ocpp1.6` or `ocpp2.0.1`
- creates the correct adapter via a factory method
- keeps the rest of the threading/reconnect behavior the same

Done when:

- A 1.6 session still connects exactly as before.
- A 2.0.1 session connects with `subprotocols=["ocpp2.0.1"]`.

---

## Phase 2: Shared Adapter Abstractions — DONE

### Task 4: Extract shared adapter behavior into `BaseAdapter` — DONE

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/base_adapter.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/__init__.py`

Move shared behavior out of the current 1.6 adapter:

- common events
- logger plumbing
- connector callback injection points
- registration bookkeeping
- helper methods for timestamps, message logging, queue replay hooks, and transaction lookup

Do not try to force identical method signatures where the protocol shapes are fundamentally different.

Done when:

- `V16Adapter` can inherit from `BaseAdapter` without changing user-visible behavior.
- The bridge talks to a stable shared adapter contract.

### Task 5: Split the current adapter into `V16Adapter` — DONE

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/v16_adapter.py`
- Modify: imports that currently point at `adapter.py`
- Test: existing OCPP 1.6 tests

This is a refactor-only step.

Done when:

- Existing tests still pass against the refactored 1.6 adapter.
- No 2.0.1 behavior is introduced yet.

---

## Phase 3: OCPP 2.0.1 Core Transport and Session Flow — NEXT UP

### Task 6: Add the initial `V201Adapter` — TODO

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Test: `tests/test_v201_adapter.py`

Set up the new adapter using `ocpp.v201`:

- subclass `ocpp.v201.ChargePoint`
- wire the same logging/event hooks as the 1.6 adapter
- implement `send_boot_notification()`
- implement `send_heartbeat()`
- implement `send_status_notification()`
- implement `send_authorize()`

Done when:

- The simulator can register to a 2.0.1 CSMS and emit the basic station state.

### Task 7: Replace 1.6 transaction semantics with 2.0.1 `TransactionEvent` — TODO

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/transaction_manager_v201.py`
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Test: `tests/test_v201_transactions.py`

OCPP 2.0.1 does not use `StartTransaction` and `StopTransaction`.

Implement:

- `TransactionEvent(Started)` when a session begins
- `TransactionEvent(Updated)` for meter updates and state changes
- `TransactionEvent(Ended)` when a session stops

Bridge responsibilities:

- map engine session lifecycle to 2.0.1 event types
- include meter values in transaction events where appropriate
- preserve the offline queue behavior for 2.0.1 transaction events

Done when:

- A full charge session in 2.0.1 mode produces a valid event stream instead of 1.6-style transaction messages.

### Task 8: Implement core inbound controls — TODO

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Test: `tests/test_v201_remote_controls.py`

Implement inbound CSMS operations:

- `RequestStartTransaction`
- `RequestStopTransaction`
- `TriggerMessage`
- `ChangeAvailability`
- `UnlockConnector`
- `Reset`

Done when:

- The existing engine command queue can be driven from OCPP 2.0.1 control actions.

---

## Phase 4: Device Model and Configuration Variables — TODO

### Task 9: Add a 2.0.1 component-variable registry — TODO

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/component_registry_v201.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Test: `tests/test_v201_variables.py`

OCPP 2.0.1 replaces 1.6 configuration keys with a component/variable model.

Implement a registry that can expose:

- station-wide controller variables
- per-EVSE variables
- read-only runtime values
- writable simulator settings where safe

Support:

- `GetVariables`
- `SetVariables`
- `GetBaseReport`
- `GetReport`
- `NotifyReport`

Done when:

- 2.0.1 variable and report requests can query the simulator state without reusing the 1.6 key model directly.

### Task 10: Add variable monitoring support — TODO

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/variable_monitor_v201.py`
- Test: `tests/test_v201_monitoring.py`

Implement:

- `SetVariableMonitoring`
- `ClearVariableMonitoring`
- `GetMonitoringReport`
- `NotifyMonitoringReport`
- `SetMonitoringBase`
- `SetMonitoringLevel`

Done when:

- Monitoring rules can be installed, queried, and reported.

---

## Phase 5: Smart Charging in OCPP 2.0.1 — TODO

### Task 11: Add OCPP 2.0.1 charging profile support — TODO

**Files:**
- Modify or extend: `src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py`
- Or create: `src/chargeghost_evse/ocpp_adapter/charging_profile_manager_v201.py`
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Test: `tests/test_v201_charging_profiles.py`

Implement the 2.0.1 smart charging flow:

- `SetChargingProfile`
- `ClearChargingProfile`
- `GetChargingProfiles`
- `ReportChargingProfiles`
- `GetCompositeSchedule`
- `NotifyChargingLimit`
- `ClearedChargingLimit`

Design note:

- Reuse the existing charging limit calculation logic where possible.
- Keep a separate payload translation layer for 2.0.1 structures.

Done when:

- The engine can keep using an injected current-limit callback while 2.0.1-specific profile operations work end to end.

### Task 12: Support EV charging needs and schedule notifications — TODO

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Test: `tests/test_v201_ev_charging_needs.py`

Implement:

- `NotifyEVChargingNeeds`
- `NotifyEVChargingSchedule`

If full EV-side simulation is not yet present, send deterministic simulator-grade payloads that are clearly documented.

Done when:

- These messages exist and integrate cleanly with the smart-charging path.

---

## Phase 6: Authorization, Reservation, and Local Auth — TODO

### Task 13: Extend authorization to 2.0.1 token models — TODO

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Reuse or extend: `src/chargeghost_evse/ocpp_adapter/auth_cache.py`
- Test: `tests/test_v201_authorize.py`

Support:

- `Authorize`
- 2.0.1 id token formats
- local authorization behavior compatible with the simulator model

Done when:

- 2.0.1 authorization requests and responses work without regressing 1.6 local auth behavior.

### Task 14: Add 2.0.1 reservation support — TODO

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Test: `tests/test_v201_reservations.py`

Implement:

- `ReserveNow`
- `CancelReservation`
- `ReservationStatusUpdate`

Reuse the existing engine reservation state and map it into the 2.0.1 EVSE-based message model.

Done when:

- Reservations function in both protocol modes using the same engine behavior.

### Task 15: Add local list support in 2.0.1 mode

**Files:**
- Modify or extend: `src/chargeghost_evse/ocpp_adapter/local_auth_list.py`
- Test: `tests/test_v201_local_auth.py`

Implement:

- `SendLocalList`
- `GetLocalListVersion`

Done when:

- Local authorization list management works in 2.0.1 mode with deterministic persistence semantics.

---

## Phase 7: Firmware, Logs, Security, and Certificates

### Task 16: Extend firmware and log management

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/firmware_manager_v201.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Test: `tests/test_v201_firmware.py`

Implement:

- `UpdateFirmware`
- `FirmwareStatusNotification`
- `GetLog`
- `LogStatusNotification`
- `PublishFirmware`
- `UnpublishFirmware`
- `PublishFirmwareStatusNotification`

Done when:

- Existing simulator firmware behavior is preserved in 1.6 and expanded appropriately in 2.0.1.

### Task 17: Add certificate and security flows

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/certificate_manager_v201.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Test: `tests/test_v201_certificates.py`

Implement:

- `InstallCertificate`
- `DeleteCertificate`
- `GetInstalledCertificateIds`
- `SignCertificate`
- `CertificateSigned`
- `GetCertificateStatus`
- `Get15118EVCertificate`
- `SecurityEventNotification`

Simulator note:

- The first pass may use filesystem-backed simulated certificate storage, but the API surface should match OCPP 2.0.1.

Done when:

- The simulator can participate in 2.0.1 certificate-management flows without affecting 1.6 authentication.

---

## Phase 8: Events, Display, Customer Info, and Network Profile

### Task 18: Add event and reporting messages

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/event_manager_v201.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Test: `tests/test_v201_events.py`

Implement:

- `NotifyEvent`
- `GetTransactionStatus`
- `MeterValues` where used independently from `TransactionEvent`
- `StatusNotification` follow-up flows specific to 2.0.1

Done when:

- The simulator can report non-transaction events and status updates in 2.0.1 mode.

### Task 19: Add display-message support

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/display_manager_v201.py`
- Modify: `src/chargeghost_evse/ui/`
- Test: `tests/test_v201_display_messages.py`

Implement:

- `SetDisplayMessage`
- `GetDisplayMessages`
- `ClearDisplayMessage`
- `NotifyDisplayMessages`

Done when:

- The simulator can receive and surface CSMS display messages.

### Task 20: Add customer-information and cost flows

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/customer_info_manager_v201.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Test: `tests/test_v201_customer_info.py`

Implement:

- `CustomerInformation`
- `NotifyCustomerInformation`
- `CostUpdated`

Done when:

- These 2.0.1-specific informational flows are available in simulator mode.

### Task 21: Add network-profile support

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/network_profile_manager_v201.py`
- Test: `tests/test_v201_network_profile.py`

Implement:

- `SetNetworkProfile`

Done when:

- Network profile requests can be accepted, stored, and surfaced in a simulator-appropriate way.

---

## Phase 9: Data Transfer and Compatibility Helpers

### Task 22: Support `DataTransfer` in 2.0.1 mode

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/data_transfer.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/v201_adapter.py`
- Test: `tests/test_v201_data_transfer.py`

Reuse the existing data-transfer registry pattern where possible.

Done when:

- Vendor-specific simulator extensions remain available in both protocol modes.

### Task 23: Keep message queue and bridge plumbing protocol-neutral

**Files:**
- Modify: `src/chargeghost_evse/bridge/message_queue.py`
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Test: `tests/test_message_queue.py`

Ensure the offline queue can store and replay both:

- 1.6 transaction messages
- 2.0.1 transaction events and other outbound calls

Done when:

- Reconnect behavior remains reliable in both modes.

---

## Phase 10: Validation and Documentation

### Task 24: Add OCPP 2.0.1 test coverage by feature group

Create targeted tests for:

- adapter boot and registration
- remote controls
- transaction events
- variables and reports
- monitoring
- smart charging
- authorization and reservations
- local auth lists
- firmware and certificates
- display, customer info, and events

### Task 25: Run the validation suite

Run:

```bash
poetry run pytest
poetry run ruff check src/ tests/
poetry run mypy src/
```

If the repository validation skill is used later, run the full validation flow before claiming completion.

### Task 26: Document supported protocol surfaces clearly

Update user-facing docs after implementation lands:

- `README.md`
- protocol support matrix
- settings documentation
- any release notes for the new mode

Do not mark OCPP 2.0.1 as complete until interoperability has been verified against a real CSMS.

---

## Recommended Delivery Order

1. Config/UI version selection
2. Adapter factory in bridge
3. `BaseAdapter` extraction
4. `V16Adapter` refactor without behavior changes
5. `V201Adapter` boot, heartbeat, status, authorize
6. `TransactionEvent` implementation
7. Remote control actions
8. Variable/report model
9. Smart charging
10. Authorization, reservations, local list
11. Firmware, log, security, certificates
12. Display, customer info, network profile, events
13. Full regression and documentation

---

## Risks and Design Watchouts

- Do not regress OCPP 1.6J behavior while extracting shared code.
- Do not leak 2.0.1-specific payload structures into the engine layer.
- Be careful with transaction semantics: `TransactionEvent` is not a thin rename of `StartTransaction` and `StopTransaction`.
- Keep one clear mapping between simulator connectors and 2.0.1 EVSE identifiers.
- Do not overload the 1.6 configuration-key manager for 2.0.1 component variables.
- Keep offline replay deterministic for both protocols.
- Treat certificate and ISO 15118 support as simulator-grade unless hardware-backed behavior is explicitly added later.

---

## Definition of Done

This plan is complete only when all of the following are true:

- OCPP 1.6J remains selectable and green.
- OCPP 2.0.1 is selectable and functionally implemented across the planned message groups.
- Core bridge, queue, and engine behaviors work in both modes.
- Automated tests cover both protocol paths.
- A real OCPP 2.0.1 CSMS interoperability pass has been completed and documented.
