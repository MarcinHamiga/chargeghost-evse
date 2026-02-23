import threading
from chargeghost_evse.util.event import Event


class TestEvent:
	def test_subscribe_and_emit(self):
		event = Event()
		results = []
		
		def callback(value):
			results.append(value)
		
		event.subscribe(callback)
		event.emit(value=1)
		event.emit(value=2)
		
		assert results == [1, 2]

	def test_multiple_subscribers(self):
		event = Event()
		results1 = []
		results2 = []
		
		cb1 = lambda x: results1.append(x)
		cb2 = lambda x: results2.append(x)
		event.subscribe(cb1)
		event.subscribe(cb2)
		event.emit(x="test")
		
		assert results1 == ["test"]
		assert results2 == ["test"]

	def test_unsubscribe(self):
		event = Event()
		results = []
		
		def callback(value):
			results.append(value)
		
		unsub = event.subscribe(callback)
		event.emit(value=1)
		unsub()
		event.emit(value=2)
		
		assert results == [1]

	def test_emit_with_kwargs(self):
		event = Event()
		results = []
		
		def callback(a, b):
			results.append((a, b))
		
		event.subscribe(callback)
		event.emit(a=1, b=2)
		
		assert results == [(1, 2)]

	def test_emit_with_args(self):
		event = Event()
		results = []
		
		def callback(a, b):
			results.append((a, b))
		
		event.subscribe(callback)
		event.emit(1, 2)
		
		assert results == [(1, 2)]

	def test_thread_safety(self):
		event = Event()
		results = []
		lock = threading.Lock()
		
		def callback(value):
			with lock:
				results.append(value)
		
		event.subscribe(callback)
		
		threads = []
		for i in range(100):
			t = threading.Thread(target=event.emit, kwargs={"value": i})
			threads.append(t)
			t.start()
		
		for t in threads:
			t.join()
		
		assert len(results) == 100
		assert set(results) == set(range(100))

	def test_dead_reference_cleanup(self):
		event = Event()
		
		def create_callback():
			data = [1, 2, 3]
			return lambda: data
		
		callback = create_callback()
		event.subscribe(callback)
		del callback
		
		event.emit()
		assert len(event.callbacks) == 0

	def test_method_subscription(self):
		class Handler:
			def __init__(self):
				self.results = []
			
			def on_event(self, value):
				self.results.append(value)
		
		event = Event()
		handler = Handler()
		event.subscribe(handler.on_event)
		event.emit(value=42)
		
		assert handler.results == [42]
