import argparse
import sys
import time
from pathlib import Path

from chargeghost_evse.devtools.scenario_loader import ScenarioLoader, ScenarioLoadError
from chargeghost_evse.devtools.scenario_runner import ScenarioRunner, RunnerState
from chargeghost_evse.devtools.simulator_controller import SimulatorController
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.util.config import SimulationConfig


def run_headless(scenario_path: str, timeout: float = 60.0) -> int:
    config = SimulationConfig.load()
    engine = Engine(multi_evse_mode=config.multi_evse_mode)

    for connector_config in config.connectors:
        engine.add_connector(
            voltage=connector_config.voltage,
            current=connector_config.current,
            phase=connector_config.phase,
        )

    controller = SimulatorController(engine=engine, bridge=None)
    runner = ScenarioRunner(controller=controller)

    path = Path(scenario_path)
    if not path.exists():
        print(f"Error: Scenario file not found: {scenario_path}", file=sys.stderr)
        return 1

    try:
        scenario = ScenarioLoader.load(path)
    except ScenarioLoadError as e:
        print(f"Error loading scenario: {e}", file=sys.stderr)
        return 1

    print(f"Running scenario: {scenario.name}")
    print(f"Steps: {len(scenario.steps)}")

    success = runner.start(scenario)
    if not success:
        print("Error: Failed to start scenario", file=sys.stderr)
        return 1

    start_time = time.monotonic()
    last_report_time = start_time

    while runner.state in (RunnerState.RUNNING, RunnerState.IDLE):
        elapsed = time.monotonic() - start_time
        if elapsed > timeout:
            print(f"Error: Scenario timed out after {timeout}s", file=sys.stderr)
            runner.cancel()
            return 1

        runner.tick(0.1)
        time.sleep(0.1)

        current_time = time.monotonic()
        if current_time - last_report_time >= 1.0:
            last_report_time = current_time
            print(f"  [{int(elapsed)}s] state={runner.state.value}, step={runner._current_step_index}")

    if runner.state == RunnerState.COMPLETED:
        print(f"Scenario completed successfully in {elapsed:.1f}s")
        if runner.report:
            print(f"  Steps completed: {len(runner.report.step_results)}")
            print(f"  Duration: {runner.report.duration_seconds:.1f}s")
        return 0
    elif runner.state == RunnerState.FAILED:
        print("Scenario failed", file=sys.stderr)
        if runner.report:
            print(f"  Failed at step {runner.report.failed_step_index}", file=sys.stderr)
            print(f"  Reason: {runner.report.failure_reason}", file=sys.stderr)
        return 1
    elif runner.state == RunnerState.CANCELLED:
        print("Scenario cancelled by user")
        return 2
    else:
        print(f"Scenario ended with unexpected state: {runner.state}", file=sys.stderr)
        return 1


def add_cli_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run-scenario",
        metavar="PATH",
        help="Run a scenario file in headless mode",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        metavar="SECONDS",
        help="Timeout for headless scenario execution (default: 60)",
    )
