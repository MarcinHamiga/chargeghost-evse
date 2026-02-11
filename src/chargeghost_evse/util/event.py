from collections.abc import Callable
import weakref

class Event:
	def __init__(self):
		self.callbacks: list[weakref.ref] = []

	def subscribe(self, callback: Callable) -> Callable:
		if hasattr(callback, "__self__") and hasattr(callback, "__func__"):
			ref = weakref.WeakMethod(callback)
		else:
			ref = weakref.ref(callback)
		
		self.callbacks.append(ref)
		return lambda: self.unsubscribe(ref)

	def unsubscribe(self, ref: weakref.ref) -> None:
		if ref in self.callbacks:
			self.callbacks.remove(ref)

	def emit(self, *args, **kwargs) -> None:
		for ref in list(self.callbacks):
			callback = ref()
			if callback is not None:
				callback(*args, **kwargs)
			else:
				self.callbacks.remove(ref)
