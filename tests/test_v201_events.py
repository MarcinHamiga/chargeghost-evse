import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from ocpp.v201.datatypes import ComponentType, EVSEType, VariableType
from ocpp.v201.enums import EventNotificationEnumType, EventTriggerEnumType

from chargeghost_evse.ocpp_adapter.device_model.monitoring import (
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
) -> VariableMonitor:
    return VariableMonitor(
        id=monitor_id,
        component=component or _make_component(),
        variable=variable or _make_variable(),
        monitor_type=monitor_type,
        value=value,
        severity=severity,
        transaction_id=transaction_id,
    )


class TestSendNotifyEvent:
    def test_send_notify_event_basic(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        response = asyncio.run(
            adapter.send_notify_event(
                connector_id=1,
                event_id=42,
                trigger=EventTriggerEnumType.alerting,
                actual_value="Faulted",
                event_notification_type=EventNotificationEnumType.custom_monitor,
                component_name="EVSE",
                variable_name="FaultState",
                severity=5,
            )
        )
        assert response == mock_response
        adapter.call.assert_awaited_once()

        request = adapter.call.call_args[0][0]
        assert request.seq_no == 42
        assert len(request.event_data) == 1
        ed = request.event_data[0]
        assert ed.event_id == 42
        assert ed.trigger == EventTriggerEnumType.alerting
        assert ed.actual_value == "Faulted"
        assert ed.event_notification_type == EventNotificationEnumType.custom_monitor
        assert ed.component.name == "EVSE"
        assert ed.variable.name == "FaultState"
        assert ed.cause == 5

    def test_send_notify_event_auto_assigns_event_id(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_notify_event(
                connector_id=1,
                trigger=EventTriggerEnumType.alerting,
                actual_value="100.0",
                event_notification_type=EventNotificationEnumType.custom_monitor,
                component_name="Connector",
                variable_name="Power.Active.Import",
                severity=3,
            )
        )

        request = adapter.call.call_args[0][0]
        assert request.event_data[0].event_id == 1
        assert request.seq_no == 1
        assert adapter._event_seq_no == 1

    def test_send_notify_event_increments_seq_no(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_notify_event(
                connector_id=1,
                event_id=10,
                trigger=EventTriggerEnumType.alerting,
                actual_value="test",
            )
        )
        asyncio.run(
            adapter.send_notify_event(
                connector_id=1,
                event_id=20,
                trigger=EventTriggerEnumType.alerting,
                actual_value="test",
            )
        )

        first_request = adapter.call.call_args_list[0][0][0]
        second_request = adapter.call.call_args_list[1][0][0]
        assert first_request.event_data[0].event_id == 10
        assert second_request.event_data[0].event_id == 20

    def test_send_notify_event_with_explicit_event_id_uses_it(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_notify_event(
                connector_id=2,
                event_id=99,
                trigger=EventTriggerEnumType.alerting,
                actual_value="test",
            )
        )

        request = adapter.call.call_args[0][0]
        assert request.event_data[0].event_id == 99

    def test_send_notify_event_default_params(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(adapter.send_notify_event(connector_id=1))

        request = adapter.call.call_args[0][0]
        ed = request.event_data[0]
        assert ed.trigger == EventTriggerEnumType.alerting
        assert ed.actual_value == ""
        assert ed.component.name == "EVSE"
        assert ed.variable.name == ""
        assert ed.cause == 0
        assert ed.cleared is False
        assert ed.variable_monitoring_id is None
        assert ed.transaction_id is None
        assert ed.tech_code is None
        assert ed.tech_info is None

    def test_send_notify_event_with_all_optional_fields(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_notify_event(
                connector_id=1,
                event_id=1,
                trigger=EventTriggerEnumType.alerting,
                actual_value="85.5",
                event_notification_type=EventNotificationEnumType.custom_monitor,
                component_name="TemperatureSensor",
                variable_name="Temperature",
                severity=7,
                transaction_id="tx_123",
                tech_code="OverTemperature",
                tech_info="Sensor reading exceeded limit",
                cleared=True,
                variable_monitoring_id=5,
            )
        )

        request = adapter.call.call_args[0][0]
        ed = request.event_data[0]
        assert ed.cause == 7
        assert ed.transaction_id == "tx_123"
        assert ed.tech_code == "OverTemperature"
        assert ed.tech_info == "Sensor reading exceeded limit"
        assert ed.cleared is True
        assert ed.variable_monitoring_id == 5

    def test_send_notify_event_component_has_evse(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_notify_event(
                connector_id=3,
                event_id=1,
                component_name="Connector",
            )
        )

        request = adapter.call.call_args[0][0]
        ed = request.event_data[0]
        assert ed.component.evse.id == 3
        assert ed.component.evse.connector_id == 1


class TestSendEventNotification:
    def test_send_event_notification_delegates_to_send_notify_event(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_event_notification(
                connector_id=1,
                trigger=EventTriggerEnumType.alerting,
                actual_value="50.0",
                event_notification_type=EventNotificationEnumType.custom_monitor,
                component_name="Connector",
                variable_name="Power.Active.Import",
                severity=5,
            )
        )

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        ed = request.event_data[0]
        assert ed.trigger == EventTriggerEnumType.alerting
        assert ed.actual_value == "50.0"
        assert ed.event_notification_type == EventNotificationEnumType.custom_monitor
        assert ed.component.name == "Connector"
        assert ed.variable.name == "Power.Active.Import"
        assert ed.cause == 5

    def test_send_event_notification_auto_assigns_event_id(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_event_notification(
                connector_id=1,
                trigger=EventTriggerEnumType.alerting,
                actual_value="test",
                event_notification_type=EventNotificationEnumType.hard_wired_monitor,
                component_name="EVSE",
                variable_name="Status",
            )
        )

        request = adapter.call.call_args[0][0]
        assert request.event_data[0].event_id == 1


class TestOnMonitorThresholdBreach:
    def test_threshold_breach_schedules_notify_event(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        comp = _make_component(name="Connector", evse_id=1)
        var = _make_variable(name="Power.Active.Import")
        monitor = _make_monitor(
            monitor_id=1,
            monitor_type="UpperThreshold",
            value=100.0,
            severity=5,
            component=comp,
            variable=var,
        )

        asyncio.run(self._run_breach(adapter, [monitor]))

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        ed = request.event_data[0]
        assert ed.trigger == EventTriggerEnumType.alerting
        assert ed.event_notification_type == EventNotificationEnumType.custom_monitor
        assert ed.component.name == "Connector"
        assert ed.variable.name == "Power.Active.Import"
        assert ed.cause == 5
        assert ed.actual_value == "100.0"
        assert ed.variable_monitoring_id == 1

    def test_threshold_breach_multiple_monitors(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        comp1 = _make_component(name="Connector", evse_id=1)
        var1 = _make_variable(name="Power.Active.Import")
        m1 = _make_monitor(
            monitor_id=1, value=100.0, severity=5, component=comp1, variable=var1
        )

        comp2 = _make_component(name="Connector", evse_id=2)
        var2 = _make_variable(name="Temperature")
        m2 = _make_monitor(
            monitor_id=2,
            monitor_type="LowerThreshold",
            value=10.0,
            severity=3,
            component=comp2,
            variable=var2,
        )

        asyncio.run(self._run_breach(adapter, [m1, m2]))

        assert adapter.call.await_count == 2

        req1 = adapter.call.call_args_list[0][0][0]
        assert req1.event_data[0].component.evse.id == 1
        assert req1.event_data[0].variable_monitoring_id == 1

        req2 = adapter.call.call_args_list[1][0][0]
        assert req2.event_data[0].component.evse.id == 2
        assert req2.event_data[0].variable_monitoring_id == 2

    def test_threshold_breach_with_transaction_id(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        comp = _make_component(name="Connector", evse_id=1)
        var = _make_variable(name="Energy.Active.Import.Register")
        monitor = _make_monitor(
            monitor_id=3,
            value=50000.0,
            severity=7,
            component=comp,
            variable=var,
            transaction_id="tx_abc",
        )

        asyncio.run(self._run_breach(adapter, [monitor]))

        request = adapter.call.call_args[0][0]
        ed = request.event_data[0]
        assert ed.transaction_id == "tx_abc"
        assert ed.actual_value == "50000.0"
        assert ed.cause == 7

    def test_threshold_breach_no_evse_defaults_to_zero(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        comp = ComponentType(name="ChargingStation")
        var = _make_variable()
        monitor = _make_monitor(
            monitor_id=4, value=10.0, severity=2, component=comp, variable=var
        )

        asyncio.run(self._run_breach(adapter, [monitor]))

        request = adapter.call.call_args[0][0]
        ed = request.event_data[0]
        assert ed.component.evse.id == 0

    def test_monitor_manager_subscribed_on_init(self):
        adapter = _make_adapter()
        assert len(adapter.monitor_manager.on_threshold_breach.callbacks) > 0

    def test_monitor_manager_breach_triggers_notify_event(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        comp = _make_component(name="Connector", evse_id=1)
        var = _make_variable(name="Power.Active.Import")
        adapter.monitor_manager.set_monitor(
            _make_monitor(
                monitor_id=0, monitor_type="UpperThreshold", value=50.0, severity=4
            )
        )

        asyncio.run(self._run_evaluate(adapter, 75.0, comp, var))

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        ed = request.event_data[0]
        assert ed.event_notification_type == EventNotificationEnumType.custom_monitor
        assert ed.variable_monitoring_id == 1

    @staticmethod
    async def _run_breach(
        adapter: V201Adapter, monitors: list[VariableMonitor]
    ) -> None:
        tasks = []
        original_create = asyncio.create_task

        def tracking_create_task(coro, **kwargs):
            task = original_create(coro, **kwargs)
            tasks.append(task)
            return task

        with patch("asyncio.create_task", side_effect=tracking_create_task):
            adapter._on_monitor_threshold_breach(monitors)
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _run_evaluate(
        adapter: V201Adapter,
        value: float,
        component: ComponentType,
        variable: VariableType,
    ) -> None:
        tasks = []
        original_create = asyncio.create_task

        def tracking_create_task(coro, **kwargs):
            task = original_create(coro, **kwargs)
            tasks.append(task)
            return task

        with patch("asyncio.create_task", side_effect=tracking_create_task):
            adapter.monitor_manager.evaluate(value, component, variable)
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)


class TestFaultNotifyEvent:
    def test_fault_event_via_send_notify_event(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_notify_event(
                connector_id=1,
                trigger=EventTriggerEnumType.alerting,
                actual_value="Faulted",
                event_notification_type=EventNotificationEnumType.custom_monitor,
                component_name="EVSE",
                variable_name="FaultState",
                severity=5,
            )
        )

        request = adapter.call.call_args[0][0]
        ed = request.event_data[0]
        assert ed.trigger == EventTriggerEnumType.alerting
        assert ed.actual_value == "Faulted"
        assert ed.event_notification_type == EventNotificationEnumType.custom_monitor
        assert ed.cause == 5

    def test_event_id_counter_independent_of_monitor_seq(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        asyncio.run(
            adapter.send_notify_event(
                connector_id=1,
                event_id=1,
                trigger=EventTriggerEnumType.alerting,
                actual_value="test",
            )
        )

        assert adapter._event_seq_no == 1
        assert adapter._monitor_seq_no == 0
