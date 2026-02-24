# Charge Profiles Design — 2026-02-25

## Overview

Implement the full OCPP 1.6J Smart Charging profile feature set for ChargeGhost EVSE. Profiles must enforce actual simulated charging limits on top of the connector's base configuration, in addition to sending spec-compliant OCPP responses.

---

## 1. Data Model

### ChargingProfile (dataclass)

Mirrors the OCPP 1.6J spec:

```
ChargingProfile:
  chargingProfileId: int
  stackLevel: int
  chargingProfilePurpose: ChargePointMaxProfile | TxDefaultProfile | TxProfile
  chargingProfileKind: Absolute | Recurring | Relative
  recurrencyKind: Daily | Weekly | None
  validFrom: datetime | None
  validTo: datetime | None
  transactionId: int | None
  chargingSchedule:
    duration: int | None          # seconds; None = no expiry
    startSchedule: datetime | None
    chargingRateUnit: A | W
    minChargingRate: float | None
    chargingSchedulePeriod: list of (startPeriod: int, limit: float, numberPhases: int | None)
```

### Storage

`ChargingProfileManager` stores profiles in a `dict[int, ChargingProfile]` keyed by `chargingProfileId`.

Lookup helpers:
- `get_profiles_for_purpose(purpose, connector_id)` — returns valid profiles sorted by stackLevel descending
- `get_transaction_profiles(transaction_id)` — profiles bound to a specific transaction

### Constraints enforced on SetChargingProfile

| Constraint | Config key | Reject if |
|---|---|---|
| Total profiles | `MaxChargingProfilesInstalled` (20) | Exceeded |
| Stack level | `ChargeProfileMaxStackLevel` (5) | Exceeded |
| Schedule periods | `ChargingScheduleMaxPeriods` (10) | Exceeded |
| Rate unit | `ChargingScheduleAllowedChargingRateUnit` | Unknown unit |
| TxProfile | — | No `transactionId` present |

---

## 2. Composite Schedule Algorithm

`get_composite_limit(connector_id, transaction_id, now, connector_voltage) -> float | None`

Returns effective limit in **Amps**, or `None` if no profiles are active (use connector's full configured current).

### Steps

**1. Filter valid profiles** at time `now` for each purpose:
- `validFrom <= now <= validTo` (if set)
- `TxProfile`: `transactionId` must match active transaction
- `ChargePointMaxProfile` / `TxDefaultProfile`: `connectorId == 0` (all) or exact match

**2. Pick highest stack level** within each purpose.

**3. Resolve active schedule period** for the winning profile:
- **Relative**: offset from transaction start time
- **Absolute**: `startSchedule` is t=0 anchor
- **Recurring Daily**: `(now - startSchedule) % 86400` seconds into cycle
- **Recurring Weekly**: `(now - startSchedule) % 604800` seconds into cycle
- Walk `chargingSchedulePeriod` list to find period whose `startPeriod <= elapsed`
- If `duration` is set and elapsed > duration → treat as inactive

**4. Combine across purposes** (most restrictive wins):
- Take `min(ChargePointMaxProfile limit, TxProfile OR TxDefaultProfile limit)`
- If no `TxProfile` active but `TxDefaultProfile` exists, use `TxDefaultProfile`

**5. Unit normalisation**: if `chargingRateUnit == W`, divide by `connector_voltage × numberPhases` to get Amps.

### Used by GetCompositeSchedule

Same algorithm run across a requested `duration` window, building a merged period list of how the combined limit changes over time.

---

## 3. Architecture & Wiring

### New file: `src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py`

- `ChargingProfileManager` class
- `threading.RLock` protecting all reads and writes
- Public API: `set_profile()`, `clear_profile()`, `get_composite_limit()`, `get_composite_schedule()`

### Adapter changes (`ocpp_adapter/adapter.py`)

- Instantiates `ChargingProfileManager` in `__init__`
- Adds handlers: `@on("SetChargingProfile")`, `@on("ClearChargingProfile")`, `@on("GetCompositeSchedule")`
- Sources `transaction_id` from `self.active_transactions` for composite queries

### Engine changes (`engine/engine.py`)

- Accepts `get_limit: Callable[[int, Optional[int]], Optional[float]] | None` (injectable, defaults to `None`)
- In `simulate()`, before calling `EnergyMeter.update()`, calls `get_limit(connector_id, transaction_id)` and clamps `connector.current` to the result

### Bridge changes (`bridge/bridge.py`)

- After `AsyncRunner` starts, injects a limit-getter lambda into the engine:
  ```python
  engine.get_limit = lambda conn_id, tx_id: (
      runner.adapter.charging_profile_manager.get_composite_limit(
          conn_id, tx_id, datetime.now(timezone.utc), connector_voltage
      )
      if runner.adapter else None
  )
  ```

### UI changes

- New read-only panel showing active profiles per connector: purpose, stack level, current limit in effect
- Sourced by polling `charging_profile_manager` on a timer or via an event emitted on profile change

---

## 4. Error Handling & OCPP Responses

| Scenario | Response |
|---|---|
| Profile exceeds `MaxChargingProfilesInstalled` | `SetChargingProfile` → `Rejected` |
| `stackLevel` > `ChargeProfileMaxStackLevel` | `Rejected` |
| Schedule periods > `ChargingScheduleMaxPeriods` | `Rejected` |
| Unknown `chargingRateUnit` | `Rejected` |
| `TxProfile` with no `transactionId` | `Rejected` |
| `ClearChargingProfile` matches nothing | `Unknown` |
| `ClearChargingProfile` matches profiles | `Accepted` |
| `GetCompositeSchedule` connector not found | `status: Rejected` |
| `GetCompositeSchedule` no active profiles | `status: Accepted`, empty schedule |

---

## 5. Testing

### Unit tests: `tests/test_charging_profile_manager.py`

- Profile storage and retrieval
- Stack level resolution (highest wins within purpose)
- Constraint validation (all rejection cases)
- Composite limit calculation for each `chargingProfileKind`
- Multi-purpose precedence and min-of-limits logic
- Period walk with `duration` expiry
- Unit conversion (W → A)
- Recurring schedule cycle wrapping (Daily, Weekly)

### Integration tests: `tests/test_smart_charging.py`

- `SetChargingProfile` → handler → profile stored → composite limit changes
- `ClearChargingProfile` → correct profiles removed, limit reverts
- `GetCompositeSchedule` → correct period list for a given time window
- Engine enforcement: session at 32A, profile caps to 16A → `EnergyMeter` simulates at 16A
- Stack level override: higher-level profile replaces lower-level limit
- Profile expiry: after `duration` elapses, limit reverts to connector default
