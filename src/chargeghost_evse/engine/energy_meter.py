"""
Energy Meter Module.

This module defines the EnergyMeter class which simulates the physical
energy meter in an EVSE unit. It tracks cumulative energy consumption
and calculates energy delivery based on electrical parameters.

Classes:
    EnergyMeter: Simulates EVSE energy metering functionality.
"""

from chargeghost_evse.util.event import Event
from chargeghost_evse.util.subscriber import Subscriber


class EnergyMeter(Subscriber):
    """
    Simulates an EVSE energy meter for tracking cumulative energy consumption.

    The EnergyMeter maintains a running total of energy consumed during
    charging sessions, similar to a physical meter in an EVSE unit. It
    calculates energy based on voltage, current, phases, and time interval.

    The meter value persists across sessions and represents the total
    cumulative energy delivered (like an odometer for electricity).

    Events:
        energy_consumed: Emitted when energy is added to the meter.
            Parameters: amount (float) - Energy in Watt-hours.

    Attributes:
        value: Cumulative energy reading in the configured unit (default Wh).
        unit: Unit of measurement (default "Wh" for Watt-hours).
        is_charging: Whether the meter is currently accumulating energy.

    Example:
        >>> meter = EnergyMeter(initial_value=1000.0)  # Start at 1 kWh
        >>> meter.is_charging = True
        >>> meter.update(voltage=230.0, current=16.0, phase=1, interval_seconds=60.0)
        >>> print(f"Meter: {meter.get_meter_reading():.2f} {meter.unit}")
        Meter: 1061.33 Wh
    """

    def __init__(self, initial_value: float = 0.0, unit: str = "Wh") -> None:
        """
        Initialize the energy meter with an optional starting value.

        Args:
            initial_value: Starting meter reading in the specified unit.
                Defaults to 0.0 for a new meter.
            unit: Unit of measurement for display purposes. Defaults to "Wh"
                (Watt-hours) per OCPP 1.6 standard.
        """
        super().__init__()
        self.value: float = initial_value
        self.unit: str = unit
        self.is_charging: bool = False
        self.energy_consumed: Event = Event()

    def get_meter_reading(self) -> float:
        """
        Get the current cumulative meter reading.

        Returns:
            Current energy value in the configured unit (default Wh).
        """
        return self.value

    def consume_energy(self, amount: float) -> None:
        """
        Add energy to the cumulative meter reading.

        Increments the meter value and emits the energy_consumed event.

        Args:
            amount: Energy to add in Watt-hours (Wh).
        """
        self.value += amount
        self.energy_consumed.emit(amount=amount)

    def update(
        self, voltage: float, current: float, phase: int, interval_seconds: float
    ) -> None:
        """
        Calculate and add energy consumed during a time interval.

        This method calculates the energy consumed based on electrical
        parameters and time, then updates the meter. It only accumulates
        energy when is_charging is True.

        Calculation:
            Power (W) = Voltage (V) × Current (A) × Phases
            Energy (Wh) = Power (W) × Time (h)

        Args:
            voltage: Operating voltage in volts (V).
            current: Charging current in amperes (A).
            phase: Number of electrical phases (1 or 3).
            interval_seconds: Time interval in seconds since last update.

        Note:
            The interval is converted from seconds to hours for the
            energy calculation (seconds / 3600 = hours).
        """
        if not self.is_charging:
            return

        # Power (W) = Voltage (V) * Current (A)
        power = voltage * current * phase
        # Energy (Wh) = Power (W) * Time (h)
        # interval_seconds / 3600 converts seconds to hours
        wh_consumed = (power * interval_seconds) / 3600.0

        self.consume_energy(wh_consumed)

    def handle_max_charge_reached(self, connector_id: int) -> None:
        """
        Handle event when EV reaches maximum charge.

        Stops energy accumulation by setting is_charging to False.
        This is called when the EV battery is full and stops accepting
        charge, transitioning to SUSPENDED_EV state.

        Args:
            connector_id: ID of the connector whose EV reached max charge.
        """
        self.is_charging = False
