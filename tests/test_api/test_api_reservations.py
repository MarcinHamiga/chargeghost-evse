from __future__ import annotations

from datetime import datetime, timezone


class MockReservation:
    def __init__(
        self, reservation_id, connector_id, id_tag, expiry_date, parent_id_tag=None
    ):
        self.reservation_id = reservation_id
        self.connector_id = connector_id
        self.id_tag = id_tag
        self.expiry_date = expiry_date
        self.parent_id_tag = parent_id_tag

    def is_expired(self, now=None):
        current_time = now or datetime.now(timezone.utc)
        expiry = self.expiry_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return current_time >= expiry


class TestReservationRoutes:
    def test_list_reservations_empty(self, client, mock_controller):
        mock_controller.engine._reservations = {}

        response = client.get("/api/v1/reservations")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_reservations_with_reservation(self, client, mock_controller):
        future_date = datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        reservation = MockReservation(
            reservation_id=42,
            connector_id=1,
            id_tag="TAG123",
            expiry_date=future_date,
            parent_id_tag=None,
        )
        mock_controller.engine._reservations = {1: reservation}

        response = client.get("/api/v1/reservations")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["reservation_id"] == 42
        assert data[0]["connector_id"] == 1
        assert data[0]["id_tag"] == "TAG123"

    def test_get_reservation_for_connector(self, client, mock_controller):
        future_date = datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        reservation = MockReservation(
            reservation_id=42,
            connector_id=1,
            id_tag="TAG123",
            expiry_date=future_date,
            parent_id_tag=None,
        )
        mock_controller.engine.get_reservation.return_value = reservation

        response = client.get("/api/v1/reservations/1")

        assert response.status_code == 200
        data = response.json()
        assert data["reservation_id"] == 42

    def test_get_reservation_not_found(self, client, mock_controller):
        mock_controller.engine._reservations = {}

        response = client.get("/api/v1/reservations/1")

        assert response.status_code == 200
        assert response.json() is None

    def test_create_reservation_success(self, client, mock_controller):
        mock_controller.engine._reservations = {}
        mock_controller.engine.reserve_connector.return_value = "accepted"

        response = client.post(
            "/api/v1/reservations",
            json={
                "connector_id": 1,
                "reservation_id": 99,
                "id_tag": "NEWTAG",
                "expiry_date": "2099-12-31T23:59:59Z",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "99" in data["message"]

    def test_create_reservation_failed(self, client, mock_controller):
        mock_controller.engine._reservations = {}
        mock_controller.engine.reserve_connector.return_value = "faulted"

        response = client.post(
            "/api/v1/reservations",
            json={
                "connector_id": 1,
                "reservation_id": 99,
                "id_tag": "NEWTAG",
                "expiry_date": "2099-12-31T23:59:59Z",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "faulted" in data["message"]

    def test_create_reservation_invalid_date(self, client, mock_controller):
        response = client.post(
            "/api/v1/reservations",
            json={
                "connector_id": 1,
                "reservation_id": 99,
                "id_tag": "NEWTAG",
                "expiry_date": "not-a-valid-date",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    def test_cancel_reservation_success(self, client, mock_controller):
        mock_controller.engine.cancel_reservation.return_value = "accepted"

        response = client.delete("/api/v1/reservations/42")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "42" in data["message"]

    def test_cancel_reservation_failed(self, client, mock_controller):
        mock_controller.engine.cancel_reservation.return_value = "rejected"

        response = client.delete("/api/v1/reservations/42")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
