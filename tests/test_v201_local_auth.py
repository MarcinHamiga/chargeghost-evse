import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from ocpp.v201.datatypes import AuthorizationData, IdTokenInfoType, IdTokenType
from ocpp.v201.enums import (
    AuthorizationStatusEnumType,
    ClearCacheStatusEnumType,
    IdTokenEnumType,
    SendLocalListStatusEnumType,
    UpdateEnumType,
)

from chargeghost_evse.ocpp_adapter.local_auth_list_v201 import LocalAuthListManagerV201


class _EventCollector:
    def __init__(self):
        self.versions = []

    def on_version(self, version: int) -> None:
        self.versions.append(version)


def _make_manager(tmp_path: Path, **kwargs) -> LocalAuthListManagerV201:
    file_path = tmp_path / "local_auth_list_v201.json"
    return LocalAuthListManagerV201(_file_path=file_path, **kwargs)


def _make_auth_data(
    id_token_str: str = "TAG1",
    token_type: IdTokenEnumType = IdTokenEnumType.central,
    status: AuthorizationStatusEnumType = AuthorizationStatusEnumType.accepted,
) -> AuthorizationData:
    token = IdTokenType(id_token=id_token_str, type=token_type)
    info = IdTokenInfoType(status=status)
    return AuthorizationData(id_token=token, id_token_info=info)


class TestLocalAuthListManagerV201:
    def test_initial_version_is_zero(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.version == 0
        assert mgr.hash is None
        assert mgr.entry_count == 0

    def test_full_update_accepted(self, tmp_path):
        mgr = _make_manager(tmp_path)
        auth_data = _make_auth_data("TAG1")
        status, msg = mgr.send_local_list(
            list_version=1,
            local_authorization_list=[auth_data],
            update_type=UpdateEnumType.full,
        )
        assert status == SendLocalListStatusEnumType.accepted
        assert mgr.version == 1
        assert mgr.entry_count == 1

    def test_full_update_clears_existing(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.enabled = True
        auth_data1 = _make_auth_data("TAG1")
        mgr.send_local_list(
            list_version=1,
            local_authorization_list=[auth_data1],
            update_type=UpdateEnumType.full,
        )
        auth_data2 = _make_auth_data("TAG2")
        mgr.send_local_list(
            list_version=2,
            local_authorization_list=[auth_data2],
            update_type=UpdateEnumType.full,
        )
        assert mgr.entry_count == 1
        assert mgr.find_entry("TAG2", "Central") is not None
        assert mgr.find_entry("TAG1", "Central") is None

    def test_full_update_with_none_clears(self, tmp_path):
        mgr = _make_manager(tmp_path)
        auth_data = _make_auth_data("TAG1")
        mgr.send_local_list(
            list_version=1,
            local_authorization_list=[auth_data],
            update_type=UpdateEnumType.full,
        )
        status, msg = mgr.send_local_list(
            list_version=2,
            local_authorization_list=None,
            update_type=UpdateEnumType.full,
        )
        assert status == SendLocalListStatusEnumType.accepted
        assert mgr.entry_count == 0
        assert mgr.version == 2

    def test_full_update_rejects_zero_version(self, tmp_path):
        mgr = _make_manager(tmp_path)
        status, msg = mgr.send_local_list(
            list_version=0,
            local_authorization_list=None,
            update_type=UpdateEnumType.full,
        )
        assert status == SendLocalListStatusEnumType.failed

    def test_full_update_rejects_negative_version(self, tmp_path):
        mgr = _make_manager(tmp_path)
        status, msg = mgr.send_local_list(
            list_version=-1,
            local_authorization_list=None,
            update_type=UpdateEnumType.full,
        )
        assert status == SendLocalListStatusEnumType.failed

    def test_full_update_exceeds_max_entries(self, tmp_path):
        mgr = _make_manager(tmp_path, max_entries=1)
        entries = [_make_auth_data(f"TAG{i}") for i in range(3)]
        status, msg = mgr.send_local_list(
            list_version=1,
            local_authorization_list=entries,
            update_type=UpdateEnumType.full,
        )
        assert status == SendLocalListStatusEnumType.failed
        assert "max entries" in msg

    def test_differential_update_accepted(self, tmp_path):
        mgr = _make_manager(tmp_path)
        auth_data1 = _make_auth_data("TAG1")
        mgr.send_local_list(
            list_version=1,
            local_authorization_list=[auth_data1],
            update_type=UpdateEnumType.full,
        )
        auth_data2 = _make_auth_data("TAG2")
        status, msg = mgr.send_local_list(
            list_version=2,
            local_authorization_list=[auth_data2],
            update_type=UpdateEnumType.differential,
        )
        assert status == SendLocalListStatusEnumType.accepted
        assert mgr.entry_count == 2
        assert mgr.version == 2

    def test_differential_update_version_mismatch(self, tmp_path):
        mgr = _make_manager(tmp_path)
        auth_data = _make_auth_data("TAG1")
        mgr.send_local_list(
            list_version=1,
            local_authorization_list=[auth_data],
            update_type=UpdateEnumType.full,
        )
        status, msg = mgr.send_local_list(
            list_version=5,
            local_authorization_list=[_make_auth_data("TAG2")],
            update_type=UpdateEnumType.differential,
        )
        assert status == SendLocalListStatusEnumType.version_mismatch

    def test_differential_update_removes_entry_with_none_info(self, tmp_path):
        mgr = _make_manager(tmp_path)
        auth_data = _make_auth_data("TAG1")
        mgr.send_local_list(
            list_version=1,
            local_authorization_list=[auth_data],
            update_type=UpdateEnumType.full,
        )
        token = IdTokenType(id_token="TAG1", type=IdTokenEnumType.central)
        remove_data = AuthorizationData(id_token=token, id_token_info=None)
        status, msg = mgr.send_local_list(
            list_version=2,
            local_authorization_list=[remove_data],
            update_type=UpdateEnumType.differential,
        )
        assert status == SendLocalListStatusEnumType.accepted
        assert mgr.entry_count == 0

    def test_differential_update_exceeds_max_entries(self, tmp_path):
        mgr = _make_manager(tmp_path, max_entries=1)
        auth_data1 = _make_auth_data("TAG1")
        mgr.send_local_list(
            list_version=1,
            local_authorization_list=[auth_data1],
            update_type=UpdateEnumType.full,
        )
        auth_data2 = _make_auth_data("TAG2")
        status, msg = mgr.send_local_list(
            list_version=2,
            local_authorization_list=[auth_data2],
            update_type=UpdateEnumType.differential,
        )
        assert status == SendLocalListStatusEnumType.failed
        assert "max entries" in msg
        assert mgr.entry_count == 1

    def test_entries_keyed_by_id_token_and_type(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.enabled = True
        auth_central = _make_auth_data("TAG1", IdTokenEnumType.central)
        auth_ema_id = _make_auth_data("TAG1", IdTokenEnumType.e_maid)
        mgr.send_local_list(
            list_version=1,
            local_authorization_list=[auth_central, auth_ema_id],
            update_type=UpdateEnumType.full,
        )
        assert mgr.entry_count == 2
        assert mgr.find_entry("TAG1", "Central") is not None
        assert mgr.find_entry("TAG1", "eMAID") is not None

    def test_find_entry_returns_none_when_disabled(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.enabled = False
        auth_data = _make_auth_data("TAG1")
        mgr.send_local_list(
            list_version=1,
            local_authorization_list=[auth_data],
            update_type=UpdateEnumType.full,
        )
        assert mgr.find_entry("TAG1", "Central") is None

    def test_find_entry_returns_none_for_unknown(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.enabled = True
        assert mgr.find_entry("UNKNOWN", "Central") is None

    def test_get_local_list_version(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.get_local_list_version() == 0
        mgr.send_local_list(
            list_version=5,
            local_authorization_list=None,
            update_type=UpdateEnumType.full,
        )
        assert mgr.get_local_list_version() == 5

    def test_clear_cache(self, tmp_path):
        mgr = _make_manager(tmp_path)
        auth_data = _make_auth_data("TAG1")
        mgr.send_local_list(
            list_version=3,
            local_authorization_list=[auth_data],
            update_type=UpdateEnumType.full,
        )
        success, msg = mgr.clear_cache()
        assert success is True
        assert mgr.version == 0
        assert mgr.hash is None
        assert mgr.entry_count == 0

    def test_on_list_changed_event(self, tmp_path):
        mgr = _make_manager(tmp_path)
        collector = _EventCollector()
        mgr.on_list_changed.subscribe(collector.on_version)
        mgr.send_local_list(
            list_version=1,
            local_authorization_list=None,
            update_type=UpdateEnumType.full,
        )
        assert collector.versions == [1]

    def test_hash_stored_on_update(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.send_local_list(
            list_version=1,
            local_authorization_list=None,
            update_type=UpdateEnumType.full,
            remote_hash="abc123",
        )
        assert mgr.hash == "abc123"

    def test_authorize_returns_status(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.enabled = True
        auth_data = _make_auth_data("TAG1", status=AuthorizationStatusEnumType.accepted)
        mgr.send_local_list(
            list_version=1,
            local_authorization_list=[auth_data],
            update_type=UpdateEnumType.full,
        )
        result = mgr.authorize("TAG1", "Central")
        assert result == AuthorizationStatusEnumType.accepted

    def test_authorize_returns_none_when_disabled(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.enabled = False
        result = mgr.authorize("TAG1", "Central")
        assert result is None

    def test_authorize_returns_none_for_unknown(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.enabled = True
        result = mgr.authorize("UNKNOWN", "Central")
        assert result is None


class TestV201AdapterLocalAuthHandlers:
    def test_adapter_has_local_auth_manager(self, tmp_path):
        from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter

        mock_conn = MagicMock()
        mock_conn.recv = AsyncMock()
        mock_conn.send = AsyncMock()
        file_path = tmp_path / "auth_list.json"
        adapter = V201Adapter(
            id="CP_1",
            connection=mock_conn,
            command_queue=MagicMock(),
        )
        adapter.local_auth_manager = LocalAuthListManagerV201(_file_path=file_path)
        assert isinstance(adapter.local_auth_manager, LocalAuthListManagerV201)

    def test_on_get_local_list_version(self, tmp_path):
        from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter

        mock_conn = MagicMock()
        mock_conn.recv = AsyncMock()
        mock_conn.send = AsyncMock()
        file_path = tmp_path / "auth_list.json"
        adapter = V201Adapter(
            id="CP_1",
            connection=mock_conn,
            command_queue=MagicMock(),
        )
        adapter.local_auth_manager = LocalAuthListManagerV201(_file_path=file_path)
        adapter.local_auth_manager.send_local_list(
            list_version=7,
            local_authorization_list=None,
            update_type=UpdateEnumType.full,
        )
        result = asyncio.run(adapter.on_get_local_list_version())
        assert result.version_number == 7

    def test_on_send_local_list_full(self, tmp_path):
        from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter

        mock_conn = MagicMock()
        mock_conn.recv = AsyncMock()
        mock_conn.send = AsyncMock()
        file_path = tmp_path / "auth_list.json"
        adapter = V201Adapter(
            id="CP_1",
            connection=mock_conn,
            command_queue=MagicMock(),
        )
        adapter.local_auth_manager = LocalAuthListManagerV201(_file_path=file_path)
        auth_data = _make_auth_data("TAG1")
        result = asyncio.run(
            adapter.on_send_local_list(
                version_number=1,
                update_type=UpdateEnumType.full,
                local_authorization_list=[auth_data],
            )
        )
        assert result.status == SendLocalListStatusEnumType.accepted
        assert adapter.local_auth_manager.version == 1
        assert adapter.local_auth_manager.entry_count == 1

    def test_on_send_local_list_differential(self, tmp_path):
        from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter

        mock_conn = MagicMock()
        mock_conn.recv = AsyncMock()
        mock_conn.send = AsyncMock()
        file_path = tmp_path / "auth_list.json"
        adapter = V201Adapter(
            id="CP_1",
            connection=mock_conn,
            command_queue=MagicMock(),
        )
        adapter.local_auth_manager = LocalAuthListManagerV201(_file_path=file_path)
        auth_data1 = _make_auth_data("TAG1")
        asyncio.run(
            adapter.on_send_local_list(
                version_number=1,
                update_type=UpdateEnumType.full,
                local_authorization_list=[auth_data1],
            )
        )
        auth_data2 = _make_auth_data("TAG2")
        result = asyncio.run(
            adapter.on_send_local_list(
                version_number=2,
                update_type=UpdateEnumType.differential,
                local_authorization_list=[auth_data2],
            )
        )
        assert result.status == SendLocalListStatusEnumType.accepted
        assert adapter.local_auth_manager.entry_count == 2

    def test_on_send_local_list_version_mismatch(self, tmp_path):
        from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter

        mock_conn = MagicMock()
        mock_conn.recv = AsyncMock()
        mock_conn.send = AsyncMock()
        file_path = tmp_path / "auth_list.json"
        adapter = V201Adapter(
            id="CP_1",
            connection=mock_conn,
            command_queue=MagicMock(),
        )
        adapter.local_auth_manager = LocalAuthListManagerV201(_file_path=file_path)
        auth_data = _make_auth_data("TAG1")
        result = asyncio.run(
            adapter.on_send_local_list(
                version_number=5,
                update_type=UpdateEnumType.differential,
                local_authorization_list=[auth_data],
            )
        )
        assert result.status == SendLocalListStatusEnumType.version_mismatch

    def test_on_send_local_list_invalid_update_type(self, tmp_path):
        from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter

        mock_conn = MagicMock()
        mock_conn.recv = AsyncMock()
        mock_conn.send = AsyncMock()
        file_path = tmp_path / "auth_list.json"
        adapter = V201Adapter(
            id="CP_1",
            connection=mock_conn,
            command_queue=MagicMock(),
        )
        adapter.local_auth_manager = LocalAuthListManagerV201(_file_path=file_path)
        result = asyncio.run(
            adapter.on_send_local_list(
                version_number=1,
                update_type="InvalidType",
                local_authorization_list=None,
            )
        )
        assert result.status == SendLocalListStatusEnumType.failed

    def test_on_clear_cache(self, tmp_path):
        from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter

        mock_conn = MagicMock()
        mock_conn.recv = AsyncMock()
        mock_conn.send = AsyncMock()
        file_path = tmp_path / "auth_list.json"
        adapter = V201Adapter(
            id="CP_1",
            connection=mock_conn,
            command_queue=MagicMock(),
        )
        adapter.local_auth_manager = LocalAuthListManagerV201(_file_path=file_path)
        auth_data = _make_auth_data("TAG1")
        asyncio.run(
            adapter.on_send_local_list(
                version_number=1,
                update_type=UpdateEnumType.full,
                local_authorization_list=[auth_data],
            )
        )
        result = asyncio.run(adapter.on_clear_cache())
        assert result.status == ClearCacheStatusEnumType.accepted
        assert adapter.local_auth_manager.version == 0
        assert adapter.local_auth_manager.entry_count == 0

    def test_on_clear_cache_already_empty(self, tmp_path):
        from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter

        mock_conn = MagicMock()
        mock_conn.recv = AsyncMock()
        mock_conn.send = AsyncMock()
        file_path = tmp_path / "auth_list.json"
        adapter = V201Adapter(
            id="CP_1",
            connection=mock_conn,
            command_queue=MagicMock(),
        )
        adapter.local_auth_manager = LocalAuthListManagerV201(_file_path=file_path)
        result = asyncio.run(adapter.on_clear_cache())
        assert result.status == ClearCacheStatusEnumType.accepted
