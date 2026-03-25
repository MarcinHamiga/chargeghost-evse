from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class Reservation:
    reservation_id: int
    connector_id: int
    id_tag: str
    expiry_date: datetime
    parent_id_tag: Optional[str] = None

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        current_time = now or datetime.now(timezone.utc)
        expiry_date = self.expiry_date
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)
        return current_time >= expiry_date
