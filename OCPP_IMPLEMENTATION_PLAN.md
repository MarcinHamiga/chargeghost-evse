# OCPP 1.6J Implementation Plan

This document is the single source of truth for remaining OCPP 1.6J implementation and compliance work in ChargeGhost EVSE.

It replaces the previous status and compliance markdown files and is based on a source-level audit of the current codebase against implemented behavior, OCPP 1.6 errata, and OCPP 1.6-J errata.

## Goal

- Close the remaining behavioral and interoperability gaps for the currently supported OCPP 1.6J feature profiles.
- Prioritize protocol correctness before adding new optional features.
- Keep simulator-oriented behavior where appropriate, but avoid violating required protocol semantics.

## Current Position

- Broad feature coverage already exists for `Core`, `FirmwareManagement`, `LocalAuthListManagement`, `Reservation`, `RemoteTrigger`, and `SmartCharging`.
- Priority 1 items 1–6 are complete.
- Priority 2 items 7–10 are complete.
- Priority 3 items 11–13 are complete.
- All OCPP 1.6J implementation plan items are now complete.

## Priority 1: Required Protocol Fixes

### 1. Initial status notifications after successful boot ✅

**Status: Done** (committed `87a1dc7`)

- After `BootNotification.conf(Accepted)`, `bridge.py` now sends `StatusNotification` for `connectorId = 0` first, then one per configured connector.
- `_get_status_notification_status()` derives a charge-point-wide status using priority order (Faulted > Unavailable > SuspendedEVSE > ... > Available).

**Done when:** Accepted boot always results in one `connectorId = 0` status plus one status per configured connector. ✅

### 2. Support `RemoteStartTransaction.chargingProfile` ✅

**Status: Done** (committed `87a1dc7`)

- `adapter.py` parses and validates `chargingProfile` as a `TxProfile`; rejects non-TxProfile purposes or malformed payloads.
- `engine.py` / `session.py` carry the deferred profile through pending-connector auto-selection into the started session.
- `bridge.py` installs the profile as a `TxProfile` once `StartTransaction.conf` provides a transaction ID.
- `charging_profile_manager.py` replaces prior TxProfile at same connector/transaction/stack level.

**Done when:** A remote start with `chargingProfile` changes the active charging limit for the started transaction. ✅

### 3. Smart Charging error semantics ✅

**Status: Done** (committed `6b6afcc`)

- Invalid Smart Charging inputs now raise `PropertyConstraintViolationError` as RPC `CallError` instead of returning `Rejected`:
  - `SetChargingProfile`: invalid connectorId, missing TxProfile transactionId, malformed payload, `too_many_periods`, `stack_level_exceeded`, `tx_profile_missing_transaction_id`
  - `ClearChargingProfile`: invalid id/stackLevel, unknown purpose
  - `GetCompositeSchedule`: unknown connectorId, invalid `chargingRateUnit`
- Schema-valid but semantically invalid inputs (e.g., `max_profiles_exceeded`) still return `Rejected` as before.

**Done when:** Invalid Smart Charging inputs produce the expected RPC-level errors and valid inputs keep the existing accepted behavior. ✅

### 4. Honor `UpdateFirmware.retrieveDate` ✅

**Status: Done** (committed `6b6afcc`)

- `firmware_manager.py` added `wait_until_retrieve_date()` and `get_retrieve_delay_seconds()`.
- `adapter.py` calls `wait_until_retrieve_date()` before starting download, so future scheduled times sleep until the configured wall-clock moment.
- Past/invalid timestamps fall back to immediate start (preserving existing behavior).

**Done when:** Firmware download/install does not begin before the configured retrieval time. ✅

### 5. Local authorization list version handling ✅

**Status: Done** (committed `070d769`)

- `local_auth_list.py` rejects `listVersion <= 0` immediately.
- Differential updates require exact next version (`current + 1`); mismatches return `UpdateStatus.version_mismatch` without mutating stored list.
- `adapter.py` preserves `VersionMismatch` from the manager and returns it as the OCPP status.

**Done when:** Invalid or out-of-sequence local list updates are rejected deterministically. ✅

### 6. Failed `StartTransaction` fallback handling ✅

**Status: Done** (committed `7f13aca`)

- `bridge.py` added `_get_ocpp_transaction_id()` — returns `-1` when no positive transaction ID has been assigned.
- `get_meter_snapshot`, meter values loop, and `StopTransaction` queue all use `-1` for follow-up messages before `StartTransaction.conf` succeeds.
- Previously the loop gated on `transaction_id > 0`, silently skipping metering in the failure window.

**Done when:** Transaction retry/failure behavior is deterministic and documented. ✅

## Priority 2: Metering and Persistence Compliance

### 7. Clock-aligned `MeterValues` ✅

**Status: Done** (committed `7f13aca`)

- `_meter_values_loop()` now tracks both `last_sampled_at` and `next_aligned_at` across iterations.
- `_collect_meter_value_contexts()` returns `Sample.Periodic` and/or `Sample.Clock` based on wall-clock boundaries.
- `_get_meter_values_wait_interval()` sleeps until the next actual event (not just the sample interval), so aligned boundaries don't cause unnecessary polling.
- Helper `_send_meter_value(context)` sends `Sample.Clock` or `Sample.Periodic` with correct `context` field.

**Done when:** `ClockAlignedDataInterval > 0` produces aligned `MeterValues` at the expected boundaries. ✅

### 8. Metering configuration validation and `StopTransaction` rules ✅

**Status: Done** (committed `92e56bb`)

- `config_keys.py` validates measurand lists in `MeterValuesSampledData`, `MeterValuesAlignedData`, `StopTxnSampledData`, `StopTxnAlignedData` against the OCPP 1.6J `Measurand` enum.
- `StopTxnSampledData` and `StopTxnAlignedData` configuration keys added.
- `get_measurand_list()` helper parses comma-separated values.
- `send_stop_transaction()` only sends `transactionData` if `Energy.Active.Import.Register` is in the measurand list; trims to `[first, ...last N-1]` to preserve start/stop boundaries.

**Done when:** Metering behavior is driven by OCPP configuration, not only by local defaults. ✅

### 9. Charging profile persistence across restart ✅

**Status: Done** (committed `7f07a9f`)

- `ChargingProfileData.to_ocpp_dict()` serializes profiles to OCPP dict format.
- `ChargingProfileManager.__init__` accepts `persist_path`; defaults to `~/.chargeghost/charging_profiles.json`.
- `_persist()` saves all profiles after `set_profile` and `clear_profiles`; `_restore()` loads them on construction.
- Corrupted files and partial entries are skipped gracefully.
- Adapter passes `persist_path` on construction so production code gets persistence automatically.

**Done when:** Supported charging profiles survive application restart and are restored consistently. ✅

### 10. Reservation and transaction linkage ✅

**Status: Done** (committed with this change)

- `engine/session.py`: Added `reservation_id: Optional[int]` attribute to `Session`.
- `engine/engine.py`: `start_session()` now passes `reservation_id` from the active reservation to `Session`.
- `bridge/bridge.py`: `on_engine_session_started()` includes `session.reservation_id` in `start_kwargs`.
- `ocpp_adapter/adapter.py`: `send_start_transaction()` now accepts `reservation_id` and passes it to the OCPP `StartTransaction` call.

**Done when:** Reserved sessions are represented correctly in outgoing protocol messages. ✅

## Priority 3: Interoperability and Cleanup

### 11. Standard configuration key interoperability ✅

**Status: Done**

- `config_keys.py`: Added `MessageTimeout` configuration key (optional, default 30s).
- `adapter.py`: `MessageTimeout` now updates `response_timeout` alongside `ConnectionTimeout`.
- `AuthorizationKey`: Not exposed as OCPP configuration key; the existing `SimulationConfig.ocpp_password` mechanism provides equivalent WebSocket authentication functionality.

**Done when:** OCPP configuration keys match expected 1.6J interoperability behavior for the supported security model. ✅

### 12. Schema and enum verification against 1.6-J errata ✅

**Status: Done**

- Schema validation is handled by the `ocpp` library (v2.1.0) using JSON schema validators.
- The `ocpp` library handles decimal parsing for `GetCompositeSchedule`, `SetChargingProfile`, and `RemoteStartTransaction` to avoid float precision issues.
- Enum validation is handled by the `ocpp` library's `StrEnum` types.
- Application-level validation (e.g., measurand list validation in `config_keys.py`) is handled locally.

**Done when:** We can state clearly which 1.6-J schema errata are handled by upstream and which are handled locally. ✅

### 13. Documentation alignment ✅

**Status: Done**

- `README.md` updated to remove percentage-complete claims and outdated feature status.
- `README.md` now references `OCPP_IMPLEMENTATION_PLAN.md` as the canonical roadmap.
- Updated OCPP 1.6 Support section with accurate feature profile status.

**Done when:** The repository has one clear, current roadmap for OCPP compliance work. ✅

## Test and Validation Plan

For each completed item:

- Add or update focused unit tests under `tests/`.
- Add integration-style tests for protocol message sequences where behavior spans adapter, bridge, and engine.
- Run:

```bash
poetry run pytest
poetry run ruff check src/ tests/
poetry run mypy src/
```

Before claiming compliance:

- Run the repository validation flow.
- Run an external OCPP conformance tool or CSMS interoperability test pass.
- Record the tested errata cases and their outcomes in this document or a follow-up validation report.

## Definition of Done

We can describe ChargeGhost EVSE as fully implemented for its intended OCPP 1.6J scope only when:

- Priority 1 items are complete.
- Priority 2 items are complete or consciously documented as simulator-only deviations.
- Automated tests cover all corrected behaviors.
- External interoperability/conformance validation has been run and documented.
