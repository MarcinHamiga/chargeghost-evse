import logging
import threading
from typing import Optional

from chargeghost_evse.devtools.fault_catalog import FAULT_CATALOG, get_fault_definition
from chargeghost_evse.devtools.fault_models import (
    FaultConfig,
    FaultLifetime,
    FaultState,
    FaultTriggerResult,
)
from chargeghost_evse.util.event import Event


class FaultManager:
    def __init__(self) -> None:
        self._states: dict[str, FaultState] = {
            fid: FaultState(fault_id=fid) for fid in FAULT_CATALOG
        }
        self._lock = threading.RLock()
        self.fault_changed = Event()
        self._logger = logging.getLogger("chargeghost.devtools.fault_manager")

    def _log(self, level: int, msg: str, **extra: object) -> None:
        self._logger.log(level, msg, extra={"source": "fault_manager", **extra})

    def enable(self, fault_id: str, config: Optional[FaultConfig] = None) -> None:
        get_fault_definition(fault_id)
        with self._lock:
            state = self._states[fault_id]
            state.enabled = True
            state.config = config
            state.trigger_count = 0
        self._log(
            logging.INFO,
            "Fault enabled",
            fault_id=fault_id,
        )
        self.fault_changed.emit(fault_id=fault_id, enabled=True)

    def disable(self, fault_id: str) -> None:
        with self._lock:
            state = self._states.get(fault_id)
            if state is None:
                return
            state.enabled = False
        self._log(
            logging.INFO,
            "Fault disabled",
            fault_id=fault_id,
        )
        self.fault_changed.emit(fault_id=fault_id, enabled=False)

    def clear_all(self) -> None:
        with self._lock:
            for state in self._states.values():
                state.enabled = False
                state.trigger_count = 0
        self._log(logging.INFO, "All faults cleared")

    def peek(self, fault_id: str) -> Optional[FaultState]:
        with self._lock:
            state = self._states.get(fault_id)
            if state is None:
                return None
            return FaultState(
                fault_id=state.fault_id,
                enabled=state.enabled,
                trigger_count=state.trigger_count,
                config=state.config,
            )

    def consume_if_active(self, fault_id: str) -> FaultTriggerResult:
        with self._lock:
            state = self._states.get(fault_id)
            if state is None or not state.enabled:
                return FaultTriggerResult(fault_id=fault_id, triggered=False)

            state.trigger_count += 1
            defn = get_fault_definition(fault_id)
            limit = state.config.count_limit if state.config else None

            if limit is not None:
                remaining = limit - state.trigger_count
                if remaining <= 0:
                    state.enabled = False
                    self._log(
                        logging.INFO,
                        "Count-limited fault auto-disabled",
                        fault_id=fault_id,
                    )
                    self.fault_changed.emit(fault_id=fault_id, enabled=False)
                    return FaultTriggerResult(
                        fault_id=fault_id,
                        triggered=True,
                        remaining=0,
                    )
                return FaultTriggerResult(
                    fault_id=fault_id,
                    triggered=True,
                    remaining=remaining,
                )

            if defn.lifetime == FaultLifetime.ONE_SHOT:
                state.enabled = False
                self._log(
                    logging.INFO,
                    "One-shot fault auto-disabled after trigger",
                    fault_id=fault_id,
                )
                self.fault_changed.emit(fault_id=fault_id, enabled=False)
                return FaultTriggerResult(
                    fault_id=fault_id, triggered=True, remaining=0
                )

            return FaultTriggerResult(fault_id=fault_id, triggered=True, remaining=None)

    def get_active_summary(self) -> list[FaultState]:
        with self._lock:
            return [
                FaultState(
                    fault_id=s.fault_id,
                    enabled=s.enabled,
                    trigger_count=s.trigger_count,
                    config=s.config,
                )
                for s in self._states.values()
                if s.enabled
            ]

    def is_active(self, fault_id: str) -> bool:
        with self._lock:
            state = self._states.get(fault_id)
            return state.enabled if state is not None else False
