from textual.widgets import RichLog
from textual.app import ComposeResult

class LogPanel(RichLog):
    def __init__(self, **kwargs):
        super().__init__(highlight=True, markup=True, **kwargs)

    def log_message(self, message: str):
        self.write(message)
