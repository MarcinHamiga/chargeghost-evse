from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


class MockUpdateManager:
    def __init__(self, current_version: str = "1.0.0") -> None:
        self.current_version = current_version

    @staticmethod
    def is_update_available(current: str, latest: str) -> bool:
        return current != latest


class TestUpdateRoutes:
    def test_check_for_updates(self, client, runtime):
        runtime.check_for_updates = AsyncMock(
            return_value={
                "update_available": True,
                "current_version": "1.0.0",
                "latest_version": "1.1.0",
                "release": {
                    "tag_name": "1.1.0",
                    "body": "Bug fixes",
                    "published_at": "2024-01-01T00:00:00Z",
                    "assets": [
                        {
                            "name": "ChargeGhost.dmg",
                            "url": "https://example.test/download",
                            "size": 123,
                        }
                    ],
                },
            }
        )

        response = client.get("/api/v1/updates/check")

        assert response.status_code == 200
        data = response.json()
        assert data["update_available"] is True
        assert data["release"]["tag_name"] == "1.1.0"

    def test_get_status_without_update_manager(self, client, runtime):
        runtime._update_manager = None
        runtime._latest_release = None

        response = client.get("/api/v1/updates/status")

        assert response.status_code == 200
        assert response.json() == {
            "current_version": "0.0.0",
            "latest_version": None,
            "update_available": False,
        }

    def test_get_status_with_cached_release(self, client, runtime):
        runtime._update_manager = MockUpdateManager("1.0.0")
        runtime._latest_release = SimpleNamespace(tag_name="1.1.0")

        response = client.get("/api/v1/updates/status")

        assert response.status_code == 200
        assert response.json() == {
            "current_version": "1.0.0",
            "latest_version": "1.1.0",
            "update_available": True,
        }

    def test_download_update(self, client, runtime):
        runtime.download_update = AsyncMock(
            return_value={"status": "ready", "progress": 100, "message": "downloaded"}
        )

        response = client.post("/api/v1/updates/download")

        assert response.status_code == 200
        assert response.json() == {
            "status": "ready",
            "progress": 100,
            "message": "downloaded",
        }

    def test_ignore_version(self, client, runtime):
        runtime.ignore_version_sync = MagicMock()

        response = client.post("/api/v1/updates/ignore?tag=1.1.0")

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "message": "Ignored version 1.1.0",
            "details": None,
        }
        runtime.ignore_version_sync.assert_called_once_with("1.1.0")
