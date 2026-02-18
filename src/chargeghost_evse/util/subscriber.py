from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chargeghost_evse.util.event import Event


class Subscriber:
    def __init__(self):
        self._subscriptions: dict["Event", list[Callable]] = {}

    def subscribe_to(self, event: "Event", callback: Callable) -> None:
        unsub = event.subscribe(callback)
        if event not in self._subscriptions:
            self._subscriptions[event] = []
        self._subscriptions[event].append(unsub)

    def unsubscribe_from(self, event: "Event") -> None:
        if event in self._subscriptions:
            for unsub in self._subscriptions[event]:
                unsub()
            del self._subscriptions[event]

    def unsubscribe_all(self) -> None:
        for unsubs in list(self._subscriptions.values()):
            for unsub in unsubs:
                unsub()
        self._subscriptions.clear()

    def close(self) -> None:
        self.unsubscribe_all()

    def __enter__(self) -> "Subscriber":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self):
        self.unsubscribe_all()
