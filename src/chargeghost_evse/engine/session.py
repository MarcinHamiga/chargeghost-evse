"""
Charging Session Module.

This module defines the Session class which represents an active charging
session between the EVSE and an electric vehicle. Sessions track energy
delivery, state of charge, and session timing.

Classes:
    Session: Manages charging session state and energy tracking.
"""

import time
from typing import Optional

from chargeghost_evse.util.event import Event
from chargeghost_evse.util.subscriber import Subscriber


class Session(Subscriber):
    """
    Represents an active charging session for a single transaction.

    A Session tracks the energy delivery to an EV during a charging
    transaction, including the amount of energy transferred, the state
    of charge percentage, and session timing. It emits events when
    the EV reaches its maximum charge capacity.

    The session calculates state of charge (SoC) as a percentage of
    the max_energy value, simulating battery charging behavior.

    Events:
        ev_max_charge_reached: Emitted when the EV battery is fully charged.
            Parameters: connector_id (int)

    Attributes:
        transaction_id: OCPP transaction identifier for this session.
        start_time: POSIX timestamp (time.time()) when the session started.
        energy_charged: Total energy delivered in Watt-hours (Wh).
        connector_id: ID of the connector used for this session.
        state_of_charge: Current battery percentage (0-100).
        max_energy: Maximum battery capacity in Watt-hours (Wh).
        id_tag: Authorization identifier for this session.

    Example:
        >>> session = Session(
        ...     transaction_id=12345,
        ...     connector_id=1,
        ...     max_energy=60000.0,  # 60 kWh battery
        ...     id_tag="ABC123"
        ... )
        >>> session.process_energy_delivery(1500.0)  # Add 1.5 kWh
        >>> print(f"SoC: {session.state_of_charge:.1f}%")
        SoC: 2.5%
    """

    def __init__(
        self,
        transaction_id: int = -1,
        connector_id: int = 0,
        max_energy: float = 0.0,
        id_tag: Optional[str] = None,
    ) -> None:
        """
        Initialize a new charging session.

        Args:
            transaction_id: OCPP transaction identifier. Use -1 for unassigned.
            connector_id: ID of the connector for this session.
            max_energy: Maximum battery capacity in Watt-hours (Wh).
                Use 0.0 for unlimited/unknown capacity (disables SoC calculation).
            id_tag: Authorization identifier from the central system.
        """
        super().__init__()
        self.transaction_id: int = transaction_id
        self.start_time: float = time.time()
        self.energy_charged: float = 0.0
        self.connector_id: int = connector_id
        self.state_of_charge: float = 0.0
        self.max_energy: float = max_energy
        self.id_tag: Optional[str] = id_tag

        # Event emitted when EV reaches full charge
        self.ev_max_charge_reached: Event = Event()

    def process_energy_delivery(self, amount: float = 0.0) -> None:
        """
        Process energy delivery and update session state.

        Adds the delivered energy to the running total, capping at
        max_energy if specified. Updates the state of charge percentage.
        Emits ev_max_charge_reached event when the battery is full.

        Args:
            amount: Energy delivered in Watt-hours (Wh).

        Note:
            When max_energy is 0.0, SoC calculation is disabled and
            the session tracks unlimited energy delivery.
        """
        if self.max_energy > 0:
            # Cap energy at max capacity
            self.energy_charged += (
                amount
                if self.energy_charged + amount <= self.max_energy
                else self.max_energy - self.energy_charged
            )
            # Calculate state of charge as percentage
            self.state_of_charge = (self.energy_charged / self.max_energy) * 100
        else:
            # Unlimited capacity mode - no SoC calculation
            self.energy_charged += amount
            self.state_of_charge = 0.0

        # Check if EV has reached maximum charge
        if self.max_energy > 0 and self.energy_charged >= self.max_energy:
            self.energy_charged = self.max_energy
            self.ev_max_charge_reached.emit(connector_id=self.connector_id)
