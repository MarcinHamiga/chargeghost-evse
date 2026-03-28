from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class StepResult:
    step_index: int
    kind: str
    label: str
    success: bool
    duration: float
    error_message: str | None = None


@dataclass
class ScenarioReport:
    scenario_name: str
    started_at: datetime = field(default_factory=lambda: datetime.now())
    finished_at: datetime | None = None
    step_results: list[StepResult] = field(default_factory=list)
    success: bool = True
    failure_reason: str | None = None
    failed_step_index: int | None = None
    last_completed_step: int | None = None

    @property
    def total_steps(self) -> int:
        return len(self.step_results)

    def add_step_result(self, result: StepResult) -> None:
        self.step_results.append(result)
        self.last_completed_step = result.step_index

    def mark_completed(self) -> None:
        self.success = True
        self.finished_at = datetime.now()

    def mark_failed(self, reason: str, step_index: int) -> None:
        self.success = False
        self.failure_reason = reason
        self.failed_step_index = step_index
        self.finished_at = datetime.now()

    @property
    def duration_seconds(self) -> float:
        if self.finished_at is None:
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()
