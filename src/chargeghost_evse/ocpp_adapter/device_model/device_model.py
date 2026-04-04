import logging
import threading
from typing import Optional

from chargeghost_evse.util.event import Event

from chargeghost_evse.ocpp_adapter.device_model.component import (
    Component,
    ConnectorComponent,
    EVSEComponent,
)
from chargeghost_evse.ocpp_adapter.device_model.variable import (
    Variable,
    VariableAttribute,
    VariableCharacteristics,
)


def _var(
    name: str,
    data_type: str = "string",
    value: str = "",
    mutability: str = "ReadOnly",
    persist: bool = False,
    supports_monitoring: bool = True,
    min_value: Optional[str] = None,
    max_value: Optional[str] = None,
    values_list: Optional[str] = None,
    instance: Optional[str] = None,
) -> Variable:
    chars = VariableCharacteristics(
        data_type=data_type,
        supports_monitoring=supports_monitoring,
        min_value=min_value,
        max_value=max_value,
        values_list=values_list,
    )
    actual = VariableAttribute(
        attribute_type="Actual",
        mutability=mutability,
        value=value,
        persist=persist,
    )
    attributes: dict[str, VariableAttribute] = {"Actual": actual}
    return Variable(
        name=name, instance=instance, characteristics=chars, attributes=attributes
    )


class ChargingStationDeviceModel:
    def __init__(self, num_connectors: int = 1) -> None:
        self._lock = threading.RLock()
        self._components: dict[Component, list[Variable]] = {}
        self._evse_components: dict[int, EVSEComponent] = {}
        self.on_variable_changed = Event()
        self.logger = logging.getLogger("chargeghost.ocpp.device_model")
        self._init_controllers()
        self._init_physical_components(num_connectors)

    def _log(self, message: str, *, level: int = logging.INFO, **extra) -> None:
        self.logger.log(level, message, extra={"source": "ocpp", **extra})

    def _init_controllers(self) -> None:
        ctrlr_vars: dict[str, list[Variable]] = {
            "TxCtrlr": [
                _var("Enabled", "boolean", "true", "ReadWrite", True),
                _var(
                    "TxStartPoint",
                    "string",
                    "PowerPathClosed",
                    "ReadWrite",
                    True,
                    values_list="Authorized,EvConnected,PowerPathClosed",
                ),
            ],
            "SmartChargingCtrlr": [
                _var("Enabled", "boolean", "true", "ReadWrite", True),
                _var("MaxProfileStackLevel", "integer", "5"),
                _var("ProfileStackLevels", "integer", "5", "ReadWrite", True),
            ],
            "AuthCtrlr": [
                _var("Enabled", "boolean", "true", "ReadWrite", True),
                _var("CentralRemoteVerification", "boolean", "true", "ReadWrite", True),
                _var("LocalAuthorizeOffline", "boolean", "true", "ReadWrite", True),
                _var("LocalPreAuthorize", "boolean", "false", "ReadWrite", True),
            ],
            "OCPPCommCtrlr": [
                _var("AllMessagesAttempted", "integer", "0"),
                _var("AllMessagesFailed", "integer", "0"),
                _var("MessageAttempts", "integer", "3", "ReadWrite", True),
                _var("MessageAttemptInterval", "integer", "10", "ReadWrite", True),
                _var("MessageTimeout", "integer", "30", "ReadWrite", True),
            ],
            "TariffCostCtrlr": [
                _var("Enabled", "boolean", "true", "ReadWrite", True),
                _var("Available", "boolean", "true", "ReadOnly"),
                _var("Currency", "string", "", "ReadWrite", True),
                _var("TariffFallbackMessage", "string", "", "ReadWrite", True),
                _var("TotalCostFallbackMessage", "string", "", "ReadWrite", True),
            ],
            "SampledDataCtrlr": [
                _var("Available", "boolean", "true"),
                _var("AlignInterval", "integer", "0", "ReadWrite", True),
                _var(
                    "Measurands",
                    "string",
                    "Energy.Active.Import.Register,Power.Active.Import",
                    "ReadWrite",
                    True,
                ),
            ],
        }
        for name, variables in ctrlr_vars.items():
            self._components[Component(name=name)] = variables

    def _init_physical_components(self, num_connectors: int) -> None:
        self._components[Component(name="Meter")] = [
            _var("MeterType", "string", "WholeCurrent", supports_monitoring=False),
        ]
        self._components[Component(name="TemperatureSensor")] = [
            _var("Temperature", "decimal", "0.0"),
        ]
        self._components[Component(name="AcDcConverter")] = [
            _var("Efficiency", "decimal", "95.0"),
            _var("RatedOutputPower", "decimal", "11000", supports_monitoring=False),
        ]
        for i in range(1, num_connectors + 1):
            conn = ConnectorComponent(name="Connector", evse_id=i, connector_id=i)
            evse = EVSEComponent(name="EVSE", evse_id=i, connectors=(conn,))
            self._evse_components[i] = evse
            self._components[Component(name="EVSE", evse_id=i)] = [
                _var("Available", "boolean", "true", "ReadWrite", True),
                _var("Enabled", "boolean", "true", "ReadWrite", True),
                _var("PhaseRotation", "string", "0.RST", "ReadWrite", True),
                _var("Voltage", "decimal", "230"),
                _var("NumberOfPhases", "integer", "1"),
            ]
            self._components[Component(name="Connector", evse_id=i, connector_id=i)] = [
                _var(
                    "AvailabilityState",
                    "string",
                    "Available",
                    supports_monitoring=False,
                    values_list="Available,Occupied,Reserved,Unavailable,Faulted",
                ),
                _var("Enabled", "boolean", "true", "ReadWrite", True),
                _var("ConnectorType", "string", "Type2", supports_monitoring=False),
                _var("SupplyPhases", "integer", "1", "ReadWrite", True),
                _var(
                    "MaxCurrent",
                    "decimal",
                    "32",
                    "ReadWrite",
                    True,
                    min_value="6",
                    max_value="150",
                ),
                _var(
                    "CurrentType",
                    "string",
                    "AC",
                    supports_monitoring=False,
                    values_list="AC,DC",
                ),
            ]

    def get_variable(
        self,
        component: Component,
        variable_name: str,
        attribute_type: str = "Actual",
    ) -> Optional[VariableAttribute]:
        with self._lock:
            variables = self._components.get(component)
            if variables is None:
                return None
            for var in variables:
                if var.name == variable_name:
                    return var.attributes.get(attribute_type)
            return None

    def set_variable(
        self,
        component: Component,
        variable_name: str,
        attribute_type: str,
        value: str,
    ) -> bool:
        with self._lock:
            variables = self._components.get(component)
            if variables is None:
                return False
            for var in variables:
                if var.name == variable_name:
                    attr = var.attributes.get(attribute_type)
                    if attr is None:
                        return False
                    if attr.mutability == "ReadOnly":
                        return False
                    old_value = attr.value
                    attr.value = value
                    self.on_variable_changed.emit(
                        component=component,
                        variable=var,
                        attribute_type=attribute_type,
                        old_value=old_value,
                        new_value=value,
                    )
                    self._log(
                        f"Variable changed: {component.name}/{variable_name}"
                        f".{attribute_type} = {value}",
                    )
                    return True
            return False

    def get_all_variables(self) -> list[tuple[Component, list[Variable]]]:
        with self._lock:
            return list(self._components.items())

    def get_components(self) -> list[Component]:
        with self._lock:
            return list(self._components.keys())

    def find_component(
        self,
        name: str,
        instance: Optional[str] = None,
        evse_id: Optional[int] = None,
    ) -> Optional[Component]:
        with self._lock:
            for comp in self._components:
                if (
                    comp.name == name
                    and comp.instance == instance
                    and comp.evse_id == evse_id
                ):
                    return comp
            return None

    def find_variable(
        self,
        component: Component,
        name: str,
        instance: Optional[str] = None,
    ) -> Optional[Variable]:
        with self._lock:
            variables = self._components.get(component)
            if variables is None:
                return None
            for var in variables:
                if var.name == name and var.instance == instance:
                    return var
            return None
