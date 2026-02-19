from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from chargeghost_evse.ocpp_adapter.config_keys import ConfigurationKey


class ConfigKeysPanel(QWidget):
    key_changed = Signal(str, str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._key_inputs: dict[str, QLineEdit] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("configKeysScroll")

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setSpacing(20)
        self._content_layout.setContentsMargins(0, 0, 8, 0)

        self._mandatory_group = QGroupBox("Mandatory Configuration")
        mandatory_desc = QLabel(
            "Required OCPP 1.6 configuration keys with recommended defaults."
        )
        mandatory_desc.setWordWrap(True)
        mandatory_desc.setObjectName("configGroupDescription")
        self._mandatory_layout = QVBoxLayout(self._mandatory_group)
        self._mandatory_layout.setContentsMargins(8, 16, 8, 8)
        self._mandatory_layout.setSpacing(8)
        self._mandatory_layout.addWidget(mandatory_desc)

        self._mandatory_form = QFormLayout()
        self._mandatory_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self._mandatory_form.setSpacing(12)
        self._mandatory_layout.addLayout(self._mandatory_form)
        self._content_layout.addWidget(self._mandatory_group)

        self._optional_group = QGroupBox("Optional Configuration")
        optional_desc = QLabel(
            "Additional configuration keys for extended functionality."
        )
        optional_desc.setWordWrap(True)
        optional_desc.setObjectName("configGroupDescription")
        self._optional_layout = QVBoxLayout(self._optional_group)
        self._optional_layout.setContentsMargins(8, 16, 8, 8)
        self._optional_layout.setSpacing(8)
        self._optional_layout.addWidget(optional_desc)

        self._optional_form = QFormLayout()
        self._optional_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self._optional_form.setSpacing(12)
        self._optional_layout.addLayout(self._optional_form)
        self._content_layout.addWidget(self._optional_group)

        self._readonly_group = QGroupBox("Read-Only Configuration")
        readonly_desc = QLabel(
            "Device capabilities and limits reported to the Central System."
        )
        readonly_desc.setWordWrap(True)
        readonly_desc.setObjectName("configGroupDescription")
        self._readonly_layout = QVBoxLayout(self._readonly_group)
        self._readonly_layout.setContentsMargins(8, 16, 8, 8)
        self._readonly_layout.setSpacing(8)
        self._readonly_layout.addWidget(readonly_desc)

        self._readonly_form = QFormLayout()
        self._readonly_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self._readonly_form.setSpacing(12)
        self._readonly_layout.addLayout(self._readonly_form)
        self._content_layout.addWidget(self._readonly_group)

        self._content_layout.addStretch()

        scroll.setWidget(self._content)
        layout.addWidget(scroll)

    def set_keys(self, keys: list["ConfigurationKey"]) -> None:
        self._clear_forms()

        mandatory_editable = [k for k in keys if k.mandatory and not k.readonly]
        optional_editable = [k for k in keys if not k.mandatory and not k.readonly]
        readonly_keys = [k for k in keys if k.readonly]

        for key in mandatory_editable:
            self._add_key_row(key, self._mandatory_form)

        for key in optional_editable:
            self._add_key_row(key, self._optional_form)

        for key in readonly_keys:
            self._add_key_row(key, self._readonly_form, readonly=True)

        if self._mandatory_form.rowCount() == 0:
            self._mandatory_group.hide()
        else:
            self._mandatory_group.show()

        if self._optional_form.rowCount() == 0:
            self._optional_group.hide()
        else:
            self._optional_group.show()

        if self._readonly_form.rowCount() == 0:
            self._readonly_group.hide()
        else:
            self._readonly_group.show()

    def _clear_forms(self) -> None:
        while self._mandatory_form.rowCount() > 0:
            self._mandatory_form.removeRow(0)
        while self._optional_form.rowCount() > 0:
            self._optional_form.removeRow(0)
        while self._readonly_form.rowCount() > 0:
            self._readonly_form.removeRow(0)
        self._key_inputs.clear()

    def _add_key_row(
        self, key: "ConfigurationKey", form: QFormLayout, readonly: bool = False
    ) -> None:
        line_edit = QLineEdit()
        line_edit.setText(key.value)
        tooltip = key.description
        if key.default:
            tooltip += f"\nDefault: {key.default}"
        line_edit.setToolTip(tooltip)
        if key.default:
            line_edit.setPlaceholderText(f"Default: {key.default}")
        if readonly or key.readonly:
            line_edit.setEnabled(False)

        line_edit.textChanged.connect(
            lambda text, k=key.key: self._on_text_changed(k, text)
        )

        self._key_inputs[key.key] = line_edit
        form.addRow(f"{key.key}:", line_edit)

    def _on_text_changed(self, key_name: str, new_value: str) -> None:
        self.key_changed.emit(key_name, new_value)

    def update_key(self, key_name: str, new_value: str) -> None:
        line_edit = self._key_inputs.get(key_name)
        if line_edit:
            line_edit.blockSignals(True)
            line_edit.setText(new_value)
            line_edit.blockSignals(False)
