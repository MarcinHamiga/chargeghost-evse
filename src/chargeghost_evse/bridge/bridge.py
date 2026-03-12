"""
Bridge Module - Engine to OCPP Adapter Integration.

This module provides the bridge between the simulation Engine and the OCPP
Adapter, enabling communication between the EVSE simulator and Central System.
It handles WebSocket connection management, event forwarding, and message
synchronization between threads.

The bridge consists of two main components:
- AsyncRunner: Manages the async WebSocket connection in a dedicated thread
- Bridge: Coordinates events between Engine and AsyncRunner

Threading Architecture:
    - Main Thread: Qt UI and Engine simulation
    - AsyncRunner Thread: WebSocket/OCPP communication with its own event loop
    - Meter Values Thread: Periodic meter value sampling

Classes:
    AsyncRunner: WebSocket connection manager running in a dedicated thread.
    Bridge: Event coordinator between Engine and OCPP adapter.

Example:
    >>> from chargeghost_evse.bridge.bridge import Bridge
    >>> from chargeghost_evse.engine.engine import Engine
    >>> 
    >>> engine = Engine()
    >>> bridge = Bridge(
    ...     engine=engine,
    ...     url="wss://csms.example.com/CP_1",
    ...     charge_point_id="CP_1"
    ... )
    >>> bridge.setup()  # Start connection
    >>> # ... run simulation ...
    >>> bridge.shutdown()  # Clean up
"""

import asyncio
import base64
import concurrent.futures
import logging
import ssl
import threading
import traceback
import websockets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from chargeghost_evse.bridge.message_queue import (
    InMemoryBackend,
    JsonFileBackend,
    MessageQueue,
)
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ocpp_adapter.adapter import Adapter
from chargeghost_evse.util.event import Event


class AsyncRunner:
    """
    Manages WebSocket connection and OCPP adapter in a dedicated thread.

    Creates and manages an asyncio event loop in a daemon thread for
    WebSocket communication. Handles connection establishment, reconnection
    with exponential backoff, and graceful shutdown.

    The runner automatically:
    - Reconnects on connection failure with exponential backoff (1s to 60s)
    - Sends BootNotification on connection
    - Maintains heartbeat loop based on server-configured interval

    Attributes:
        charge_point_id: OCPP charge point identifier.
        url: WebSocket URL (wss:// or ws://).
        password: Optional HTTP Basic Auth password.
        skip_tls_verify: Whether to skip TLS certificate verification.
        charge_point_model: Model name for BootNotification.
        charge_point_vendor: Vendor name for BootNotification.
        command_queue: Queue for receiving commands from Engine.
        loop: The asyncio event loop (created in worker thread).
        adapter: The OCPP adapter instance (created on connection).
        on_log: Event emitted for log messages.
        on_adapter_registered: Event emitted after each successful BootNotification.

    Example:
        >>> runner = AsyncRunner(
        ...     charge_point_id="CP_1",
        ...     url="wss://localhost:3000",
        ...     command_queue=engine.command_queue
        ... )
        >>> runner.run_in_thread()  # Start in background
        >>> # ... later ...
        >>> runner.shutdown()  # Signal shutdown
    """

    def __init__(
        self,
        charge_point_id: str,
        url: str,
        command_queue,
        password: str = "",
        skip_tls_verify: bool = False,
        charge_point_model: str = "ChargeGhostV1",
        charge_point_vendor: str = "ChargeGhost",
    ) -> None:
        """
        Initialize the async runner.

        Args:
            charge_point_id: Unique identifier for this charge point.
            url: WebSocket server URL (charge_point_id will be appended if not present).
            command_queue: Queue for receiving commands from the Engine.
            password: Optional password for HTTP Basic Authentication.
            skip_tls_verify: If True, skip TLS certificate verification.
            charge_point_model: Model name reported in BootNotification.
            charge_point_vendor: Vendor name reported in BootNotification.
        """
        self.charge_point_id = charge_point_id

        # Ensure URL ends with charge_point_id
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

        # Async resources (created in worker thread)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.adapter: Optional[Adapter] = None

        # Python logger for this module
        self.logger = logging.getLogger("chargeghost.bridge")

        # Event emitted after each successful boot notification / registration
        self.on_adapter_registered: Event = Event()
        self.on_reset_requested: Event = Event()

        # Connection state
        self._connected = False
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Shutdown signaling
        self._shutdown_event: Optional[asyncio.Event] = None
        self._thread_shutdown = threading.Event()

    def _log(self, message: str, *, level: int = logging.INFO, **extra) -> None:
        """
        Emit a log message via the Python logger.

        Args:
            message: Log message text.
            level: Logging level (default INFO).
            **extra: Additional key-value pairs attached as log record extras.
        """
        self.logger.log(level, message, extra={"source": "bridge", **extra})

    def run_in_thread(self) -> threading.Thread:
        """
        Start the runner in a daemon thread.

        Creates a new daemon thread and starts the asyncio event loop.
        The thread will automatically exit when the main thread exits.

        Returns:
            The created Thread instance.
        """
        thread = threading.Thread(target=self._start_loop, daemon=True)
        thread.start()
        return thread

    def shutdown(self) -> None:
        """
        Signal the runner to shut down.

        Sets both the thread shutdown event and the async shutdown event
        (if available) to signal graceful termination.
        """
        self._thread_shutdown.set()
        if self._shutdown_event and self.loop:
            self.loop.call_soon_threadsafe(self._shutdown_event.set)

    def _start_loop(self) -> None:
        """
        Create and run the asyncio event loop (runs in worker thread).

        This is the thread entry point that creates a new asyncio event
        loop and runs the adapter connection loop until shutdown.
        """
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._shutdown_event = asyncio.Event()
        self.loop.run_until_complete(self._run_adapter())

    def _get_auth_header(self) -> dict:
        """
        Build HTTP Basic Authentication header if password is set.

        Returns:
            Dictionary with Authorization header, or empty dict if no password.
        """
        if self.password:
            credentials = f"{self.charge_point_id}:{self.password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {}

    def _get_ssl_context(self) -> Optional[ssl.SSLContext]:
        """
        Create SSL context for secure WebSocket connections.

        Returns:
            SSL context for wss:// URLs, None for ws:// URLs.
        """
        if self.url.startswith("wss://"):
            ssl_context = ssl.create_default_context()
            if self.skip_tls_verify:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            return ssl_context
        return None

    @property
    def is_connected(self) -> bool:
        """
        Check if WebSocket is connected and adapter is ready.

        Returns:
            True if connected and adapter exists, False otherwise.
        """
        return self._connected and self.adapter is not None

    async def _run_adapter(self) -> None:
        """
        Main connection loop with automatic reconnection.

        Establishes WebSocket connection, creates the OCPP adapter, sends
        BootNotification, and runs until disconnection or shutdown.
        On connection failure, waits with exponential backoff before retrying.

        Reconnection behavior:
        - Initial retry delay: 1 second
        - Maximum retry delay: 60 seconds
        - Delay doubles on each failure, resets on success
        """
        retry_delay = 1
        max_retry_delay = 60

        while self._shutdown_event is not None and not self._shutdown_event.is_set():
            try:
                self._log(message=f"Connecting to {self.url}...")
                extra_headers = self._get_auth_header()
                ssl_context = self._get_ssl_context()

                async with websockets.connect(
                    self.url,
                    subprotocols=["ocpp1.6"],  # type: ignore[list-item]
                    additional_headers=extra_headers,
                    ssl=ssl_context,
                ) as ws:
                    # Create and configure the OCPP adapter
                    self.adapter = Adapter(
                        self.charge_point_id,
                        ws,
                        command_queue=self.command_queue,
                        charge_point_model=self.charge_point_model,
                        charge_point_vendor=self.charge_point_vendor,
                    )
                    self.adapter.on_registration_accepted.subscribe(
                        self.on_adapter_registered.emit
                    )
                    self.adapter.on_reset_requested.subscribe(
                        self.on_reset_requested.emit
                    )
                    self._connected = True
                    retry_delay = 1  # Reset backoff after successful connection
                    self._log(message="WebSocket connected. Starting OCPP adapter...")

                    adapter_task = asyncio.create_task(self.adapter.start())

                    try:
                        # Send BootNotification to register with Central System
                        await self.adapter.send_boot_notification()

                        if self.adapter.registration_status:
                            reg_status = self.adapter.registration_status
                            if hasattr(reg_status, "value"):
                                reg_status = reg_status.value
                            self._log(message=f"Registration status: {reg_status}")

                        # Run adapter and heartbeat concurrently
                        await asyncio.gather(adapter_task, self._heartbeat_loop())
                    finally:
                        if not adapter_task.done():
                            adapter_task.cancel()
                        try:
                            await adapter_task
                        except asyncio.CancelledError:
                            pass
                        except Exception as e:
                            self._log(
                                message=f"Adapter task error: {type(e).__name__}: {e}",
                                level=logging.ERROR,
                            )

            except websockets.ConnectionClosed as e:
                self._log(
                    message=f"Connection closed: code={e.code}, reason={e.reason}",
                    level=logging.WARNING,
                )
            except ConnectionRefusedError:
                self._log(
                    message="Connection refused by server",
                    level=logging.ERROR,
                )
            except Exception as e:
                self._log(
                    message=f"Connection error: {type(e).__name__}: {e}",
                    level=logging.ERROR,
                )
                traceback.print_exc()
            finally:
                self._connected = False
                self.adapter = None
                if self._heartbeat_task and not self._heartbeat_task.done():
                    self._heartbeat_task.cancel()

            # Exponential backoff before retry
            if self._shutdown_event is not None and not self._shutdown_event.is_set():
                self._log(message=f"Retrying in {retry_delay}s...", level=logging.WARNING)
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=retry_delay
                    )
                except asyncio.TimeoutError:
                    pass
                retry_delay = min(retry_delay * 2, max_retry_delay)

    async def _heartbeat_loop(self) -> None:
        """
        Periodic heartbeat transmission loop.

        Sends Heartbeat messages at the interval specified by the Central
        System (via HeartbeatInterval configuration). Uses a default of
        300 seconds if not configured.

        The loop exits on shutdown signal or if heartbeat fails.
        """
        while (
            self._connected
            and self.adapter
            and self._shutdown_event is not None
            and not self._shutdown_event.is_set()
        ):
            # Get interval from adapter configuration
            interval = self.adapter.heartbeat_interval
            if interval <= 0:
                interval = 300  # Default to 5 minutes

            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                break  # Shutdown signaled
            except asyncio.TimeoutError:
                pass  # Interval elapsed, send heartbeat

            if (
                self._connected
                and self.adapter
                and self._shutdown_event is not None
                and not self._shutdown_event.is_set()
            ):
                try:
                    await self.adapter.send_heartbeat()
                except Exception as e:
                    self._log(message=f"Heartbeat failed: {e}", level=logging.ERROR)
                    break


class Bridge:
    """
    Coordinates events between the Engine and OCPP adapter.

    The Bridge connects the simulation Engine to the OCPP communication
    layer, translating Engine events into OCPP messages and vice versa.
    It manages multiple background threads for different tasks.

    Responsibilities:
    - Forward session start/stop events to OCPP (StartTransaction/StopTransaction)
    - Forward connector status changes to OCPP (StatusNotification)
    - Send periodic MeterValues during charging sessions
    - Inject charging profile limit callback into Engine
    - Send initial status notifications on connection

    Threading:
    - AsyncRunner thread: WebSocket/OCPP communication
    - Meter values thread: Periodic meter value sampling

    Attributes:
        engine: The simulation Engine instance.
        url: WebSocket URL for OCPP connection.
        runner: The AsyncRunner managing WebSocket connection.
        on_log: Event for log messages (forwarded from runner).

    Example:
        >>> engine = Engine()
        >>> bridge = Bridge(engine, url="wss://csms.example.com/CP_1")
        >>> bridge.setup()
        >>> 
        >>> # Engine events automatically forwarded to OCPP
        >>> engine.start_session(connector_id=1, transaction_id=123)
        >>> 
        >>> bridge.shutdown()
    """

    def __init__(
        self,
        engine: Engine,
        url: str = "wss://localhost:3000/CP_1",
        charge_point_id: str = "CP_1",
        password: str = "",
        skip_tls_verify: bool = False,
        charge_point_model: str = "ChargeGhostV1",
        charge_point_vendor: str = "ChargeGhost",
        persist_message_queue: bool = False,
    ) -> None:
        """
        Initialize the Bridge with Engine and connection parameters.

        Args:
            engine: The simulation Engine to bridge to OCPP.
            url: WebSocket URL for the Central System.
            charge_point_id: Unique identifier for this charge point.
            password: Optional HTTP Basic Auth password.
            skip_tls_verify: If True, skip TLS certificate verification.
            charge_point_model: Model name for BootNotification.
            charge_point_vendor: Vendor name for BootNotification.
            persist_message_queue: If True, persist message queue to disk.
        """
        self.engine = engine
        self.url = url

        # Create the async runner for WebSocket communication
        self.runner = AsyncRunner(
            charge_point_id=charge_point_id,
            url=url,
            command_queue=engine.command_queue,
            password=password,
            skip_tls_verify=skip_tls_verify,
            charge_point_model=charge_point_model,
            charge_point_vendor=charge_point_vendor,
        )

        # Offline message queue
        self._message_queue = self._create_message_queue(persist=persist_message_queue)

        # Background threads
        self._meter_values_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

    def setup(self) -> None:
        """
        Start the bridge and background threads.

        Subscribes to Engine events, starts the WebSocket connection,
        launches the meter values background thread, and registers an
        event handler that fires after each successful BootNotification.
        """
        # Subscribe to Engine events
        self.engine.session_started.subscribe(self.on_engine_session_started)
        self.engine.session_stopped.subscribe(self.on_engine_session_stopped)
        self.engine.connector_status_changed.subscribe(self.on_connector_status_change)

        # Start WebSocket connection in background thread
        self.runner.run_in_thread()

        # Start meter values sampling thread
        self._meter_values_thread = threading.Thread(
            target=self._meter_values_loop, daemon=True
        )
        self._meter_values_thread.start()

        # Subscribe to registration event to send status and inject limit getter
        self.runner.on_adapter_registered.subscribe(self._on_adapter_registered)
        self.runner.on_reset_requested.subscribe(self.on_reset_requested)

    def shutdown(self) -> None:
        """
        Shut down the bridge and all background threads.

        Removes callbacks, signals shutdown to all threads, and waits
        for them to terminate gracefully.
        """
        self._remove_limit_getter()
        self._shutdown_event.set()
        self.runner.shutdown()

    def _create_message_queue(self, persist: bool) -> MessageQueue:
        """Create message queue with appropriate backend."""
        if persist:
            filepath = Path.home() / ".chargeghost" / "message_queue.json"
            backend = JsonFileBackend(filepath)
        else:
            backend = InMemoryBackend()
        return MessageQueue(backend=backend, max_attempts=3)

    def _on_adapter_registered(self) -> None:
        """Called after each successful boot notification / registration."""
        self._log(
            message="[cyan]OCPP:[/cyan] Adapter registered, sending initial status and enabling charging profiles"
        )
        self._send_initial_status_notifications()
        self._inject_limit_getter()
        self._drain_message_queue()

    def _drain_message_queue(self) -> None:
        """Replay queued messages after reconnection."""
        if self._message_queue.size == 0:
            return

        adapter = self.runner.adapter
        loop = self.runner.loop
        if not adapter or not loop:
            return

        self._log(
            message=f"[cyan]Queue:[/cyan] Draining {self._message_queue.size} buffered message(s)..."
        )

        async def _do_drain() -> None:
            def on_start_tx_response(response: Any, kwargs: dict) -> None:
                """Assign CSMS-provided transaction ID to the active session."""
                tx_id = getattr(response, "transaction_id", None)
                if not tx_id:
                    return
                session = self.engine.session
                if session and session.connector_id == kwargs.get("connector_id"):
                    session.transaction_id = tx_id
                    set_active = getattr(adapter, "set_active_transaction", None)
                    if callable(set_active):
                        set_active(kwargs["connector_id"], tx_id)
                    self._log(
                        message=f"Transaction ID assigned from queue drain: {tx_id}"
                    )

            sent = await self._message_queue.drain(
                adapter,
                response_callbacks={"StartTransaction": on_start_tx_response},
            )
            remaining = self._message_queue.size
            self._log(
                message=f"[cyan]Queue:[/cyan] Sent {sent} message(s), {remaining} remaining"
            )

        future = asyncio.run_coroutine_threadsafe(_do_drain(), loop)
        future.add_done_callback(self._handle_future_error)

    def _inject_limit_getter(self) -> None:
        """
        Inject callbacks for charging profile limits and connector info.

        Sets up bidirectional callbacks between Engine and Adapter:
        - Engine.get_limit: Returns charging current limit from profiles
        - Adapter.get_connector_info: Returns connector voltage and phases
        """
        def get_limit(connector_id: int, transaction_id: Optional[int]) -> Optional[float]:
            """
            Get charging current limit from charging profiles.

            Args:
                connector_id: ID of the connector.
                transaction_id: Current transaction ID.

            Returns:
                Maximum current in amperes, or None for no limit.
            """
            if not self.runner.adapter or not self.runner.adapter.charging_profile_manager:
                return None

            connector = self.engine.get_connector(connector_id)
            if not connector:
                return None

            # Get transaction start time for TxProfile matching
            session = self.engine.session
            transaction_start = None
            if session and session.connector_id == connector_id:
                transaction_start = datetime.fromtimestamp(session.start_time, tz=timezone.utc)

            return self.runner.adapter.charging_profile_manager.get_composite_limit(
                connector_id=connector_id,
                transaction_id=transaction_id,
                now=datetime.now(timezone.utc),
                connector_voltage=connector.voltage,
                transaction_start=transaction_start,
                phases=connector.phase,
            )

        self.engine.get_limit = get_limit

        def get_connector_info(connector_id: int) -> Optional[tuple[float, int]]:
            """
            Get connector electrical parameters.

            Args:
                connector_id: ID of the connector.

            Returns:
                Tuple of (voltage, phases), or None if not found.
            """
            connector = self.engine.get_connector(connector_id)
            if not connector:
                return None
            return (connector.voltage, connector.phase)

        if self.runner.adapter:
            self.runner.adapter.get_connector_info = get_connector_info
            self.runner.adapter.known_connector_ids = [
                conn.id for conn in self.engine.connectors
            ]
            self.runner.adapter.set_connector_availability = (
                self.engine.set_connector_availability
            )

    def _remove_limit_getter(self) -> None:
        """
        Remove injected callbacks during shutdown.

        Clears the callbacks to prevent calls to disconnected adapter.
        """
        self.engine.get_limit = None
        if self.runner.adapter:
            self.runner.adapter.get_connector_info = None
            self.runner.adapter.known_connector_ids = []
            self.runner.adapter.set_connector_availability = None

    def _send_initial_status_notifications(self) -> None:
        """
        Send StatusNotification for all connectors after registration.

        Called once after successful BootNotification to report the
        initial status of all connectors to the Central System.
        """
        adapter = self.runner.adapter
        loop = self.runner.loop
        if not adapter or not loop:
            return

        self._log(message="Sending initial StatusNotification for all connectors...")

        for connector in self.engine.connectors:
            conn_status = connector.status.value

            future = asyncio.run_coroutine_threadsafe(
                adapter.send_status_notification(
                    connector_id=connector.id,
                    error_code="NoError",
                    status=conn_status,
                ),
                loop,
            )
            future.add_done_callback(self._handle_future_error)

    def _meter_values_loop(self) -> None:
        """
        Periodic meter value sampling and transmission loop.

        Samples the energy meter at the configured MeterValueSampleInterval
        and sends MeterValues to the Central System during active sessions.
        """
        while not self._shutdown_event.is_set():
            # Get sampling interval from configuration
            interval = 60  # Default to 60 seconds
            if self.runner.adapter:
                interval = self.runner.adapter.config_manager.get_int_value(
                    "MeterValueSampleInterval", 60
                )

            # Send meter values if session is active and charging
            if (
                interval > 0
                and self.engine.session
                and self.engine.session.transaction_id > 0
                and self.engine.energy_meter.is_charging
            ):
                adapter = self.runner.adapter
                loop = self.runner.loop
                if adapter and loop:
                    future = asyncio.run_coroutine_threadsafe(
                        adapter.send_meter_values(
                            connector_id=self.engine.session.connector_id,
                            value=self.engine.energy_meter.get_meter_reading(),
                            transaction_id=self.engine.session.transaction_id,
                        ),
                        loop,
                    )
                    future.add_done_callback(self._handle_future_error)
                else:
                    self._message_queue.enqueue("MeterValues", {
                        "connector_id": self.engine.session.connector_id,
                        "value": self.engine.energy_meter.get_meter_reading(),
                        "transaction_id": self.engine.session.transaction_id,
                    })

            # Wait for the interval or until shutdown
            wait_interval = max(interval, 1) if interval > 0 else 1
            self._shutdown_event.wait(timeout=wait_interval)

    def _handle_future_error(self, future: "concurrent.futures.Future[Any]") -> None:
        """Log exceptions from fire-and-forget coroutine futures."""
        exc = future.exception()
        if exc is not None:
            self._log(
                message=f"[red]OCPP send failed:[/red] {type(exc).__name__}: {exc}",
                level=logging.ERROR,
            )

    async def _send_boot_notification_for_reset(self, reset_type: str) -> None:
        """
        Send BootNotification to simulate a completed remote reset.

        Args:
            reset_type: Requested reset type ("Soft" or "Hard").
        """
        adapter = self.runner.adapter
        if adapter is None:
            return

        self._log(message=f"{reset_type} reset completed. Sending BootNotification.")
        await adapter.send_boot_notification()

    def _log(self, message: str, *, level: int = logging.INFO, **extra) -> None:
        """
        Emit a log message via the runner's Python logger.

        Args:
            message: Log message text.
            level: Logging level (default INFO).
            **extra: Additional key-value pairs attached as log record extras.
        """
        self.runner.logger.log(level, message, extra={"source": "bridge", **extra})

    def on_reset_requested(self, reset_type: str) -> None:
        """
        Handle a remote reset request forwarded by the adapter.

        If no transaction is active, the reset completes immediately by
        sending a fresh BootNotification. Active-session resets are
        completed in on_engine_session_stopped after StopTransaction.

        Args:
            reset_type: Requested reset type ("Soft" or "Hard").
        """
        self._log(message=f"Remote reset requested: {reset_type}")
        # Ordering: on_reset in the adapter enqueues the RESET command AND emits this
        # event synchronously in the same call. This handler runs first (before the
        # engine processes the command queue), so the session is still non-None here
        # for an active session. That's intentional — the BootNotification is deferred
        # to on_engine_session_stopped, which fires after StopTransaction completes.
        if self.engine.session is not None:
            return

        adapter = self.runner.adapter
        loop = self.runner.loop
        if not adapter or not loop:
            return

        future = asyncio.run_coroutine_threadsafe(
            self._send_boot_notification_for_reset(reset_type),
            loop,
        )
        future.add_done_callback(self._handle_future_error)

    def on_connector_status_change(self, connector_id: int, status) -> None:
        """
        Handle connector status change events from the Engine.

        Forwards status changes to the Central System via StatusNotification.

        Args:
            connector_id: ID of the connector that changed.
            status: New ConnectorState value.
        """
        adapter = self.runner.adapter
        loop = self.runner.loop
        if adapter and loop:
            conn_status = status.value if hasattr(status, "value") else str(status)

            self._log(
                message=f"Connector {connector_id} status changed to {conn_status}"
            )
            future = asyncio.run_coroutine_threadsafe(
                adapter.send_status_notification(
                    connector_id=connector_id,
                    error_code="NoError",
                    status=conn_status,
                ),
                loop,
            )
            future.add_done_callback(self._handle_future_error)

    def on_engine_session_started(self, connector_id: int) -> None:
        """
        Handle session started events from the Engine.

        Sends StartTransaction to the Central System and updates the
        session with the assigned transaction ID. If disconnected, queues
        the message for replay on reconnection.

        Args:
            connector_id: ID of the connector where session started.
        """
        session = self.engine.session
        if not session:
            return

        self._log(message=f"Session started on connector {connector_id}")
        id_tag = session.id_tag or "UNKNOWN_TAG"
        start_kwargs = {
            "connector_id": connector_id,
            "id_tag": id_tag,
            "meter_start": int(self.engine.energy_meter.get_meter_reading()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        adapter = self.runner.adapter
        loop = self.runner.loop
        if not adapter or not loop:
            self._message_queue.enqueue("StartTransaction", start_kwargs)
            self._log(
                message="[yellow]Queued[/yellow] StartTransaction (offline)",
                level=logging.WARNING,
            )
            return

        async def send_start_tx() -> None:
            """Send StartTransaction and update session with transaction ID."""
            try:
                response = await adapter.send_start_transaction(**start_kwargs)
                if response and response.transaction_id and self.engine.session is session:
                    session.transaction_id = response.transaction_id
                    self._log(message=f"Transaction ID assigned: {response.transaction_id}")
            except Exception as e:
                self._log(
                    message=f"[red]StartTransaction failed:[/red] {type(e).__name__}: {e}",
                    level=logging.ERROR,
                )
                self._message_queue.enqueue("StartTransaction", start_kwargs)
                self._log(
                    message="[yellow]Queued[/yellow] StartTransaction for retry",
                    level=logging.WARNING,
                )

        future = asyncio.run_coroutine_threadsafe(send_start_tx(), loop)
        future.add_done_callback(self._handle_future_error)

    def on_engine_session_stopped(self, connector_id: int) -> None:
        """
        Handle session stopped events from the Engine.

        Sends StopTransaction to the Central System with the final
        meter reading and stop reason. If disconnected, queues the
        message for replay on reconnection.

        Args:
            connector_id: ID of the connector where session stopped.
        """
        last_session = self.engine.last_stopped_session
        if not last_session:
            self._log(
                message=f"No session info available for connector {connector_id}",
                level=logging.WARNING,
            )
            return

        transaction_id = last_session.get("transaction_id", 0)
        meter_stop = last_session.get("meter_stop", 0)
        reason = last_session.get("reason", "Local")
        stop_kwargs = {
            "meter_stop": int(meter_stop),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transaction_id": transaction_id,
            "reason": reason,
        }

        self._log(
            message=f"Session stopped on connector {connector_id}, tx_id={transaction_id}, reason={reason}"
        )

        adapter = self.runner.adapter
        loop = self.runner.loop
        if not adapter or not loop:
            self._message_queue.enqueue("StopTransaction", stop_kwargs)
            self._log(
                message="[yellow]Queued[/yellow] StopTransaction (offline)",
                level=logging.WARNING,
            )
            return

        async def _send_stop() -> None:
            try:
                await adapter.send_stop_transaction(**stop_kwargs)
            except Exception as e:
                self._log(
                    message=f"[red]StopTransaction failed:[/red] {type(e).__name__}: {e}",
                    level=logging.ERROR,
                )
                self._message_queue.enqueue("StopTransaction", stop_kwargs)
                self._log(
                    message="[yellow]Queued[/yellow] StopTransaction for retry",
                    level=logging.WARNING,
                )
            if reason in {"SoftReset", "HardReset"}:
                await self._send_boot_notification_for_reset(reason.removesuffix("Reset"))

        future = asyncio.run_coroutine_threadsafe(_send_stop(), loop)
        future.add_done_callback(self._handle_future_error)

    def send_authorize(self, id_tag: str) -> None:
        """
        Send an Authorize request to the Central System.

        Args:
            id_tag: The identifier to authorize.
        """
        adapter = self.runner.adapter
        loop = self.runner.loop
        if adapter and loop:
            future = asyncio.run_coroutine_threadsafe(
                adapter.send_authorize(id_tag=id_tag), loop
            )
            future.add_done_callback(self._handle_future_error)

    def send_heartbeat(self) -> None:
        """
        Send a manual Heartbeat to the Central System.

        Note: Heartbeats are normally sent automatically by the AsyncRunner.
        This method is for manual triggering if needed.
        """
        adapter = self.runner.adapter
        loop = self.runner.loop
        if adapter and loop:
            future = asyncio.run_coroutine_threadsafe(
                adapter.send_heartbeat(), loop
            )
            future.add_done_callback(self._handle_future_error)
