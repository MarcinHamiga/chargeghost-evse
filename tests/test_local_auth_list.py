from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ocpp.v16.enums import AuthorizationStatus, UpdateStatus, UpdateType

from chargeghost_evse.ocpp_adapter.local_auth_list import (
    AuthorizationEntry,
    LocalAuthListManager,
)


class TestAuthorizationEntry:
    def test_initial_values(self):
        entry = AuthorizationEntry(id_tag="TAG123", id_tag_info={"status": "Accepted"})
        assert entry.id_tag == "TAG123"
        assert entry.id_tag_info == {"status": "Accepted"}

    def test_default_id_tag_info(self):
        entry = AuthorizationEntry(id_tag="TAG123")
        assert entry.id_tag_info == {}

    def test_not_expired_without_expiry_date(self):
        entry = AuthorizationEntry(id_tag="TAG123", id_tag_info={"status": "Accepted"})
        assert entry.is_expired() is False

    def test_not_expired_with_future_expiry_date(self):
        future = datetime.now(timezone.utc) + timedelta(days=30)
        entry = AuthorizationEntry(
            id_tag="TAG123",
            id_tag_info={"status": "Accepted", "expiryDate": future.isoformat()},
        )
        assert entry.is_expired() is False

    def test_expired_with_past_expiry_date(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        entry = AuthorizationEntry(
            id_tag="TAG123",
            id_tag_info={"status": "Accepted", "expiryDate": past.isoformat()},
        )
        assert entry.is_expired() is True

    def test_expired_with_z_suffix(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        entry = AuthorizationEntry(
            id_tag="TAG123",
            id_tag_info={
                "status": "Accepted",
                "expiryDate": past.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        assert entry.is_expired() is True

    def test_get_authorization_status_accepted(self):
        entry = AuthorizationEntry(
            id_tag="TAG123",
            id_tag_info={"status": "Accepted"},
        )
        assert entry.get_authorization_status() == AuthorizationStatus.accepted

    def test_get_authorization_status_blocked(self):
        entry = AuthorizationEntry(
            id_tag="TAG123",
            id_tag_info={"status": "Blocked"},
        )
        assert entry.get_authorization_status() == AuthorizationStatus.blocked

    def test_get_authorization_status_expired_by_date(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        entry = AuthorizationEntry(
            id_tag="TAG123",
            id_tag_info={"status": "Accepted", "expiryDate": past.isoformat()},
        )
        assert entry.get_authorization_status() == AuthorizationStatus.expired

    def test_get_authorization_status_invalid_status(self):
        entry = AuthorizationEntry(
            id_tag="TAG123",
            id_tag_info={"status": "InvalidStatus"},
        )
        assert entry.get_authorization_status() == AuthorizationStatus.invalid

    def test_get_authorization_status_no_status(self):
        entry = AuthorizationEntry(id_tag="TAG123", id_tag_info={})
        assert entry.get_authorization_status() == AuthorizationStatus.invalid


class TestLocalAuthListManager:
    def test_initial_state(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            assert manager.version == 0
            assert manager.entry_count == 0
            assert manager.enabled is False

    def test_full_update(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            entries = [
                {"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}},
                {"idTag": "TAG002", "idTagInfo": {"status": "Blocked"}},
            ]

            status, message = manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            assert status == UpdateStatus.accepted
            assert manager.version == 1
            assert manager.entry_count == 2

    def test_full_update_exceeds_max(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager(max_entries=2)
            entries = [
                {"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}},
                {"idTag": "TAG002", "idTagInfo": {"status": "Accepted"}},
                {"idTag": "TAG003", "idTagInfo": {"status": "Accepted"}},
            ]

            status, message = manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            assert status == UpdateStatus.failed
            assert "exceeds max entries" in message

    def test_full_update_clears_previous(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            entries = [
                {"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}},
                {"idTag": "TAG002", "idTagInfo": {"status": "Blocked"}},
            ]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            new_entries = [{"idTag": "TAG003", "idTagInfo": {"status": "Accepted"}}]
            manager.update_list(
                list_version=2,
                local_authorization_list=new_entries,
                update_type=UpdateType.full,
            )

            assert manager.entry_count == 1
            assert manager.version == 2

    def test_full_update_empty_list(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            status, message = manager.update_list(
                list_version=2,
                local_authorization_list=None,
                update_type=UpdateType.full,
            )

            assert status == UpdateStatus.accepted
            assert manager.entry_count == 0
            assert manager.version == 2

    def test_differential_update_add(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            diff_entries = [{"idTag": "TAG002", "idTagInfo": {"status": "Blocked"}}]
            status, message = manager.update_list(
                list_version=2,
                local_authorization_list=diff_entries,
                update_type=UpdateType.differential,
            )

            assert status == UpdateStatus.accepted
            assert manager.entry_count == 2
            assert manager.version == 2

    def test_differential_update_remove(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            manager.enabled = True
            entries = [
                {"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}},
                {"idTag": "TAG002", "idTagInfo": {"status": "Blocked"}},
            ]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            diff_entries = [{"idTag": "TAG001", "idTagInfo": None}]
            status, message = manager.update_list(
                list_version=2,
                local_authorization_list=diff_entries,
                update_type=UpdateType.differential,
            )

            assert status == UpdateStatus.accepted
            assert manager.entry_count == 1
            assert manager.authorize("TAG001") is None
            assert manager.authorize("TAG002") == AuthorizationStatus.blocked

    def test_differential_update_modify(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            manager.enabled = True
            entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            diff_entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Blocked"}}]
            status, message = manager.update_list(
                list_version=2,
                local_authorization_list=diff_entries,
                update_type=UpdateType.differential,
            )

            assert status == UpdateStatus.accepted
            assert manager.authorize("TAG001") == AuthorizationStatus.blocked

    def test_full_update_rejects_reserved_version_zero(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()

            status, message = manager.update_list(
                list_version=0,
                local_authorization_list=[],
                update_type=UpdateType.full,
            )

            assert status == UpdateStatus.failed
            assert "Reserved or invalid list version" in message
            assert manager.version == 0

    def test_full_update_rejects_reserved_version_minus_one(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()

            status, message = manager.update_list(
                list_version=-1,
                local_authorization_list=[],
                update_type=UpdateType.full,
            )

            assert status == UpdateStatus.failed
            assert "Reserved or invalid list version" in message
            assert manager.version == 0

    def test_differential_update_requires_next_version(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            manager.update_list(
                list_version=1,
                local_authorization_list=[
                    {"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}
                ],
                update_type=UpdateType.full,
            )

            status, message = manager.update_list(
                list_version=3,
                local_authorization_list=[
                    {"idTag": "TAG002", "idTagInfo": {"status": "Blocked"}}
                ],
                update_type=UpdateType.differential,
            )

            assert status == UpdateStatus.version_mismatch
            assert "Expected differential list version 2, got 3" in message
            assert manager.version == 1
            assert manager.entry_count == 1

    def test_authorize_when_disabled(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            manager.enabled = False
            entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            result = manager.authorize("TAG001")
            assert result is None

    def test_authorize_when_enabled(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            manager.enabled = True
            entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            result = manager.authorize("TAG001")
            assert result == AuthorizationStatus.accepted

    def test_authorize_unknown_tag(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            manager.enabled = True

            result = manager.authorize("UNKNOWN_TAG")
            assert result is None

    def test_authorize_expired_tag(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            manager.enabled = True
            past = datetime.now(timezone.utc) - timedelta(days=1)
            entries = [
                {
                    "idTag": "TAG001",
                    "idTagInfo": {"status": "Accepted", "expiryDate": past.isoformat()},
                }
            ]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            result = manager.authorize("TAG001")
            assert result == AuthorizationStatus.expired

    def test_get_id_tag_info(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            manager.enabled = True
            entries = [
                {
                    "idTag": "TAG001",
                    "idTagInfo": {"status": "Accepted", "parentIdTag": "PARENT1"},
                }
            ]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            info = manager.get_id_tag_info("TAG001")
            assert info == {"status": "Accepted", "parentIdTag": "PARENT1"}

    def test_get_id_tag_info_unknown(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            manager.enabled = True

            info = manager.get_id_tag_info("UNKNOWN_TAG")
            assert info is None

    def test_persistence(self, tmp_path):
        file_path = tmp_path / "local_auth_list.json"
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            file_path,
        ):
            manager = LocalAuthListManager()
            entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            assert file_path.exists()

            manager2 = LocalAuthListManager()
            assert manager2.version == 1
            assert manager2.entry_count == 1

    def test_clear(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            manager.clear()

            assert manager.version == 0
            assert manager.entry_count == 0

    def test_list_updated_event(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager()
            events = []

            def on_updated(version: int):
                events.append(version)

            manager.on_list_updated.subscribe(on_updated)

            entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            assert len(events) == 1
            assert events[0] == 1

    def test_differential_update_exceeds_max(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager(max_entries=2)
            entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            diff_entries = [
                {"idTag": "TAG002", "idTagInfo": {"status": "Accepted"}},
                {"idTag": "TAG003", "idTagInfo": {"status": "Accepted"}},
            ]
            status, message = manager.update_list(
                list_version=2,
                local_authorization_list=diff_entries,
                update_type=UpdateType.differential,
            )

            assert status == UpdateStatus.failed
            assert "exceeds max entries" in message

    def test_differential_update_rollback_on_max_exceeded(self, tmp_path):
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            tmp_path / "local_auth_list.json",
        ):
            manager = LocalAuthListManager(max_entries=2)
            manager.enabled = True
            entries = [
                {"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}},
                {"idTag": "TAG002", "idTagInfo": {"status": "Blocked"}},
            ]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            original_count = manager.entry_count
            original_version = manager.version

            diff_entries = [
                {"idTag": "TAG001", "idTagInfo": {"status": "Blocked"}},
                {"idTag": "TAG003", "idTagInfo": {"status": "Accepted"}},
            ]
            status, message = manager.update_list(
                list_version=2,
                local_authorization_list=diff_entries,
                update_type=UpdateType.differential,
            )

            assert status == UpdateStatus.failed
            assert manager.entry_count == original_count
            assert manager.version == original_version
            assert manager.authorize("TAG001") == AuthorizationStatus.accepted
            assert manager.authorize("TAG002") == AuthorizationStatus.blocked

    def test_enabled_state_not_persisted(self, tmp_path):
        file_path = tmp_path / "local_auth_list.json"
        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            file_path,
        ):
            manager = LocalAuthListManager()
            manager.enabled = True
            entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}]
            manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            assert file_path.exists()

            manager2 = LocalAuthListManager()
            assert manager2.enabled is False

    def test_load_resets_on_corrupted_file(self, tmp_path):
        file_path = tmp_path / "local_auth_list.json"
        file_path.write_text("{ invalid json }")

        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            file_path,
        ):
            manager = LocalAuthListManager()
            assert manager.version == 0
            assert manager.entry_count == 0

    def test_save_failure_returns_error(self, tmp_path):
        file_path = tmp_path / "readonly" / "local_auth_list.json"
        file_path.parent.mkdir(parents=True)

        with patch(
            "chargeghost_evse.ocpp_adapter.local_auth_list.LOCAL_AUTH_LIST_FILE",
            file_path,
        ):
            manager = LocalAuthListManager()
            file_path.parent.chmod(0o444)

            entries = [{"idTag": "TAG001", "idTagInfo": {"status": "Accepted"}}]
            status, message = manager.update_list(
                list_version=1,
                local_authorization_list=entries,
                update_type=UpdateType.full,
            )

            assert status == UpdateStatus.failed
            assert "Failed to save" in message

            file_path.parent.chmod(0o755)
