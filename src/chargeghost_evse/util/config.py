import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Literal, Optional

CONFIG_FILE = Path.home() / ".chargeghost" / "config.json"

LogMode = Literal["verbose", "compact"]

VOLTAGE_MIN = 100.0
VOLTAGE_MAX = 480.0
VOLTAGE_DEFAULT = 230.0

CURRENT_MIN = 6.0
CURRENT_MAX = 63.0
CURRENT_DEFAULT = 32.0

PHASE_MIN = 1
PHASE_MAX = 3
PHASE_DEFAULT = 1


@dataclass
class ConnectorConfig:
    voltage: float = VOLTAGE_DEFAULT
    current: float = CURRENT_DEFAULT
    phase: int = PHASE_DEFAULT

    def validate(self) -> Optional[str]:
        if not (VOLTAGE_MIN <= self.voltage <= VOLTAGE_MAX):
            return f"Voltage must be between {VOLTAGE_MIN}V and {VOLTAGE_MAX}V"
        if not (CURRENT_MIN <= self.current <= CURRENT_MAX):
            return f"Current must be between {CURRENT_MIN}A and {CURRENT_MAX}A"
        if not (PHASE_MIN <= self.phase <= PHASE_MAX):
            return f"Phase must be between {PHASE_MIN} and {PHASE_MAX}"
        return None

    @classmethod
    def from_dict(cls, data: dict) -> "ConnectorConfig":
        return cls(
            voltage=data.get("voltage", VOLTAGE_DEFAULT),
            current=data.get("current", CURRENT_DEFAULT),
            phase=data.get("phase", PHASE_DEFAULT),
        )

    def to_dict(self) -> dict:
        return {"voltage": self.voltage, "current": self.current, "phase": self.phase}


@dataclass
class SimulationConfig:
    connection_url: str = "wss://localhost:3000/CP_1"
    ocpp_id: str = "CP_1"
    ocpp_password: str = ""
    charge_point_model: str = "ChargeGhostV1"
    charge_point_vendor: str = "ChargeGhost"
    num_connectors: int = 1
    connectors: list[ConnectorConfig] = field(
        default_factory=lambda: [ConnectorConfig()]
    )
    skip_tls_verify: bool = False
    log_mode: LogMode = field(default="compact")

    @classmethod
    def load(cls) -> "SimulationConfig":
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)

                connectors_data = data.get("connectors", [])
                if connectors_data:
                    connectors = [ConnectorConfig.from_dict(c) for c in connectors_data]
                else:
                    num_connectors = data.get("num_connectors", 1)
                    connectors = [ConnectorConfig() for _ in range(num_connectors)]

                return cls(
                    connection_url=data.get(
                        "connection_url", "wss://localhost:3000/CP_1"
                    ),
                    ocpp_id=data.get("ocpp_id", "CP_1"),
                    ocpp_password=data.get("ocpp_password", ""),
                    charge_point_model=data.get("charge_point_model", "ChargeGhostV1"),
                    charge_point_vendor=data.get("charge_point_vendor", "ChargeGhost"),
                    num_connectors=len(connectors),
                    connectors=connectors,
                    skip_tls_verify=data.get("skip_tls_verify", False),
                    log_mode=data.get("log_mode", "compact"),
                )
            except (json.JSONDecodeError, IOError):
                pass
        return cls()

    def save(self) -> None:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "connection_url": self.connection_url,
            "ocpp_id": self.ocpp_id,
            "ocpp_password": self.ocpp_password,
            "charge_point_model": self.charge_point_model,
            "charge_point_vendor": self.charge_point_vendor,
            "num_connectors": len(self.connectors),
            "connectors": [c.to_dict() for c in self.connectors],
            "skip_tls_verify": self.skip_tls_verify,
            "log_mode": self.log_mode,
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
