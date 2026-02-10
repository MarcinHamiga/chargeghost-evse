from collections.abc import Callable

class Event:
	def __init__(self):
		self.callbacks: list[Callable] = []

	def subscribe(self, callback: Callable) -> Callable:
		self.callbacks.append(callback)
		return lambda: self.unsubscribe(callback)

	def unsubscribe(self, callback: Callable) -> None:
		self.callbacks.remove(callback)

	def emit(self, *args, **kwargs) -> None:
		for callback in self.callbacks:
			callback(*args, **kwargs)