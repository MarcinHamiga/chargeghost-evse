import asyncio
import ssl
import threading
import time
import websockets
from datetime import datetime, timezone
from typing import Optional
from chargeghost_evse.util.event import Event
from chargeghost_evse.ocpp_adapter.adapter import Adapter
from chargeghost_evse.engine.engine import Engine


class AsyncRunner:
    def __init__(
        self,
        charge_point_id: str,
        url: str,
        command_queue,
        password: str = "",
        skip_tls_verify: bool = False,
        charge_point_model: str = "ChargeGhostV1",
        charge_point_vendor: str = "ChargeGhost"
    ):
        self.charge_point_id = charge_point_id
        
        # Ensure URL ends with the Charge Point ID (OCPP Requirement)
        stripped_url = url.rstrip("/")
        if stripped_url.split("/")[-1] != charge_point_id:
            self.url = f"{stripped_url}/{charge_point_id}"
        else:
            self.url = stripped_url
            
        self.password = password
        self.skip_tls_verify = skip_tls_verify
        self.charge_point_model = charge_point_model
        self.charge_point_vendor = charge_point_vendor
        self.command_queue = command_queue
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.adapter: Optional[Adapter] = None
        self.on_log = Event()
        self._connected = False
        self._heartbeat_task: Optional[asyncio.Task] = None

    def _log(self, message: str) -> None:
        self.on_log.emit(message=message)

    def run_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self._start_loop, daemon=True)
        thread.start()
        return thread

    def _start_loop(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._run_adapter())

    def _get_auth_header(self) -> dict:
        if self.password:
            import base64
            credentials = f"{self.charge_point_id}:{self.password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {}

    def _get_ssl_context(self) -> Optional[ssl.SSLContext]:
        if self.url.startswith("wss://"):
            ssl_context = ssl.create_default_context()
            if self.skip_tls_verify:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            return ssl_context
        return None

    @property
    def is_connected(self) -> bool:
        return self._connected and self.adapter is not None

    async def _run_adapter(self) -> None:
        retry_delay = 1
        max_retry_delay = 60
        
        while True:
            try:
                self._log(message=f"Connecting to {self.url}...")
                extra_headers = self._get_auth_header()
                ssl_context = self._get_ssl_context()
                
                async with websockets.connect(
                    self.url,
                    subprotocols=["ocpp1.6"],
                    additional_headers=extra_headers,
                    ssl=ssl_context
                ) as ws:
                    self.adapter = Adapter(
                        self.charge_point_id,
                        ws,
                        command_queue=self.command_queue,
                        charge_point_model=self.charge_point_model,
                        charge_point_vendor=self.charge_point_vendor
                    )
                    self.adapter.on_log.subscribe(self._log)
                    self._connected = True
                    self._log(message="WebSocket connected. Starting OCPP adapter...")
                    
                    adapter_task = asyncio.create_task(self.adapter.start())
                    
                    try:
                        boot_response = await self.adapter.send_boot_notification()
                        
                        if self.adapter.registration_status:
                            reg_status = self.adapter.registration_status
                            if hasattr(reg_status, "value"):
                                reg_status = reg_status.value
                            self._log(message=f"Registration status: {reg_status}")
                        
                        await asyncio.gather(
                            adapter_task,
                            self._heartbeat_loop()
                        )
                    finally:
                        if not adapter_task.done():
                            adapter_task.cancel()
                        try:
                            await adapter_task
                        except asyncio.CancelledError:
                            pass
                        except Exception:
                            pass
                    
            except websockets.ConnectionClosed as e:
                self._log(message=f"Connection closed: code={e.code}, reason={e.reason}")
            except ConnectionRefusedError:
                self._log(message="Connection refused by server")
            except Exception as e:
                self._log(message=f"Connection error: {type(e).__name__}: {e}")
            finally:
                self._connected = False
                self.adapter = None
                if self._heartbeat_task and not self._heartbeat_task.done():
                    self._heartbeat_task.cancel()
            
            self._log(message=f"Retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)

    async def _heartbeat_loop(self) -> None:
        while self._connected and self.adapter:
            interval = self.adapter.heartbeat_interval
            if interval <= 0:
                interval = 300
            
            await asyncio.sleep(interval)
            
            if self._connected and self.adapter:
                try:
                    await self.adapter.send_heartbeat()
                except Exception as e:
                    self._log(message=f"Heartbeat failed: {e}")
                    break


class Bridge:
    def __init__(
        self,
        engine: Engine,
        url: str = "wss://localhost:3000/CP_1",
        charge_point_id: str = "CP_1",
        password: str = "",
        skip_tls_verify: bool = False,
        charge_point_model: str = "ChargeGhostV1",
        charge_point_vendor: str = "ChargeGhost"
    ):
        self.engine = engine
        self.url = url
        self.runner = AsyncRunner(
            charge_point_id=charge_point_id,
            url=url,
            command_queue=engine.command_queue,
            password=password,
            skip_tls_verify=skip_tls_verify,
            charge_point_model=charge_point_model,
            charge_point_vendor=charge_point_vendor
        )
        self.on_log = self.runner.on_log
        self._meter_values_thread: Optional[threading.Thread] = None

    def setup(self) -> None:
        self.engine.session_started.subscribe(self.on_engine_session_started)
        self.engine.session_stopped.subscribe(self.on_engine_session_stopped)
        self.engine.connector_status_changed.subscribe(self.on_connector_status_change)
        
        self.runner.run_in_thread()
        
        self._meter_values_thread = threading.Thread(target=self._meter_values_loop, daemon=True)
        self._meter_values_thread.start()
        
        threading.Thread(target=self._initial_status_loop, daemon=True).start()

    def _initial_status_loop(self) -> None:
        while True:
            if self.runner.is_connected and self.runner.adapter:
                if self.runner.adapter.registration_status:
                    self._send_initial_status_notifications()
                    break
            time.sleep(0.5)

    def _send_initial_status_notifications(self) -> None:
        if not self.runner.adapter or not self.runner.loop:
            return
        
        self._log(message="Sending initial StatusNotification for all connectors...")
        
        for connector in self.engine.connectors:
            conn_status = connector.status
            if hasattr(conn_status, "value"):
                conn_status = conn_status.value
            
            asyncio.run_coroutine_threadsafe(
                self.runner.adapter.send_status_notification(
                    connector_id=connector.id + 1,
                    error_code="NoError",
                    status=conn_status
                ),
                self.runner.loop
            )

    def _meter_values_loop(self) -> None:
        while True:
            if self.engine.session and self.engine.energy_meter.is_charging:
                if self.runner.adapter and self.runner.loop:
                    asyncio.run_coroutine_threadsafe(
                        self.runner.adapter.send_meter_values(
                            connector_id=self.engine.session.connector_id + 1,
                            value=self.engine.energy_meter.get_meter_reading(),
                            transaction_id=self.engine.session.transaction_id
                        ),
                        self.runner.loop
                    )
            time.sleep(10)

    def _log(self, message: str) -> None:
        self.on_log.emit(message=message)

    def on_connector_status_change(self, connector_id: int, status) -> None:
        if self.runner.adapter and self.runner.loop:
            conn_status = status
            if hasattr(conn_status, "value"):
                conn_status = conn_status.value
                
            self._log(message=f"Connector {connector_id} status changed to {conn_status}")
            asyncio.run_coroutine_threadsafe(
                self.runner.adapter.send_status_notification(
                    connector_id=connector_id + 1,
                    error_code="NoError",
                    status=conn_status
                ),
                self.runner.loop
            )

    def on_engine_session_started(self, connector_id: int) -> None:
        if not self.runner.adapter or not self.runner.loop:
            return
        
        session = self.engine.session
        if not session:
            return
        
        self._log(message=f"Session started on connector {connector_id}")
        id_tag = session.id_tag or "UNKNOWN_TAG"
        
        async def send_start_tx() -> None:
            response = await self.runner.adapter.send_start_transaction(
                connector_id=connector_id + 1,
                id_tag=id_tag,
                meter_start=int(self.engine.energy_meter.get_meter_reading()),
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            if response and response.transaction_id and self.engine.session is session:
                session.transaction_id = response.transaction_id
                self._log(message=f"Transaction ID assigned: {response.transaction_id}")
        
        asyncio.run_coroutine_threadsafe(send_start_tx(), self.runner.loop)

    def on_engine_session_stopped(self, connector_id: int) -> None:
        if not self.runner.adapter or not self.runner.loop:
            return
        
        last_session = self.engine.last_stopped_session
        if not last_session:
            self._log(message=f"No session info available for connector {connector_id}")
            return
        
        transaction_id = last_session.get("transaction_id", 0)
        meter_stop = last_session.get("meter_stop", 0)
        
        self._log(message=f"Session stopped on connector {connector_id}, tx_id={transaction_id}")
        
        asyncio.run_coroutine_threadsafe(
            self.runner.adapter.send_stop_transaction(
                meter_stop=int(meter_stop),
                timestamp=datetime.now(timezone.utc).isoformat(),
                transaction_id=transaction_id,
                reason="Local"
            ),
            self.runner.loop
        )

    def send_authorize(self, id_tag: str) -> None:
        if self.runner.adapter and self.runner.loop:
            asyncio.run_coroutine_threadsafe(
                self.runner.adapter.send_authorize(id_tag=id_tag),
                self.runner.loop
            )

    def send_heartbeat(self) -> None:
        if self.runner.adapter and self.runner.loop:
            asyncio.run_coroutine_threadsafe(
                self.runner.adapter.send_heartbeat(),
                self.runner.loop
            )
