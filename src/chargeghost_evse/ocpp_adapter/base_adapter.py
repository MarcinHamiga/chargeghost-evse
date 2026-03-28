"""
Shared Base Adapter for OCPP Protocol Implementations.

This module provides the BaseAdapter mixin class that encapsulates behavior
shared across OCPP protocol versions (1.6J and 2.0.1). It is not intended
to be instantiated directly — version-specific adapters inherit from it
alongside the corresponding ocpp library ChargePoint base class.

Shared responsibilities:
    - Event emitters for OCPP message logging and lifecycle signals
    - Registration state and heartbeat interval bookkeeping
    - Transaction tracking (active_transactions map)
    - Injectable connector callbacks (set by the Bridge at runtime)
    - Raw OCPP message logging helpers
    - Background send scheduling utilities

Classes:
    BaseAdapter: Mixin providing shared adapter state and helpers.
"""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Literal, Optional, TYPE_CHECKING

from ocpp.exceptions import PropertyConstraintViolationError

from chargeghost_evse.util.event import Event

if TYPE_CHECKING:
    from chargeghost_evse.devtools.timeline_store import TimelineStore


class BaseAdapter:
    """
    Shared base mixin for OCPP protocol adapters.

    Provides common events, logging, registration bookkeeping,
    transaction tracking, and injectable connector callbacks used
    by both OCPP 1.6 and 2.0.1 adapters.

    Subclasses must also inherit from the appropriate ocpp ChargePoint
    base class (e.g. ocpp.v16.ChargePoint or ocpp.v201.ChargePoint)
    and call _init_base() from their __init__ after the ChargePoint
    initialization.

    Attributes:
            command_queue: Queue for sending commands to the Engine.
            charge_point_model: Model name for BootNotification.
            charge_point_vendor: Vendor name for BootNotification.
            heartbeat_interval: Heartbeat interval in seconds from CSMS.
            registration_status: Current registration status with CSMS.
            active_transactions: Map of connector_id to transaction_id.
            on_ocpp_message: Event emitted for raw OCPP message logging.
            on_registration_accepted: Emitted when BootNotification is accepted.
            on_heartbeat_response: Emitted when Heartbeat response is received.
            on_reset_requested: Emitted when a remote reset is requested.
    """

    _log_important_actions: set[str] = set()

    def _init_base(
        self,
        *,
        command_queue: Any = None,
        charge_point_model: str = "ChargeGhostV1",
        charge_point_vendor: str = "ChargeGhost",
        response_timeout: int = 30,
        protocol_version: str = "ocpp1.6",
        timeline_store: Optional["TimelineStore"] = None,
    ) -> None:
        """
        Initialize shared adapter state.

        Must be called from the version-specific adapter's __init__
        after the OCPP ChargePoint base class has been initialized.

        Args:
                command_queue: Queue for sending commands to the Engine.
                charge_point_model: Model name reported in BootNotification.
                charge_point_vendor: Vendor name reported in BootNotification.
                response_timeout: Timeout for OCPP responses in seconds.
                protocol_version: OCPP protocol version string (e.g. "ocpp1.6").
                timeline_store: Optional TimelineStore for capturing frame events.
        """
        self.command_queue = command_queue
        self.response_timeout = response_timeout
        self.protocol_version = protocol_version
        self.timeline_store = timeline_store

        self.logger = logging.getLogger("chargeghost.ocpp")
        self._tx_logger = logging.getLogger("chargeghost.ocpp.tx")

        self.on_ocpp_message = Event()
        self.on_reset_requested = Event()
        self.on_registration_accepted = Event()
        self.on_heartbeat_response = Event()

        self.charge_point_model = charge_point_model
        self.charge_point_vendor = charge_point_vendor

        self.heartbeat_interval: int = 0
        self.registration_status: Optional[Any] = None

        self.active_transactions: dict[int, int] = {}
        self._next_transaction_id: int = 0

        self.get_connector_info: Optional[
            Callable[[int], Optional[tuple[float, int]]]
        ] = None
        self.get_connector_status: Optional[Callable[[int], Optional[str]]] = None
        self.get_meter_snapshot: Optional[
            Callable[[int], Optional[tuple[float, Optional[int]]]]
        ] = None
        self.known_connector_ids: list[int] = []

        self.set_connector_availability: Optional[Callable[[int, str], str]] = None
        self.reserve_connector: Optional[Callable[..., str]] = None
        self.cancel_reservation: Optional[Callable[[int], str]] = None

    def _log(
        self,
        message: str,
        *,
        level: int = logging.INFO,
        **extra,
    ) -> None:
        self.logger.log(level, message, extra={"source": "ocpp", **extra})

    def _log_ocpp_raw(
        self,
        direction: str,
        action: str,
        payload: Any,
        message_id: str = "",
    ) -> None:
        try:
            if isinstance(payload, dict):
                payload_str = json.dumps(payload, indent=2)
                payload_for_timeline: dict[str, Any] = payload
            else:
                payload_str = str(payload)
                payload_for_timeline = {"raw": str(payload)}
        except (TypeError, ValueError):
            payload_str = str(payload)
            payload_for_timeline = {"raw": str(payload)}

        raw_msg = f"[{direction}] {action}"
        if message_id:
            raw_msg += f" (id={message_id})"
        raw_msg += f"\n{payload_str}"

        level = logging.INFO if action in self._log_important_actions else logging.DEBUG

        normalized_direction: Literal["inbound", "outbound"] = (
            "outbound" if direction == "TX" else "inbound"
        )

        self.on_ocpp_message.emit(
            direction=direction, action=action, payload=payload_str
        )
        self._tx_logger.log(
            level,
            raw_msg,
            extra={
                "source": "ocpp",
                "ocpp_direction": direction,
                "ocpp_action": action,
                "ocpp_message_id": message_id,
                "ocpp_payload": payload if isinstance(payload, dict) else payload_str,
                "ocpp_correlated_id": message_id if direction == "RX" else None,
            },
        )

        if self.timeline_store is not None:
            correlation_key = f"{action}:{message_id}" if message_id else action
            self.timeline_store.append(
                source="ocpp",
                direction=normalized_direction,
                event_type="frame",
                action=action,
                message_id=message_id,
                level=level,
                payload=payload_for_timeline,
                protocol_version=self.protocol_version,
                correlation_key=correlation_key,
            )

    async def _send_call(self, message) -> Any:
        self._log_ocpp_raw("TX", message.__class__.__name__, message.__dict__)
        return await super()._send_call(message)  # type: ignore[misc]

    async def _handle_call(self, msg) -> Any:
        if hasattr(msg, "unique_id") and hasattr(msg, "action"):
            payload = getattr(msg, "payload", msg.__dict__)
            self._log_ocpp_raw("RX", msg.action, payload, getattr(msg, "unique_id", ""))
        return await super()._handle_call(msg)  # type: ignore[misc]

    def _schedule_background_send(self, awaitable: Awaitable[Any], action: str) -> None:
        task: asyncio.Task[Any] = asyncio.create_task(awaitable)  # type: ignore[arg-type]
        task.add_done_callback(
            lambda completed: self._handle_background_send_result(completed, action)
        )

    def _handle_background_send_result(
        self, task: asyncio.Task[Any], action: str
    ) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._log(
                f"TriggerMessage {action} failed: {exc}",
                level=logging.ERROR,
            )

    def _raise_property_constraint(self, description: str, **details: Any) -> None:
        raise PropertyConstraintViolationError(
            description=description,
            details=details or None,
        )

    def get_active_transaction_id(self, connector_id: int) -> Optional[int]:
        return self.active_transactions.get(connector_id)

    def set_active_transaction(self, connector_id: int, transaction_id: int) -> None:
        self.active_transactions[connector_id] = transaction_id

    def clear_active_transaction(self, connector_id: int) -> None:
        if connector_id in self.active_transactions:
            del self.active_transactions[connector_id]
