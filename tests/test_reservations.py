import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from ocpp.v16.enums import CancelReservationStatus, ReservationStatus

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.engine.connector import ConnectorState
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ocpp_adapter.adapter import Adapter


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


def test_reserve_connector_returns_occupied_when_connector_is_plugged_in() -> None:
	engine = Engine()
	engine.add_connector()
	engine.plug_in(1)

	status = engine.reserve_connector(
		connector_id=1,
		reservation_id=10,
		id_tag="TAG-1",
		expiry_date=datetime.now(timezone.utc) + timedelta(minutes=10),
	)

	assert status == "occupied"
	assert engine.get_reservation(1) is None


def test_reserve_connector_rejects_duplicate_reservation_id() -> None:
	engine = Engine()
	engine.add_connector()
	engine.add_connector()
	engine.reserve_connector(
		connector_id=1,
		reservation_id=10,
		id_tag="TAG-1",
		expiry_date=datetime.now(timezone.utc) + timedelta(minutes=10),
	)

	status = engine.reserve_connector(
		connector_id=2,
		reservation_id=10,
		id_tag="TAG-2",
		expiry_date=datetime.now(timezone.utc) + timedelta(minutes=10),
	)

	assert status == "rejected"
	assert engine.get_reservation(2) is None


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


def test_matching_reserved_parent_id_tag_clears_reservation_and_starts() -> None:
	engine = Engine()
	engine.add_connector()
	engine.reserve_connector(
		connector_id=1,
		reservation_id=10,
		id_tag="CHILD-TAG",
		parent_id_tag="PARENT-TAG",
		expiry_date=datetime.now(timezone.utc) + timedelta(minutes=10),
	)
	engine.plug_in(1)

	engine.start_session(connector_id=1, transaction_id=123, id_tag="PARENT-TAG")

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


def test_on_reserve_now_rejects_unknown_connector_id() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.known_connector_ids = [2]
	adapter.reserve_connector = MagicMock(return_value="accepted")

	result = asyncio.run(
		adapter.on_reserve_now(
			connector_id=1,
			expiry_date=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
			id_tag="TAG-1",
			reservation_id=10,
		)
	)

	assert result.status == ReservationStatus.rejected
	adapter.reserve_connector.assert_not_called()


def test_on_reserve_now_rejects_missing_reservation_callback() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.known_connector_ids = [1]
	adapter.reserve_connector = None

	result = asyncio.run(
		adapter.on_reserve_now(
			connector_id=1,
			expiry_date=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
			id_tag="TAG-1",
			reservation_id=10,
		)
	)

	assert result.status == ReservationStatus.rejected


def test_on_reserve_now_rejects_invalid_expiry_date() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.known_connector_ids = [1]
	adapter.reserve_connector = MagicMock(return_value="accepted")

	result = asyncio.run(
		adapter.on_reserve_now(
			connector_id=1,
			expiry_date="not-a-date",
			id_tag="TAG-1",
			reservation_id=10,
		)
	)

	assert result.status == ReservationStatus.rejected
	adapter.reserve_connector.assert_not_called()


def test_on_cancel_reservation_maps_accepted_status() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.cancel_reservation = MagicMock(return_value="accepted")

	result = asyncio.run(adapter.on_cancel_reservation(reservation_id=999))

	assert result.status == CancelReservationStatus.accepted
	adapter.cancel_reservation.assert_called_once_with(999)


def test_on_cancel_reservation_rejects_unknown_id() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.cancel_reservation = MagicMock(return_value="rejected")

	result = asyncio.run(adapter.on_cancel_reservation(reservation_id=999))

	assert result.status == CancelReservationStatus.rejected


def test_bridge_injects_reservation_callbacks() -> None:
	engine = Engine()
	engine.add_connector()
	bridge = Bridge(engine=engine, url="ws://localhost:3000/CP_1")
	bridge.runner.adapter = Adapter("CP_1", MagicMock())

	bridge._inject_limit_getter()

	assert bridge.runner.adapter is not None
	assert bridge.runner.adapter.reserve_connector == engine.reserve_connector
	assert bridge.runner.adapter.cancel_reservation == engine.cancel_reservation
