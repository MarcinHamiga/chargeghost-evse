from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Component:
    name: str
    instance: Optional[str] = None
    evse_id: Optional[int] = None
    connector_id: Optional[int] = None


@dataclass(frozen=True)
class EVSEComponent(Component):
    connectors: tuple[Component, ...] = ()

    def __hash__(self) -> int:
        return hash((self.name, self.instance, self.evse_id, self.connector_id))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Component):
            return NotImplemented
        return (
            self.name == other.name
            and self.instance == other.instance
            and self.evse_id == other.evse_id
            and self.connector_id == other.connector_id
        )


@dataclass(frozen=True)
class ConnectorComponent(Component):
    pass
