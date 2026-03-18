from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Optional


class AuthorizationCacheManager:
	def __init__(self) -> None:
		self._entries: dict[str, dict] = {}
		self._lock = RLock()

	def get(self, id_tag: str) -> Optional[dict]:
		with self._lock:
			entry = self._entries.get(id_tag)
			if entry is None:
				return None
			if self._is_expired(entry):
				del self._entries[id_tag]
				return None
			return deepcopy(entry)

	def put(self, id_tag: str, id_tag_info: Optional[dict]) -> None:
		if id_tag_info is None:
			return
		with self._lock:
			self._entries[id_tag] = deepcopy(id_tag_info)

	def clear(self) -> None:
		with self._lock:
			self._entries.clear()

	@staticmethod
	def _is_expired(id_tag_info: dict) -> bool:
		expiry_date_str = id_tag_info.get("expiryDate")
		if not expiry_date_str:
			return False

		try:
			if expiry_date_str.endswith("Z"):
				expiry_date_str = expiry_date_str[:-1] + "+00:00"
			expiry_date = datetime.fromisoformat(expiry_date_str)
			if expiry_date.tzinfo is None:
				expiry_date = expiry_date.replace(tzinfo=timezone.utc)
		except (TypeError, ValueError, AttributeError):
			return False

		return datetime.now(timezone.utc) > expiry_date
