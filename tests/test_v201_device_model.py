import pytest

from chargeghost_evse.ocpp_adapter.device_model import (
    ChargingStationDeviceModel,
    Component,
    ConnectorComponent,
    EVSEComponent,
    ReportBuilder,
    Variable,
    VariableAttribute,
    VariableCharacteristics,
)
from ocpp.v201.datatypes import VariableType
from ocpp.v201.enums import ComponentCriterionEnumType, ReportBaseEnumType


class TestComponent:
    def test_frozen_component(self):
        comp = Component(name="TxCtrlr")
        assert comp.name == "TxCtrlr"
        assert comp.instance is None
        assert comp.evse_id is None
        assert comp.connector_id is None

    def test_component_with_all_fields(self):
        comp = Component(name="Connector", evse_id=1, connector_id=1)
        assert comp.name == "Connector"
        assert comp.evse_id == 1
        assert comp.connector_id == 1

    def test_component_hashable(self):
        comp1 = Component(name="TxCtrlr")
        comp2 = Component(name="TxCtrlr")
        assert comp1 == comp2
        assert hash(comp1) == hash(comp2)

    def test_component_immutability(self):
        comp = Component(name="TxCtrlr")
        with pytest.raises(AttributeError):
            comp.name = "Other"

    def test_component_in_dict(self):
        comp1 = Component(name="TxCtrlr")
        comp2 = Component(name="TxCtrlr")
        d: dict[Component, str] = {comp1: "value"}
        assert d[comp2] == "value"

    def test_evse_component_with_connectors(self):
        conn = ConnectorComponent(name="Connector", evse_id=1, connector_id=1)
        evse = EVSEComponent(name="EVSE", evse_id=1, connectors=(conn,))
        assert evse.evse_id == 1
        assert len(evse.connectors) == 1
        assert evse.connectors[0].connector_id == 1

    def test_evse_component_equals_plain_component(self):
        evse = EVSEComponent(name="EVSE", evse_id=1, connectors=(Component(name="x"),))
        comp = Component(name="EVSE", evse_id=1)
        assert evse == comp
        assert hash(evse) == hash(comp)

    def test_evse_component_in_dict_with_plain_key(self):
        evse = EVSEComponent(name="EVSE", evse_id=1, connectors=(Component(name="x"),))
        comp = Component(name="EVSE", evse_id=1)
        d: dict[Component, str] = {comp: "value"}
        assert d[evse] == "value"

    def test_connector_component(self):
        conn = ConnectorComponent(name="Connector", evse_id=1, connector_id=1)
        assert isinstance(conn, Component)
        assert conn.connector_id == 1


class TestVariable:
    def test_variable_characteristics_frozen(self):
        chars = VariableCharacteristics(data_type="string", supports_monitoring=True)
        assert chars.data_type == "string"
        with pytest.raises(AttributeError):
            chars.data_type = "integer"

    def test_variable_characteristics_optional_fields(self):
        chars = VariableCharacteristics(
            data_type="decimal",
            supports_monitoring=True,
            min_value="0",
            max_value="100",
            values_list="A,B,C",
        )
        assert chars.min_value == "0"
        assert chars.max_value == "100"
        assert chars.values_list == "A,B,C"

    def test_variable_attribute_mutable(self):
        attr = VariableAttribute(
            attribute_type="Actual", mutability="ReadWrite", value="true", persist=True
        )
        attr.value = "false"
        assert attr.value == "false"

    def test_variable_with_attributes(self):
        chars = VariableCharacteristics(data_type="boolean", supports_monitoring=True)
        actual = VariableAttribute(
            attribute_type="Actual", mutability="ReadOnly", value="true", persist=False
        )
        target = VariableAttribute(
            attribute_type="Target", mutability="ReadWrite", value="true", persist=True
        )
        var = Variable(
            name="Enabled",
            characteristics=chars,
            attributes={"Actual": actual, "Target": target},
        )
        assert var.name == "Enabled"
        assert len(var.attributes) == 2
        assert var.attributes["Target"].value == "true"

    def test_variable_default_empty_attributes(self):
        chars = VariableCharacteristics(data_type="string", supports_monitoring=False)
        var = Variable(name="Test", characteristics=chars)
        assert len(var.attributes) == 0


class TestChargingStationDeviceModel:
    def test_init_creates_controller_components(self):
        model = ChargingStationDeviceModel()
        components = model.get_components()
        names = {c.name for c in components}
        assert "TxCtrlr" in names
        assert "SmartChargingCtrlr" in names
        assert "AuthCtrlr" in names
        assert "OCPPCommCtrlr" in names
        assert "TariffCostCtrlr" in names
        assert "SampledDataCtrlr" in names

    def test_init_creates_physical_components(self):
        model = ChargingStationDeviceModel()
        components = model.get_components()
        names = {c.name for c in components}
        assert "EVSE" in names
        assert "Connector" in names
        assert "Meter" in names
        assert "TemperatureSensor" in names
        assert "AcDcConverter" in names

    def test_init_with_multiple_connectors(self):
        model = ChargingStationDeviceModel(num_connectors=2)
        connectors = [c for c in model.get_components() if c.name == "Connector"]
        assert len(connectors) == 2
        evses = [c for c in model.get_components() if c.name == "EVSE"]
        assert len(evses) == 2

    def test_get_variable_exists(self):
        model = ChargingStationDeviceModel()
        comp = Component(name="TxCtrlr")
        attr = model.get_variable(comp, "Enabled")
        assert attr is not None
        assert attr.value == "true"

    def test_get_variable_not_found(self):
        model = ChargingStationDeviceModel()
        comp = Component(name="TxCtrlr")
        attr = model.get_variable(comp, "NonExistent")
        assert attr is None

    def test_get_variable_component_not_found(self):
        model = ChargingStationDeviceModel()
        comp = Component(name="NonExistent")
        attr = model.get_variable(comp, "Enabled")
        assert attr is None

    def test_get_variable_default_attribute(self):
        model = ChargingStationDeviceModel()
        comp = Component(name="TxCtrlr")
        attr = model.get_variable(comp, "Enabled")
        assert attr is not None
        assert attr.attribute_type == "Actual"

    def test_get_variable_specific_attribute(self):
        model = ChargingStationDeviceModel()
        comp = Component(name="TxCtrlr")
        attr = model.get_variable(comp, "Enabled", "Target")
        assert attr is None

    def test_set_variable_success(self):
        model = ChargingStationDeviceModel()
        comp = Component(name="TxCtrlr")
        result = model.set_variable(comp, "Enabled", "Actual", "false")
        assert result is True
        attr = model.get_variable(comp, "Enabled", "Actual")
        assert attr is not None
        assert attr.value == "false"

    def test_set_variable_readonly_fails(self):
        model = ChargingStationDeviceModel()
        evse_comp = model.find_component("EVSE", evse_id=1)
        assert evse_comp is not None
        result = model.set_variable(evse_comp, "Voltage", "Actual", "400")
        assert result is False

    def test_set_variable_not_found(self):
        model = ChargingStationDeviceModel()
        comp = Component(name="TxCtrlr")
        result = model.set_variable(comp, "NonExistent", "Actual", "value")
        assert result is False

    def test_set_variable_component_not_found(self):
        model = ChargingStationDeviceModel()
        comp = Component(name="NonExistent")
        result = model.set_variable(comp, "Enabled", "Actual", "value")
        assert result is False

    def test_set_variable_attribute_not_found(self):
        model = ChargingStationDeviceModel()
        comp = Component(name="TxCtrlr")
        result = model.set_variable(comp, "Enabled", "Target", "value")
        assert result is False

    def test_on_variable_changed_event(self):
        model = ChargingStationDeviceModel()
        received: list[dict] = []

        def handler(**kwargs: object) -> None:
            received.append(kwargs)

        unsub = model.on_variable_changed.subscribe(handler)
        comp = Component(name="TxCtrlr")
        model.set_variable(comp, "Enabled", "Actual", "false")
        assert len(received) == 1
        assert received[0]["new_value"] == "false"
        assert received[0]["old_value"] == "true"
        unsub()

    def test_on_variable_changed_not_fired_on_failure(self):
        model = ChargingStationDeviceModel()
        received: list[dict] = []

        def handler(**kwargs: object) -> None:
            received.append(kwargs)

        unsub = model.on_variable_changed.subscribe(handler)
        comp = Component(name="TxCtrlr")
        model.set_variable(comp, "Enabled", "Target", "value")
        assert len(received) == 0
        unsub()

    def test_find_component_by_name(self):
        model = ChargingStationDeviceModel()
        comp = model.find_component("TxCtrlr")
        assert comp is not None
        assert comp.name == "TxCtrlr"

    def test_find_component_with_evse_id(self):
        model = ChargingStationDeviceModel()
        comp = model.find_component("EVSE", evse_id=1)
        assert comp is not None
        assert comp.evse_id == 1

    def test_find_component_connector(self):
        model = ChargingStationDeviceModel()
        comp = model.find_component("Connector", evse_id=1)
        assert comp is not None
        assert comp.connector_id == 1

    def test_find_component_not_found(self):
        model = ChargingStationDeviceModel()
        comp = model.find_component("NonExistent")
        assert comp is None

    def test_find_variable(self):
        model = ChargingStationDeviceModel()
        comp = model.find_component("TxCtrlr")
        assert comp is not None
        var = model.find_variable(comp, "Enabled")
        assert var is not None
        assert var.name == "Enabled"

    def test_find_variable_not_found(self):
        model = ChargingStationDeviceModel()
        comp = model.find_component("TxCtrlr")
        assert comp is not None
        var = model.find_variable(comp, "NonExistent")
        assert var is None

    def test_find_variable_component_not_found(self):
        model = ChargingStationDeviceModel()
        comp = Component(name="NonExistent")
        var = model.find_variable(comp, "Enabled")
        assert var is None

    def test_get_all_variables(self):
        model = ChargingStationDeviceModel()
        all_vars = model.get_all_variables()
        assert len(all_vars) > 0
        for comp, variables in all_vars:
            assert isinstance(comp, Component)
            for var in variables:
                assert isinstance(var, Variable)

    def test_get_all_variables_returns_copy(self):
        model = ChargingStationDeviceModel()
        all_vars1 = model.get_all_variables()
        all_vars2 = model.get_all_variables()
        assert all_vars1 is not all_vars2
        assert len(all_vars1) == len(all_vars2)


class TestReportBuilder:
    def test_build_full_inventory_report(self):
        model = ChargingStationDeviceModel()
        builder = ReportBuilder(model)
        pages = builder.build_inventory_report(ReportBaseEnumType.full_inventory)
        assert len(pages) >= 1
        assert pages[-1][1] is False
        total = sum(len(page[0]) for page in pages)
        assert total > 0

    def test_build_configuration_inventory_report(self):
        model = ChargingStationDeviceModel()
        builder = ReportBuilder(model)
        pages = builder.build_inventory_report(
            ReportBaseEnumType.configuration_inventory
        )
        all_items = [item for page in pages for item in page[0]]
        component_names = {item.component.name for item in all_items}
        assert "TxCtrlr" in component_names
        assert "EVSE" not in component_names
        assert "Connector" not in component_names

    def test_build_summary_inventory_report(self):
        model = ChargingStationDeviceModel()
        builder = ReportBuilder(model)
        pages = builder.build_inventory_report(ReportBaseEnumType.summary_inventory)
        all_items = [item for page in pages for item in page[0]]
        assert len(all_items) > 0

    def test_pagination_multiple_pages(self):
        model = ChargingStationDeviceModel()
        builder = ReportBuilder(model)
        pages = builder.build_inventory_report(
            ReportBaseEnumType.full_inventory, page_size=3
        )
        if len(pages) > 1:
            for i, (items, tbc) in enumerate(pages):
                if i < len(pages) - 1:
                    assert tbc is True
                    assert len(items) == 3
            assert pages[-1][1] is False

    def test_pagination_single_page(self):
        model = ChargingStationDeviceModel()
        builder = ReportBuilder(model)
        pages = builder.build_inventory_report(
            ReportBaseEnumType.full_inventory, page_size=1000
        )
        assert len(pages) == 1
        assert pages[0][1] is False

    def test_pagination_empty_result(self):
        model = ChargingStationDeviceModel()
        builder = ReportBuilder(model)
        criteria = [VariableType(name="NonExistentVariable")]
        pages = builder.build_custom_report(variable_criteria=criteria)
        assert len(pages) == 1
        assert len(pages[0][0]) == 0
        assert pages[0][1] is False

    def test_custom_report_with_variable_criteria(self):
        model = ChargingStationDeviceModel()
        builder = ReportBuilder(model)
        criteria = [VariableType(name="Enabled")]
        pages = builder.build_custom_report(variable_criteria=criteria)
        all_items = [item for page in pages for item in page[0]]
        var_names = {item.variable.name for item in all_items}
        assert "Enabled" in var_names
        assert len(all_items) > 0

    def test_custom_report_with_component_criteria(self):
        model = ChargingStationDeviceModel()
        builder = ReportBuilder(model)
        pages = builder.build_custom_report(
            component_criteria=[ComponentCriterionEnumType.enabled]
        )
        all_items = [item for page in pages for item in page[0]]
        component_names = {item.component.name for item in all_items}
        assert "TxCtrlr" in component_names
        assert "AuthCtrlr" in component_names

    def test_report_data_structure(self):
        model = ChargingStationDeviceModel()
        builder = ReportBuilder(model)
        pages = builder.build_inventory_report(ReportBaseEnumType.full_inventory)
        all_items = [item for page in pages for item in page[0]]
        item = all_items[0]
        assert item.component is not None
        assert item.variable is not None
        assert len(item.variable_attribute) > 0
        assert item.variable_characteristics is not None

    def test_report_data_evse_component_has_evse(self):
        model = ChargingStationDeviceModel()
        builder = ReportBuilder(model)
        pages = builder.build_inventory_report(ReportBaseEnumType.full_inventory)
        all_items = [item for page in pages for item in page[0]]
        connector_items = [it for it in all_items if it.component.name == "Connector"]
        assert len(connector_items) > 0
        assert connector_items[0].component.evse is not None
        assert connector_items[0].component.evse.id == 1
        assert connector_items[0].component.evse.connector_id == 1
