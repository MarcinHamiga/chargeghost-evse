from collections.abc import Callable
import threading
import weakref


class Event:
    def __init__(self):
        self.callbacks: list[weakref.ReferenceType[Callable]] = []
        self._lock = threading.Lock()

    def subscribe(self, callback: Callable) -> Callable:
        if hasattr(callback, "__self__") and hasattr(callback, "__func__"):
            ref: weakref.ReferenceType[Callable] = weakref.WeakMethod(callback)
        else:
            ref = weakref.ref(callback)

        with self._lock:
            self.callbacks.append(ref)
        return lambda: self.unsubscribe(ref)

    def unsubscribe(self, ref: weakref.ReferenceType[Callable]) -> None:
        with self._lock:
            if ref in self.callbacks:
                self.callbacks.remove(ref)

    def emit(self, *args, **kwargs) -> None:
        dead_refs: list[weakref.ReferenceType[Callable]] = []
        with self._lock:
            callbacks_snapshot = list(self.callbacks)

        for ref in callbacks_snapshot:
            callback = ref()
            if callback is not None:
                callback(*args, **kwargs)
            else:
                dead_refs.append(ref)

        if dead_refs:
            with self._lock:
                for ref in dead_refs:
                    if ref in self.callbacks:
                        self.callbacks.remove(ref)
