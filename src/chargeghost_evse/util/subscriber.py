"""
Subscriber Pattern Module.

This module provides a base class for objects that need to subscribe to
multiple events and automatically clean up subscriptions when destroyed.
It implements a simplified RAII pattern for event subscription management.

Classes:
    Subscriber: Base class providing subscription tracking and cleanup.

Example:
    >>> from chargeghost_evse.util.event import Event
    >>> from chargeghost_evse.util.subscriber import Subscriber
    >>>
    >>> class MyComponent(Subscriber):
    ...     def __init__(self, event: Event):
    ...         super().__init__()
    ...         self.subscribe_to(event, self.handle_event)
    ...
    ...     def handle_event(self, value: str):
    ...         print(f"Got: {value}")
    ...
    ...     def close(self):
    ...         # Clean up subscriptions
    ...         super().close()
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chargeghost_evse.util.event import Event


class Subscriber:
    """
    Base class for objects that subscribe to events.

    Provides automatic tracking of event subscriptions and cleanup when
    the object is destroyed or close() is called. This prevents memory
    leaks from dangling event subscriptions.

    Usage:
        1. Inherit from Subscriber
        2. Call subscribe_to() to register callbacks
        3. Call unsubscribe_from() to remove specific subscriptions
        4. Call unsubscribe_all() or close() to remove all subscriptions

    Context Manager:
        Can be used as a context manager for automatic cleanup:

        >>> with MyComponent(event) as component:
        ...     component.do_work()
        # Subscriptions automatically cleaned up

    Attributes:
        _subscriptions: Dictionary mapping Events to lists of unsubscribe
            functions for tracking active subscriptions.

    Example:
        >>> class Sensor(Subscriber):
        ...     def __init__(self, update_event: Event):
        ...         super().__init__()
        ...         self.subscribe_to(update_event, self.on_update)
        ...
        ...     def on_update(self, value: float):
        ...         print(f"Sensor update: {value}")
        ...
        ...     def stop_listening(self):
        ...         # Optionally clean up early
        ...         self.unsubscribe_all()
    """

    def __init__(self) -> None:
        """
        Initialize a subscriber with no active subscriptions.
        """
        self._subscriptions: dict["Event", list[Callable]] = {}

    def subscribe_to(self, event: "Event", callback: Callable) -> None:
        """
        Subscribe to an event and track the subscription.

        The subscription is automatically tracked for later cleanup.
        Multiple callbacks can be subscribed to the same event.

        Args:
            event: The Event instance to subscribe to.
            callback: The callback function to invoke when the event emits.
        """
        unsub = event.subscribe(callback)
        if event not in self._subscriptions:
            self._subscriptions[event] = []
        self._subscriptions[event].append(unsub)

    def unsubscribe_from(self, event: "Event") -> None:
        """
        Unsubscribe all callbacks from a specific event.

        Removes all callbacks that were registered via subscribe_to()
        for the given event.

        Args:
            event: The Event instance to unsubscribe from.
        """
        if event in self._subscriptions:
            for unsub in self._subscriptions[event]:
                unsub()
            del self._subscriptions[event]

    def unsubscribe_all(self) -> None:
        """
        Unsubscribe from all tracked events.

        Removes all callbacks from all events that were registered
        via subscribe_to(). This is safe to call multiple times.
        """
        for unsubs in list(self._subscriptions.values()):
            for unsub in unsubs:
                unsub()
        self._subscriptions.clear()

    def close(self) -> None:
        """
        Close the subscriber and clean up all subscriptions.

        This method can be overridden by subclasses to perform
        additional cleanup. Always call super().close() in overrides.
        """
        self.unsubscribe_all()

    def __enter__(self) -> "Subscriber":
        """
        Enter context manager.

        Returns:
            Self for use in with statements.
        """
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """
        Exit context manager and clean up subscriptions.

        Args:
            exc_type: Exception type if an exception was raised, else None.
            exc: Exception instance if an exception was raised, else None.
            tb: Traceback if an exception was raised, else None.
        """
        self.close()

    def __del__(self) -> None:
        """
        Destructor to ensure subscriptions are cleaned up.

        Called when the object is garbage collected. Ensures that
        subscriptions are removed even if close() was not called.
        """
        self.unsubscribe_all()
