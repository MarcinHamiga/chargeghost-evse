import logging
import threading
import time
from typing import Optional

from ocpp.v201.datatypes import ComponentType, VariableType

from chargeghost_evse.ocpp_adapter.device_model.monitoring.monitor import (
    VariableMonitor,
)
from chargeghost_evse.util.event import Event


class MonitorManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._monitors: dict[int, VariableMonitor] = {}
        self._next_id = 1
        self._severity_level: int = 0
        self._monitoring_base: str = "All"
        self.on_threshold_breach = Event()
        self.logger = logging.getLogger("chargeghost.ocpp.monitoring")

    def _log(self, message: str, *, level: int = logging.INFO, **extra) -> None:
        self.logger.log(level, message, extra={"source": "ocpp", **extra})

    def set_monitor(self, monitor: VariableMonitor) -> int:
        with self._lock:
            if monitor.id == 0:
                assigned_id = self._next_id
                self._next_id += 1
                monitor = VariableMonitor(
                    id=assigned_id,
                    component=monitor.component,
                    variable=monitor.variable,
                    monitor_type=monitor.monitor_type,
                    value=monitor.value,
                    severity=monitor.severity,
                    transaction_id=monitor.transaction_id,
                    last_value=monitor.last_value,
                    next_fire_time=monitor.next_fire_time,
                )
            else:
                assigned_id = monitor.id
                if monitor.id >= self._next_id:
                    self._next_id = monitor.id + 1

            self._monitors[assigned_id] = monitor
            self._log(
                f"Monitor installed: id={assigned_id}, "
                f"type={monitor.monitor_type}, value={monitor.value}, "
                f"severity={monitor.severity}",
            )
            return assigned_id

    def clear_monitor(self, monitor_id: int) -> bool:
        with self._lock:
            if monitor_id in self._monitors:
                del self._monitors[monitor_id]
                self._log(f"Monitor cleared: id={monitor_id}")
                return True
            return False

    def get_monitor(self, monitor_id: int) -> Optional[VariableMonitor]:
        with self._lock:
            return self._monitors.get(monitor_id)

    def get_all_monitors(self) -> list[VariableMonitor]:
        with self._lock:
            return list(self._monitors.values())

    def evaluate(
        self,
        value: float,
        component: ComponentType,
        variable: VariableType,
    ) -> list[VariableMonitor]:
        breached: list[VariableMonitor] = []
        with self._lock:
            if self._monitoring_base != "All":
                return breached

            now = time.monotonic()
            updated_monitors: dict[int, VariableMonitor] = {}

            for mid, monitor in list(self._monitors.items()):
                if not self._matches_target(monitor, component, variable):
                    continue
                if monitor.severity < self._severity_level:
                    continue

                fire = False
                new_last_value = value
                new_next_fire_time = monitor.next_fire_time

                if monitor.monitor_type == "UpperThreshold":
                    if value > monitor.value:
                        fire = True

                elif monitor.monitor_type == "LowerThreshold":
                    if value < monitor.value:
                        fire = True

                elif monitor.monitor_type == "Delta":
                    if monitor.last_value is not None:
                        delta = abs(value - monitor.last_value)
                        if delta > monitor.value:
                            fire = True

                elif monitor.monitor_type == "Periodic":
                    if monitor.next_fire_time is None:
                        new_next_fire_time = now + monitor.value
                    elif now >= monitor.next_fire_time:
                        fire = True
                        new_next_fire_time = now + monitor.value

                elif monitor.monitor_type == "PeriodicClockAligned":
                    if monitor.next_fire_time is None:
                        new_next_fire_time = now + monitor.value
                    elif now >= monitor.next_fire_time:
                        fire = True
                        new_next_fire_time = now + monitor.value

                if fire:
                    breached.append(monitor)

                updated = VariableMonitor(
                    id=monitor.id,
                    component=monitor.component,
                    variable=monitor.variable,
                    monitor_type=monitor.monitor_type,
                    value=monitor.value,
                    severity=monitor.severity,
                    transaction_id=monitor.transaction_id,
                    last_value=new_last_value,
                    next_fire_time=new_next_fire_time,
                )
                updated_monitors[mid] = updated

            self._monitors.update(updated_monitors)

        if breached:
            for m in breached:
                self._log(
                    f"Threshold breached: id={m.id}, type={m.monitor_type}, "
                    f"value={value}, threshold={m.value}, severity={m.severity}",
                )
            self.on_threshold_breach.emit(monitors=breached)

        return breached

    def set_severity_level(self, level: int) -> None:
        with self._lock:
            self._severity_level = level
            self._log(f"Severity level set to {level}")

    def set_monitoring_base(self, base: str) -> None:
        with self._lock:
            self._monitoring_base = base
            self._log(f"Monitoring base set to {base}")

    @staticmethod
    def _matches_target(
        monitor: VariableMonitor,
        component: ComponentType,
        variable: VariableType,
    ) -> bool:
        if monitor.component.name != component.name:
            return False
        if monitor.component.evse is not None and component.evse is not None:
            if monitor.component.evse.id != component.evse.id:
                return False
        elif monitor.component.evse is not component.evse:
            return False
        if monitor.variable.name != variable.name:
            return False
        return True
