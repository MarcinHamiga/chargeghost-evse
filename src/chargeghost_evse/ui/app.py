from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Static, Label, Input
from textual.containers import Container, Vertical, Horizontal
from textual.binding import Binding

from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.ui.widgets.log_panel import LogPanel
from chargeghost_evse.ui.widgets.status_panel import StatusPanel

import asyncio
from datetime import datetime, timezone

class ModeSelectScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Vertical(
                Label("Choose ChargeGhost EVSE Mode:", id="title"),
                Button("Simulator Mode", variant="primary", id="simulator_mode"),
                Button("Manual Mode", variant="default", id="manual_mode"),
                classes="mode-select-container"
            )
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "simulator_mode":
            self.app.push_screen(SimulatorScreen())
        elif event.button.id == "manual_mode":
            self.app.push_screen(ManualScreen())

class SimulatorScreen(Screen):
    BINDINGS = [
        Binding("p", "plug_in", "Plug In"),
        Binding("u", "unplug", "Unplug"),
        Binding("a", "swipe_card", "Swipe Card"),
        Binding("x", "stop_session", "Stop Session"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sim-controls", classes="controls-panel"):
                yield Label("[b]Controls[/b]", classes="panel-title")
                yield Button("Plug In", id="btn_plug", variant="primary")
                yield Button("Swipe Card", id="btn_swipe", variant="success")
                yield Button("Unplug", id="btn_unplug", variant="error")
                yield StatusPanel(id="status-panel")
            yield LogPanel(id="log-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.engine = Engine()
        self.engine.add_connector()
        self.bridge = Bridge(self.engine)
        self.bridge.setup()
        
        self.log_panel = self.query_one("#log-panel", LogPanel)
        self.status_panel = self.query_one("#status-panel", StatusPanel)
        
        self.bridge.on_log.subscribe(self.on_bridge_log)
        self.engine.on_log.subscribe(self.on_engine_log)
        
        # Start the simulation timer
        self.set_interval(0.1, self.simulate_step)

    def simulate_step(self) -> None:
        self.engine.simulate()
        self.status_panel.update_status(self.engine)
        
        # Update button states based on connector status
        conn = self.engine.connectors[0]
        self.query_one("#btn_plug", Button).disabled = conn.is_plugged_in
        self.query_one("#btn_unplug", Button).disabled = not conn.is_plugged_in
        # Swipe only makes sense if plugged in and not charging? Or stop charging if charging?
        # For simplicity: Swipe is always enabled if plugged in? 
        self.query_one("#btn_swipe", Button).disabled = not conn.is_plugged_in

    def on_bridge_log(self, message: str) -> None:
        # Use call_from_thread if this is called from the adapter thread
        self.app.call_from_thread(self.log_panel.log_message, f"[blue]OCPP:[/blue] {message}")

    def on_engine_log(self, message: str) -> None:
        self.log_panel.log_message(f"[yellow]Engine:[/yellow] {message}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_plug":
            self.action_plug_in()
        elif event.button.id == "btn_unplug":
            self.action_unplug()
        elif event.button.id == "btn_swipe":
            self.action_swipe_card()

    def action_plug_in(self) -> None:
        self.engine.plug_in(0)
        self.log_panel.log_message("[green]UI:[/green] Plugged In")

    def action_unplug(self) -> None:
        self.engine.unplug(0)
        self.log_panel.log_message("[yellow]UI:[/yellow] Unplugged")

    def action_swipe_card(self) -> None:
        # Simulate Authorize -> Start Session
        # In a real scenario, this would send Authorize, wait for response, then StartTransaction
        # Here we just Start Session which triggers StartTransaction in Bridge
        if not self.engine.session:
            self.engine.start_session(connector_id=0, transaction_id=0) # 0 is temp ID
            self.log_panel.log_message("[green]UI:[/green] Swiped Card - Requesting Start Session")
        else:
            self.engine.stop_session()
            self.log_panel.log_message("[red]UI:[/red] Swiped Card - Requesting Stop Session")

    def action_stop_session(self) -> None:
        self.engine.stop_session()
        self.log_panel.log_message("[red]UI:[/red] Requested Stop Session")

    def action_quit(self) -> None:
        self.app.exit()

class ManualScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="manual-controls"):
                yield Label("[b]Manual OCPP Controls[/b]")
                yield Button("BootNotification", id="btn_boot")
                yield Button("Heartbeat", id="btn_heartbeat")
                yield Horizontal(
                    Button("StartTransaction", id="btn_start"),
                    Input(placeholder="ID Tag", id="input_tag"),
                    classes="input-row"
                )
                yield Button("StopTransaction", id="btn_stop")
                yield Button("StatusNotification", id="btn_status")
            yield LogPanel(id="manual-log-panel")
        yield Footer()

    def on_mount(self) -> None:
        # For Manual mode, we might not need a full Engine, just the Adapter
        # But Bridge has AsyncRunner which handles connection.
        # Let's use a Bridge but maybe without engine interaction?
        # Or just create AsyncRunner directly.
        from chargeghost_evse.engine.engine import Engine # Dummy engine
        self.engine = Engine()
        self.bridge = Bridge(self.engine)
        self.bridge.setup()
        
        self.log_panel = self.query_one("#manual-log-panel", LogPanel)
        self.bridge.on_log.subscribe(self.on_bridge_log)

    def on_bridge_log(self, message: str) -> None:
        self.app.call_from_thread(self.log_panel.log_message, f"[blue]OCPP:[/blue] {message}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        adapter = self.bridge.runner.adapter
        loop = self.bridge.runner.loop
        
        if not adapter or not loop:
            self.log_panel.log_message("[red]Error:[/red] Adapter not connected")
            return

        if event.button.id == "btn_boot":
            asyncio.run_coroutine_threadsafe(adapter.send_boot_notification(), loop)
        elif event.button.id == "btn_heartbeat":
            asyncio.run_coroutine_threadsafe(adapter.send_heartbeat(), loop)
        elif event.button.id == "btn_start":
            id_tag = self.query_one("#input_tag", Input).value or "MANUAL_TAG"
            asyncio.run_coroutine_threadsafe(
                adapter.send_start_transaction(
                    connector_id=1,
                    id_tag=id_tag,
                    meter_start=0,
                    timestamp=datetime.now(timezone.utc).isoformat()
                ),
                loop
            )
        elif event.button.id == "btn_stop":
            asyncio.run_coroutine_threadsafe(
                adapter.send_stop_transaction(
                    meter_stop=100,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    transaction_id=1
                ),
                loop
            )

class ChargeGhostApp(App):
    CSS = """
    .mode-select-container {
        align: center middle;
        height: 100%;
    }
    #title {
        margin-bottom: 2;
        width: 100%;
        text-align: center;
        text-style: bold;
    }
    Button {
        margin-bottom: 1;
        width: 30;
    }
    .controls-panel {
        width: 30%;
        border-right: solid white;
        padding: 1;
    }
    #status-panel {
        margin-top: 2;
        height: 100%;
        width: 100%;
    }
    #log-panel, #manual-log-panel {
        width: 70%;
        padding: 1;
    }
    .panel-title {
        text-align: center;
        margin-bottom: 1;
    }
    #manual-controls {
        width: 30%;
        border-right: solid white;
        padding: 1;
    }
    .input-row {
        height: auto;
        margin-bottom: 1;
    }
    .input-row Button {
        width: 20;
    }
    .input-row Input {
        width: 15;
    }
    """

    def on_mount(self) -> None:
        self.push_screen(ModeSelectScreen())

if __name__ == "__main__":
    app = ChargeGhostApp()
    app.run()
