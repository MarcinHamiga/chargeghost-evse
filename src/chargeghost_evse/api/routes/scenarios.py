from __future__ import annotations

from fastapi import APIRouter, Depends

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import (
    ActionResult,
    RunnerStatusResponse,
    ScenarioLoadRequest,
    ScenarioReportInfo,
    StepResultInfo,
)
from chargeghost_evse.devtools.scenario_loader import ScenarioLoader

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])


@router.post("/load", response_model=ActionResult)
async def load_scenario(
    request: ScenarioLoadRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    def do_load() -> ActionResult:
        try:
            scenario = ScenarioLoader.from_dict(request.model_dump(exclude_none=True))
            runtime._loaded_scenario = scenario
            return ActionResult(
                success=True,
                message=f"Scenario '{scenario.name}' loaded ({len(scenario.steps)} steps)",
            )
        except Exception as exc:
            return ActionResult(
                success=False, message=f"Failed to load scenario: {exc}"
            )

    return await runtime.call(do_load)


@router.post("/start", response_model=ActionResult)
async def start_scenario(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    def do_start() -> ActionResult:
        runner = runtime.scenario_runner
        if runner is None:
            return ActionResult(success=False, message="Scenario runner not available")

        scenario = runtime._loaded_scenario
        if scenario is None:
            return ActionResult(success=False, message="No scenario loaded")

        started = runner.start(scenario)
        if started:
            return ActionResult(
                success=True, message=f"Scenario '{scenario.name}' started"
            )
        return ActionResult(success=False, message="Scenario runner is already running")

    return await runtime.call(do_start)


@router.post("/cancel", response_model=ActionResult)
async def cancel_scenario(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    def do_cancel() -> ActionResult:
        runner = runtime.scenario_runner
        if runner is None:
            return ActionResult(success=False, message="Scenario runner not available")

        runner.cancel()
        return ActionResult(success=True, message="Scenario cancelled")

    return await runtime.call(do_cancel)


@router.get("/status", response_model=RunnerStatusResponse)
async def get_status(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> RunnerStatusResponse:
    def do_status() -> RunnerStatusResponse:
        runner = runtime.scenario_runner
        if runner is None:
            return RunnerStatusResponse(state="idle")

        scenario_name = (
            runtime._loaded_scenario.name if runtime._loaded_scenario else None
        )
        return RunnerStatusResponse(
            state=runner.state.value,
            scenario_name=scenario_name,
            current_step_index=runner._current_step_index,
        )

    return await runtime.call(do_status)


@router.get("/report", response_model=ScenarioReportInfo)
async def get_report(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ScenarioReportInfo:
    def do_report() -> ScenarioReportInfo:
        runner = runtime.scenario_runner
        if runner is None or runner.report is None:
            return ScenarioReportInfo(
                scenario_name="",
                success=True,
                steps=[],
            )

        report = runner.report
        return ScenarioReportInfo(
            scenario_name=report.scenario_name,
            started_at=report.started_at.isoformat() if report.started_at else None,
            finished_at=report.finished_at.isoformat() if report.finished_at else None,
            success=report.success,
            failure_reason=report.failure_reason,
            failed_step_index=report.failed_step_index,
            steps=[
                StepResultInfo(
                    step_index=r.step_index,
                    kind=r.kind,
                    label=r.label,
                    success=r.success,
                    duration=r.duration,
                    error_message=r.error_message,
                )
                for r in report.step_results
            ],
        )

    return await runtime.call(do_report)
