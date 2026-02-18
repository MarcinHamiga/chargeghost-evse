import re

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit


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
            "dim": "opacity: 0.7",
        }

        color_map = {
            "blue": "#1EAD98",
            "yellow": "#d29922",
            "green": "#238636",
            "red": "#f85149",
            "cyan": "#58a6ff",
            "magenta": "#a371f7",
            "white": "#e6edf3",
            "black": "#0d1117",
            "orange": "#d29922",
            "purple": "#a371f7",
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
