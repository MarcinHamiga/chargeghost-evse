import weakref

from PySide6.QtCore import QObject, Signal

from chargeghost_evse.util.config import LogMode


class QtSignalBridge(QObject):
    """Bridges internal Event emissions to Qt Signals for thread-safe UI updates."""

    log_received = Signal(str, str, bool)
    status_updated = Signal(object)
    connector_status_changed = Signal(int, object)
    session_started = Signal(int)
    session_stopped = Signal(int)
    connection_status_changed = Signal(bool)
    log_mode_changed = Signal()

    def __init__(self, engine, bridge):
        super().__init__()
        self._engine = weakref.ref(engine)
        self._bridge_ref = weakref.ref(bridge, self._on_bridge_deleted)
        self._last_connected = False
        self._log_mode: LogMode = "compact"

        engine.on_log.subscribe(self._on_engine_log)
        bridge.on_log.subscribe(self._on_bridge_log)
        engine.connector_status_changed.subscribe(self._on_connector_status_changed)
        engine.session_started.subscribe(self._on_session_started)
        engine.session_stopped.subscribe(self._on_session_stopped)

    @property
    def log_mode(self) -> LogMode:
        return self._log_mode

    @log_mode.setter
    def log_mode(self, value: LogMode) -> None:
        if self._log_mode != value:
            self._log_mode = value
            self._safe_emit(self.log_mode_changed)

    def _on_bridge_deleted(self, ref):
        pass

    def check_connection_status(self):
        bridge = self._bridge_ref()
        if bridge and bridge.runner:
            connected = bridge.runner.is_connected
            if connected != self._last_connected:
                self._last_connected = connected
                self._safe_emit(self.connection_status_changed, connected)
            return connected
        return False

    def _safe_emit(self, signal, *args):
        try:
            signal.emit(*args)
        except RuntimeError:
            pass

    def _on_engine_log(self, message: str, **kwargs):
        is_important = kwargs.get("is_important", True)
        self._safe_emit(self.log_received, "Engine", message, is_important)

    def _on_bridge_log(self, message: str, **kwargs):
        is_important = kwargs.get("is_important", True)
        self._safe_emit(self.log_received, "OCPP", message, is_important)

    def _on_connector_status_changed(self, connector_id: int, status):
        self._safe_emit(self.connector_status_changed, connector_id, status)

    def _on_session_started(self, connector_id: int):
        self._safe_emit(self.session_started, connector_id)

    def _on_session_stopped(self, connector_id: int):
        self._safe_emit(self.session_stopped, connector_id)
