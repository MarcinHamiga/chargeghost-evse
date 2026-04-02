import logging
import time
from enum import Enum

from chargeghost_evse.devtools.scenario_models import (
    ActionStep,
    AssertStep,
    FaultStep,
    NoteStep,
    ScenarioDefinition,
    WaitStep,
)
from chargeghost_evse.devtools.scenario_report import ScenarioReport, StepResult
from chargeghost_evse.devtools.simulator_controller import SimulatorController


class RunnerState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScenarioRunner:
    def __init__(self, controller: SimulatorController) -> None:
        self.controller = controller
        self.state = RunnerState.IDLE
        self.report: ScenarioReport | None = None
        self._scenario: ScenarioDefinition | None = None
        self._current_step_index: int = 0
        self._wait_remaining: float = 0.0
        self._wait_just_completed: bool = False
        self._logger = logging.getLogger("chargeghost.devtools.runner")

    def start(self, scenario: ScenarioDefinition) -> bool:
        if self.state == RunnerState.RUNNING:
            return False

        self._scenario = scenario
        self._current_step_index = 0
        self._wait_remaining = 0.0
        self._wait_just_completed = False
        self.report = ScenarioReport(scenario_name=scenario.name)
        self.state = RunnerState.RUNNING
        self._logger.info(f"Scenario started: {scenario.name}")
        return True

    def cancel(self) -> None:
        if self.state != RunnerState.RUNNING:
            return

        self.state = RunnerState.CANCELLED
        if self.report:
            self.report.mark_failed("Cancelled by user", self._current_step_index)
        self._logger.info("Scenario cancelled")

    def tick(self, interval_seconds: float) -> None:
        if self.state != RunnerState.RUNNING or self._scenario is None:
            return

        if self._wait_just_completed:
            self._wait_just_completed = False
            self._execute_current_step(0)
            return

        if self._wait_remaining > 0:
            self._wait_remaining -= interval_seconds
            if self._wait_remaining <= 0.001:
                self._wait_remaining = 0
                self._advance_to_next_step()
                self._wait_just_completed = True
            return

        self._execute_current_step(interval_seconds)

    def _execute_current_step(self, interval_seconds: float) -> None:
        if self._scenario is None or self.report is None:
            return

        step = self._scenario.steps[self._current_step_index]
        step_start = time.monotonic()

        if isinstance(step, NoteStep):
            self._logger.info(f"[note] {step.message}")
            self.report.add_step_result(
                StepResult(
                    step_index=step.step_index,
                    kind=step.kind,
                    label=step.label or step.message[:50],
                    success=True,
                    duration=time.monotonic() - step_start,
                )
            )
            self._advance_to_next_step()
            return

        if isinstance(step, WaitStep):
            self._wait_remaining = step.duration - interval_seconds
            if self._wait_remaining <= 0.001:
                self._wait_remaining = 0
                if self.report:
                    self.report.add_step_result(
                        StepResult(
                            step_index=step.step_index,
                            kind=step.kind,
                            label=step.label,
                            success=True,
                            duration=time.monotonic() - step_start,
                        )
                    )
                self._advance_to_next_step()
                self._wait_just_completed = True
            return

        if isinstance(step, AssertStep):
            self._handle_assert_step(step, step_start)
            return

        if isinstance(step, FaultStep):
            self._handle_fault_step(step, step_start)
            return

        if isinstance(step, ActionStep):
            connector_id = step.connector_id if step.connector_id is not None else 1
            result = self.controller.execute_action(
                step.action, connector_id=connector_id
            )
            duration = time.monotonic() - step_start
            if result.success:
                self.report.add_step_result(
                    StepResult(
                        step_index=step.step_index,
                        kind=step.kind,
                        label=step.label,
                        success=True,
                        duration=duration,
                    )
                )
                self._advance_to_next_step()
            else:
                self.report.mark_failed(
                    f"Step '{step.label}' failed: {result.message}",
                    step.step_index,
                )
                self.state = RunnerState.FAILED
                self._logger.error(
                    f"Scenario failed at step {step.step_index}: {result.message}"
                )

    def _handle_assert_step(self, step: AssertStep, step_start: float) -> None:
        if self.report is None:
            return

        success, error_msg = self._evaluate_assertion(step)
        duration = time.monotonic() - step_start

        self.report.add_step_result(
            StepResult(
                step_index=step.step_index,
                kind=step.kind,
                label=step.label,
                success=success,
                duration=duration,
                error_message=error_msg,
            )
        )

        if success:
            self._advance_to_next_step()
        else:
            self.report.mark_failed(
                f"Assertion failed: {step.label} - {error_msg}",
                step.step_index,
            )
            self.state = RunnerState.FAILED

    def _handle_fault_step(self, step: FaultStep, step_start: float) -> None:
        if self.report is None:
            return

        fault_manager = self.controller.fault_manager
        if fault_manager is None:
            self.report.add_step_result(
                StepResult(
                    step_index=step.step_index,
                    kind=step.kind,
                    label=step.label,
                    success=False,
                    duration=time.monotonic() - step_start,
                    error_message="No fault manager available",
                )
            )
            self.report.mark_failed(
                f"Fault step failed: {step.label} - No fault manager available",
                step.step_index,
            )
            self.state = RunnerState.FAILED
            return

        try:
            if step.fault_action == "enable":
                from chargeghost_evse.devtools.fault_models import FaultConfig

                config: "FaultConfig | None" = None
                if step.parameters or step.count_limit is not None:
                    config = FaultConfig(
                        fault_id=step.fault_id,
                        parameters=step.parameters,
                        count_limit=step.count_limit,
                    )
                fault_manager.enable(step.fault_id, config=config)
            elif step.fault_action == "disable":
                fault_manager.disable(step.fault_id)
            elif step.fault_action == "clear_all":
                fault_manager.clear_all()

            self.report.add_step_result(
                StepResult(
                    step_index=step.step_index,
                    kind=step.kind,
                    label=step.label,
                    success=True,
                    duration=time.monotonic() - step_start,
                )
            )
            self._advance_to_next_step()
        except ValueError as exc:
            self.report.add_step_result(
                StepResult(
                    step_index=step.step_index,
                    kind=step.kind,
                    label=step.label,
                    success=False,
                    duration=time.monotonic() - step_start,
                    error_message=str(exc),
                )
            )
            self.report.mark_failed(
                f"Fault step failed: {step.label} - {exc}",
                step.step_index,
            )
            self.state = RunnerState.FAILED

    def _evaluate_assertion(self, step: AssertStep) -> tuple[bool, str]:
        connector_id = step.connector_id if step.connector_id is not None else 1

        if step.condition == "session_exists":
            session = self.controller.get_session(connector_id)
            if step.expected is (session is not None):
                return True, ""
            actual = "exists" if session is not None else "does not exist"
            return False, f"Expected session {step.expected}, but it {actual}"

        if step.condition == "connector_status":
            conn = self.controller.get_connector(connector_id)
            if conn is None:
                return False, f"Connector {connector_id} not found"
            if conn.status.value == step.expected:
                return True, ""
            return (
                False,
                f"Expected status '{step.expected}', got '{conn.status.value}'",
            )

        if step.condition == "connection_state":
            is_connected = self.controller.is_connected
            if step.expected is is_connected:
                return True, ""
            actual = "connected" if is_connected else "disconnected"
            return False, f"Expected {step.expected}, but connection is {actual}"

        if step.condition == "meter_threshold":
            session = self.controller.get_session(connector_id)
            if session is None:
                return False, "No active session"
            meter = self.controller.engine.get_energy_meter(connector_id)
            reading = meter.get_meter_reading()
            if reading >= step.expected:
                return True, ""
            return False, f"Expected meter >= {step.expected}, got {reading}"

        return False, f"Unknown condition: {step.condition}"

    def _advance_to_next_step(self) -> None:
        if self._scenario is None:
            return

        self._current_step_index += 1
        if self._current_step_index >= len(self._scenario.steps):
            self.state = RunnerState.COMPLETED
            if self.report:
                self.report.mark_completed()
            self._logger.info("Scenario completed successfully")
