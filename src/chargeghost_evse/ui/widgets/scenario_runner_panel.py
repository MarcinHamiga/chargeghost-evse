from typing import Optional

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chargeghost_evse.devtools.scenario_models import ScenarioDefinition
from chargeghost_evse.devtools.scenario_runner import RunnerState


class ScenarioRunnerPanel(QWidget):
    load_scenario_clicked = Signal()
    start_run_clicked = Signal()
    cancel_run_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scenario: ScenarioDefinition | None = None
        self._current_step_index: int = -1
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Scenario Runner")
        title.setObjectName("sectionHeader")
        layout.addWidget(title)

        self._scenario_name_label = QLabel("No scenario loaded")
        self._scenario_name_label.setObjectName("scenarioNameLabel")
        layout.addWidget(self._scenario_name_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self._btn_load = QPushButton("Load Scenario")
        self._btn_load.setMinimumHeight(36)
        self._btn_load.clicked.connect(self._on_load_clicked)
        button_row.addWidget(self._btn_load)

        self._btn_start = QPushButton("Start")
        self._btn_start.setMinimumHeight(36)
        self._btn_start.setEnabled(False)
        self._btn_start.clicked.connect(self.start_run_clicked.emit)
        button_row.addWidget(self._btn_start)

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setMinimumHeight(36)
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self.cancel_run_clicked.emit)
        button_row.addWidget(self._btn_cancel)

        layout.addLayout(button_row)

        self._steps_list = QListWidget()
        self._steps_list.setObjectName("scenarioStepsList")
        layout.addWidget(self._steps_list, 1)

        self._status_label = QLabel("")
        self._status_label.setObjectName("scenarioStatusLabel")
        layout.addWidget(self._status_label)

        self._result_label = QLabel("")
        self._result_label.setObjectName("scenarioResultLabel")
        self._result_label.setWordWrap(True)
        layout.addWidget(self._result_label)

    def _on_load_clicked(self) -> None:
        self.load_scenario_clicked.emit()

    def set_scenario_path(self, path: str | None) -> None:
        if path:
            self._btn_load.setText("Reload")
        else:
            self._btn_load.setText("Load Scenario")

    def set_scenario(self, scenario: ScenarioDefinition | None) -> None:
        self._scenario = scenario
        self._steps_list.clear()

        if scenario is None:
            self._scenario_name_label.setText("No scenario loaded")
            self._btn_start.setEnabled(False)
            self._btn_start.setText("Start")
            self._status_label.setText("")
            self._result_label.setText("")
            return

        self._scenario_name_label.setText(scenario.name)
        self._btn_start.setEnabled(True)
        self._btn_start.setText("Start")

        for step in scenario.steps:
            kind_icon = self._kind_icon(step.kind)
            label = step.label or f"{step.kind}: {getattr(step, 'action', getattr(step, 'message', ''))}"
            item = QListWidgetItem(f"{kind_icon} {label}")
            item.setData(Qt.ItemDataRole.UserRole, step.step_index)
            self._steps_list.addItem(item)

        self._status_label.setText(f"{len(scenario.steps)} steps")
        self._result_label.setText("")

    def _kind_icon(self, kind: str) -> str:
        if kind == "action":
            return "[A]"
        elif kind == "wait":
            return "[W]"
        elif kind == "assert":
            return "[!]"
        elif kind == "note":
            return "[*]"
        return "[?]"

    def set_runner_state(self, state: RunnerState, current_step_index: int = -1) -> None:
        self._current_step_index = current_step_index

        for i in range(self._steps_list.count()):
            item = self._steps_list.item(i)
            step_idx = item.data(Qt.ItemDataRole.UserRole)
            if step_idx == current_step_index:
                item.setBackground(Qt.GlobalColor.yellow)
            else:
                item.setBackground(Qt.GlobalColor.transparent)

        if state == RunnerState.IDLE:
            self._btn_start.setEnabled(self._scenario is not None)
            self._btn_start.setText("Start")
            self._btn_cancel.setEnabled(False)
            self._status_label.setText("Idle")
        elif state == RunnerState.RUNNING:
            self._btn_start.setEnabled(False)
            self._btn_start.setText("Running...")
            self._btn_cancel.setEnabled(True)
            self._status_label.setText("Running...")
        elif state == RunnerState.COMPLETED:
            self._btn_start.setEnabled(True)
            self._btn_start.setText("Start")
            self._btn_cancel.setEnabled(False)
            self._status_label.setText("Completed")
            self._result_label.setText("Scenario completed successfully")
        elif state == RunnerState.FAILED:
            self._btn_start.setEnabled(True)
            self._btn_start.setText("Start")
            self._btn_cancel.setEnabled(False)
            self._status_label.setText("Failed")
        elif state == RunnerState.CANCELLED:
            self._btn_start.setEnabled(True)
            self._btn_start.setText("Start")
            self._btn_cancel.setEnabled(False)
            self._status_label.setText("Cancelled")

    def set_failure_message(self, message: str) -> None:
        self._result_label.setText(message)
        self._result_label.setObjectName("scenarioResultLabelError")

    def clear(self) -> None:
        self._scenario = None
        self._current_step_index = -1
        self._steps_list.clear()
        self._scenario_name_label.setText("No scenario loaded")
        self._btn_start.setEnabled(False)
        self._btn_start.setText("Start")
        self._btn_cancel.setEnabled(False)
        self._status_label.setText("")
        self._result_label.setText("")
