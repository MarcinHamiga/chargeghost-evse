from unittest.mock import MagicMock

from chargeghost_evse.devtools.scenario_models import (
    ActionStep,
    AssertStep,
    FaultStep,
    NoteStep,
    ScenarioDefinition,
    ScenarioDefaults,
    WaitStep,
)
from chargeghost_evse.devtools.scenario_report import ScenarioReport, StepResult
from chargeghost_evse.devtools.scenario_runner import ScenarioRunner, RunnerState


class TestScenarioRunner:
    def test_initial_state_is_idle(self) -> None:
        controller = MagicMock()
        runner = ScenarioRunner(controller=controller)
        assert runner.state == RunnerState.IDLE

    def test_start_transitions_to_running(self) -> None:
        controller = MagicMock()
        runner = ScenarioRunner(controller=controller)
        scenario = self._make_scenario([ActionStep(action="plug_in", label="Plug")])

        runner.start(scenario)

        assert runner.state == RunnerState.RUNNING
        assert runner.report is not None
        assert runner.report.started_at is not None

    def test_rejects_second_run_while_active(self) -> None:
        controller = MagicMock()
        runner = ScenarioRunner(controller=controller)
        scenario = self._make_scenario([ActionStep(action="plug_in", label="Plug")])

        runner.start(scenario)
        result = runner.start(scenario)

        assert result is False
        assert runner.state == RunnerState.RUNNING

    def test_runner_executes_action_steps_in_order(self) -> None:
        controller = MagicMock()
        runner = ScenarioRunner(controller=controller)
        steps = [
            ActionStep(action="plug_in", label="Plug", step_index=0),
            ActionStep(action="start_charging", label="Start", step_index=1),
        ]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)

        assert controller.execute_action.call_count == 1
        assert controller.execute_action.call_args[0][0] == "plug_in"

    def test_runner_advances_to_next_action_after_tick(self) -> None:
        controller = MagicMock()
        controller.execute_action.return_value = MagicMock(success=True)
        runner = ScenarioRunner(controller=controller)
        steps = [
            ActionStep(action="plug_in", label="Plug", step_index=0),
            ActionStep(action="start_charging", label="Start", step_index=1),
        ]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)
        runner.tick(0.1)

        assert controller.execute_action.call_count == 2
        assert controller.execute_action.call_args_list[1][0][0] == "start_charging"

    def test_runner_completes_after_all_steps(self) -> None:
        controller = MagicMock()
        controller.execute_action.return_value = MagicMock(success=True)
        runner = ScenarioRunner(controller=controller)
        steps = [ActionStep(action="plug_in", label="Plug", step_index=0)]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)
        runner.tick(0.1)

        assert runner.state == RunnerState.COMPLETED

    def test_runner_marks_step_failed_on_false_result(self) -> None:
        controller = MagicMock()
        controller.execute_action.return_value = MagicMock(success=False, message="Error")
        runner = ScenarioRunner(controller=controller)
        steps = [ActionStep(action="plug_in", label="Plug", step_index=0)]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)

        assert runner.state == RunnerState.FAILED
        assert runner.report is not None
        assert runner.report.failure_reason is not None

    def test_cancel_stops_after_current_step(self) -> None:
        controller = MagicMock()
        controller.execute_action.return_value = MagicMock(success=True)
        runner = ScenarioRunner(controller=controller)
        steps = [
            ActionStep(action="plug_in", label="Plug", step_index=0),
            ActionStep(action="start_charging", label="Start", step_index=1),
        ]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)
        runner.cancel()
        runner.tick(0.1)

        assert runner.state == RunnerState.CANCELLED
        assert controller.execute_action.call_count == 1

    def test_runner_failure_includes_step_context(self) -> None:
        controller = MagicMock()
        controller.execute_action.return_value = MagicMock(
            success=False, message="Engine error"
        )
        runner = ScenarioRunner(controller=controller)
        steps = [ActionStep(action="plug_in", label="Plug", step_index=0)]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)

        assert runner.report is not None
        assert runner.report.failed_step_index == 0
        assert "Plug" in runner.report.failure_reason

    def test_note_step_does_not_call_controller(self) -> None:
        controller = MagicMock()
        runner = ScenarioRunner(controller=controller)
        steps = [
            NoteStep(message="This is a note", label="Note", step_index=0),
            ActionStep(action="plug_in", label="Plug", step_index=1),
        ]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)

        controller.execute_action.assert_not_called()
        assert runner.state == RunnerState.RUNNING

    def test_wait_step_accumulates_time(self) -> None:
        controller = MagicMock()
        runner = ScenarioRunner(controller=controller)
        steps = [
            WaitStep(duration=1.0, label="Wait 1s", step_index=0),
            ActionStep(action="plug_in", label="Plug", step_index=1),
        ]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        for _ in range(5):
            runner.tick(0.2)

        controller.execute_action.assert_not_called()
        assert runner.state == RunnerState.RUNNING

        runner.tick(0.2)
        controller.execute_action.assert_called_once()

    def test_wait_step_transitions_to_next_step(self) -> None:
        controller = MagicMock()
        controller.execute_action.return_value = MagicMock(success=True)
        runner = ScenarioRunner(controller=controller)
        steps = [
            WaitStep(duration=0.5, label="Wait 0.5s", step_index=0),
            ActionStep(action="plug_in", label="Plug", step_index=1),
        ]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.5)

        controller.execute_action.assert_not_called()
        runner.tick(0.1)
        controller.execute_action.assert_called_once()
        assert runner.report is not None
        assert len(runner.report.step_results) == 2

    def _make_scenario(self, steps: list) -> ScenarioDefinition:
        return ScenarioDefinition(
            schema_version="1.0",
            name="Test",
            description="Test scenario",
            defaults=ScenarioDefaults(),
            steps=steps,
        )


class TestScenarioReport:
    def test_step_result_records_outcome(self) -> None:
        result = StepResult(
            step_index=0,
            kind="action",
            label="Plug",
            success=True,
            duration=0.1,
        )
        assert result.success is True

    def test_report_accumulates_results(self) -> None:
        report = ScenarioReport(scenario_name="Test")
        report.add_step_result(
            StepResult(step_index=0, kind="action", label="Step 1", success=True, duration=0.1)
        )
        report.add_step_result(
            StepResult(step_index=1, kind="action", label="Step 2", success=True, duration=0.1)
        )
        assert len(report.step_results) == 2
        assert report.total_steps == 2

    def test_report_marks_failed(self) -> None:
        report = ScenarioReport(scenario_name="Test")
        report.mark_failed("Error", 0)
        assert report.success is False
        assert report.failure_reason == "Error"
        assert report.failed_step_index == 0

    def test_report_completed_at_set_on_success(self) -> None:
        report = ScenarioReport(scenario_name="Test")
        report.mark_completed()
        assert report.finished_at is not None
        assert report.success is True


class TestWaitAndAssert:
    def test_wait_for_connector_status_succeeds_before_timeout(self) -> None:
        controller = MagicMock()
        connector = MagicMock()
        connector.status.value = "Available"
        controller.get_connector.return_value = connector
        runner = ScenarioRunner(controller=controller)

        steps = [
            ActionStep(action="plug_in", label="Plug", step_index=0),
            AssertStep(
                condition="connector_status",
                expected="Available",
                label="Check status",
                connector_id=1,
                step_index=1,
            ),
        ]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)
        runner.tick(0.1)

        assert runner.state == RunnerState.COMPLETED
        assert controller.get_connector.call_count >= 1

    def test_assert_session_active_fails_when_missing(self) -> None:
        controller = MagicMock()
        controller.get_session.return_value = None
        runner = ScenarioRunner(controller=controller)

        steps = [
            AssertStep(
                condition="session_exists",
                expected=True,
                label="Session should exist",
                step_index=0,
            ),
        ]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)

        assert runner.state == RunnerState.FAILED
        assert runner.report is not None
        assert runner.report.failure_reason is not None
        assert "Session" in runner.report.failure_reason

    def test_assert_session_not_exists_passes_when_no_session(self) -> None:
        controller = MagicMock()
        controller.get_session.return_value = None
        runner = ScenarioRunner(controller=controller)

        steps = [
            AssertStep(
                condition="session_exists",
                expected=False,
                label="No session yet",
                step_index=0,
            ),
        ]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)

        assert runner.state == RunnerState.COMPLETED

    def test_assert_connection_state_succeeds(self) -> None:
        controller = MagicMock()
        controller.is_connected = True
        runner = ScenarioRunner(controller=controller)

        steps = [
            AssertStep(
                condition="connection_state",
                expected=True,
                label="Should be connected",
                step_index=0,
            ),
        ]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)

        assert runner.state == RunnerState.COMPLETED

    def test_assert_connection_state_fails_when_disconnected(self) -> None:
        controller = MagicMock()
        controller.is_connected = False
        runner = ScenarioRunner(controller=controller)

        steps = [
            AssertStep(
                condition="connection_state",
                expected=True,
                label="Should be connected",
                step_index=0,
            ),
        ]
        scenario = self._make_scenario(steps)

        runner.start(scenario)
        runner.tick(0.1)

        assert runner.state == RunnerState.FAILED
        assert runner.report is not None
        assert "disconnected" in runner.report.failure_reason

    def _make_scenario(self, steps: list) -> ScenarioDefinition:
        return ScenarioDefinition(
            schema_version="1.0",
            name="Test",
            description="Test scenario",
            defaults=ScenarioDefaults(),
            steps=steps,
        )


def _make_scenario(steps: list) -> ScenarioDefinition:
    return ScenarioDefinition(
        schema_version="1.0",
        name="Test",
        description="Test scenario",
        defaults=ScenarioDefaults(),
        steps=steps,
    )


class TestFaultSteps:
    def test_fault_enable_step(self) -> None:
        controller = MagicMock()
        controller.fault_manager = MagicMock()
        controller.fault_manager.enable = MagicMock()

        steps = [FaultStep(fault_action="enable", fault_id="frozen_meter", step_index=0)]
        scenario = _make_scenario(steps)
        runner = ScenarioRunner(controller=controller)

        runner.start(scenario)
        runner.tick(0.1)

        controller.fault_manager.enable.assert_called_once_with(
            "frozen_meter", config=None
        )
        assert runner.state == RunnerState.COMPLETED

    def test_fault_enable_step_with_config(self) -> None:
        controller = MagicMock()
        controller.fault_manager = MagicMock()

        steps = [
            FaultStep(
                fault_action="enable",
                fault_id="meter_jump",
                parameters={"amount_kwh": 5.0},
                count_limit=3,
                step_index=0,
            )
        ]
        scenario = _make_scenario(steps)
        runner = ScenarioRunner(controller=controller)

        runner.start(scenario)
        runner.tick(0.1)

        call_args = controller.fault_manager.enable.call_args
        assert call_args[0][0] == "meter_jump"
        config = call_args[1].get("config") or call_args[0][1]
        assert config.parameters == {"amount_kwh": 5.0}
        assert config.count_limit == 3

    def test_fault_disable_step(self) -> None:
        controller = MagicMock()
        controller.fault_manager = MagicMock()

        steps = [FaultStep(fault_action="disable", fault_id="frozen_meter", step_index=0)]
        scenario = _make_scenario(steps)
        runner = ScenarioRunner(controller=controller)

        runner.start(scenario)
        runner.tick(0.1)

        controller.fault_manager.disable.assert_called_once_with("frozen_meter")
        assert runner.state == RunnerState.COMPLETED

    def test_fault_clear_all_step(self) -> None:
        controller = MagicMock()
        controller.fault_manager = MagicMock()

        steps = [FaultStep(fault_action="clear_all", step_index=0)]
        scenario = _make_scenario(steps)
        runner = ScenarioRunner(controller=controller)

        runner.start(scenario)
        runner.tick(0.1)

        controller.fault_manager.clear_all.assert_called_once()
        assert runner.state == RunnerState.COMPLETED

    def test_fault_enable_unknown_id_fails(self) -> None:
        controller = MagicMock()
        controller.fault_manager = MagicMock()
        controller.fault_manager.enable.side_effect = ValueError("Unknown fault")

        steps = [FaultStep(fault_action="enable", fault_id="nonexistent", step_index=0)]
        scenario = _make_scenario(steps)
        runner = ScenarioRunner(controller=controller)

        runner.start(scenario)
        runner.tick(0.1)

        assert runner.state == RunnerState.FAILED

    def test_fault_step_without_manager_fails(self) -> None:
        controller = MagicMock()
        controller.fault_manager = None

        steps = [FaultStep(fault_action="enable", fault_id="frozen_meter", step_index=0)]
        scenario = _make_scenario(steps)
        runner = ScenarioRunner(controller=controller)

        runner.start(scenario)
        runner.tick(0.1)

        assert runner.state == RunnerState.FAILED

    def test_fault_step_records_in_report(self) -> None:
        controller = MagicMock()
        controller.fault_manager = MagicMock()

        steps = [
            FaultStep(
                fault_action="enable",
                fault_id="frozen_meter",
                label="Freeze meter",
                step_index=0,
            )
        ]
        scenario = _make_scenario(steps)
        runner = ScenarioRunner(controller=controller)

        runner.start(scenario)
        runner.tick(0.1)

        assert len(runner.report.step_results) == 1
        result = runner.report.step_results[0]
        assert result.kind == "fault"
        assert result.label == "Freeze meter"
        assert result.success is True
