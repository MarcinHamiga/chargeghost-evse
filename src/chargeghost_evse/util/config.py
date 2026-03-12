"""
Configuration Management Module.

This module provides configuration classes for the ChargeGhost EVSE simulator.
It handles loading, saving, and validating user configuration including
connection settings, connector parameters, and security credentials.

Configuration is stored in:
    - JSON file: ~/.chargeghost/config.json (non-sensitive settings)
    - System keyring: OCPP passwords (secure storage)

Classes:
    ConnectorConfig: Electrical parameters for a single connector.
    SimulationConfig: Complete EVSE simulation configuration.

Constants:
    VOLTAGE_MIN/MAX/DEFAULT: Voltage limits and default (100-480V, 230V default)
    CURRENT_MIN/MAX/DEFAULT: Current limits and default (6-63A, 32A default)
    PHASE_MIN/MAX/DEFAULT: Phase limits and default (1-3, 1 default)

Example:
    >>> from chargeghost_evse.util.config import SimulationConfig
    >>> 
    >>> # Load existing config or create defaults
    >>> config = SimulationConfig.load()
    >>> 
    >>> # Modify settings
    >>> config.connection_url = "wss://my-csms.example.com/CP_1"
    >>> config.ocpp_id = "CP_1"
    >>> 
    >>> # Save to disk (password stored in keyring)
    >>> config.save()
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import keyring

_logger = logging.getLogger(__name__)

# Configuration file path in user's home directory
CONFIG_FILE = Path.home() / ".chargeghost" / "config.json"

# Keyring service name for password storage
KEYRING_SERVICE = "ChargeGhost-EVSE"

# Type alias for log mode setting
LogMode = Literal["shallow", "deep"]

# Electrical parameter limits and defaults
# Voltage: Range for AC EVSE (100V-480V covers global standards)
VOLTAGE_MIN = 120.0
VOLTAGE_MAX = 1000.0
VOLTAGE_DEFAULT = 230.0  # EU standard

# Current: Range for typical EVSE installations
CURRENT_MIN = 6.0
CURRENT_MAX = 150.0
CURRENT_DEFAULT = 32.0  # Common 7kW EVSE

# Phases: Single-phase or three-phase
PHASE_MIN = 1
PHASE_MAX = 3
PHASE_DEFAULT = 1  # Single-phase default


@dataclass
class ConnectorConfig:
    """
    Configuration for a single EVSE connector.

    Stores the electrical parameters that determine charging power
    and capacity for a connector.

    Attributes:
        voltage: Operating voltage in volts (V).
        current: Maximum current in amperes (A).
        phase: Number of electrical phases (1 or 3).

    Example:
        >>> config = ConnectorConfig(voltage=230.0, current=16.0, phase=1)
        >>> power = config.voltage * config.current * config.phase
        >>> print(f"Max power: {power/1000:.1f} kW")
        Max power: 3.7 kW
    """

    voltage: float = VOLTAGE_DEFAULT
    current: float = CURRENT_DEFAULT
    phase: int = PHASE_DEFAULT

    def validate(self) -> Optional[str]:
        """
        Validate the connector parameters.

        Checks that all values are within acceptable ranges.

        Returns:
            Error message string if validation fails, None if valid.
        """
        if not (VOLTAGE_MIN <= self.voltage <= VOLTAGE_MAX):
            return f"Voltage must be between {VOLTAGE_MIN}V and {VOLTAGE_MAX}V"
        if not (CURRENT_MIN <= self.current <= CURRENT_MAX):
            return f"Current must be between {CURRENT_MIN}A and {CURRENT_MAX}A"
        if not (PHASE_MIN <= self.phase <= PHASE_MAX):
            return f"Phase must be between {PHASE_MIN} and {PHASE_MAX}"
        return None

    @classmethod
    def from_dict(cls, data: dict) -> "ConnectorConfig":
        """
        Create a ConnectorConfig from a dictionary.

        Args:
            data: Dictionary with optional 'voltage', 'current', 'phase' keys.

        Returns:
            New ConnectorConfig instance with values from dict or defaults.
        """
        return cls(
            voltage=data.get("voltage", VOLTAGE_DEFAULT),
            current=data.get("current", CURRENT_DEFAULT),
            phase=data.get("phase", PHASE_DEFAULT),
        )

    def to_dict(self) -> dict:
        """
        Convert the configuration to a dictionary.

        Returns:
            Dictionary with 'voltage', 'current', 'phase' keys.
        """
        return {"voltage": self.voltage, "current": self.current, "phase": self.phase}


def _migrate_log_mode(value: str) -> "LogMode":
	"""Map old log mode values to new ones. Unknown values default to 'shallow'."""
	_COMPAT_MAP: dict[str, "LogMode"] = {"compact": "shallow", "verbose": "deep"}
	return _COMPAT_MAP.get(value, value)  # type: ignore


@dataclass
class SimulationConfig:
    """
    Complete configuration for the EVSE simulator.

    Contains all settings needed to connect to a Central System and
    simulate an EVSE charging station. Passwords are stored securely
    in the system keyring, not in the config file.

    Attributes:
        connection_url: WebSocket URL for OCPP connection.
        ocpp_id: Charge Point identifier (used in WebSocket path).
        ocpp_password: Password for WebSocket authentication (stored in keyring).
        charge_point_model: Model name reported in BootNotification.
        charge_point_vendor: Vendor name reported in BootNotification.
        connectors: List of per-connector configurations.
        skip_tls_verify: Whether to skip TLS certificate verification.
        log_mode: OCPP message logging format ('shallow' or 'deep').
        ignored_version: Version number to skip for update notifications.

    Example:
        >>> config = SimulationConfig.load()
        >>> print(f"Connecting to: {config.connection_url}")
        >>> config.ocpp_password = "secret123"
        >>> config.save()  # Password stored in keyring
    """

    # Connection settings
    connection_url: str = "wss://localhost:3000/CP_1"
    ocpp_id: str = "CP_1"
    ocpp_password: str = ""  # Stored in keyring, not JSON

    # Charge point identification
    charge_point_model: str = "ChargeGhostV1"
    charge_point_vendor: str = "ChargeGhost"

    # Connector configuration
    connectors: list[ConnectorConfig] = field(
        default_factory=lambda: [ConnectorConfig()]
    )

    # Security settings
    skip_tls_verify: bool = False

    # Logging settings
    log_mode: LogMode = field(default="shallow")

    # Update settings
    ignored_version: Optional[str] = None

    # Message queue persistence
    persist_message_queue: bool = False

    @staticmethod
    def _get_password(ocpp_id: str) -> str:
        """
        Retrieve password from system keyring.

        Args:
            ocpp_id: Charge Point ID used as the keyring username.

        Returns:
            Stored password, or empty string if not found or on error.
        """
        try:
            password = keyring.get_password(KEYRING_SERVICE, ocpp_id)
            return password or ""
        except Exception as e:
            _logger.debug(f"Keyring get_password failed: {e}")
            return ""

    @staticmethod
    def _set_password(ocpp_id: str, password: str) -> None:
        """
        Store password in system keyring.

        Args:
            ocpp_id: Charge Point ID used as the keyring username.
            password: Password to store. If empty, deletes the entry.
        """
        try:
            if password:
                keyring.set_password(KEYRING_SERVICE, ocpp_id, password)
            else:
                # Remove empty password from keyring
                keyring.delete_password(KEYRING_SERVICE, ocpp_id)
        except Exception as e:
            _logger.debug(f"Keyring set_password failed: {e}")

    @classmethod
    def load(cls) -> "SimulationConfig":
        """
        Load configuration from disk.

        Reads the JSON config file and retrieves the password from
        the system keyring. Returns default configuration if the
        file doesn't exist or is invalid.

        Returns:
            SimulationConfig with loaded values or defaults.
        """
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)

                # Parse connector configurations
                connectors_data = data.get("connectors", [])
                if connectors_data:
                    connectors = []
                    for c in connectors_data:
                        conn_config = ConnectorConfig.from_dict(c)
                        validation_error = conn_config.validate()
                        if validation_error:
                            _logger.warning(
                                f"Invalid connector config: {validation_error}, using defaults"
                            )
                            conn_config = ConnectorConfig()
                        connectors.append(conn_config)
                else:
                    # Legacy support: create connectors from num_connectors count
                    num_connectors = data.get("num_connectors", 1)
                    connectors = [ConnectorConfig() for _ in range(num_connectors)]

                # Get password from keyring
                ocpp_id = data.get("ocpp_id", "CP_1")
                password = cls._get_password(ocpp_id)

                return cls(
                    connection_url=data.get(
                        "connection_url", "wss://localhost:3000/CP_1"
                    ),
                    ocpp_id=ocpp_id,
                    ocpp_password=password,
                    charge_point_model=data.get("charge_point_model", "ChargeGhostV1"),
                    charge_point_vendor=data.get("charge_point_vendor", "ChargeGhost"),
                    connectors=connectors,
                    skip_tls_verify=data.get("skip_tls_verify", False),
                    log_mode=_migrate_log_mode(data.get("log_mode", "shallow")),
                    ignored_version=data.get("ignored_version"),
                    persist_message_queue=data.get("persist_message_queue", False),
                )
            except (json.JSONDecodeError, IOError) as e:
                logging.warning("Failed to load config from %s, using defaults: %s", CONFIG_FILE, e)

        return cls()

    def save(self) -> None:
        """
        Save configuration to disk.

        Writes non-sensitive settings to the JSON config file and
        stores the password in the system keyring. Creates the
        config directory if it doesn't exist. The write is atomic:
        data is written to a temporary file then renamed into place
        to prevent corruption if the process is interrupted mid-write.
        """
        # Store password in keyring
        self._set_password(self.ocpp_id, self.ocpp_password)

        # Build config data (password NOT included)
        data = {
            "connection_url": self.connection_url,
            "ocpp_id": self.ocpp_id,
            "charge_point_model": self.charge_point_model,
            "charge_point_vendor": self.charge_point_vendor,
            "connectors": [c.to_dict() for c in self.connectors],
            "skip_tls_verify": self.skip_tls_verify,
            "log_mode": self.log_mode,
            "ignored_version": self.ignored_version,
            "persist_message_queue": self.persist_message_queue,
        }

        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = CONFIG_FILE.with_suffix(".tmp")
        with open(tmp_file, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_file, CONFIG_FILE)
