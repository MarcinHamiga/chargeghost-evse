import logging
from typing import Optional

from ocpp.v201.datatypes import (
    ComponentType,
    EVSEType,
    ReportDataType,
    VariableAttributeType,
    VariableCharacteristicsType,
    VariableType,
)
from ocpp.v201.enums import (
    AttributeEnumType,
    ComponentCriterionEnumType,
    DataEnumType,
    MutabilityEnumType,
    ReportBaseEnumType,
)

from chargeghost_evse.ocpp_adapter.device_model.component import Component
from chargeghost_evse.ocpp_adapter.device_model.device_model import (
    ChargingStationDeviceModel,
)
from chargeghost_evse.ocpp_adapter.device_model.variable import (
    Variable,
    VariableAttribute,
    VariableCharacteristics,
)

_DATA_TYPE_MAP: dict[str, DataEnumType] = {
    "string": DataEnumType.string,
    "decimal": DataEnumType.decimal,
    "integer": DataEnumType.integer,
    "boolean": DataEnumType.boolean,
    "dateTime": DataEnumType.date_time,
    "OptionList": DataEnumType.option_list,
    "SequenceList": DataEnumType.sequence_list,
    "MemberList": DataEnumType.member_list,
}

_MUTABILITY_MAP: dict[str, MutabilityEnumType] = {
    "ReadOnly": MutabilityEnumType.read_only,
    "WriteOnly": MutabilityEnumType.write_only,
    "ReadWrite": MutabilityEnumType.read_write,
}

_ATTRIBUTE_MAP: dict[str, AttributeEnumType] = {
    "Actual": AttributeEnumType.actual,
    "Target": AttributeEnumType.target,
    "MinSet": AttributeEnumType.min_set,
    "MaxSet": AttributeEnumType.max_set,
}

_CONTROLLER_NAMES: frozenset[str] = frozenset(
    {
        "TxCtrlr",
        "SmartChargingCtrlr",
        "AuthCtrlr",
        "OCPPCommCtrlr",
        "TariffCostCtrlr",
        "SampledDataCtrlr",
    }
)


def _str_to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class ReportBuilder:
    def __init__(self, device_model: ChargingStationDeviceModel) -> None:
        self._device_model = device_model
        self.logger = logging.getLogger("chargeghost.ocpp.device_model.report")

    def _log(self, message: str, *, level: int = logging.INFO, **extra) -> None:
        self.logger.log(level, message, extra={"source": "ocpp", **extra})

    def _to_ocpp_component(self, component: Component) -> ComponentType:
        evse = None
        if component.evse_id is not None:
            evse = EVSEType(id=component.evse_id, connector_id=component.connector_id)
        return ComponentType(
            name=component.name, instance=component.instance, evse=evse
        )

    def _to_ocpp_variable(self, variable: Variable) -> VariableType:
        return VariableType(name=variable.name, instance=variable.instance)

    def _to_ocpp_attributes(
        self, attributes: dict[str, VariableAttribute]
    ) -> list[VariableAttributeType]:
        result: list[VariableAttributeType] = []
        for attr_type, attr in attributes.items():
            ocpp_type = _ATTRIBUTE_MAP.get(attr_type)
            if ocpp_type is None:
                continue
            ocpp_mut = _MUTABILITY_MAP.get(attr.mutability)
            result.append(
                VariableAttributeType(
                    type=ocpp_type,
                    value=attr.value,
                    mutability=ocpp_mut,
                    persistent=attr.persist,
                )
            )
        return result

    def _to_ocpp_characteristics(
        self, characteristics: VariableCharacteristics
    ) -> Optional[VariableCharacteristicsType]:
        data_enum = _DATA_TYPE_MAP.get(characteristics.data_type)
        if data_enum is None:
            return None
        return VariableCharacteristicsType(
            data_type=data_enum,
            supports_monitoring=characteristics.supports_monitoring,
            min_limit=_str_to_float(characteristics.min_value),
            max_limit=_str_to_float(characteristics.max_value),
            values_list=characteristics.values_list,
        )

    def _build_report_items(
        self, component: Component, variables: list[Variable]
    ) -> list[ReportDataType]:
        items: list[ReportDataType] = []
        ocpp_comp = self._to_ocpp_component(component)
        for var in variables:
            ocpp_var = self._to_ocpp_variable(var)
            ocpp_attrs = self._to_ocpp_attributes(var.attributes)
            ocpp_chars = self._to_ocpp_characteristics(var.characteristics)
            items.append(
                ReportDataType(
                    component=ocpp_comp,
                    variable=ocpp_var,
                    variable_attribute=ocpp_attrs,
                    variable_characteristics=ocpp_chars,
                )
            )
        return items

    def _paginate(
        self, items: list[ReportDataType], page_size: int
    ) -> list[tuple[list[ReportDataType], bool]]:
        if not items:
            return [([], False)]
        pages: list[tuple[list[ReportDataType], bool]] = []
        for i in range(0, len(items), page_size):
            page = items[i : i + page_size]
            tbc = i + page_size < len(items)
            pages.append((page, tbc))
        return pages

    def _matches_component_criteria(
        self,
        component: Component,
        variables: list[Variable],
        criteria: list[ComponentCriterionEnumType],
    ) -> bool:
        if not criteria:
            return True
        var_map = {v.name: v for v in variables}
        for criterion in criteria:
            if criterion == ComponentCriterionEnumType.enabled:
                enabled_var = var_map.get("Enabled")
                if enabled_var is not None:
                    actual = enabled_var.attributes.get("Actual")
                    if actual is not None and actual.value.lower() == "true":
                        continue
                return False
            elif criterion == ComponentCriterionEnumType.available:
                available_var = var_map.get("Available")
                if available_var is not None:
                    actual = available_var.attributes.get("Actual")
                    if actual is not None and actual.value.lower() == "true":
                        continue
                return False
        return True

    def _collect_inventory_items(
        self, criterion: ReportBaseEnumType
    ) -> list[ReportDataType]:
        items: list[ReportDataType] = []
        all_vars = self._device_model.get_all_variables()
        if criterion == ReportBaseEnumType.configuration_inventory:
            for comp, variables in all_vars:
                if comp.name in _CONTROLLER_NAMES:
                    items.extend(self._build_report_items(comp, variables))
        elif criterion == ReportBaseEnumType.summary_inventory:
            for comp, variables in all_vars:
                if variables:
                    items.extend(self._build_report_items(comp, [variables[0]]))
        else:
            for comp, variables in all_vars:
                items.extend(self._build_report_items(comp, variables))
        return items

    def _collect_custom_items(
        self,
        component_criteria: Optional[list[ComponentCriterionEnumType]],
        variable_criteria: Optional[list[VariableType]],
    ) -> list[ReportDataType]:
        items: list[ReportDataType] = []
        all_vars = self._device_model.get_all_variables()
        for comp, variables in all_vars:
            if not self._matches_component_criteria(
                comp, variables, component_criteria or []
            ):
                continue
            if variable_criteria:
                matching = [
                    v
                    for v in variables
                    if any(
                        vc.name == v.name and vc.instance == v.instance
                        for vc in variable_criteria
                    )
                ]
            else:
                matching = variables
            if matching:
                items.extend(self._build_report_items(comp, matching))
        return items

    def build_inventory_report(
        self,
        criterion: ReportBaseEnumType,
        page_size: int = 50,
    ) -> list[tuple[list[ReportDataType], bool]]:
        self._log(f"Building inventory report: {criterion.value}")
        items = self._collect_inventory_items(criterion)
        return self._paginate(items, page_size)

    def build_custom_report(
        self,
        component_criteria: Optional[list[ComponentCriterionEnumType]] = None,
        variable_criteria: Optional[list[VariableType]] = None,
        page_size: int = 50,
    ) -> list[tuple[list[ReportDataType], bool]]:
        self._log("Building custom report")
        items = self._collect_custom_items(component_criteria, variable_criteria)
        return self._paginate(items, page_size)
