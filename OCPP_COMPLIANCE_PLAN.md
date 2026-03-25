# OCPP 1.6J Compliance Implementation Plan

This document outlines the implementation plan to achieve full OCPP 1.6J compliance, addressing all identified gaps and errata-related issues.

---

## Overview

| Priority | Category | Issues | Estimated Effort |
|----------|----------|--------|------------------|
| P1 | Critical | 2 | 4-6 hours |
| P2 | Important | 4 | 6-8 hours |
| P3 | Minor | 3 | 2-3 hours |

**Total Estimated Effort**: 12-17 hours

---

## P1: Critical Compliance Issues

### 1. StopTransaction Missing `transactionData`

**Spec Reference**: OCPP 1.6 §4.10, Errata 4.10  
**Current State**: StopTransaction only sends `meter_stop`, `timestamp`, `transaction_id`, `reason`  
**Required**: Include `transactionData` array with recent meter values up to `StopTransactionMaxLength`

#### Implementation

**Files to Modify**:
- `src/chargeghost_evse/ocpp_adapter/adapter.py`
- `src/chargeghost_evse/bridge/bridge.py`
- `src/chargeghost_evse/engine/session.py` (new)

**Step 1**: Add meter value history tracking to Session

```python
# In src/chargeghost_evse/engine/session.py
# Add new class attribute and method

class Session:
    def __init__(self, ...):
        # ... existing init ...
        self._meter_history: list[dict] = []
        self._max_meter_history: int = 10
    
    def record_meter_value(self, value: float, timestamp: str) -> None:
        """Record a meter value for inclusion in StopTransaction."""
        self._meter_history.append({
            "timestamp": timestamp,
            "value": value,
        })
        # Trim to max history
        if len(self._meter_history) > self._max_meter_history:
            self._meter_history = self._meter_history[-self._max_meter_history:]
    
    def get_meter_history(self) -> list[dict]:
        """Return meter history for StopTransaction.transactionData."""
        return list(self._meter_history)
```

**Step 2**: Update Bridge to record meter values during session

```python
# In src/chargeghost_evse/bridge/bridge.py::_meter_values_loop
# After sending MeterValues, also record in session

if self.engine.session and self.engine.session.transaction_id > 0:
    meter_value = self.engine.energy_meter.get_meter_reading()
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Record for StopTransaction
    self.engine.session.record_meter_value(meter_value, timestamp)
    
    # ... existing send_meter_values code ...
```

**Step 3**: Update adapter's send_stop_transaction to include transactionData

```python
# In src/chargeghost_evse/ocpp_adapter/adapter.py::send_stop_transaction
# Add signature parameter and build transactionData

async def send_stop_transaction(
    self,
    meter_stop: int,
    timestamp: str,
    transaction_id: int,
    reason: Optional[str] = None,
    meter_history: Optional[list[dict]] = None,  # NEW
) -> call_result.StopTransaction:
    """Send StopTransaction to the Central System."""
    
    # Build transactionData from meter history
    transaction_data: Optional[list[dict]] = None
    max_values = self.config_manager.get_int_value("StopTransactionMaxLength", 0)
    
    if max_values > 0 and meter_history:
        # Take up to max_values most recent entries
        recent = meter_history[-max_values:] if len(meter_history) > max_values else meter_history
        transaction_data = [
            {
                "timestamp": entry["timestamp"],
                "sampledValue": [
                    {
                        "value": str(entry["value"]),
                        "context": "Sample.Periodic",
                        "measurand": "Energy.Active.Import.Register",
                        "unit": "Wh",
                        "format": "Raw",
                    }
                ],
            }
            for entry in recent
        ]
    
    request = call.StopTransaction(
        meter_stop=meter_stop,
        timestamp=timestamp,
        transaction_id=transaction_id,
        reason=reason,
        transaction_data=transaction_data,  # NEW
    )
    # ... rest of method ...
```

**Step 4**: Update Bridge to pass meter history

```python
# In src/chargeghost_evse/bridge/bridge.py::on_engine_session_stopped

meter_history = last_session.get("meter_history", [])
stop_kwargs = {
    "meter_stop": int(meter_stop),
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "transaction_id": transaction_id,
    "reason": reason,
    "meter_history": meter_history,  # NEW
}

# Also update last_stopped_session in engine.py::stop_session
self.last_stopped_session = {
    # ... existing fields ...
    "meter_history": self.session.get_meter_history() if self.session else [],
}
```

**Tests**:
- `tests/test_stop_transaction_data.py` (new)
  - Test that meter history is recorded during session
  - Test that StopTransaction includes transactionData
  - Test that transactionData respects StopTransactionMaxLength

---

### 2. Clock-Aligned MeterValues Implementation

**Spec Reference**: OCPP 1.6 §4.10  
**Current State**: Only periodic sampled MeterValues sent at `MeterValueSampleInterval`  
**Required**: Additionally send clock-aligned MeterValues at `ClockAlignedDataInterval`

#### Implementation

**Files to Modify**:
- `src/chargeghost_evse/bridge/bridge.py`

**Step 1**: Add clock-aligned meter values logic

```python
# In src/chargeghost_evse/bridge/bridge.py

def _meter_values_loop(self) -> None:
    """Periodic and clock-aligned meter value sampling."""
    last_clock_aligned: Optional[datetime] = None
    
    while not self._shutdown_event.is_set():
        sample_interval = self._get_sample_interval()
        clock_interval = self._get_clock_aligned_interval()
        
        now = datetime.now(timezone.utc)
        
        # 1. Send periodic sampled data (existing behavior)
        if (
            sample_interval > 0
            and self.engine.session
            and self.engine.session.transaction_id > 0
            and self.engine.energy_meter.is_charging
        ):
            self._send_periodic_meter_values()
        
        # 2. Send clock-aligned data if interval configured
        if (
            clock_interval > 0
            and self.engine.session
            and self.engine.session.transaction_id > 0
        ):
            last_clock_aligned = self._maybe_send_clock_aligned(
                now, clock_interval, last_clock_aligned
            )
        
        # Wait for minimum interval
        wait_interval = max(min(sample_interval, clock_interval) if clock_interval > 0 else sample_interval, 1)
        self._shutdown_event.wait(timeout=wait_interval)

def _get_sample_interval(self) -> int:
    """Get MeterValueSampleInterval from config."""
    if self.runner.adapter:
        return self.runner.adapter.config_manager.get_int_value(
            "MeterValueSampleInterval", 60
        )
    return 60

def _get_clock_aligned_interval(self) -> int:
    """Get ClockAlignedDataInterval from config."""
    if self.runner.adapter:
        return self.runner.adapter.config_manager.get_int_value(
            "ClockAlignedDataInterval", 0
        )
    return 0

def _maybe_send_clock_aligned(
    self,
    now: datetime,
    interval_seconds: int,
    last_sent: Optional[datetime],
) -> Optional[datetime]:
    """
    Send clock-aligned MeterValues if we've crossed a boundary.
    
    Clock-aligned intervals occur at:
    - 0, 900, 1800, ... for 15-minute intervals
    - 0, 300, 600, ... for 5-minute intervals
    etc.
    """
    # Calculate current position in day
    seconds_since_midnight = (
        now.hour * 3600 + now.minute * 60 + now.second
    )
    
    # Check if we're at a clock boundary
    current_interval_index = seconds_since_midnight // interval_seconds
    current_interval_start = current_interval_index * interval_seconds
    
    # Create the aligned timestamp
    aligned_time = now.replace(
        hour=current_interval_start // 3600,
        minute=(current_interval_start % 3600) // 60,
        second=0,
        microsecond=0
    )
    
    # Check if we already sent for this interval
    if last_sent is not None and last_sent >= aligned_time:
        return last_sent
    
    # Check if we're within 1 second of the aligned time (allowing for loop delay)
    seconds_since_aligned = (now - aligned_time).total_seconds()
    if seconds_since_aligned > 1.0:
        return last_sent  # Missed the window, wait for next
    
    # Send clock-aligned meter values
    adapter = self.runner.adapter
    loop = self.runner.loop
    if adapter and loop:
        future = asyncio.run_coroutine_threadsafe(
            adapter.send_meter_values(
                connector_id=self.engine.session.connector_id,
                value=self.engine.energy_meter.get_meter_reading(),
                transaction_id=self.engine.session.transaction_id,
                context="Sample.Clock",  # Different context for clock-aligned
            ),
            loop,
        )
        future.add_done_callback(self._handle_future_error)
    
    return aligned_time
```

**Step 2**: Update send_meter_values to accept context parameter

```python
# In src/chargeghost_evse/ocpp_adapter/adapter.py::send_meter_values

async def send_meter_values(
    self,
    connector_id: int,
    value: float,
    transaction_id: Optional[int] = None,
    context: str = "Sample.Periodic",  # NEW: allow "Sample.Clock"
) -> call_result.MeterValues:
    """Send MeterValues to the Central System."""
    request = call.MeterValues(
        connector_id=connector_id,
        transaction_id=transaction_id,
        meter_value=[
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sampled_value": [
                    {
                        "value": str(value),
                        "context": context,  # Use provided context
                        "measurand": "Energy.Active.Import.Register",
                        "unit": "Wh",
                        "format": "Raw",
                        "location": "Outlet",
                    }
                ],
            }
        ],
    )
    # ... rest of method ...
```

**Tests**:
- `tests/test_clock_aligned_meter_values.py` (new)
  - Test that clock-aligned values are sent at correct intervals
  - Test that periodic and clock-aligned can coexist
  - Test boundary crossing detection

---

## P2: Important Compliance Issues

### 3. GetCompositeSchedule Status Enum Fix

**Spec Reference**: OCPP 1.6 §5.22  
**Current State**: Uses raw string "Rejected" / "Accepted"  
**Required**: Use `GetCompositeScheduleStatus` enum

#### Implementation

**Files to Modify**:
- `src/chargeghost_evse/ocpp_adapter/adapter.py`

```python
# Add import at top of file
from ocpp.v16.enums import GetCompositeScheduleStatus

# In on_get_composite_schedule (line 1477)
# BEFORE:
return call_result.GetCompositeSchedule(status="Rejected")

# AFTER:
return call_result.GetCompositeSchedule(
    status=GetCompositeScheduleStatus.rejected
)

# And at line 1493:
# BEFORE:
status="Accepted",

# AFTER:
status=GetCompositeScheduleStatus.accepted,
```

**Tests**:
- `tests/test_adapter_composite_schedule.py` - add test for status enum type

---

### 4. MeterValues Format Improvements

**Spec Reference**: OCPP 1.6 §4.8, Errata 4.8  
**Current State**: Missing `format` and `location` fields  
**Required**: Include `format: "Raw"` and `location: "Outlet"` (optional but recommended)

#### Implementation

**Files to Modify**:
- `src/chargeghost_evse/ocpp_adapter/adapter.py`

```python
# In send_meter_values (around line 1774)
"sampled_value": [
    {
        "value": str(value),
        "context": context,
        "measurand": "Energy.Active.Import.Register",
        "unit": "Wh",
        "format": "Raw",        # NEW
        "location": "Outlet",   # NEW
    }
]
```

**Tests**:
- Update existing `tests/test_adapter.py` or add assertion for format/location

---

### 5. minChargingRate Enforcement

**Spec Reference**: OCPP 1.6 §6.2, Errata  
**Current State**: `minChargingRate` stored but not enforced  
**Required**: If composite limit < minChargingRate, suspend charging (return 0)

#### Implementation

**Files to Modify**:
- `src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py`

```python
# In _get_limit_from_profile (around line 610-621)
# AFTER finding the period limit:

# Find the active period limit
limit = self._find_period_limit(schedule.charging_schedule_period, elapsed)
if limit is None:
    return None

# NEW: Enforce minChargingRate
if schedule.min_charging_rate is not None:
    if limit < schedule.min_charging_rate:
        # Per OCPP spec: if limit is below minimum, suspend charging
        self.logger.debug(
            f"Limit {limit}A below minChargingRate {schedule.min_charging_rate}A, suspending",
            extra={"source": "ocpp"},
        )
        return 0.0

# Convert Watts to Amperes if necessary
if schedule.charging_rate_unit == ChargingRateUnitType.watts:
    # ... existing conversion code ...
```

**Tests**:
- `tests/test_charging_profile_manager.py` - add tests for minChargingRate enforcement
  - Test limit above minChargingRate returns normal limit
  - Test limit below minChargingRate returns 0
  - Test minChargingRate with Watts unit

---

### 6. Configuration Key Validation

**Spec Reference**: OCPP 1.6 §7  
**Current State**: No validation of configuration values  
**Required**: Validate values per spec constraints

#### Implementation

**Files to Modify**:
- `src/chargeghost_evse/ocpp_adapter/config_keys.py`

```python
# Add validation method to ConfigurationKeyManager

class ConfigurationKeyManager:
    # ... existing code ...
    
    # Define validation rules per OCPP 1.6 spec
    _VALIDATORS: dict[str, Callable[[str], tuple[bool, Optional[str]]]] = {}
    
    @staticmethod
    def _validate_non_negative_int(value: str) -> tuple[bool, Optional[str]]:
        """Validate that value is a non-negative integer."""
        try:
            ivalue = int(value)
            if ivalue >= 0:
                return True, None
            return False, "Value must be non-negative"
        except ValueError:
            return False, "Value must be an integer"
    
    @staticmethod
    def _validate_positive_or_zero_int(value: str) -> tuple[bool, Optional[str]]:
        """Validate that value is 0 or a positive integer."""
        try:
            ivalue = int(value)
            if ivalue >= 0:
                return True, None
            return False, "Value must be 0 or positive"
        except ValueError:
            return False, "Value must be an integer"
    
    @staticmethod
    def _validate_clock_aligned_interval(value: str) -> tuple[bool, Optional[str]]:
        """Validate ClockAlignedDataInterval: 0 or >= 60."""
        try:
            ivalue = int(value)
            if ivalue == 0 or ivalue >= 60:
                return True, None
            return False, "Value must be 0 or >= 60 seconds"
        except ValueError:
            return False, "Value must be an integer"
    
    @staticmethod
    def _validate_bool(value: str) -> tuple[bool, Optional[str]]:
        """Validate boolean value."""
        if value.lower() in ("true", "false"):
            return True, None
        return False, "Value must be 'true' or 'false'"
    
    def _init_validators(self) -> None:
        """Initialize validation rules."""
        self._VALIDATORS = {
            "MeterValueSampleInterval": self._validate_positive_or_zero_int,
            "ClockAlignedDataInterval": self._validate_clock_aligned_interval,
            "ConnectionTimeout": self._validate_non_negative_int,
            "HeartbeatInterval": self._validate_non_negative_int,
            "TransactionMessageAttempts": self._validate_positive_or_zero_int,
            "TransactionMessageRetryInterval": self._validate_positive_or_zero_int,
            "ResetRetries": self._validate_non_negative_int,
            "WebSocketPingInterval": self._validate_non_negative_int,
            "LocalAuthListEnabled": self._validate_bool,
            "AuthorizationCacheEnabled": self._validate_bool,
            "AuthorizeRemoteTxRequests": self._validate_bool,
            "LocalAuthorizeOffline": self._validate_bool,
            "LocalPreAuthorize": self._validate_bool,
            "StopTransactionOnEVSideDisconnect": self._validate_bool,
            "StopTransactionOnInvalidId": self._validate_bool,
            "UnlockConnectorOnEVSideDisconnect": self._validate_bool,
            "AllowOfflineTxForUnknownId": self._validate_bool,
        }
    
    def set_key(self, key: str, value: str) -> ConfigurationStatus:
        """Set a configuration key value with validation."""
        config_key = self._keys.get(key)
        if config_key is None:
            return ConfigurationStatus.not_supported
        if config_key.readonly:
            return ConfigurationStatus.rejected
        
        # Validate if validator exists
        if key in self._VALIDATORS:
            is_valid, error_msg = self._VALIDATORS[key](value)
            if not is_valid:
                self.logger.warning(
                    f"Configuration validation failed for {key}: {error_msg}"
                )
                return ConfigurationStatus.rejected
        
        config_key.value = value
        self.on_key_changed.emit(key_name=key, new_value=value)
        return ConfigurationStatus.accepted
    
    def __init__(self) -> None:
        self._keys: dict[str, ConfigurationKey] = {}
        self.on_key_changed: Event = Event()
        self._VALIDATORS: dict[str, Callable[[str], tuple[bool, Optional[str]]]] = {}
        self._init_validators()
```

**Tests**:
- `tests/test_config_keys.py` - add validation tests
  - Test ClockAlignedDataInterval rejects values 1-59
  - Test MeterValueSampleInterval accepts 0 and positive values
  - Test boolean fields reject non-boolean values

---

### 7. Local Auth List idTagInfo Validation

**Spec Reference**: OCPP 1.6 §5.10  
**Current State**: Accepts any dict structure for `idTagInfo`  
**Required**: Validate structure contains valid `status` and optional fields

#### Implementation

**Files to Modify**:
- `src/chargeghost_evse/ocpp_adapter/local_auth_list.py`

```python
# Add validation helper

def _validate_id_tag_info(id_tag_info: dict) -> tuple[bool, Optional[str]]:
    """
    Validate idTagInfo structure per OCPP 1.6.
    
    Required: status (AuthorizationStatus enum value)
    Optional: expiryDate (ISO 8601), parentIdTag (string)
    """
    if not isinstance(id_tag_info, dict):
        return False, "idTagInfo must be a dictionary"
    
    status = id_tag_info.get("status")
    if status is None:
        return False, "idTagInfo must contain 'status'"
    
    # Validate status is a valid AuthorizationStatus
    valid_statuses = {"Accepted", "Blocked", "Expired", "Invalid", "ConcurrentTx"}
    if status not in valid_statuses:
        return False, f"Invalid status: {status}"
    
    # Validate expiryDate format if present
    expiry_date = id_tag_info.get("expiryDate")
    if expiry_date is not None:
        try:
            if expiry_date.endswith("Z"):
                expiry_date = expiry_date[:-1] + "+00:00"
            datetime.fromisoformat(expiry_date)
        except ValueError:
            return False, f"Invalid expiryDate format: {expiry_date}"
    
    return True, None

# In _handle_full_update and _handle_differential_update
# Validate before adding entries:

def _handle_full_update(self, list_version: int, local_authorization_list: Optional[list[dict]]) -> tuple[bool, str]:
    # ... existing code ...
    
    for entry_data in local_authorization_list:
        id_tag = entry_data.get("idTag")
        if not id_tag:
            continue
        
        id_tag_info = entry_data.get("idTagInfo", {})
        
        # NEW: Validate idTagInfo
        is_valid, error = _validate_id_tag_info(id_tag_info)
        if not is_valid:
            self.logger.warning(f"Invalid idTagInfo for {id_tag}: {error}")
            continue  # Skip invalid entry
        
        self._entries[id_tag] = AuthorizationEntry(
            id_tag=id_tag,
            id_tag_info=id_tag_info,
        )
    # ... rest of method ...
```

**Tests**:
- `tests/test_local_auth_list.py` - add validation tests
  - Test valid idTagInfo is accepted
  - Test missing status is rejected
  - Test invalid status is rejected
  - Test invalid expiryDate format is rejected

---

## P3: Minor Compliance Issues

### 8. Transaction ID Conflict Prevention

**Spec Reference**: OCPP 1.6 §4.9  
**Current State**: Local auth generates client-side transaction IDs  
**Required**: Ensure transaction IDs from CSMS take precedence

#### Implementation

**Files to Modify**:
- `src/chargeghost_evse/ocpp_adapter/adapter.py`
- `src/chargeghost_evse/bridge/bridge.py`

**Strategy**: When using local auth, use negative transaction IDs to avoid collision with CSMS-assigned positive IDs.

```python
# In adapter.py::send_start_transaction (around line 1667)
# BEFORE:
self._next_transaction_id += 1
transaction_id = self._next_transaction_id

# AFTER:
# Use negative IDs for locally-generated transaction IDs
# This prevents collision with CSMS-assigned positive IDs
self._next_transaction_id -= 1
transaction_id = self._next_transaction_id
```

**Alternative Strategy**: Track both local and CSMS transaction IDs:

```python
# In adapter.py, add to class:
self._local_transaction_counter: int = -1  # Start at -1 for local IDs

# When local auth succeeds:
self._local_transaction_counter -= 1
local_tx_id = self._local_transaction_counter

# The CSMS will assign a real transaction_id in StartTransaction.conf
# The bridge already handles updating the session with the CSMS-assigned ID
```

**Tests**:
- `tests/test_transaction_ids.py` (new)
  - Test local auth uses distinct transaction IDs
  - Test CSMS-assigned ID overwrites local ID

---

### 9. TriggerMessage Coverage Expansion

**Spec Reference**: OCPP 1.6 §5.13  
**Current State**: 6 trigger types supported  
**Required**: Add `Authorize` trigger support

#### Implementation

**Files to Modify**:
- `src/chargeghost_evse/ocpp_adapter/adapter.py`

```python
# In on_trigger_message, add Authorize handler

if trigger == MessageTrigger.authorize:
    # Per spec, Authorize trigger should use a cached idTag
    # Since we don't have a cached idTag in this context,
    # we need additional context from the engine
    if (
        self.get_cached_id_tag is None
        or not self.known_connector_ids
    ):
        return call_result.TriggerMessage(status=TriggerMessageStatus.rejected)
    
    cached_id_tag = self.get_cached_id_tag()
    if cached_id_tag is None:
        return call_result.TriggerMessage(status=TriggerMessageStatus.rejected)
    
    self._schedule_background_send(
        self.send_authorize(id_tag=cached_id_tag),
        trigger.value,
    )
    return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)
```

**Add callback injection in Bridge**:

```python
# In bridge.py::_inject_limit_getter

def get_cached_id_tag() -> Optional[str]:
    """Get the most recent idTag from the current or last session."""
    if self.engine.session and self.engine.session.id_tag:
        return self.engine.session.id_tag
    if self.engine.last_stopped_session:
        return self.engine.last_stopped_session.get("id_tag")
    return None

if self.runner.adapter:
    # ... existing callbacks ...
    self.runner.adapter.get_cached_id_tag = get_cached_id_tag
```

**Tests**:
- `tests/test_trigger_message.py` - add Authorize trigger test

---

### 10. EVSE Suspension StatusNotification Verification

**Spec Reference**: OCPP 1.6 §4.6  
**Current State**: Engine transitions to `SuspendedEVSE`, but verify StatusNotification sent  
**Required**: Ensure `SuspendedEVSE` status is sent via StatusNotification

#### Implementation

**Verification Only** - Check that the existing code path correctly emits StatusNotification:

1. Engine calls `connector.suspend_evse()` in `engine.py:714`
2. Connector transitions status to `SuspendedEVSE` 
3. Connector's `on_status_change` event fires
4. Engine's `handle_connector_status_change` receives event and emits `connector_status_changed`
5. Bridge's `on_connector_status_change` sends StatusNotification

**Test to verify**:

```python
# In tests/test_engine.py or new test file

def test_suspend_evse_sends_status_notification(mocker):
    """Verify that EVSE suspension triggers StatusNotification."""
    engine = Engine()
    connector = engine.add_connector()
    engine.plug_in(connector_id=1)
    engine.start_session(connector_id=1, transaction_id=1)
    
    # Mock the status change handler
    status_changes = []
    engine.connector_status_changed.subscribe(
        lambda connector_id, status: status_changes.append((connector_id, status))
    )
    
    # Set a charging profile that limits to 0A
    # (This is tested in integration with ChargingProfileManager)
    
    # Verify status changed to SuspendedEVSE
    # ... assertions ...
```

---

## Implementation Order

### Phase 1: Critical (Week 1)
1. ✅ StopTransaction transactionData (#1)
2. ✅ Clock-Aligned MeterValues (#2)

### Phase 2: Important (Week 2)
3. ✅ GetCompositeSchedule status enum (#3)
4. ✅ MeterValues format improvements (#4)
5. ✅ minChargingRate enforcement (#5)
6. ✅ Configuration key validation (#6)
7. ✅ Local auth list validation (#7)

### Phase 3: Minor (Week 3)
8. ✅ Transaction ID conflict prevention (#8)
9. ✅ TriggerMessage Authorize support (#9)
10. ✅ EVSE suspension verification (#10)

---

## Testing Strategy

### Unit Tests
- Each implementation should have corresponding unit tests
- Use pytest fixtures for common setup
- Mock OCPP calls where appropriate

### Integration Tests
- Test full message flow from Engine → Bridge → Adapter
- Test charging profile integration with Engine simulation
- Test offline queue behavior with new StopTransaction data

### Compliance Tests
- Run against OCPP 1.6 test suite if available
- Test against multiple CSMS implementations
- Verify errata compliance specifically

---

## Rollback Plan

Each change should be:
1. Implemented behind a feature flag if risky
2. Merged with comprehensive tests
3. Monitored in production for any CSMS compatibility issues

Feature flags can be added to `SimulationConfig`:

```python
@dataclass
class SimulationConfig:
    # ... existing fields ...
    ocpp_include_transaction_data: bool = True
    ocpp_clock_aligned_meter_values: bool = True
    ocpp_validate_config_keys: bool = True
```

---

## Documentation Updates

After implementation:
1. Update `AGENTS.md` with new configuration keys and behavior
2. Update inline code documentation
3. Update README if user-facing behavior changes
4. Add migration notes for existing users
