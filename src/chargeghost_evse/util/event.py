"""
Event System Module.

This module provides a thread-safe implementation of the Observer pattern
using weak references for automatic cleanup of deleted subscribers.

The Event class allows objects to emit events that multiple subscribers
can listen to, without creating strong references that would prevent
garbage collection of subscribers.

Classes:
    Event: Thread-safe event emitter with weak reference support.

Example:
    >>> from chargeghost_evse.util.event import Event
    >>>
    >>> class TemperatureSensor:
    ...     def __init__(self):
    ...         self.on_reading = Event()
    ...
    ...     def read(self, temp: float):
    ...         self.on_reading.emit(temperature=temp)
    >>>
    >>> sensor = TemperatureSensor()
    >>> sensor.on_reading.subscribe(lambda temperature: print(f"Temp: {temperature}°C"))
    >>> sensor.read(23.5)
    Temp: 23.5°C
"""

from collections.abc import Callable
import threading
import weakref


class Event:
    """
    Thread-safe event emitter using weak references for subscriber management.

    Events allow multiple callbacks to subscribe to notifications. When the
    event is emitted, all subscribed callbacks are invoked with the provided
    arguments. Uses weak references to automatically clean up callbacks when
    their owning objects are garbage collected.

    Thread Safety:
        All operations (subscribe, unsubscribe, emit) are thread-safe using
        an internal lock. Callbacks are invoked outside the lock to prevent
        deadlocks.

    Memory Management:
        - Uses WeakMethod for bound methods to avoid keeping objects alive
        - Uses weakref.ref for free functions
        - Dead references are cleaned up during emit()

    Attributes:
        callbacks: List of weak references to subscribed callbacks.

    Example:
        >>> event = Event()
        >>>
        >>> class Handler:
        ...     def on_event(self, value: int):
        ...         print(f"Received: {value}")
        >>>
        >>> handler = Handler()
        >>> event.subscribe(handler.on_event)
        >>> event.emit(value=42)  # Prints: Received: 42
    """

    def __init__(self) -> None:
        """
        Initialize an empty event with no subscribers.
        """
        self.callbacks: list[weakref.ReferenceType[Callable]] = []
        self._lock = threading.Lock()

    def subscribe(self, callback: Callable) -> Callable:
        """
        Subscribe a callback to this event.

        The callback will be invoked whenever emit() is called. Uses weak
        references to allow the callback's owner to be garbage collected.

        Args:
            callback: Function or method to call when the event is emitted.
                For bound methods, uses WeakMethod to avoid circular references.

        Returns:
            Unsubscribe function that can be called to remove this callback.
            The returned function takes no arguments and returns None.

        Example:
            >>> event = Event()
            >>> unsub = event.subscribe(lambda x: print(x))
            >>> event.emit(x="hello")
            hello
            >>> unsub()  # Remove the subscription
        """
        # Use WeakMethod for bound methods to avoid keeping objects alive
        if hasattr(callback, "__self__") and hasattr(callback, "__func__"):
            ref: weakref.ReferenceType[Callable] = weakref.WeakMethod(callback)
        else:
            # Use regular weakref for free functions
            ref = weakref.ref(callback)

        with self._lock:
            self.callbacks.append(ref)

        # Return unsubscribe function for convenience
        return lambda: self.unsubscribe(ref)

    def unsubscribe(self, ref: weakref.ReferenceType[Callable]) -> None:
        """
        Remove a callback reference from the subscriber list.

        Args:
            ref: Weak reference to the callback to remove, as returned
                from subscribe() or captured in the unsubscribe function.
        """
        with self._lock:
            if ref in self.callbacks:
                self.callbacks.remove(ref)

    def emit(self, *args, **kwargs) -> None:
        """
        Emit the event, invoking all subscribed callbacks.

        All callbacks are invoked with the provided arguments. Dead references
        (callbacks whose owners have been garbage collected) are automatically
        removed from the subscriber list.

        Note:
            Callbacks are invoked outside the lock to prevent deadlocks if
            a callback tries to modify subscriptions. This means callbacks
            may be invoked even after unsubscribing if emit() is in progress.

        Args:
            *args: Positional arguments passed to all callbacks.
            **kwargs: Keyword arguments passed to all callbacks.
        """
        dead_refs: list[weakref.ReferenceType[Callable]] = []

        # Snapshot callbacks under lock to minimize lock time
        with self._lock:
            callbacks_snapshot = list(self.callbacks)

        # Invoke callbacks outside the lock
        for ref in callbacks_snapshot:
            callback = ref()
            if callback is not None:
                callback(*args, **kwargs)
            else:
                # Reference is dead (object was garbage collected)
                dead_refs.append(ref)

        # Clean up dead references
        if dead_refs:
            with self._lock:
                for ref in dead_refs:
                    if ref in self.callbacks:
                        self.callbacks.remove(ref)
