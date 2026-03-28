import tempfile
import os
from unittest.mock import patch, MagicMock


class TestMainHeadlessTimeline:
	def test_headless_runtime_can_export_timeline(self):
		from chargeghost_evse.devtools.scenario_cli import run_headless
		from chargeghost_evse.devtools.timeline_store import TimelineStore

		store = TimelineStore()
		store.append(
			source="engine",
			direction="local",
			event_type="session",
			action="session_started",
			summary="Test event",
		)

		with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
			tmp_path = f.name

		try:
			from chargeghost_evse.devtools.scenario_cli import _HeadlessBridge

			class _TestBridge(_HeadlessBridge):
				def __init__(self, timeline_store=None):
					super().__init__()
					self.timeline_store = timeline_store

			from chargeghost_evse.devtools.simulator_controller import (
				SimulatorController,
			)
			from chargeghost_evse.engine.engine import Engine
			from chargeghost_evse.devtools.scenario_runner import ScenarioRunner

			engine = Engine()
			engine.timeline_store = store
			bridge = _TestBridge(timeline_store=store)
			controller = SimulatorController(engine=engine, bridge=bridge)
			runner = ScenarioRunner(controller=controller)

			with patch(
				"chargeghost_evse.devtools.scenario_cli.ScenarioRunner",
				return_value=runner,
			):
				with patch(
					"chargeghost_evse.devtools.scenario_cli.ScenarioLoader"
				) as mock_loader:
					mock_scenario = MagicMock()
					mock_scenario.name = "Test"
					mock_scenario.steps = []
					mock_loader.load.return_value = mock_scenario

					runner.start = MagicMock(return_value=True)
					runner.state = MagicMock()
					import chargeghost_evse.devtools.scenario_cli as cli

					original_runner_state = cli.RunnerState

					class MockRunnerState:
						RUNNING = "running"
						IDLE = "idle"
						COMPLETED = "completed"

					cli.RunnerState = MockRunnerState
					runner.state = "completed"
					runner.report = MagicMock()
					runner.report.step_results = []
					runner.report.duration_seconds = 1.0

					try:
						with tempfile.NamedTemporaryFile(
							suffix=".json", delete=False
						) as f:
							exported_path = f.name

						run_headless(
							"/fake/path.scenario",
							timeout=5.0,
							timeline_store=store,
							timeline_export_path=exported_path,
						)
					finally:
						cli.RunnerState = original_runner_state

		finally:
			if tmp_path and os.path.exists(tmp_path):
				os.unlink(tmp_path)

	def test_main_still_defaults_to_desktop_mode(self):
		import chargeghost_evse.main as main_module

		with patch("sys.argv", ["chargeghost-evse"]):
			with patch("chargeghost_evse.ui.app.main") as mock_ui_main:
				mock_ui_main.side_effect = SystemExit(0)
				try:
					main_module.main_entry()
				except SystemExit:
					pass

				mock_ui_main.assert_called_once()


class TestMainEntry:
	def test_main_entry_without_args_does_not_raise(self):
		import chargeghost_evse.main as main_module

		with patch("sys.argv", ["chargeghost-evse"]):
			with patch("chargeghost_evse.ui.app.main") as mock_ui_main:
				mock_ui_main.side_effect = SystemExit(0)
				try:
					main_module.main_entry()
				except SystemExit:
					pass

				mock_ui_main.assert_called_once()

	def test_headless_with_timeline_store_creates_store(self):
		from chargeghost_evse.devtools.scenario_cli import run_headless
		from chargeghost_evse.devtools.timeline_store import TimelineStore
		from chargeghost_evse.devtools.simulator_controller import SimulatorController
		from chargeghost_evse.engine.engine import Engine

		store_created = []

		original_init = TimelineStore.__init__

		def mock_init(self, *args, **kwargs):
			original_init(self, *args, **kwargs)
			store_created.append(True)

		with patch.object(TimelineStore, "__init__", mock_init):
			from chargeghost_evse.devtools.scenario_cli import _HeadlessBridge
			from chargeghost_evse.devtools.scenario_runner import ScenarioRunner

			engine = Engine()
			bridge = _HeadlessBridge()
			controller = SimulatorController(engine=engine, bridge=bridge)
			runner = ScenarioRunner(controller=controller)

			with patch(
				"chargeghost_evse.devtools.scenario_cli.ScenarioRunner",
				return_value=runner,
			):
				with patch(
					"chargeghost_evse.devtools.scenario_cli.ScenarioLoader"
				) as mock_loader:
					mock_scenario = MagicMock()
					mock_scenario.name = "Test"
					mock_scenario.steps = []
					mock_loader.load.return_value = mock_scenario

					runner.start = MagicMock(return_value=True)

					import chargeghost_evse.devtools.scenario_cli as cli

					original_runner_state = cli.RunnerState

					class MockRunnerState:
						RUNNING = "running"
						IDLE = "idle"
						COMPLETED = "completed"

					cli.RunnerState = MockRunnerState
					runner.state = "completed"
					runner.report = MagicMock()
					runner.report.step_results = []
					runner.report.duration_seconds = 1.0

					with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
						exported_path = f.name

					try:
						run_headless(
							"/fake/path.scenario",
							timeout=5.0,
							timeline_store=None,
							timeline_export_path=exported_path,
						)
					finally:
						cli.RunnerState = original_runner_state
						os.unlink(exported_path)
