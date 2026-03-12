"""
Log Panel Widget.

Displays application log entries. Supports both simple text entries
(via log_message) and structured LogRecord entries with collapsible
OCPP payloads and profile evaluation traces (via log_record).
"""

import json
import logging
import re
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from chargeghost_evse.ui.styles import colors
from chargeghost_evse.ui.widgets.log_entry import CollapsibleLogEntry

_MAX_ENTRIES = 500


class LogPanel(QScrollArea):
	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self.setObjectName("LogPanel")
		self.setWidgetResizable(True)
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

		self._container = QWidget()
		self._layout = QVBoxLayout(self._container)
		self._layout.setContentsMargins(4, 4, 4, 4)
		self._layout.setSpacing(2)
		self._layout.addStretch()
		self.setWidget(self._container)

		self._entry_count = 0

	def log_message(self, message: str) -> None:
		"""Add a simple text log entry (backward compatible)."""
		html = self._textual_to_html(message)
		label = QLabel(html)
		label.setTextFormat(Qt.TextFormat.RichText)
		label.setWordWrap(True)
		self._add_entry(label)

	def log_record(self, record: logging.LogRecord) -> None:
		"""Add a log entry from a Python LogRecord, with collapsible support."""
		message = record.getMessage()
		html_message = self._textual_to_html(self._format_summary(record, message))

		# Check for collapsible content
		payload = getattr(record, "ocpp_payload", None)
		evaluated = getattr(record, "evaluated_profiles", None)

		if payload is not None:
			detail = json.dumps(payload, indent=2) if isinstance(payload, dict) else str(payload)
			entry = CollapsibleLogEntry(summary=html_message, detail=detail)
			self._add_entry(entry)
		elif evaluated is not None:
			limit = getattr(record, "computed_limit_amps", None)
			lines = [f"Profiles evaluated: {len(evaluated)}"]
			for p in evaluated:
				lines.append(f"  {p.get('purpose', '?')}: {p.get('limit', '?')}A")
			if limit is not None:
				lines.append(f"Effective limit: {limit}A")
			entry = CollapsibleLogEntry(summary=html_message, detail="\n".join(lines))
			self._add_entry(entry)
		else:
			label = QLabel(html_message)
			label.setTextFormat(Qt.TextFormat.RichText)
			label.setWordWrap(True)
			self._add_entry(label)

	def _format_summary(self, record: logging.LogRecord, message: str) -> str:
		"""Format a one-line summary for the log entry."""
		name = record.name
		if name.startswith("chargeghost.engine"):
			tag = "engine"
			source = "Engine"
		elif name.startswith("chargeghost.ocpp") or name.startswith("chargeghost.bridge"):
			tag = "ocpp"
			source = "OCPP"
		else:
			tag = "white"
			source = "System"

		prefix = ""
		if record.levelno >= logging.ERROR:
			prefix = "[red]ERROR[/red] "
		elif record.levelno >= logging.WARNING:
			prefix = "[yellow]WARN[/yellow] "

		return f"{prefix}[{tag}]{source}:[/] {message}"

	def _add_entry(self, widget: QWidget) -> None:
		"""Add widget before the stretch, enforce max entries."""
		self._layout.insertWidget(self._layout.count() - 1, widget)
		self._entry_count += 1

		while self._entry_count > _MAX_ENTRIES:
			item = self._layout.itemAt(0)
			if item and item.widget():
				w = item.widget()
				self._layout.removeWidget(w)
				w.deleteLater()
				self._entry_count -= 1
			else:
				break  # safety: don't remove stretch or spacer items

		# Auto-scroll to bottom
		self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

	def clear(self) -> None:
		"""Remove all log entries."""
		while self._layout.count() > 1:  # keep the stretch
			item = self._layout.takeAt(0)
			if item and item.widget():
				item.widget().deleteLater()
		self._entry_count = 0

	def _textual_to_html(self, text: str) -> str:
		text = self._escape_html(text)
		text = self._convert_style_tags(text)
		return text

	def _escape_html(self, text: str) -> str:
		text = text.replace("&", "&amp;")
		text = text.replace("<", "&lt;")
		text = text.replace(">", "&gt;")
		return text

	def _convert_style_tags(self, text: str) -> str:
		style_map = {
			"b": "font-weight: bold",
			"bold": "font-weight: bold",
			"i": "font-style: italic",
			"italic": "font-style: italic",
			"u": "text-decoration: underline",
			"underline": "text-decoration: underline",
			"dim": f"color: {colors.TEXT_MUTED}",
		}

		color_map = {
			"blue": colors.INFO,
			"yellow": colors.WARNING,
			"green": colors.SUCCESS,
			"red": colors.DANGER,
			"cyan": colors.INFO,
			"magenta": "#a371f7",
			"white": colors.TEXT_PRIMARY,
			"black": colors.BG_MAIN,
			"orange": colors.WARNING,
			"purple": "#a371f7",
			"teal": colors.ACCENT_TEAL,
			"gray": colors.TEXT_SECONDARY,
			"muted": colors.TEXT_MUTED,
			"engine": colors.LOG_COLORS["engine"],
			"ocpp": colors.LOG_COLORS["ocpp"],
			"ui": colors.LOG_COLORS["ui"],
		}

		tag_pattern = re.compile(r"\[([^\]]+)\]")

		result = []
		pos = 0
		open_tags: list[str] = []

		for match in tag_pattern.finditer(text):
			result.append(text[pos : match.start()])
			pos = match.end()

			tag = match.group(1)

			if tag.startswith("/"):
				if open_tags:
					open_tags.pop()
					result.append("</span>")
			elif tag in style_map:
				result.append(f'<span style="{style_map[tag]}">')
				open_tags.append(tag)
			elif tag in color_map:
				result.append(f'<span style="color:{color_map[tag]}">')
				open_tags.append(tag)
			else:
				result.append(match.group(0))

		result.append(text[pos:])

		while open_tags:
			result.append("</span>")
			open_tags.pop()

		return "".join(result)
