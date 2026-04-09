from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class VariableCharacteristics:
    data_type: str
    supports_monitoring: bool
    min_value: Optional[str] = None
    max_value: Optional[str] = None
    values_list: Optional[str] = None


@dataclass
class VariableAttribute:
    attribute_type: str
    mutability: str
    value: str
    persist: bool


@dataclass
class Variable:
    name: str
    characteristics: VariableCharacteristics
    instance: Optional[str] = None
    attributes: dict[str, VariableAttribute] = field(default_factory=dict)
