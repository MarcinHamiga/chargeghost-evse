import asyncio
import threading
import time
import websockets
from datetime import datetime, timezone
from chargeghost_evse.util.event import Event
from chargeghost_evse.ocpp_adapter.adapter import Adapter
from chargeghost_evse.engine.engine import Engine

class AsyncRunner:
    def __init__(self, charge_point_id: str, url: str, command_queue):
        self.charge_point_id = charge_point_id
        self.url = url
        self.command_queue = command_queue
        self.loop = None
        self.adapter = None
        self.on_log = Event()

    def _log(self, message):
        self.on_log.emit(message)

    def run_in_thread(self):
        thread = threading.Thread(target=self._start_loop, daemon=True)
        thread.start()

    def _start_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        self.loop.run_until_complete(self._run_adapter())

    async def _run_adapter(self):
        retry_delay = 1
        while True:
            try:
                self._log(f"AsyncRunner: Connecting to {self.url}...")
                async with websockets.connect(
                    self.url, subprotocols=["ocpp1.6"]
                ) as ws:
                    self.adapter = Adapter(self.charge_point_id, ws, command_queue=self.command_queue)
                    self.adapter.on_log.subscribe(self._log)
                    self._log(f"AsyncRunner: Connected. Starting Adapter...")
                    
                    # Start the adapter and send boot notification
                    await asyncio.gather(
                        self.adapter.start(),
                        self.adapter.send_boot_notification()
                    )
            except (websockets.ConnectionClosed, ConnectionRefusedError, Exception) as e:
                self._log(f"AsyncRunner: Connection error: {e}. Retrying in {retry_delay}s...")
                self.adapter = None
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60) # Exponential backoff

class Bridge:
    def __init__(self, engine: Engine, url: str = "ws://localhost:3000/CP_1"):
        self.engine = engine
        self.url = url
        self.runner = AsyncRunner("CP_1", url, engine.command_queue)
        self.on_log = self.runner.on_log

    def setup(self):
        # Subscribe to Engine events
        self.engine.session_started.subscribe(self.on_engine_start)
        self.engine.session_stopped.subscribe(self.on_engine_stop)
        self.engine.connector_status_changed.subscribe(self.on_connector_status_change)
        
        # Start the adapter thread
        self.runner.run_in_thread()
        
        # Start meter values loop
        threading.Thread(target=self._meter_values_loop, daemon=True).start()

    def _meter_values_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while True:
            if self.engine.session and self.engine.energy_meter.is_charging:
                if self.runner.adapter and self.runner.loop:
                     asyncio.run_coroutine_threadsafe(
                        self.runner.adapter.send_meter_values(
                            connector_id=self.engine.session.connector_id,
                            value=self.engine.energy_meter.get_meter_reading()
                        ),
                        self.runner.loop
                    )
            time.sleep(10) # Send every 10 seconds

    def _log(self, message):
        self.on_log.emit(message)

    def on_connector_status_change(self, connector_id, status):
        if self.runner.adapter and self.runner.loop:
            self._log(f"Bridge: Connector {connector_id} status changed to {status.value}")
            asyncio.run_coroutine_threadsafe(
                self.runner.adapter.send_status_notification(
                    connector_id=connector_id,
                    error_code="NoError",
                    status=status.value
                ),
                self.runner.loop
            )

    def on_engine_start(self, connector_id):
        if self.runner.adapter and self.runner.loop:
            session = self.engine.session
            if session:
                self._log(f"Bridge: Engine started session on connector {connector_id}")
                
                async def send_start_tx():
                    response = await self.runner.adapter.send_start_transaction(
                        connector_id=connector_id,
                        id_tag="DEMO_TAG", # Default for now
                        meter_start=int(self.engine.energy_meter.get_meter_reading()),
                        timestamp=datetime.now(timezone.utc).isoformat()
                    )
                    if response and response.transaction_id:
                         self.engine.session.transaction_id = response.transaction_id
                         self._log(f"Bridge: Updated Transaction ID to {response.transaction_id}")

                asyncio.run_coroutine_threadsafe(
                    send_start_tx(),
                    self.runner.loop
                )

    def on_engine_stop(self, connector_id):
        if self.runner.adapter and self.runner.loop:
            session = self.engine.session
            if session:
                self._log(f"Bridge: Engine stopping session on connector {connector_id}")
                asyncio.run_coroutine_threadsafe(
                    self.runner.adapter.send_stop_transaction(
                        meter_stop=int(self.engine.energy_meter.get_meter_reading()),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        transaction_id=session.transaction_id
                    ),
                    self.runner.loop
                )
