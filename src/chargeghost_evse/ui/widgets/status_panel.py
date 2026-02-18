from textual.widgets import Static
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Label

class StatusPanel(Static):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.energy_label = Label("Energy: 0.000 Wh")
        self.session_label = Label("No active session")
        self.connectors_container = Vertical(id="connectors-list")

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("[b]EVSE Status[/b]", classes="panel-title"),
            self.energy_label,
            self.session_label,
            Label("[b]Connectors:[/b]"),
            self.connectors_container,
            classes="status-panel-content"
        )

    def update_status(self, engine):
        self.energy_label.update(f"Energy Meter: {engine.energy_meter.get_meter_reading():.3f} Wh")
        if engine.session:
            self.session_label.update(f"Session: Trans ID {engine.session.transaction_id}\nEnergy Delivered: {engine.session.energy_charged:.3f} Wh\nSoC: {engine.session.state_of_charge:.1f}%")
        else:
            self.session_label.update("No active session")
        
        # Detailed connector status update
        self.connectors_container.remove_children()
        for conn in engine.connectors:
            plug_status = "Plugged In" if conn.is_plugged_in else "Unplugged"
            id_tag_status = f"ID Tag: {conn.id_tag}" if conn.id_tag else "No ID Tag"
            
            conn_label = Label(
                f"Connector {conn.id}:\n"
                f"  Status: {conn.status.value}\n"
                f"  Plug: {plug_status}\n"
                f"  {id_tag_status}\n"
                f"  Output: {conn.voltage}V {conn.current}A {conn.phase}Ph"
            )
            self.connectors_container.mount(conn_label)
