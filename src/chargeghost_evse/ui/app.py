from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Header,
    Footer,
    Button,
    Label,
    Input,
    TabbedContent,
    TabPane,
    Checkbox,
)
from textual.containers import Container, Vertical, Horizontal
from textual.binding import Binding

from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.ui.widgets.log_panel import LogPanel
from chargeghost_evse.ui.widgets.status_panel import StatusPanel
from chargeghost_evse.util.config import SimulationConfig

import asyncio
import threading
from datetime import datetime, timezone


class ModeSelectScreen(Screen):
    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Vertical(
                Label("Choose ChargeGhost EVSE Mode:", id="title"),
                Button("Simulator Mode", variant="primary", id="simulator_mode"),
                Button("Manual Mode", variant="default", id="manual_mode"),
                classes="mode-select-container",
            )
        )
        yield Footer()

    def action_quit(self) -> None:
        self.app.exit()

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
        Binding("c", "copy_logs", "Copy Logs"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sim-controls", classes="controls-panel"):
                yield Label("[b]Controls[/b]", classes="panel-title")
                with TabbedContent(id="main-tabs", initial="controls-tab"):
                    with TabPane("Controls", id="controls-tab"):
                        yield Button("Plug In", id="btn_plug", variant="primary")
                        yield Button("Swipe Card", id="btn_swipe", variant="success")
                        yield Button("Unplug", id="btn_unplug", variant="error")
                        yield StatusPanel(id="status-panel")
                    with TabPane("Config", id="config-tab"):
                        yield Label("Connection URL:", classes="config-label")
                        yield Input(
                            placeholder="wss://localhost:3000/CP_1", id="input_url"
                        )
                        yield Label("OCPP ID:", classes="config-label")
                        yield Input(placeholder="CP_1", id="input_ocpp_id")
                        yield Label("OCPP Password:", classes="config-label")
                        yield Input(
                            placeholder="Password", id="input_password", password=True
                        )
                        yield Label("Charge Point Model:", classes="config-label")
                        yield Input(placeholder="ChargeGhostV1", id="input_model")
                        yield Label("Charge Point Vendor:", classes="config-label")
                        yield Input(placeholder="ChargeGhost", id="input_vendor")
                        yield Label("Number of Connectors:", classes="config-label")
                        yield Input(placeholder="1", id="input_connectors")
                        yield Checkbox("Skip TLS Verification", id="checkbox_skip_tls")
                        yield Button(
                            "Save Config", id="btn_save_config", variant="primary"
                        )
            yield LogPanel(id="log-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.config = SimulationConfig.load()
        self._populate_config_fields()

        self.engine = Engine()
        for _ in range(self.config.num_connectors):
            self.engine.add_connector()

        self.bridge = Bridge(
            self.engine,
            url=self.config.connection_url,
            charge_point_id=self.config.ocpp_id,
            password=self.config.ocpp_password,
            skip_tls_verify=self.config.skip_tls_verify,
            charge_point_model=self.config.charge_point_model,
            charge_point_vendor=self.config.charge_point_vendor,
        )
        self.bridge.setup()

        self.log_panel = self.query_one("#log-panel", LogPanel)
        self.status_panel = self.query_one("#status-panel", StatusPanel)

        self.bridge.on_log.subscribe(self.on_bridge_log)
        self.engine.on_log.subscribe(self.on_engine_log)

        self.set_interval(0.1, self.simulate_step)

    def _populate_config_fields(self) -> None:
        self.query_one("#input_url", Input).value = self.config.connection_url
        self.query_one("#input_ocpp_id", Input).value = self.config.ocpp_id
        self.query_one("#input_password", Input).value = self.config.ocpp_password
        self.query_one("#input_model", Input).value = self.config.charge_point_model
        self.query_one("#input_vendor", Input).value = self.config.charge_point_vendor
        self.query_one("#input_connectors", Input).value = str(
            self.config.num_connectors
        )
        self.query_one(
            "#checkbox_skip_tls", Checkbox
        ).value = self.config.skip_tls_verify

    def simulate_step(self) -> None:
        self.engine.simulate()
        self.status_panel.update_status(self.engine)

        if self.engine.connectors:
            conn = self.engine.connectors[0]
            self.query_one("#btn_plug", Button).disabled = conn.is_plugged_in
            self.query_one("#btn_unplug", Button).disabled = not conn.is_plugged_in
            self.query_one("#btn_swipe", Button).disabled = not conn.is_plugged_in

    def on_bridge_log(self, message: str) -> None:
        if threading.current_thread() != threading.main_thread():
            self.app.call_from_thread(
                self.log_panel.log_message, f"[blue]OCPP:[/blue] {message}"
            )
        else:
            self.log_panel.log_message(f"[blue]OCPP:[/blue] {message}")

    def on_engine_log(self, message: str) -> None:
        self.log_panel.log_message(f"[yellow]Engine:[/yellow] {message}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_plug":
            self.action_plug_in()
        elif event.button.id == "btn_unplug":
            self.action_unplug()
        elif event.button.id == "btn_swipe":
            self.action_swipe_card()
        elif event.button.id == "btn_save_config":
            self.action_save_config()

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
            self.engine.start_session(connector_id=0, transaction_id=0)  # 0 is temp ID
            self.log_panel.log_message(
                "[green]UI:[/green] Swiped Card - Requesting Start Session"
            )
        else:
            self.engine.stop_session()
            self.log_panel.log_message(
                "[red]UI:[/red] Swiped Card - Requesting Stop Session"
            )

    def action_stop_session(self) -> None:
        self.engine.stop_session()
        self.log_panel.log_message("[red]UI:[/red] Requested Stop Session")

    def action_save_config(self) -> None:
        self.config.connection_url = self.query_one("#input_url", Input).value
        self.config.ocpp_id = self.query_one("#input_ocpp_id", Input).value
        self.config.ocpp_password = self.query_one("#input_password", Input).value
        self.config.charge_point_model = (
            self.query_one("#input_model", Input).value or "ChargeGhostV1"
        )
        self.config.charge_point_vendor = (
            self.query_one("#input_vendor", Input).value or "ChargeGhost"
        )
        try:
            self.config.num_connectors = int(
                self.query_one("#input_connectors", Input).value or "1"
            )
        except ValueError:
            self.config.num_connectors = 1
        self.config.skip_tls_verify = self.query_one(
            "#checkbox_skip_tls", Checkbox
        ).value
        self.config.save()
        self.log_panel.log_message(
            "[green]Config:[/green] Configuration saved. Restart to apply connection changes."
        )

    def action_quit(self) -> None:
        self.app.exit()

    def action_copy_logs(self) -> None:
        self.log_panel.action_copy()


class ManualScreen(Screen):
    BINDINGS = [
        Binding("c", "copy_logs", "Copy Logs"),
        Binding("q", "quit", "Quit"),
    ]

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
                    classes="input-row",
                )
                yield Button("StopTransaction", id="btn_stop")
                yield Button("StatusNotification", id="btn_status")
            yield LogPanel(id="manual-log-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.config = SimulationConfig.load()
        self.engine = Engine()
        self.engine.add_connector()
        self.bridge = Bridge(
            self.engine,
            url=self.config.connection_url,
            charge_point_id=self.config.ocpp_id,
            password=self.config.ocpp_password,
            skip_tls_verify=self.config.skip_tls_verify,
            charge_point_model=self.config.charge_point_model,
            charge_point_vendor=self.config.charge_point_vendor,
        )
        self.bridge.setup()

        self.log_panel = self.query_one("#manual-log-panel", LogPanel)
        self.bridge.on_log.subscribe(self.on_bridge_log)

    def on_bridge_log(self, message: str) -> None:
        if threading.current_thread() != threading.main_thread():
            self.app.call_from_thread(
                self.log_panel.log_message, f"[blue]OCPP:[/blue] {message}"
            )
        else:
            self.log_panel.log_message(f"[blue]OCPP:[/blue] {message}")

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
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
                loop,
            )
        elif event.button.id == "btn_stop":
            asyncio.run_coroutine_threadsafe(
                adapter.send_stop_transaction(
                    meter_stop=100,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    transaction_id=1,
                ),
                loop,
            )
        elif event.button.id == "btn_status":
            asyncio.run_coroutine_threadsafe(
                adapter.send_status_notification(
                    connector_id=1, error_code="NoError", status="Available"
                ),
                loop,
            )

    def action_copy_logs(self) -> None:
        self.log_panel.action_copy()

    def action_quit(self) -> None:
        self.app.exit()


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
    TabbedContent {
        height: 100%;
    }
    #controls-tab {
        padding: 1;
    }
    #config-tab {
        padding: 1;
    }
    .config-label {
        margin-top: 1;
        margin-bottom: 0;
    }
    #config-tab Input {
        width: 100%;
        margin-bottom: 1;
    }
    #config-tab Button {
        width: 100%;
        margin-top: 1;
    }
    #config-tab Checkbox {
        margin-top: 1;
        margin-bottom: 1;
    }
    """

    def on_mount(self) -> None:
        self.push_screen(ModeSelectScreen())


if __name__ == "__main__":
    app = ChargeGhostApp()
    app.run()
