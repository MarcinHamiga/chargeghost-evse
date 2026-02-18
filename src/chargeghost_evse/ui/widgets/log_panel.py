from textual.widgets import RichLog
from textual.binding import Binding
from rich.markup import escape


class LogPanel(RichLog):
    BINDINGS = [
        Binding("c", "copy", "Copy Logs"),
    ]

    def __init__(self, **kwargs):
        super().__init__(highlight=True, markup=True, **kwargs)

    def log_message(self, message: str):
        self.write(message)

    def log_untrusted(self, message: str):
        self.write(escape(message))

    def action_copy(self) -> None:
        """Copy all log content to the clipboard."""
        try:
            log_text = "\n".join(line.text for line in self.lines)
            if log_text:
                self.app.copy_to_clipboard(log_text)
                self.notify("Logs copied to clipboard", severity="information")
            else:
                self.notify("Log is empty", severity="warning")
        except Exception as e:
            self.notify(f"Failed to copy logs: {e}", severity="error")
