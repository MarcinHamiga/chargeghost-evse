# Missing OCPP Messages Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the remaining missing OCPP 1.6J message types in this simulator: `ReserveNow`, `CancelReservation`, `ClearCache`, `TriggerMessage`, and `DataTransfer`.

**Architecture:** Keep the existing layer split. The `Engine` owns reservation state and connector behavior. The `Adapter` owns OCPP request/response translation, auth-cache semantics, and vendor data-transfer routing. The `Bridge` stays thin and only injects the extra engine callbacks the adapter needs for reservation handling and triggered outbound messages.

**Tech Stack:** Python 3.14, PySide6, `ocpp` v16, `dataclasses`, `datetime`, `threading`, `pytest`

---

## Context You Must Know

- Baseline is green: `poetry run pytest` currently passes with `392 passed`.
- Existing inbound OCPP handlers live in `src/chargeghost_evse/ocpp_adapter/adapter.py`.
- Existing bridge callback injection pattern already exists for `ChangeAvailability` and smart charging in `src/chargeghost_evse/bridge/bridge.py`.
- Existing connector state model in `src/chargeghost_evse/engine/connector.py` does **not** yet include `Reserved`.
- The UI connector strip already has a `Reserved` icon mapping, so reservation work should primarily be domain/OCPP work, not UI work.
- Existing config keys already include `AuthorizationCacheEnabled`, but there is no actual cache implementation yet.
- OCPP 1.6 signatures from the installed `ocpp` library:
  - `ReserveNow(connector_id, expiry_date, id_tag, reservation_id, parent_id_tag=None)`
  - `CancelReservation(reservation_id)`
  - `ClearCache()`
  - `TriggerMessage(requested_message, connector_id=None)`
  - `DataTransfer(vendor_id, message_id=None, data=None)`
- Relevant enums:
  - `ReservationStatus`: `Accepted`, `Faulted`, `Occupied`, `Rejected`, `Unavailable`
  - `CancelReservationStatus`: `Accepted`, `Rejected`
  - `ClearCacheStatus`: `Accepted`, `Rejected`
  - `TriggerMessageStatus`: `Accepted`, `Rejected`, `NotImplemented`
  - `MessageTrigger`: `BootNotification`, `Heartbeat`, `MeterValues`, `StatusNotification`, `DiagnosticsStatusNotification`, `FirmwareStatusNotification`, plus unsupported certificate/log actions
  - `DataTransferStatus`: `Accepted`, `Rejected`, `UnknownMessageId`, `UnknownVendorId`

## Recommended Scope

Implement this as **simulator-grade OCPP support**, not a general plugin framework:

- Reservations are real domain state and affect connector status plus start authorization.
- Authorization cache is a small in-memory manager gated by `AuthorizationCacheEnabled`.
- Triggered messages support the subset that the simulator can already produce today.
- Data transfer uses a lightweight registry in the adapter and ships with one small built-in `ChargeGhost/Capabilities` handler so the feature has a positive-path integration test.

Do **not** add a database, background scheduler thread, or a generic extension bus in this pass.

---

## Task 1: Add Reservation Domain State and `Reserved` Connector Behavior

**Files:**
- Create: `src/chargeghost_evse/engine/reservation.py`
- Modify: `src/chargeghost_evse/engine/connector.py`
- Modify: `src/chargeghost_evse/engine/engine.py`
- Test: `tests/test_connector.py`
- Test: `tests/test_engine.py`
- Test: `tests/test_reservations.py`

### Step 1: Write the failing tests

Create `tests/test_reservations.py` with focused reservation coverage:

```python
from datetime import datetime, timedelta, timezone

from chargeghost_evse.engine.connector import ConnectorState
from chargeghost_evse.engine.engine import Engine


def test_reserve_connector_sets_reserved_status() -> None:
	engine = Engine()
	engine.add_connector()

	status = engine.reserve_connector(
		connector_id=1,
		reservation_id=10,
		id_tag="TAG-1",
		expiry_date=datetime.now(timezone.utc) + timedelta(minutes=10),
	)

	assert status == "accepted"
	assert engine.get_connector(1).status == ConnectorState.RESERVED


def test_start_session_rejects_mismatched_reserved_id_tag() -> None:
	engine = Engine()
	engine.add_connector()
	engine.reserve_connector(
		connector_id=1,
		reservation_id=10,
		id_tag="TAG-1",
		expiry_date=datetime.now(timezone.utc) + timedelta(minutes=10),
	)
	engine.plug_in(1)

	engine.start_session(connector_id=1, transaction_id=123, id_tag="OTHER")

	assert engine.session is None
	assert engine.get_connector(1).status == ConnectorState.PREPARING


def test_matching_reserved_id_tag_clears_reservation_and_starts() -> None:
	engine = Engine()
	engine.add_connector()
	engine.reserve_connector(
		connector_id=1,
		reservation_id=10,
		id_tag="TAG-1",
		expiry_date=datetime.now(timezone.utc) + timedelta(minutes=10),
	)
	engine.plug_in(1)

	engine.start_session(connector_id=1, transaction_id=123, id_tag="TAG-1")

	assert engine.session is not None
	assert engine.get_reservation(1) is None


def test_cancel_reservation_restores_available_status() -> None:
	engine = Engine()
	engine.add_connector()
	engine.reserve_connector(
		connector_id=1,
		reservation_id=10,
		id_tag="TAG-1",
		expiry_date=datetime.now(timezone.utc) + timedelta(minutes=10),
	)

	status = engine.cancel_reservation(10)

	assert status == "accepted"
	assert engine.get_connector(1).status == ConnectorState.AVAILABLE


def test_expired_reservation_is_cleared_on_simulate() -> None:
	engine = Engine()
	engine.add_connector()
	engine.reserve_connector(
		connector_id=1,
		reservation_id=10,
		id_tag="TAG-1",
		expiry_date=datetime.now(timezone.utc) - timedelta(seconds=1),
	)

	engine.simulate(0.1)

	assert engine.get_reservation(1) is None
	assert engine.get_connector(1).status == ConnectorState.AVAILABLE
```

Add connector-state tests to `tests/test_connector.py`:

```python
def test_plug_in_from_reserved_transitions_to_preparing(self):
	connector = Connector(id=1)
	connector.set_reserved()
	error = connector.plug_in()
	assert error is None
	assert connector.status == ConnectorState.PREPARING


def test_clear_reservation_restores_available_when_idle(self):
	connector = Connector(id=1)
	connector.set_reserved()
	connector.clear_reservation()
	assert connector.status == ConnectorState.AVAILABLE
```

### Step 2: Run the targeted tests to verify they fail

Run:

```bash
poetry run pytest tests/test_connector.py tests/test_engine.py tests/test_reservations.py -v
```

Expected:
- `ImportError` for `reservation.py`
- `AttributeError` for `ConnectorState.RESERVED`
- `AttributeError` for `Engine.reserve_connector`

### Step 3: Write the minimal reservation implementation

Create `src/chargeghost_evse/engine/reservation.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Reservation:
	reservation_id: int
	connector_id: int
	id_tag: str
	expiry_date: datetime
	parent_id_tag: Optional[str] = None
```

Modify `src/chargeghost_evse/engine/connector.py`:

```python
class ConnectorState(enum.Enum):
	AVAILABLE = "Available"
	PREPARING = "Preparing"
	CHARGING = "Charging"
	SUSPENDED_EVSE = "SuspendedEVSE"
	SUSPENDED_EV = "SuspendedEV"
	FINISHING = "Finishing"
	RESERVED = "Reserved"
	UNAVAILABLE = "Unavailable"
	FAULTED = "Faulted"


VALID_TRANSITIONS = {
	(ConnectorState.AVAILABLE, "plug_in"): ConnectorState.PREPARING,
	(ConnectorState.RESERVED, "plug_in"): ConnectorState.PREPARING,
	...
}


def set_reserved(self) -> None:
	if self._status in (ConnectorState.UNAVAILABLE, ConnectorState.FAULTED):
		return
	self._persistent_status = ConnectorState.RESERVED
	target = ConnectorState.PREPARING if self.is_plugged_in else ConnectorState.RESERVED
	if self._status != target:
		self.status = target


def clear_reservation(self) -> None:
	self._persistent_status = ConnectorState.AVAILABLE
	target = ConnectorState.PREPARING if self.is_plugged_in else ConnectorState.AVAILABLE
	if self._status in (ConnectorState.RESERVED, ConnectorState.PREPARING):
		self.status = target
```

Modify `src/chargeghost_evse/engine/engine.py`:

```python
from datetime import datetime, timezone

from chargeghost_evse.engine.reservation import Reservation


self._reservations: dict[int, Reservation] = {}


def get_reservation(self, connector_id: int) -> Optional[Reservation]:
	self._expire_reservations()
	return self._reservations.get(connector_id)


def reserve_connector(
	self,
	connector_id: int,
	reservation_id: int,
	id_tag: str,
	expiry_date: datetime,
	parent_id_tag: Optional[str] = None,
) -> str:
	self._expire_reservations()
	connector = self.get_connector(connector_id)
	if connector is None:
		return "rejected"
	if connector.status == ConnectorState.FAULTED:
		return "faulted"
	if connector.status == ConnectorState.UNAVAILABLE:
		return "unavailable"
	if self.session is not None and self.session.connector_id == connector_id:
		return "occupied"
	if connector_id in self._reservations:
		return "occupied"

	self._reservations[connector_id] = Reservation(
		reservation_id=reservation_id,
		connector_id=connector_id,
		id_tag=id_tag,
		expiry_date=expiry_date,
		parent_id_tag=parent_id_tag,
	)
	connector.set_reserved()
	return "accepted"


def cancel_reservation(self, reservation_id: int) -> str:
	for connector_id, reservation in list(self._reservations.items()):
		if reservation.reservation_id == reservation_id:
			del self._reservations[connector_id]
			connector = self.get_connector(connector_id)
			if connector:
				connector.clear_reservation()
			return "accepted"
	return "rejected"


def _expire_reservations(self) -> None:
	now = datetime.now(timezone.utc)
	for connector_id, reservation in list(self._reservations.items()):
		if reservation.expiry_date <= now:
			del self._reservations[connector_id]
			connector = self.get_connector(connector_id)
			if connector:
				connector.clear_reservation()
```

Also update `start_session()` so a live reservation:
- allows the session only when `id_tag` matches the reservation `id_tag` or `parent_id_tag`
- clears the reservation before transitioning into a live session
- still allows pending remote starts when the reserved connector is unplugged and the `id_tag` matches

### Step 4: Run the tests again

Run:

```bash
poetry run pytest tests/test_connector.py tests/test_engine.py tests/test_reservations.py -v
```

Expected: all reservation tests PASS.

### Step 5: Commit

```bash
git add src/chargeghost_evse/engine/reservation.py src/chargeghost_evse/engine/connector.py src/chargeghost_evse/engine/engine.py tests/test_connector.py tests/test_engine.py tests/test_reservations.py
git commit -m "feat: add engine-side reservation support"
```

---

## Task 2: Implement `ReserveNow` and `CancelReservation` in the Adapter

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py`
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Test: `tests/test_reservations.py`

### Step 1: Add failing adapter tests

Extend `tests/test_reservations.py`:

```python
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from ocpp.v16.enums import CancelReservationStatus, ReservationStatus

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def test_on_reserve_now_maps_engine_result_to_ocpp_status() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.known_connector_ids = [1]
	adapter.reserve_connector = MagicMock(return_value="accepted")

	result = asyncio.run(
		adapter.on_reserve_now(
			connector_id=1,
			expiry_date=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
			id_tag="TAG-1",
			reservation_id=10,
		)
	)

	assert result.status == ReservationStatus.accepted


def test_on_cancel_reservation_rejects_unknown_id() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.cancel_reservation = MagicMock(return_value="rejected")

	result = asyncio.run(adapter.on_cancel_reservation(reservation_id=999))

	assert result.status == CancelReservationStatus.rejected
```

### Step 2: Run the tests to verify failure

Run:

```bash
poetry run pytest tests/test_reservations.py -v
```

Expected:
- `AttributeError` for missing adapter callbacks
- `AttributeError` for missing `on_reserve_now`
- `AttributeError` for missing `on_cancel_reservation`

### Step 3: Implement the handlers and callback injection

Modify `src/chargeghost_evse/ocpp_adapter/adapter.py`:

```python
from ocpp.v16.enums import CancelReservationStatus, ReservationStatus


self.reserve_connector: Optional[Callable[..., str]] = None
self.cancel_reservation: Optional[Callable[[int], str]] = None


@on("ReserveNow")
async def on_reserve_now(
	self,
	connector_id: int,
	expiry_date: str,
	id_tag: str,
	reservation_id: int,
	parent_id_tag: Optional[str] = None,
	**kwargs,
) -> call_result.ReserveNow:
	if connector_id not in self.known_connector_ids:
		return call_result.ReserveNow(status=ReservationStatus.rejected)
	if self.reserve_connector is None:
		return call_result.ReserveNow(status=ReservationStatus.rejected)

	parsed_expiry = self.parse_ocpp_timestamp(expiry_date)
	if parsed_expiry is None:
		return call_result.ReserveNow(status=ReservationStatus.rejected)

	result = self.reserve_connector(
		connector_id,
		reservation_id,
		id_tag,
		parsed_expiry,
		parent_id_tag,
	)
	status_map = {
		"accepted": ReservationStatus.accepted,
		"occupied": ReservationStatus.occupied,
		"faulted": ReservationStatus.faulted,
		"unavailable": ReservationStatus.unavailable,
		"rejected": ReservationStatus.rejected,
	}
	return call_result.ReserveNow(status=status_map.get(result, ReservationStatus.rejected))


@on("CancelReservation")
async def on_cancel_reservation(self, reservation_id: int, **kwargs) -> call_result.CancelReservation:
	if self.cancel_reservation is None:
		return call_result.CancelReservation(status=CancelReservationStatus.rejected)
	result = self.cancel_reservation(reservation_id)
	status = (
		CancelReservationStatus.accepted
		if result == "accepted"
		else CancelReservationStatus.rejected
	)
	return call_result.CancelReservation(status=status)
```

Modify `src/chargeghost_evse/bridge/bridge.py` inside `_inject_limit_getter()`:

```python
if self.runner.adapter:
	self.runner.adapter.reserve_connector = self.engine.reserve_connector
	self.runner.adapter.cancel_reservation = self.engine.cancel_reservation
```

Modify `_remove_limit_getter()` to clear the new callbacks too.

### Step 4: Run the reservation tests again

Run:

```bash
poetry run pytest tests/test_reservations.py -v
```

Expected: adapter reservation tests PASS.

### Step 5: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/adapter.py src/chargeghost_evse/bridge/bridge.py tests/test_reservations.py
git commit -m "feat: add ReserveNow and CancelReservation handlers"
```

---

## Task 3: Add a Real Authorization Cache and Implement `ClearCache`

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/auth_cache.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py`
- Test: `tests/test_clear_cache.py`

### Step 1: Write failing tests

Create `tests/test_clear_cache.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

from ocpp.v16.enums import AuthorizationStatus, ClearCacheStatus

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def test_send_authorize_uses_cache_when_enabled() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.config_manager.set_key("AuthorizationCacheEnabled", "true")
	adapter.auth_cache.put("TAG-1", {"status": AuthorizationStatus.accepted.value})
	adapter.call = AsyncMock()

	result = asyncio.run(adapter.send_authorize("TAG-1"))

	assert result.id_tag_info["status"] == AuthorizationStatus.accepted.value
	adapter.call.assert_not_called()


def test_clear_cache_empties_cache_and_returns_accepted() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.auth_cache.put("TAG-1", {"status": AuthorizationStatus.accepted.value})

	result = asyncio.run(adapter.on_clear_cache())

	assert result.status == ClearCacheStatus.accepted
	assert adapter.auth_cache.get("TAG-1") is None
```

### Step 2: Run the tests to verify failure

Run:

```bash
poetry run pytest tests/test_clear_cache.py -v
```

Expected:
- missing `auth_cache`
- missing `on_clear_cache`

### Step 3: Implement the cache manager and handler

Create `src/chargeghost_evse/ocpp_adapter/auth_cache.py`:

```python
from datetime import datetime, timezone
from typing import Optional


class AuthorizationCacheManager:
	def __init__(self) -> None:
		self._entries: dict[str, dict] = {}

	def get(self, id_tag: str) -> Optional[dict]:
		entry = self._entries.get(id_tag)
		if entry is None:
			return None
		expiry_date = entry.get("expiryDate")
		if expiry_date:
			parsed = datetime.fromisoformat(expiry_date.replace("Z", "+00:00"))
			if parsed <= datetime.now(timezone.utc):
				del self._entries[id_tag]
				return None
		return entry.copy()

	def put(self, id_tag: str, id_tag_info: Optional[dict]) -> None:
		if id_tag_info is None:
			return
		self._entries[id_tag] = id_tag_info.copy()

	def clear(self) -> None:
		self._entries.clear()
```

Modify `src/chargeghost_evse/ocpp_adapter/adapter.py`:

```python
from ocpp.v16.enums import ClearCacheStatus

from chargeghost_evse.ocpp_adapter.auth_cache import AuthorizationCacheManager


self.auth_cache = AuthorizationCacheManager()


@on("ClearCache")
async def on_clear_cache(self, **kwargs) -> call_result.ClearCache:
	self.auth_cache.clear()
	return call_result.ClearCache(status=ClearCacheStatus.accepted)


async def send_authorize(self, id_tag: str) -> call_result.Authorize:
	self._log(f"Authorize: id_tag={id_tag}")

	local_result = self._check_local_auth(id_tag)
	if local_result is not None:
		...

	use_cache = self.config_manager.get_bool_value("AuthorizationCacheEnabled", True)
	if use_cache:
		cached = self.auth_cache.get(id_tag)
		if cached is not None:
			return call_result.Authorize(id_tag_info=cached)

	request = call.Authorize(id_tag=id_tag)
	response = await self.call(request)
	if use_cache and response.id_tag_info:
		self.auth_cache.put(id_tag, response.id_tag_info)
	return response
```

Do **not** reuse the local auth list as the cache. They are different OCPP concepts.

### Step 4: Run the tests again

Run:

```bash
poetry run pytest tests/test_clear_cache.py -v
```

Expected: cache tests PASS.

### Step 5: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/auth_cache.py src/chargeghost_evse/ocpp_adapter/adapter.py tests/test_clear_cache.py
git commit -m "feat: add authorization cache and ClearCache support"
```

---

## Task 4: Implement `TriggerMessage` for the Simulator-Supported Trigger Set

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py`
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Test: `tests/test_trigger_message.py`

### Step 1: Write failing tests

Create `tests/test_trigger_message.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

from ocpp.v16.enums import DiagnosticsStatus, FirmwareStatus, TriggerMessageStatus

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def test_trigger_boot_notification_calls_sender() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.send_boot_notification = AsyncMock()

	result = asyncio.run(adapter.on_trigger_message(requested_message="BootNotification"))

	assert result.status == TriggerMessageStatus.accepted
	adapter.send_boot_notification.assert_awaited_once()


def test_trigger_unsupported_message_returns_not_implemented() -> None:
	adapter = Adapter("CP_1", MagicMock())

	result = asyncio.run(adapter.on_trigger_message(requested_message="LogStatusNotification"))

	assert result.status == TriggerMessageStatus.not_implemented


def test_trigger_status_notification_for_connector() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.known_connector_ids = [1]
	adapter.get_connector_status = MagicMock(return_value="Available")
	adapter.send_status_notification = AsyncMock()

	result = asyncio.run(
		adapter.on_trigger_message(requested_message="StatusNotification", connector_id=1)
	)

	assert result.status == TriggerMessageStatus.accepted
	adapter.send_status_notification.assert_awaited_once()


def test_trigger_meter_values_without_snapshot_is_rejected() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.get_meter_snapshot = MagicMock(return_value=None)

	result = asyncio.run(
		adapter.on_trigger_message(requested_message="MeterValues", connector_id=1)
	)

	assert result.status == TriggerMessageStatus.rejected
```

### Step 2: Run the tests to verify failure

Run:

```bash
poetry run pytest tests/test_trigger_message.py -v
```

Expected: missing `on_trigger_message` and missing injected callbacks.

### Step 3: Implement the handler and bridge callbacks

Modify `src/chargeghost_evse/ocpp_adapter/adapter.py`:

```python
from ocpp.v16.enums import MessageTrigger, TriggerMessageStatus


self.get_connector_status: Optional[Callable[[int], Optional[str]]] = None
self.get_meter_snapshot: Optional[
	Callable[[int], Optional[tuple[float, Optional[int]]]]
] = None


@on("TriggerMessage")
async def on_trigger_message(
	self,
	requested_message: str,
	connector_id: Optional[int] = None,
	**kwargs,
) -> call_result.TriggerMessage:
	try:
		trigger = MessageTrigger(requested_message)
	except ValueError:
		return call_result.TriggerMessage(status=TriggerMessageStatus.not_implemented)

	if trigger == MessageTrigger.boot_notification:
		await self.send_boot_notification()
		return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

	if trigger == MessageTrigger.heartbeat:
		await self.send_heartbeat()
		return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

	if trigger == MessageTrigger.status_notification:
		if connector_id is None or self.get_connector_status is None:
			return call_result.TriggerMessage(status=TriggerMessageStatus.rejected)
		status = self.get_connector_status(connector_id)
		if status is None:
			return call_result.TriggerMessage(status=TriggerMessageStatus.rejected)
		await self.send_status_notification(connector_id, "NoError", status)
		return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

	if trigger == MessageTrigger.meter_values:
		if connector_id is None or self.get_meter_snapshot is None:
			return call_result.TriggerMessage(status=TriggerMessageStatus.rejected)
		snapshot = self.get_meter_snapshot(connector_id)
		if snapshot is None:
			return call_result.TriggerMessage(status=TriggerMessageStatus.rejected)
		value, transaction_id = snapshot
		await self.send_meter_values(connector_id, value, transaction_id)
		return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

	if trigger == MessageTrigger.diagnostics_status_notification:
		await self.send_diagnostics_status_notification(
			self.firmware_manager.get_diagnostics_status()
		)
		return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

	if trigger == MessageTrigger.firmware_status_notification:
		await self.send_firmware_status_notification(
			self.firmware_manager.get_firmware_status()
		)
		return call_result.TriggerMessage(status=TriggerMessageStatus.accepted)

	return call_result.TriggerMessage(status=TriggerMessageStatus.not_implemented)
```

Modify `src/chargeghost_evse/bridge/bridge.py` inside `_inject_limit_getter()`:

```python
def get_connector_status(connector_id: int) -> Optional[str]:
	connector = self.engine.get_connector(connector_id)
	if connector is None:
		return None
	return connector.status.value


def get_meter_snapshot(connector_id: int) -> Optional[tuple[float, Optional[int]]]:
	if self.engine.session is None or self.engine.session.connector_id != connector_id:
		return None
	return (
		self.engine.energy_meter.get_meter_reading(),
		self.engine.session.transaction_id,
	)


if self.runner.adapter:
	self.runner.adapter.get_connector_status = get_connector_status
	self.runner.adapter.get_meter_snapshot = get_meter_snapshot
```

Clear both callbacks in `_remove_limit_getter()`.

### Step 4: Run the tests again

Run:

```bash
poetry run pytest tests/test_trigger_message.py -v
```

Expected: trigger tests PASS.

### Step 5: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/adapter.py src/chargeghost_evse/bridge/bridge.py tests/test_trigger_message.py
git commit -m "feat: add TriggerMessage support for simulator messages"
```

---

## Task 5: Implement `DataTransfer` Inbound Routing and an Outbound Helper

**Files:**
- Create: `src/chargeghost_evse/ocpp_adapter/data_transfer.py`
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py`
- Test: `tests/test_data_transfer.py`

### Step 1: Write failing tests

Create `tests/test_data_transfer.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

from ocpp.v16.enums import DataTransferStatus

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def test_unknown_vendor_returns_unknown_vendor_id() -> None:
	adapter = Adapter("CP_1", MagicMock())

	result = asyncio.run(adapter.on_data_transfer(vendor_id="OtherVendor"))

	assert result.status == DataTransferStatus.unknown_vendor_id


def test_known_vendor_unknown_message_returns_unknown_message_id() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.register_data_transfer_handler("ChargeGhost", "Known", lambda data: ("Accepted", data))

	result = asyncio.run(
		adapter.on_data_transfer(vendor_id="ChargeGhost", message_id="Unknown")
	)

	assert result.status == DataTransferStatus.unknown_message_id


def test_registered_handler_returns_payload() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.register_data_transfer_handler(
		"ChargeGhost",
		"Echo",
		lambda data: (DataTransferStatus.accepted, data),
	)

	result = asyncio.run(
		adapter.on_data_transfer(vendor_id="ChargeGhost", message_id="Echo", data="hello")
	)

	assert result.status == DataTransferStatus.accepted
	assert result.data == "hello"


def test_send_data_transfer_calls_ocpp_call() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.call = AsyncMock(return_value=MagicMock(status=DataTransferStatus.accepted, data="ok"))

	result = asyncio.run(adapter.send_data_transfer("ChargeGhost", "Echo", "hello"))

	assert result.status == DataTransferStatus.accepted
	adapter.call.assert_awaited_once()
```

### Step 2: Run the tests to verify failure

Run:

```bash
poetry run pytest tests/test_data_transfer.py -v
```

Expected: missing handler registry and missing outbound helper.

### Step 3: Implement the registry and adapter methods

Create `src/chargeghost_evse/ocpp_adapter/data_transfer.py`:

```python
from collections.abc import Callable
from typing import Optional

from ocpp.v16.enums import DataTransferStatus


Handler = Callable[[Optional[str]], tuple[DataTransferStatus, Optional[str]]]


class DataTransferRegistry:
	def __init__(self) -> None:
		self._handlers: dict[tuple[str, str], Handler] = {}

	def register(self, vendor_id: str, message_id: str, handler: Handler) -> None:
		self._handlers[(vendor_id, message_id)] = handler

	def handle(
		self,
		vendor_id: str,
		message_id: Optional[str],
		data: Optional[str],
	) -> tuple[DataTransferStatus, Optional[str]]:
		vendor_handlers = [key for key in self._handlers if key[0] == vendor_id]
		if not vendor_handlers:
			return DataTransferStatus.unknown_vendor_id, None
		if message_id is None:
			return DataTransferStatus.unknown_message_id, None
		handler = self._handlers.get((vendor_id, message_id))
		if handler is None:
			return DataTransferStatus.unknown_message_id, None
		return handler(data)
```

Modify `src/chargeghost_evse/ocpp_adapter/adapter.py`:

```python
from ocpp.v16.enums import DataTransferStatus

from chargeghost_evse.ocpp_adapter.data_transfer import DataTransferRegistry


self.data_transfer_registry = DataTransferRegistry()
self.register_data_transfer_handler(
	"ChargeGhost",
	"Capabilities",
	lambda data: (
		DataTransferStatus.accepted,
		json.dumps(
			{
				"supports": [
					"ReserveNow",
					"CancelReservation",
					"ClearCache",
					"TriggerMessage",
					"DataTransfer",
				]
			}
		),
	),
)


def register_data_transfer_handler(self, vendor_id: str, message_id: str, handler) -> None:
	self.data_transfer_registry.register(vendor_id, message_id, handler)


@on("DataTransfer")
async def on_data_transfer(
	self,
	vendor_id: str,
	message_id: Optional[str] = None,
	data: Optional[str] = None,
	**kwargs,
) -> call_result.DataTransfer:
	status, payload = self.data_transfer_registry.handle(vendor_id, message_id, data)
	return call_result.DataTransfer(status=status, data=payload)


async def send_data_transfer(
	self,
	vendor_id: str,
	message_id: Optional[str] = None,
	data: Optional[str] = None,
) -> call_result.DataTransfer:
	request = call.DataTransfer(vendor_id=vendor_id, message_id=message_id, data=data)
	return await self.call(request)
```

### Step 4: Run the tests again

Run:

```bash
poetry run pytest tests/test_data_transfer.py -v
```

Expected: data-transfer tests PASS.

### Step 5: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/data_transfer.py src/chargeghost_evse/ocpp_adapter/adapter.py tests/test_data_transfer.py
git commit -m "feat: add DataTransfer support"
```

---

## Task 6: Final Regression, Documentation, and Full OCPP Gap Closure Check

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py`
- Modify: `src/chargeghost_evse/bridge/bridge.py`
- Modify: `src/chargeghost_evse/engine/engine.py`
- Modify: `src/chargeghost_evse/engine/connector.py`
- Test: `tests/test_connector.py`
- Test: `tests/test_engine.py`
- Test: `tests/test_reservations.py`
- Test: `tests/test_clear_cache.py`
- Test: `tests/test_trigger_message.py`
- Test: `tests/test_data_transfer.py`

### Step 1: Update top-level adapter documentation and log coverage

Update the adapter module docstring so the supported feature list now includes:

```python
- Reservation profile: ReserveNow, CancelReservation
- Core maintenance: ClearCache, TriggerMessage
- Vendor extensions: DataTransfer
```

Add or update any adapter logging tests only if the new actions should be treated as important shallow-mode actions.

### Step 2: Run the targeted message tests

Run:

```bash
poetry run pytest tests/test_reservations.py tests/test_clear_cache.py tests/test_trigger_message.py tests/test_data_transfer.py -v
```

Expected: PASS.

### Step 3: Run the full regression suite

Run:

```bash
poetry run pytest -v
```

Expected:
- all existing tests still pass
- no regressions in smart charging, reset, bridge, or message queue behavior

### Step 4: Sanity-check the code search for the formerly missing actions

Run:

```bash
rg -n "ReserveNow|CancelReservation|ClearCache|TriggerMessage|DataTransfer" src tests
```

Expected: each action now appears in production code and tests.

### Step 5: Commit

```bash
git add src/chargeghost_evse/ocpp_adapter/adapter.py src/chargeghost_evse/bridge/bridge.py src/chargeghost_evse/engine/engine.py src/chargeghost_evse/engine/connector.py tests/test_connector.py tests/test_engine.py tests/test_reservations.py tests/test_clear_cache.py tests/test_trigger_message.py tests/test_data_transfer.py
git commit -m "feat: complete remaining OCPP 1.6J message support"
```

---

## Risks to Watch During Implementation

- `Reserved` status must not break the existing unplug/plug/status-notification flow.
- Reservation expiry should be opportunistic and deterministic; do not add a background timer thread.
- `ClearCache` must stay separate from `LocalAuthList`; do not delete the local auth list.
- `TriggerMessage` must only claim `Accepted` when the requested message was actually sent.
- `DataTransfer` should not become a generic extension framework in this pass.
- Keep the single-active-session constraint intact.

## Suggested Implementation Order

1. Reservation domain state
2. ReserveNow/CancelReservation adapter hooks
3. Authorization cache + ClearCache
4. TriggerMessage
5. DataTransfer
6. Full regression
