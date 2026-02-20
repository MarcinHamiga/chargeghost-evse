from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
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
        self._category_groups: dict[str, QGroupBox] = {}
        self._category_forms: dict[str, QFormLayout] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search configuration keys...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self._search_input)
        layout.addLayout(search_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("configKeysScroll")

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setSpacing(20)
        self._content_layout.setContentsMargins(0, 0, 8, 0)

        scroll.setWidget(self._content)
        layout.addWidget(scroll)

    def set_keys(self, keys: list["ConfigurationKey"]) -> None:
        self._clear_forms()

        # Sort keys by category then by name
        sorted_keys = sorted(keys, key=lambda k: (k.category, k.key))

        for key in sorted_keys:
            if key.category not in self._category_groups:
                self._create_category_group(key.category)
            
            form = self._category_forms[key.category]
            self._add_key_row(key, form)

        self._content_layout.addStretch()

    def _create_category_group(self, category: str) -> None:
        group = QGroupBox(f"{category} Configuration")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setSpacing(12)
        layout.addLayout(form)

        self._content_layout.addWidget(group)
        self._category_groups[category] = group
        self._category_forms[category] = form

    def _clear_forms(self) -> None:
        # Clear the content layout (except stretch if we can, but easier to just rebuild)
        for i in reversed(range(self._content_layout.count())):
            item = self._content_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
            else:
                self._content_layout.removeItem(item)

        self._category_groups.clear()
        self._category_forms.clear()
        self._key_inputs.clear()

    def _add_key_row(
        self, key: "ConfigurationKey", form: QFormLayout
    ) -> None:
        line_edit = QLineEdit()
        line_edit.setText(key.value)
        
        label_text = key.key
        if key.mandatory:
            label_text += " *"
            line_edit.setProperty("mandatory", True)
        
        tooltip = key.description
        if key.default:
            tooltip += f"\nDefault: {key.default}"
        if key.readonly:
            tooltip += "\n[Read-Only]"
        
        line_edit.setToolTip(tooltip)
        if key.default:
            line_edit.setPlaceholderText(f"Default: {key.default}")
        
        if key.readonly:
            line_edit.setEnabled(False)

        line_edit.textChanged.connect(
            lambda text, k=key.key: self._on_text_changed(k, text)
        )

        self._key_inputs[key.key] = line_edit
        form.addRow(f"{label_text}:", line_edit)

    def _on_search_changed(self, text: str) -> None:
        search_term = text.lower()
        for category, form in self._category_forms.items():
            has_visible_rows = False
            for row in range(form.rowCount()):
                label_item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                field_item = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
                
                if label_item and field_item:
                    label_widget = label_item.widget()
                    field_widget = field_item.widget()
                    
                    if label_widget and field_widget:
                        # Check key name (from label) and description (from tooltip)
                        visible = (
                            search_term in label_widget.text().lower() or
                            search_term in field_widget.toolTip().lower()
                        )
                        label_widget.setVisible(visible)
                        field_widget.setVisible(visible)
                        if visible:
                            has_visible_rows = True
            
            # Hide category group if no rows are visible
            self._category_groups[category].setVisible(has_visible_rows)

    def _on_text_changed(self, key_name: str, new_value: str) -> None:
        self.key_changed.emit(key_name, new_value)

    def update_key(self, key_name: str, new_value: str) -> None:
        line_edit = self._key_inputs.get(key_name)
        if line_edit:
            line_edit.blockSignals(True)
            line_edit.setText(new_value)
            line_edit.blockSignals(False)
