from __future__ import annotations

from chargeghost_evse import __version__


class TestAboutRoute:
	def test_get_about_returns_version_info(self, client):
		response = client.get("/api/v1/about")

		assert response.status_code == 200
		data = response.json()
		assert data["version"] == __version__
		assert data["description"] == "ChargeGhost EVSE Simulator"
		assert data["ocpp_versions"] == ["OCPP 1.6J"]
		assert data["license"] == "AGPLv3"
		assert "REST API" in data["features"]
		assert "WebSocket" in data["features"]
		assert "OCPP 1.6J" in data["features"]
		assert "Smart Charging" in data["features"]
		assert "Local Auth List" in data["features"]
		assert "Firmware Management" in data["features"]

	def test_get_about_features_count(self, client):
		response = client.get("/api/v1/about")

		assert response.status_code == 200
		assert len(response.json()["features"]) == 6
