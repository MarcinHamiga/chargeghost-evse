from dataclasses import dataclass
from typing import Any, Optional

from chargeghost_evse.engine.engine import Engine


@dataclass
class ActionResult:
    success: bool
    message: str
    details: Optional[dict[str, Any]] = None

    @classmethod
    def ok(
        cls, message: str, details: Optional[dict[str, Any]] = None
    ) -> "ActionResult":
        return cls(success=True, message=message, details=details)

    @classmethod
    def fail(
        cls, message: str, details: Optional[dict[str, Any]] = None
    ) -> "ActionResult":
        return cls(success=False, message=message, details=details)


class SimulatorController:
    def __init__(
        self, engine: Engine, bridge: Any, fault_manager: Optional[Any] = None
    ) -> None:
        self.engine = engine
        self.bridge = bridge
        self.fault_manager = fault_manager
        self._transaction_counter: int = 0

    @property
    def is_connected(self) -> bool:
        return getattr(self.bridge.runner, "is_connected", False)

    def execute_action(
        self, action: str, connector_id: int = 1, **kwargs: Any
    ) -> ActionResult:
        if action == "connect":
            return self.connect()
        elif action == "disconnect":
            return self.disconnect()
        elif action == "authorize":
            return self.authorize(kwargs.get("id_tag", ""))
        elif action == "plug_in":
            return self.plug_in(connector_id)
        elif action == "unplug":
            return self.unplug(connector_id)
        elif action == "start_charging":
            return self.start_charging(connector_id)
        elif action == "stop_charging":
            return self.stop_charging()
        elif action == "suspend_ev":
            return self.suspend_ev(connector_id)
        elif action == "resume_charging":
            return self.resume_charging(connector_id)
        elif action == "set_rfid":
            return self.set_rfid(kwargs.get("rfid_tag", ""), connector_id)
        elif action == "clear_rfid":
            return self.clear_rfid(connector_id)
        elif action == "send_heartbeat":
            return self.send_heartbeat()
        return ActionResult.fail(f"Unknown action: {action}")

    def connect(self) -> ActionResult:
        self.bridge.setup()
        return ActionResult.ok("Connect requested")

    def disconnect(self) -> ActionResult:
        self.bridge.shutdown()
        return ActionResult.ok("Disconnect requested")

    def authorize(self, id_tag: str) -> ActionResult:
        self.bridge.send_authorize(id_tag)
        return ActionResult.ok(f"Authorize sent: {id_tag}")

    def plug_in(self, connector_id: int) -> ActionResult:
        self.engine.plug_in(connector_id)
        return ActionResult.ok(f"Plugged In to Connector {connector_id}")

    def unplug(self, connector_id: int) -> ActionResult:
        self.engine.unplug(connector_id)
        return ActionResult.ok(f"Unplugged from Connector {connector_id}")

    def start_charging(self, connector_id: int) -> ActionResult:
        self._transaction_counter += 1
        transaction_id = self._transaction_counter
        self.engine.start_session(
            connector_id=connector_id, transaction_id=transaction_id
        )
        return ActionResult.ok(
            f"Started charging session on Connector {connector_id}",
            details={"transaction_id": transaction_id},
        )

    def stop_charging(self) -> ActionResult:
        self.engine.stop_session()
        return ActionResult.ok("Stopped charging session")

    def suspend_ev(self, connector_id: int) -> ActionResult:
        self.engine.suspend_ev(connector_id)
        return ActionResult.ok(f"Suspended EV on Connector {connector_id}")

    def resume_charging(self, connector_id: int) -> ActionResult:
        self.engine.resume_charging(connector_id)
        return ActionResult.ok(f"Resumed charging on Connector {connector_id}")

    def set_rfid(self, rfid_tag: str, connector_id: int) -> ActionResult:
        conn = self.engine.get_connector(connector_id)
        if conn:
            conn.id_tag = rfid_tag
        return ActionResult.ok(f"RFID set to: {rfid_tag}")

    def clear_rfid(self, connector_id: int) -> ActionResult:
        conn = self.engine.get_connector(connector_id)
        if conn:
            conn.id_tag = None
        return ActionResult.ok("RFID cleared")

    def send_heartbeat(self) -> ActionResult:
        self.bridge.send_heartbeat()
        return ActionResult.ok("Heartbeat sent")

    def get_connector(self, connector_id: int) -> Any:
        return self.engine.get_connector(connector_id)

    def get_session(self, connector_id: int) -> Any:
        return self.engine.get_session(connector_id)
