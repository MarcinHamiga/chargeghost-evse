import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ocpp.v16.enums import AuthorizationStatus, UpdateType

from chargeghost_evse.util.event import Event
from chargeghost_evse.util.subscriber import Subscriber


LOCAL_AUTH_LIST_FILE = Path.home() / ".chargeghost" / "local_auth_list.json"


@dataclass
class AuthorizationEntry:
    id_tag: str
    id_tag_info: dict = field(default_factory=dict)

    def is_expired(self) -> bool:
        expiry_date_str = self.id_tag_info.get("expiryDate")
        if not expiry_date_str:
            return False
        try:
            if expiry_date_str.endswith("Z"):
                expiry_date_str = expiry_date_str[:-1] + "+00:00"
            expiry_date = datetime.fromisoformat(expiry_date_str)
            if expiry_date.tzinfo is None:
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) > expiry_date
        except (ValueError, TypeError, AttributeError):
            return False

    def get_authorization_status(self) -> AuthorizationStatus:
        if self.is_expired():
            return AuthorizationStatus.expired
        status_str = self.id_tag_info.get("status", "")
        try:
            return AuthorizationStatus(status_str)
        except ValueError:
            return AuthorizationStatus.invalid


class LocalAuthListManager(Subscriber):
    def __init__(self, max_entries: int = 100) -> None:
        super().__init__()
        self._max_entries: int = max_entries
        self._version: int = 0
        self._entries: dict[str, AuthorizationEntry] = {}
        self._enabled: bool = False
        self.on_list_updated: Event = Event()
        self.on_load_error: Event = Event()
        self._load()

    def _load(self) -> None:
        if not LOCAL_AUTH_LIST_FILE.exists():
            return
        try:
            with open(LOCAL_AUTH_LIST_FILE, "r") as f:
                data = json.load(f)
            self._version = data.get("version", 0)
            entries_data = data.get("entries", {})
            self._entries = {}
            for id_tag, entry_data in entries_data.items():
                self._entries[id_tag] = AuthorizationEntry(
                    id_tag=id_tag,
                    id_tag_info=entry_data.get("idTagInfo", {}),
                )
        except (json.JSONDecodeError, TypeError):
            self._entries = {}
            self._version = 0
            self.on_load_error.emit(message="Corrupted auth list file, reset to empty")

    def _save(self) -> tuple[bool, str]:
        try:
            LOCAL_AUTH_LIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": self._version,
                "entries": {
                    id_tag: {"idTagInfo": entry.id_tag_info}
                    for id_tag, entry in self._entries.items()
                },
            }
            with open(LOCAL_AUTH_LIST_FILE, "w") as f:
                json.dump(data, f, indent=2)
            return True, "Saved successfully"
        except OSError as e:
            return False, f"Failed to save auth list: {e}"

    @property
    def version(self) -> int:
        return self._version

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

    def update_list(
        self,
        list_version: int,
        local_authorization_list: Optional[list[dict]],
        update_type: UpdateType,
    ) -> tuple[bool, str]:
        if update_type == UpdateType.full:
            return self._handle_full_update(list_version, local_authorization_list)
        else:
            return self._handle_differential_update(
                list_version, local_authorization_list
            )

    def _handle_full_update(
        self, list_version: int, local_authorization_list: Optional[list[dict]]
    ) -> tuple[bool, str]:
        if local_authorization_list is None:
            self._entries.clear()
            self._version = list_version
            saved, save_msg = self._save()
            if not saved:
                return False, save_msg
            self.on_list_updated.emit(version=self._version)
            return True, "Full update completed (cleared list)"

        new_entries_count = len(local_authorization_list)
        if new_entries_count > self._max_entries:
            return (
                False,
                f"List exceeds max entries ({new_entries_count} > {self._max_entries})",
            )

        self._entries.clear()
        for entry_data in local_authorization_list:
            id_tag = entry_data.get("idTag")
            if not id_tag:
                continue
            self._entries[id_tag] = AuthorizationEntry(
                id_tag=id_tag,
                id_tag_info=entry_data.get("idTagInfo", {}),
            )

        self._version = list_version
        saved, save_msg = self._save()
        if not saved:
            return False, save_msg
        self.on_list_updated.emit(version=self._version)
        return True, f"Full update completed ({len(self._entries)} entries)"

    def _handle_differential_update(
        self, list_version: int, local_authorization_list: Optional[list[dict]]
    ) -> tuple[bool, str]:
        if local_authorization_list is None:
            self._version = list_version
            saved, save_msg = self._save()
            if not saved:
                return False, save_msg
            self.on_list_updated.emit(version=self._version)
            return True, "Differential update completed (no changes)"

        original_entries = copy.deepcopy(self._entries)
        original_version = self._version

        for entry_data in local_authorization_list:
            id_tag = entry_data.get("idTag")
            if not id_tag:
                continue

            id_tag_info = entry_data.get("idTagInfo")
            if id_tag_info is None:
                if id_tag in self._entries:
                    del self._entries[id_tag]
            else:
                if (
                    len(self._entries) >= self._max_entries
                    and id_tag not in self._entries
                ):
                    self._entries = original_entries
                    self._version = original_version
                    return False, f"List exceeds max entries ({self._max_entries})"
                self._entries[id_tag] = AuthorizationEntry(
                    id_tag=id_tag,
                    id_tag_info=id_tag_info,
                )

        self._version = list_version
        saved, save_msg = self._save()
        if not saved:
            self._entries = original_entries
            self._version = original_version
            return False, save_msg
        self.on_list_updated.emit(version=self._version)
        return True, f"Differential update completed ({len(self._entries)} entries)"

    def authorize(self, id_tag: str) -> Optional[AuthorizationStatus]:
        if not self._enabled:
            return None

        entry = self._entries.get(id_tag)
        if entry is None:
            return None

        return entry.get_authorization_status()

    def get_id_tag_info(self, id_tag: str) -> Optional[dict]:
        if not self._enabled:
            return None

        entry = self._entries.get(id_tag)
        if entry is None:
            return None

        if entry.is_expired():
            return {"status": AuthorizationStatus.expired.value}

        return entry.id_tag_info.copy()

    def clear(self) -> tuple[bool, str]:
        self._entries.clear()
        self._version = 0
        saved, save_msg = self._save()
        if saved:
            self.on_list_updated.emit(version=self._version)
        return saved, save_msg
