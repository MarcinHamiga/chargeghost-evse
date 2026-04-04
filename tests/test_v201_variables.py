import asyncio
from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.ocpp_adapter.device_model.component import Component
from chargeghost_evse.ocpp_adapter.device_model.device_model import (
    ChargingStationDeviceModel,
)
from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter
from ocpp.v201.datatypes import (
    ComponentType,
    EVSEType,
    VariableType,
)
from ocpp.v201.enums import (
    AttributeEnumType,
    GetVariableStatusEnumType,
    SetVariableStatusEnumType,
)


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


def _make_get_request(
    component_name: str,
    variable_name: str,
    evse_id: int = None,
    attribute_type=None,
) -> dict:
    component = ComponentType(name=component_name)
    if evse_id is not None:
        component.evse = EVSEType(id=evse_id, connector_id=1)
    variable = VariableType(name=variable_name)
    item: dict = {"component": component, "variable": variable}
    if attribute_type is not None:
        item["attribute_type"] = attribute_type
    return item


def _make_set_request(
    component_name: str,
    variable_name: str,
    attribute_value: str,
    evse_id: int = None,
    attribute_type=None,
) -> dict:
    component = ComponentType(name=component_name)
    if evse_id is not None:
        component.evse = EVSEType(id=evse_id, connector_id=1)
    variable = VariableType(name=variable_name)
    item: dict = {
        "attribute_value": attribute_value,
        "component": component,
        "variable": variable,
    }
    if attribute_type is not None:
        item["attribute_type"] = attribute_type
    return item


class TestV201AdapterDeviceModel:
    def test_device_model_created_on_init(self):
        adapter = _make_adapter()
        assert isinstance(adapter.device_model, ChargingStationDeviceModel)

    def test_device_model_has_components(self):
        adapter = _make_adapter()
        components = adapter.device_model.get_components()
        names = [c.name for c in components]
        assert "TxCtrlr" in names
        assert "EVSE" in names
        assert "Connector" in names

    def test_on_variable_changed_event_exists(self):
        adapter = _make_adapter()
        assert hasattr(adapter.device_model, "on_variable_changed")


class TestGetVariables:
    def test_get_existing_variable(self):
        adapter = _make_adapter()
        requests = [_make_get_request("TxCtrlr", "Enabled")]
        result = asyncio.run(adapter.on_get_variables(get_variable_data=requests))
        assert len(result.get_variable_result) == 1
        r = result.get_variable_result[0]
        assert r.attribute_status == GetVariableStatusEnumType.accepted
        assert r.attribute_value == "true"

    def test_get_variable_with_target_attribute_not_found(self):
        adapter = _make_adapter()
        requests = [
            _make_get_request(
                "TxCtrlr", "Enabled", attribute_type=AttributeEnumType.target
            )
        ]
        result = asyncio.run(adapter.on_get_variables(get_variable_data=requests))
        assert result.get_variable_result[0].attribute_status == (
            GetVariableStatusEnumType.not_supported_attribute_type
        )

    def test_get_unknown_component(self):
        adapter = _make_adapter()
        requests = [_make_get_request("NonExistent", "Foo")]
        result = asyncio.run(adapter.on_get_variables(get_variable_data=requests))
        assert result.get_variable_result[0].attribute_status == (
            GetVariableStatusEnumType.unknown_component
        )

    def test_get_unknown_variable(self):
        adapter = _make_adapter()
        requests = [_make_get_request("TxCtrlr", "NonExistentVar")]
        result = asyncio.run(adapter.on_get_variables(get_variable_data=requests))
        assert result.get_variable_result[0].attribute_status == (
            GetVariableStatusEnumType.unknown_variable
        )

    def test_get_with_evse_scoping(self):
        adapter = _make_adapter()
        requests = [_make_get_request("EVSE", "Available", evse_id=1)]
        result = asyncio.run(adapter.on_get_variables(get_variable_data=requests))
        assert result.get_variable_result[0].attribute_status == (
            GetVariableStatusEnumType.accepted
        )
        assert result.get_variable_result[0].attribute_value == "true"

    def test_get_evse_scoping_wrong_id(self):
        adapter = _make_adapter()
        requests = [_make_get_request("EVSE", "Available", evse_id=99)]
        result = asyncio.run(adapter.on_get_variables(get_variable_data=requests))
        assert result.get_variable_result[0].attribute_status == (
            GetVariableStatusEnumType.unknown_component
        )

    def test_get_multiple_items_mixed_results(self):
        adapter = _make_adapter()
        requests = [
            _make_get_request("TxCtrlr", "Enabled"),
            _make_get_request("NonExistent", "Foo"),
            _make_get_request("EVSE", "Available", evse_id=1),
        ]
        result = asyncio.run(adapter.on_get_variables(get_variable_data=requests))
        assert len(result.get_variable_result) == 3
        assert result.get_variable_result[0].attribute_status == (
            GetVariableStatusEnumType.accepted
        )
        assert result.get_variable_result[1].attribute_status == (
            GetVariableStatusEnumType.unknown_component
        )
        assert result.get_variable_result[2].attribute_status == (
            GetVariableStatusEnumType.accepted
        )

    def test_get_default_attribute_is_actual(self):
        adapter = _make_adapter()
        requests = [_make_get_request("TxCtrlr", "Enabled")]
        result = asyncio.run(adapter.on_get_variables(get_variable_data=requests))
        assert result.get_variable_result[0].attribute_type == AttributeEnumType.actual

    def test_get_connector_variable(self):
        adapter = _make_adapter()
        requests = [_make_get_request("Connector", "Enabled", evse_id=1)]
        result = asyncio.run(adapter.on_get_variables(get_variable_data=requests))
        assert result.get_variable_result[0].attribute_status == (
            GetVariableStatusEnumType.accepted
        )
        assert result.get_variable_result[0].attribute_value == "true"


class TestSetVariables:
    def test_set_writable_variable(self):
        adapter = _make_adapter()
        requests = [_make_set_request("TxCtrlr", "Enabled", "false")]
        result = asyncio.run(adapter.on_set_variables(set_variable_data=requests))
        assert len(result.set_variable_result) == 1
        assert result.set_variable_result[0].attribute_status == (
            SetVariableStatusEnumType.accepted
        )
        attr = adapter.device_model.get_variable(
            Component(name="TxCtrlr"), "Enabled", "Actual"
        )
        assert attr is not None
        assert attr.value == "false"

    def test_set_readonly_variable_rejected(self):
        adapter = _make_adapter()
        requests = [_make_set_request("Meter", "MeterType", "DC")]
        result = asyncio.run(adapter.on_set_variables(set_variable_data=requests))
        assert result.set_variable_result[0].attribute_status == (
            SetVariableStatusEnumType.rejected
        )
        assert (
            result.set_variable_result[0].attribute_status_info.reason_code
            == "ReadOnly"
        )

    def test_set_unknown_component(self):
        adapter = _make_adapter()
        requests = [_make_set_request("NonExistent", "Foo", "bar")]
        result = asyncio.run(adapter.on_set_variables(set_variable_data=requests))
        assert result.set_variable_result[0].attribute_status == (
            SetVariableStatusEnumType.unknown_component
        )

    def test_set_unknown_variable(self):
        adapter = _make_adapter()
        requests = [_make_set_request("TxCtrlr", "NonExistent", "bar")]
        result = asyncio.run(adapter.on_set_variables(set_variable_data=requests))
        assert result.set_variable_result[0].attribute_status == (
            SetVariableStatusEnumType.unknown_variable
        )

    def test_set_unsupported_attribute_type(self):
        adapter = _make_adapter()
        requests = [
            _make_set_request(
                "TxCtrlr",
                "Enabled",
                "false",
                attribute_type=AttributeEnumType.target,
            )
        ]
        result = asyncio.run(adapter.on_set_variables(set_variable_data=requests))
        assert result.set_variable_result[0].attribute_status == (
            SetVariableStatusEnumType.not_supported_attribute_type
        )

    def test_set_evse_scoped_variable(self):
        adapter = _make_adapter()
        requests = [_make_set_request("EVSE", "Available", "false", evse_id=1)]
        result = asyncio.run(adapter.on_set_variables(set_variable_data=requests))
        assert result.set_variable_result[0].attribute_status == (
            SetVariableStatusEnumType.accepted
        )
        attr = adapter.device_model.get_variable(
            Component(name="EVSE", evse_id=1), "Available", "Actual"
        )
        assert attr is not None
        assert attr.value == "false"

    def test_set_emits_variable_changed_event(self):
        adapter = _make_adapter()
        captured = []
        handler = lambda **kw: captured.append(kw)
        unsub = adapter.device_model.on_variable_changed.subscribe(handler)
        requests = [_make_set_request("TxCtrlr", "Enabled", "false")]
        asyncio.run(adapter.on_set_variables(set_variable_data=requests))
        unsub()
        assert len(captured) == 1
        assert captured[0]["old_value"] == "true"
        assert captured[0]["new_value"] == "false"

    def test_set_multiple_items_mixed_results(self):
        adapter = _make_adapter()
        requests = [
            _make_set_request("TxCtrlr", "Enabled", "false"),
            _make_set_request("Meter", "MeterType", "DC"),
            _make_set_request("EVSE", "Enabled", "false", evse_id=1),
        ]
        result = asyncio.run(adapter.on_set_variables(set_variable_data=requests))
        assert len(result.set_variable_result) == 3
        assert result.set_variable_result[0].attribute_status == (
            SetVariableStatusEnumType.accepted
        )
        assert result.set_variable_result[1].attribute_status == (
            SetVariableStatusEnumType.rejected
        )
        assert result.set_variable_result[2].attribute_status == (
            SetVariableStatusEnumType.accepted
        )
