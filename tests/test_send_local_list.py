import asyncio
from unittest.mock import AsyncMock, MagicMock

from ocpp.v16.enums import UpdateStatus

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def _make_adapter() -> Adapter:
	mock_conn = MagicMock()
	mock_conn.recv = AsyncMock()
	mock_conn.send = AsyncMock()
	return Adapter("CP_1", mock_conn)


def test_send_local_list_rejects_reserved_version_zero() -> None:
	adapter = _make_adapter()

	response = asyncio.run(
		adapter.on_send_local_list(
			list_version=0,
			local_authorization_list=[],
			update_type="Full",
		)
	)

	assert response.status == UpdateStatus.failed


def test_send_local_list_returns_version_mismatch_for_bad_differential_version() -> None:
	adapter = _make_adapter()
	asyncio.run(
		adapter.on_send_local_list(
			list_version=1,
			local_authorization_list=[
				{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}
			],
			update_type="Full",
		)
	)

	response = asyncio.run(
		adapter.on_send_local_list(
			list_version=3,
			local_authorization_list=[
				{"idTag": "TAG002", "idTagInfo": {"status": "Blocked"}}
			],
			update_type="Differential",
		)
	)

	assert response.status == UpdateStatus.version_mismatch
	assert adapter.local_auth_list.version == 1
