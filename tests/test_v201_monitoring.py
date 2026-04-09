import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from ocpp.v201.datatypes import ComponentType, EVSEType, VariableType
from ocpp.v201.enums import (
    ClearMonitoringStatusEnumType,
    GenericDeviceModelStatusEnumType,
    GenericStatusEnumType,
    MonitorEnumType,
    MonitorBaseEnumType,
    SetMonitoringStatusEnumType,
)

from chargeghost_evse.ocpp_adapter.device_model.monitoring import (
    MonitorManager,
    VariableMonitor,
)
from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter


def _make_adapter(**overrides) -> V201Adapter:
    mock_conn = MagicMock()
    mock_conn.recv = AsyncMock()
    mock_conn.send = AsyncMock()
    kwargs = {
        "id": "CP_1",
        "connection": mock_conn,
        "command_queue": MagicMock(),
        "charge_point_model": "ChargeGhostV2",
        "charge_point_vendor": "ChargeGhost",
    }
    kwargs.update(overrides)
    return V201Adapter(**kwargs)


def _make_component(name: str = "Connector", evse_id: int = 1) -> ComponentType:
    return ComponentType(name=name, evse=EVSEType(id=evse_id, connector_id=1))


def _make_variable(name: str = "Power.Active.Import") -> VariableType:
    return VariableType(name=name)


def _make_monitor(
    monitor_id: int = 0,
    monitor_type: str = "UpperThreshold",
    value: float = 100.0,
    severity: int = 5,
    component: ComponentType | None = None,
    variable: VariableType | None = None,
    transaction_id: str | None = None,
    last_value: float | None = None,
) -> VariableMonitor:
    return VariableMonitor(
        id=monitor_id,
        component=component or _make_component(),
        variable=variable or _make_variable(),
        monitor_type=monitor_type,
        value=value,
        severity=severity,
        transaction_id=transaction_id,
        last_value=last_value,
    )


class TestVariableMonitor:
    def test_create_with_defaults(self):
        m = _make_monitor(monitor_id=1)
        assert m.id == 1
        assert m.monitor_type == "UpperThreshold"
        assert m.value == 100.0
        assert m.severity == 5
        assert m.transaction_id is None
        assert m.last_value is None
        assert m.next_fire_time is None

    def test_severity_validation(self):
        with pytest.raises(ValueError, match="severity"):
            _make_monitor(monitor_id=1, severity=10)
        with pytest.raises(ValueError, match="severity"):
            _make_monitor(monitor_id=1, severity=-1)

    def test_valid_severity(self):
        m = _make_monitor(monitor_id=1, severity=0)
        assert m.severity == 0
        m = _make_monitor(monitor_id=2, severity=9)
        assert m.severity == 9

    def test_to_variable_monitoring_type(self):
        m = _make_monitor(monitor_id=42, monitor_type="Delta", severity=3)
        vm = m.to_variable_monitoring_type(transaction=True)
        assert vm.id == 42
        assert vm.transaction is True
        assert vm.value == 100.0
        assert vm.type == MonitorEnumType.delta
        assert vm.severity == 3

    def test_frozen(self):
        m = _make_monitor(monitor_id=1)
        with pytest.raises(AttributeError):
            m.id = 99


class TestMonitorManager:
    def test_set_monitor_auto_assigns_id(self):
        mgr = MonitorManager()
        m1 = _make_monitor(monitor_id=0)
        id1 = mgr.set_monitor(m1)
        assert id1 == 1

        m2 = _make_monitor(monitor_id=0)
        id2 = mgr.set_monitor(m2)
        assert id2 == 2

    def test_set_monitor_with_provided_id(self):
        mgr = MonitorManager()
        m = _make_monitor(monitor_id=100)
        assigned = mgr.set_monitor(m)
        assert assigned == 100

        m2 = _make_monitor(monitor_id=0)
        id2 = mgr.set_monitor(m2)
        assert id2 == 101

    def test_clear_monitor(self):
        mgr = MonitorManager()
        m = _make_monitor(monitor_id=0)
        mid = mgr.set_monitor(m)
        assert mgr.clear_monitor(mid) is True
        assert mgr.clear_monitor(mid) is False

    def test_get_monitor(self):
        mgr = MonitorManager()
        m = _make_monitor(monitor_id=0)
        mid = mgr.set_monitor(m)
        result = mgr.get_monitor(mid)
        assert result is not None
        assert result.id == mid

    def test_get_monitor_not_found(self):
        mgr = MonitorManager()
        assert mgr.get_monitor(999) is None

    def test_get_all_monitors(self):
        mgr = MonitorManager()
        mgr.set_monitor(_make_monitor(monitor_id=0))
        mgr.set_monitor(_make_monitor(monitor_id=0))
        assert len(mgr.get_all_monitors()) == 2

    def test_evaluate_upper_threshold_breach(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(monitor_id=0, monitor_type="UpperThreshold", value=50.0)
        )

        breached = mgr.evaluate(75.0, comp, var)
        assert len(breached) == 1
        assert breached[0].monitor_type == "UpperThreshold"

    def test_evaluate_upper_threshold_no_breach(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(monitor_id=0, monitor_type="UpperThreshold", value=50.0)
        )

        breached = mgr.evaluate(25.0, comp, var)
        assert len(breached) == 0

    def test_evaluate_lower_threshold_breach(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(monitor_id=0, monitor_type="LowerThreshold", value=10.0)
        )

        breached = mgr.evaluate(5.0, comp, var)
        assert len(breached) == 1

    def test_evaluate_delta_breach(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(
                monitor_id=0, monitor_type="Delta", value=5.0, last_value=10.0
            )
        )

        breached = mgr.evaluate(20.0, comp, var)
        assert len(breached) == 1

    def test_evaluate_delta_no_breach(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(
                monitor_id=0, monitor_type="Delta", value=5.0, last_value=10.0
            )
        )

        breached = mgr.evaluate(12.0, comp, var)
        assert len(breached) == 0

    def test_evaluate_no_match_different_component(self):
        mgr = MonitorManager()
        comp = _make_component(name="TemperatureSensor")
        var = _make_variable(name="Temperature")
        mgr.set_monitor(
            _make_monitor(
                monitor_id=0,
                monitor_type="UpperThreshold",
                value=50.0,
                component=comp,
                variable=var,
            )
        )

        wrong_comp = _make_component(name="Connector")
        wrong_var = _make_variable()
        breached = mgr.evaluate(75.0, wrong_comp, wrong_var)
        assert len(breached) == 0

    def test_evaluate_no_match_different_evse(self):
        mgr = MonitorManager()
        comp = _make_component(evse_id=1)
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(
                monitor_id=0,
                monitor_type="UpperThreshold",
                value=50.0,
                component=comp,
            )
        )

        comp2 = _make_component(evse_id=2)
        breached = mgr.evaluate(75.0, comp2, var)
        assert len(breached) == 0

    def test_severity_level_filter(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(
                monitor_id=0, monitor_type="UpperThreshold", value=50.0, severity=3
            )
        )
        mgr.set_monitor(
            _make_monitor(
                monitor_id=0, monitor_type="UpperThreshold", value=50.0, severity=7
            )
        )

        mgr.set_severity_level(5)
        breached = mgr.evaluate(75.0, comp, var)
        assert len(breached) == 1
        assert breached[0].severity == 7

    def test_monitoring_base_filter(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(monitor_id=0, monitor_type="UpperThreshold", value=50.0)
        )

        mgr.set_monitoring_base("FactoryDefault")
        breached = mgr.evaluate(75.0, comp, var)
        assert len(breached) == 0

    def test_evaluate_updates_last_value(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(_make_monitor(monitor_id=0, monitor_type="Delta", value=5.0))

        mgr.evaluate(10.0, comp, var)
        monitor = mgr.get_monitor(1)
        assert monitor is not None
        assert monitor.last_value == 10.0

    def test_evaluate_periodic_sets_next_fire_time(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(monitor_id=0, monitor_type="Periodic", value=60.0)
        )

        breached = mgr.evaluate(10.0, comp, var)
        assert len(breached) == 0

        monitor = mgr.get_monitor(1)
        assert monitor is not None
        assert monitor.next_fire_time is not None

    def test_evaluate_periodic_fires_after_interval(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(monitor_id=0, monitor_type="Periodic", value=0.001)
        )

        mgr.evaluate(10.0, comp, var)
        time.sleep(0.002)
        breached = mgr.evaluate(10.0, comp, var)
        assert len(breached) == 1

    def test_on_threshold_breach_event(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(monitor_id=0, monitor_type="UpperThreshold", value=50.0)
        )

        received = []

        def _handler(monitors: list[VariableMonitor]) -> None:
            received.append(monitors)

        mgr.on_threshold_breach.subscribe(_handler)

        mgr.evaluate(75.0, comp, var)
        assert len(received) == 1
        assert len(received[0]) == 1

    def test_on_threshold_breach_not_emitted_without_breach(self):
        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()
        mgr.set_monitor(
            _make_monitor(monitor_id=0, monitor_type="UpperThreshold", value=50.0)
        )

        received = []

        def _handler(monitors: list[VariableMonitor]) -> None:
            received.append(monitors)

        mgr.on_threshold_breach.subscribe(_handler)

        mgr.evaluate(25.0, comp, var)
        assert len(received) == 0


class TestV201AdapterMonitoringHandlers:
    def test_adapter_has_monitor_manager(self):
        adapter = _make_adapter()
        assert adapter.monitor_manager is not None
        assert isinstance(adapter.monitor_manager, MonitorManager)

    def test_on_set_variable_monitoring_auto_assigns_id(self):
        adapter = _make_adapter()
        comp = _make_component()
        var = _make_variable()

        item = MagicMock()
        item.component = comp
        item.variable = var
        item.type = MonitorEnumType.upper_threshold
        item.severity = 5
        item.value = 100.0
        item.id = None
        item.transaction = False

        result = asyncio.run(
            adapter.on_set_variable_monitoring(set_monitoring_data=[item])
        )
        assert len(result.set_monitoring_result) == 1
        sr = result.set_monitoring_result[0]
        assert sr.status == SetMonitoringStatusEnumType.accepted
        assert sr.id == 1

    def test_on_set_variable_monitoring_with_provided_id(self):
        adapter = _make_adapter()
        comp = _make_component()
        var = _make_variable()

        item = MagicMock()
        item.component = comp
        item.variable = var
        item.type = MonitorEnumType.lower_threshold
        item.severity = 3
        item.value = 10.0
        item.id = 42
        item.transaction = False

        result = asyncio.run(
            adapter.on_set_variable_monitoring(set_monitoring_data=[item])
        )
        sr = result.set_monitoring_result[0]
        assert sr.status == SetMonitoringStatusEnumType.accepted
        assert sr.id == 42

    def test_on_set_variable_monitoring_invalid_severity(self):
        adapter = _make_adapter()
        comp = _make_component()
        var = _make_variable()

        item = MagicMock()
        item.component = comp
        item.variable = var
        item.type = MonitorEnumType.upper_threshold
        item.severity = 15
        item.value = 100.0
        item.id = None
        item.transaction = False

        result = asyncio.run(
            adapter.on_set_variable_monitoring(set_monitoring_data=[item])
        )
        sr = result.set_monitoring_result[0]
        assert sr.status == SetMonitoringStatusEnumType.rejected

    def test_on_clear_variable_monitoring(self):
        adapter = _make_adapter()
        comp = _make_component()
        var = _make_variable()

        item = MagicMock()
        item.component = comp
        item.variable = var
        item.type = MonitorEnumType.upper_threshold
        item.severity = 5
        item.value = 100.0
        item.id = None
        item.transaction = False

        asyncio.run(adapter.on_set_variable_monitoring(set_monitoring_data=[item]))

        result = asyncio.run(adapter.on_clear_variable_monitoring(id=[1]))
        assert len(result.clear_monitoring_result) == 1
        assert (
            result.clear_monitoring_result[0] == ClearMonitoringStatusEnumType.accepted
        )

    def test_on_clear_variable_monitoring_not_found(self):
        adapter = _make_adapter()

        result = asyncio.run(adapter.on_clear_variable_monitoring(id=[999]))
        assert (
            result.clear_monitoring_result[0] == ClearMonitoringStatusEnumType.not_found
        )

    def test_on_get_monitoring_report_with_monitors(self):
        adapter = _make_adapter()
        comp = _make_component()
        var = _make_variable()

        item = MagicMock()
        item.component = comp
        item.variable = var
        item.type = MonitorEnumType.periodic
        item.severity = 2
        item.value = 60.0
        item.id = None
        item.transaction = False

        asyncio.run(adapter.on_set_variable_monitoring(set_monitoring_data=[item]))

        result = asyncio.run(adapter.on_get_monitoring_report(request_id=42))
        assert result.status == GenericDeviceModelStatusEnumType.accepted

    def test_on_get_monitoring_report_empty(self):
        adapter = _make_adapter()

        result = asyncio.run(adapter.on_get_monitoring_report(request_id=42))
        assert result.status == GenericDeviceModelStatusEnumType.empty_result_set

    def test_on_set_monitoring_base(self):
        adapter = _make_adapter()

        result = asyncio.run(
            adapter.on_set_monitoring_base(monitoring_base=MonitorBaseEnumType.all)
        )
        assert result.status == GenericDeviceModelStatusEnumType.accepted
        assert adapter.monitor_manager._monitoring_base == "All"

    def test_on_set_monitoring_level(self):
        adapter = _make_adapter()

        result = asyncio.run(adapter.on_set_monitoring_level(severity=5))
        assert result.status == GenericStatusEnumType.accepted
        assert adapter.monitor_manager._severity_level == 5

    def test_send_notify_monitoring_report(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        comp = _make_component()
        var = _make_variable()
        monitors = [
            _make_monitor(monitor_id=1, component=comp, variable=var),
            _make_monitor(
                monitor_id=2, component=comp, variable=var, monitor_type="Delta"
            ),
        ]

        response = asyncio.run(
            adapter.send_notify_monitoring_report(request_id=42, monitors=monitors)
        )
        assert response == mock_response
        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.request_id == 42
        assert request.seq_no == 1
        assert len(request.monitor) == 2

    def test_send_notify_monitoring_report_empty(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        response = asyncio.run(
            adapter.send_notify_monitoring_report(request_id=42, monitors=[])
        )
        assert response == mock_response
        request = adapter.call.call_args[0][0]
        assert request.monitor is None

    def test_send_notify_monitoring_report_increments_seq_no(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        comp = _make_component()
        var = _make_variable()

        asyncio.run(
            adapter.send_notify_monitoring_report(
                request_id=1,
                monitors=[_make_monitor(monitor_id=1, component=comp, variable=var)],
            )
        )
        asyncio.run(
            adapter.send_notify_monitoring_report(
                request_id=2,
                monitors=[_make_monitor(monitor_id=2, component=comp, variable=var)],
            )
        )

        assert adapter._monitor_seq_no == 2


class TestMonitorManagerThreadSafety:
    def test_concurrent_set_and_evaluate(self):
        import threading

        mgr = MonitorManager()
        comp = _make_component()
        var = _make_variable()

        errors = []

        def set_monitors():
            try:
                for i in range(100):
                    mgr.set_monitor(
                        _make_monitor(
                            monitor_id=0,
                            monitor_type="UpperThreshold",
                            value=50.0,
                            severity=i % 10,
                        )
                    )
            except Exception as e:
                errors.append(e)

        def evaluate():
            try:
                for _ in range(100):
                    mgr.evaluate(75.0, comp, var)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=set_monitors)
        t2 = threading.Thread(target=evaluate)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0

    def test_concurrent_clear_and_get_all(self):
        import threading

        mgr = MonitorManager()
        for i in range(50):
            mgr.set_monitor(_make_monitor(monitor_id=0))

        errors = []

        def clear():
            try:
                for i in range(1, 51):
                    mgr.clear_monitor(i)
            except Exception as e:
                errors.append(e)

        def get_all():
            try:
                for _ in range(50):
                    mgr.get_all_monitors()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=clear)
        t2 = threading.Thread(target=get_all)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0
