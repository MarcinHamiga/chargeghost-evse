import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from ocpp.v16.enums import AuthorizationStatus, ClearCacheStatus

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def test_send_authorize_uses_cached_response_when_enabled() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.config_manager.set_key("AuthorizationCacheEnabled", "true")
	adapter.auth_cache.put("TAG-1", {"status": AuthorizationStatus.accepted.value})
	adapter.call = AsyncMock()

	response = asyncio.run(adapter.send_authorize("TAG-1"))

	assert response.id_tag_info["status"] == AuthorizationStatus.accepted.value
	adapter.call.assert_not_called()


def test_send_authorize_skips_cache_when_disabled() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.config_manager.set_key("AuthorizationCacheEnabled", "false")
	adapter.auth_cache.put("TAG-1", {"status": AuthorizationStatus.accepted.value})
	adapter.call = AsyncMock(
		return_value=MagicMock(id_tag_info={"status": AuthorizationStatus.accepted.value})
	)

	response = asyncio.run(adapter.send_authorize("TAG-1"))

	assert response.id_tag_info["status"] == AuthorizationStatus.accepted.value
	adapter.call.assert_awaited_once()


def test_send_authorize_caches_csms_response_when_enabled() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.config_manager.set_key("AuthorizationCacheEnabled", "true")
	adapter.call = AsyncMock(
		return_value=MagicMock(id_tag_info={"status": AuthorizationStatus.accepted.value})
	)

	first = asyncio.run(adapter.send_authorize("TAG-1"))
	second = asyncio.run(adapter.send_authorize("TAG-1"))

	assert first.id_tag_info["status"] == AuthorizationStatus.accepted.value
	assert second.id_tag_info["status"] == AuthorizationStatus.accepted.value
	adapter.call.assert_awaited_once()


def test_send_authorize_ignores_expired_cached_response() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.local_auth_list.enabled = False
	adapter.config_manager.set_key("AuthorizationCacheEnabled", "true")
	expiry_date = (
		datetime.now(timezone.utc) - timedelta(days=1)
	).isoformat().replace("+00:00", "Z")
	adapter.auth_cache.put(
		"TAG-1",
		{
			"status": AuthorizationStatus.accepted.value,
			"expiryDate": expiry_date,
		},
	)
	adapter.call = AsyncMock(
		return_value=MagicMock(id_tag_info={"status": AuthorizationStatus.blocked.value})
	)

	response = asyncio.run(adapter.send_authorize("TAG-1"))

	assert response.id_tag_info["status"] == AuthorizationStatus.blocked.value
	adapter.call.assert_awaited_once()
	assert adapter.auth_cache.get("TAG-1")["status"] == AuthorizationStatus.blocked.value


def test_on_clear_cache_clears_cache_and_returns_accepted() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.auth_cache.put("TAG-1", {"status": AuthorizationStatus.accepted.value})

	result = asyncio.run(adapter.on_clear_cache())

	assert result.status == ClearCacheStatus.accepted
	assert adapter.auth_cache.get("TAG-1") is None


def test_on_clear_cache_does_not_clear_local_auth_list() -> None:
	adapter = Adapter("CP_1", MagicMock())
	adapter.auth_cache.put("TAG-1", {"status": AuthorizationStatus.accepted.value})
	adapter.local_auth_list = MagicMock()

	result = asyncio.run(adapter.on_clear_cache())

	assert result.status == ClearCacheStatus.accepted
	assert adapter.auth_cache.get("TAG-1") is None
	adapter.local_auth_list.clear.assert_not_called()
