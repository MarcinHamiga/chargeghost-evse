import copy
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ocpp.v201.datatypes import AuthorizationData, IdTokenInfoType, IdTokenType
from ocpp.v201.enums import (
    AuthorizationStatusEnumType,
    SendLocalListStatusEnumType,
    UpdateEnumType,
)

from chargeghost_evse.util.event import Event


LOCAL_AUTH_LIST_FILE = Path.home() / ".chargeghost" / "local_auth_list_v201.json"

_logger = logging.getLogger("chargeghost.local_auth_list_v201")


def _is_expired(info: Optional[IdTokenInfoType]) -> bool:
    if info is None or info.cache_expiry_date_time is None:
        return False
    try:
        date_str = info.cache_expiry_date_time
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"
        expiry_date = datetime.fromisoformat(date_str)
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expiry_date
    except (ValueError, TypeError, AttributeError):
        return False


def _get_authorization_status(
    info: Optional[IdTokenInfoType],
) -> AuthorizationStatusEnumType:
    if info is None:
        return AuthorizationStatusEnumType.invalid
    if _is_expired(info):
        return AuthorizationStatusEnumType.expired
    if isinstance(info.status, AuthorizationStatusEnumType):
        return info.status
    try:
        return AuthorizationStatusEnumType(info.status)
    except (ValueError, TypeError):
        return AuthorizationStatusEnumType.invalid


class LocalAuthListManagerV201:
    def __init__(
        self, max_entries: int = 100, *, _file_path: Optional[Path] = None
    ) -> None:
        self._lock = threading.RLock()
        self._max_entries: int = max_entries
        self._version: int = 0
        self._hash: Optional[str] = None
        self._entries: dict[tuple[str, str], AuthorizationData] = {}
        self._enabled: bool = False
        self._file_path: Path = _file_path or LOCAL_AUTH_LIST_FILE
        self.on_list_changed: Event = Event()
        self._load()

    def _entry_key(self, id_token: IdTokenType) -> tuple[str, str]:
        type_str = (
            id_token.type.value
            if hasattr(id_token.type, "value")
            else str(id_token.type)
        )
        return (id_token.id_token, type_str)

    def _load(self) -> None:
        if not self._file_path.exists():
            return
        try:
            with open(self._file_path, "r") as f:
                data = json.load(f)
            self._version = data.get("version", 0)
            self._hash = data.get("hash")
            self._entries = {}
            for key_str, entry_data in data.get("entries", {}).items():
                parts = key_str.split("|", 1)
                if len(parts) != 2:
                    continue
                id_token_str, type_str = parts
                token = IdTokenType(id_token=id_token_str, type=type_str)
                info_data = entry_data.get("id_token_info")
                if info_data is not None:
                    status = info_data.get("status", "Accepted")
                    info = IdTokenInfoType(
                        status=status,
                        cache_expiry_date_time=info_data.get("cache_expiry_date_time"),
                        charging_priority=info_data.get("charging_priority"),
                        language_1=info_data.get("language_1"),
                        language_2=info_data.get("language_2"),
                    )
                    auth_data = AuthorizationData(id_token=token, id_token_info=info)
                else:
                    auth_data = AuthorizationData(id_token=token, id_token_info=None)
                self._entries[(id_token_str, type_str)] = auth_data
        except (json.JSONDecodeError, TypeError):
            self._entries = {}
            self._version = 0
            self._hash = None
            _logger.warning("Corrupted auth list file, reset to empty")

    def _save(self) -> tuple[bool, str]:
        try:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            entries: dict[str, dict] = {}
            for (id_token_str, type_str), auth_data in self._entries.items():
                key = f"{id_token_str}|{type_str}"
                if auth_data.id_token_info is not None:
                    info = auth_data.id_token_info
                    entries[key] = {
                        "id_token_info": {
                            "status": (
                                info.status.value
                                if hasattr(info.status, "value")
                                else str(info.status)
                            ),
                            "cache_expiry_date_time": info.cache_expiry_date_time,
                            "charging_priority": info.charging_priority,
                            "language_1": info.language_1,
                            "language_2": info.language_2,
                        }
                    }
                else:
                    entries[key] = {}
            data: dict = {
                "version": self._version,
                "hash": self._hash,
                "entries": entries,
            }
            with open(self._file_path, "w") as f:
                json.dump(data, f, indent=2)
            return True, "Saved successfully"
        except OSError as e:
            return False, f"Failed to save auth list: {e}"

    @property
    def version(self) -> int:
        return self._version

    @property
    def hash(self) -> Optional[str]:
        return self._hash

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @max_entries.setter
    def max_entries(self, value: int) -> None:
        self._max_entries = value

    def send_local_list(
        self,
        list_version: int,
        local_authorization_list: Optional[list[AuthorizationData]],
        update_type: UpdateEnumType,
        remote_hash: Optional[str] = None,
    ) -> tuple[SendLocalListStatusEnumType, str]:
        with self._lock:
            if list_version <= 0:
                return (
                    SendLocalListStatusEnumType.failed,
                    "Invalid list version",
                )

            if update_type == UpdateEnumType.full:
                return self._handle_full_update(
                    list_version, local_authorization_list, remote_hash
                )
            else:
                return self._handle_differential_update(
                    list_version, local_authorization_list, remote_hash
                )

    def _handle_full_update(
        self,
        list_version: int,
        local_authorization_list: Optional[list[AuthorizationData]],
        remote_hash: Optional[str],
    ) -> tuple[SendLocalListStatusEnumType, str]:
        if local_authorization_list is None:
            self._entries.clear()
            self._version = list_version
            self._hash = remote_hash
            saved, save_msg = self._save()
            if not saved:
                return SendLocalListStatusEnumType.failed, save_msg
            self.on_list_changed.emit(version=self._version)
            return (
                SendLocalListStatusEnumType.accepted,
                "Full update completed (cleared list)",
            )

        new_entries_count = len(local_authorization_list)
        if new_entries_count > self._max_entries:
            return (
                SendLocalListStatusEnumType.failed,
                f"List exceeds max entries ({new_entries_count} > {self._max_entries})",
            )

        self._entries.clear()
        for auth_data in local_authorization_list:
            if auth_data.id_token is None:
                continue
            key = self._entry_key(auth_data.id_token)
            self._entries[key] = auth_data

        self._version = list_version
        self._hash = remote_hash
        saved, save_msg = self._save()
        if not saved:
            return SendLocalListStatusEnumType.failed, save_msg
        self.on_list_changed.emit(version=self._version)
        return (
            SendLocalListStatusEnumType.accepted,
            f"Full update completed ({len(self._entries)} entries)",
        )

    def _handle_differential_update(
        self,
        list_version: int,
        local_authorization_list: Optional[list[AuthorizationData]],
        remote_hash: Optional[str],
    ) -> tuple[SendLocalListStatusEnumType, str]:
        expected_version = self._version + 1
        if list_version != expected_version:
            return (
                SendLocalListStatusEnumType.version_mismatch,
                f"Expected version {expected_version}, got {list_version}",
            )

        if local_authorization_list is None:
            self._version = list_version
            self._hash = remote_hash
            saved, save_msg = self._save()
            if not saved:
                return SendLocalListStatusEnumType.failed, save_msg
            self.on_list_changed.emit(version=self._version)
            return (
                SendLocalListStatusEnumType.accepted,
                "Differential update completed (no changes)",
            )

        original_entries = copy.deepcopy(self._entries)
        original_version = self._version

        for auth_data in local_authorization_list:
            if auth_data.id_token is None:
                continue

            key = self._entry_key(auth_data.id_token)

            if auth_data.id_token_info is None:
                if key in self._entries:
                    del self._entries[key]
            else:
                if len(self._entries) >= self._max_entries and key not in self._entries:
                    self._entries = original_entries
                    self._version = original_version
                    return (
                        SendLocalListStatusEnumType.failed,
                        f"List exceeds max entries ({self._max_entries})",
                    )
                self._entries[key] = auth_data

        self._version = list_version
        self._hash = remote_hash
        saved, save_msg = self._save()
        if not saved:
            self._entries = original_entries
            self._version = original_version
            return SendLocalListStatusEnumType.failed, save_msg
        self.on_list_changed.emit(version=self._version)
        return (
            SendLocalListStatusEnumType.accepted,
            f"Differential update completed ({len(self._entries)} entries)",
        )

    def get_local_list_version(self) -> int:
        return self._version

    def find_entry(self, id_token: str, token_type: str) -> Optional[AuthorizationData]:
        if not self._enabled:
            return None
        return self._entries.get((id_token, token_type))

    def clear_cache(self) -> tuple[bool, str]:
        with self._lock:
            self._entries.clear()
            self._version = 0
            self._hash = None
            saved, save_msg = self._save()
            if saved:
                self.on_list_changed.emit(version=self._version)
            return saved, save_msg

    def authorize(
        self, id_token: str, token_type: str
    ) -> Optional[AuthorizationStatusEnumType]:
        if not self._enabled:
            return None
        entry = self._entries.get((id_token, token_type))
        if entry is None:
            return None
        return _get_authorization_status(entry.id_token_info)
