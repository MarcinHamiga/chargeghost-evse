import json
from pathlib import Path
from dataclasses import dataclass, asdict

CONFIG_FILE = Path.home() / ".chargeghost" / "config.json"


@dataclass
class SimulationConfig:
    connection_url: str = "wss://localhost:3000/CP_1"
    ocpp_id: str = "CP_1"
    ocpp_password: str = ""
    charge_point_model: str = "ChargeGhostV1"
    charge_point_vendor: str = "ChargeGhost"
    num_connectors: int = 1
    skip_tls_verify: bool = False

    @classmethod
    def load(cls) -> "SimulationConfig":
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                return cls(
                    connection_url=data.get(
                        "connection_url", "wss://localhost:3000/CP_1"
                    ),
                    ocpp_id=data.get("ocpp_id", "CP_1"),
                    ocpp_password=data.get("ocpp_password", ""),
                    charge_point_model=data.get("charge_point_model", "ChargeGhostV1"),
                    charge_point_vendor=data.get("charge_point_vendor", "ChargeGhost"),
                    num_connectors=data.get("num_connectors", 1),
                    skip_tls_verify=data.get("skip_tls_verify", False),
                )
            except (json.JSONDecodeError, IOError):
                pass
        return cls()

    def save(self) -> None:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(asdict(self), f, indent=2)
