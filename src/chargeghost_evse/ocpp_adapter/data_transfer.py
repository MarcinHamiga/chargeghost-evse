from collections.abc import Callable
from typing import Optional

from ocpp.v16.enums import DataTransferStatus


Handler = Callable[[Optional[str]], tuple[DataTransferStatus, Optional[str]]]


class DataTransferRegistry:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], Handler] = {}

    def register(self, vendor_id: str, message_id: str, handler: Handler) -> None:
        self._handlers[(vendor_id, message_id)] = handler

    def handle(
        self,
        vendor_id: str,
        message_id: Optional[str],
        data: Optional[str],
    ) -> tuple[DataTransferStatus, Optional[str]]:
        has_vendor = any(
            key_vendor_id == vendor_id for key_vendor_id, _ in self._handlers
        )
        if not has_vendor:
            return DataTransferStatus.unknown_vendor_id, None

        if message_id is None:
            return DataTransferStatus.unknown_message_id, None

        handler = self._handlers.get((vendor_id, message_id))
        if handler is None:
            return DataTransferStatus.unknown_message_id, None

        return handler(data)
