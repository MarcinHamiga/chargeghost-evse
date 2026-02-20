import re
from typing import Optional

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit

from chargeghost_evse.ui.styles import colors


class LogPanel(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setObjectName("LogPanel")

    def log_message(self, message: str):
        html_message = self._textual_to_html(message)
        self.append(html_message)
        self.moveCursor(QTextCursor.MoveOperation.End)

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
            "cyan": colors.INFO,  # Default cyan to info blue for unity
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

    def action_copy(self):
        self.selectAll()
        self.copy()
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
