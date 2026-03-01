from typing import Optional

from PySide6.QtCore import QSettings


class AppSettings:
    SETTING_WINDOW_GEOMETRY = "window/geometry"
    SETTING_WINDOW_STATE = "window/state"
    SETTING_LOG_PANEL_EXPANDED = "ui/logPanelExpanded"
    SETTING_LOG_MODE = "ui/logMode"
    SETTING_LAST_CONNECTOR_ID = "ui/lastConnectorId"
    SETTING_RECENT_TAGS = "ui/recentTags"
    SETTING_LAST_MODE = "ui/lastMode"
    MAX_RECENT_TAGS = 10

    def __init__(self) -> None:
        self._settings = QSettings("ChargeGhost", "EVSE")

    def get(self, key: str, default=None):
        return self._settings.value(key, default)

    def set(self, key: str, value) -> None:
        self._settings.setValue(key, value)

    @property
    def window_geometry(self) -> Optional[bytes]:
        geometry = self._settings.value(self.SETTING_WINDOW_GEOMETRY)
        return bytes(geometry) if geometry else None

    @window_geometry.setter
    def window_geometry(self, geometry: bytes) -> None:
        self._settings.setValue(self.SETTING_WINDOW_GEOMETRY, geometry)

    @property
    def window_state(self) -> Optional[bytes]:
        state = self._settings.value(self.SETTING_WINDOW_STATE)
        return bytes(state) if state else None

    @window_state.setter
    def window_state(self, state: bytes) -> None:
        self._settings.setValue(self.SETTING_WINDOW_STATE, state)

    @property
    def log_panel_expanded(self) -> bool:
        return bool(self._settings.value(self.SETTING_LOG_PANEL_EXPANDED, False))

    @log_panel_expanded.setter
    def log_panel_expanded(self, expanded: bool) -> None:
        self._settings.setValue(self.SETTING_LOG_PANEL_EXPANDED, expanded)

    @property
    def log_mode(self) -> str:
        return str(self._settings.value(self.SETTING_LOG_MODE, "compact"))

    @log_mode.setter
    def log_mode(self, mode: str) -> None:
        self._settings.setValue(self.SETTING_LOG_MODE, mode)

    @property
    def last_connector_id(self) -> int:
        val = self._settings.value(self.SETTING_LAST_CONNECTOR_ID, 1)
        if val is None:
            return 1
        try:
            return int(val)  # type: ignore[call-overload]
        except (TypeError, ValueError):
            return 1

    @last_connector_id.setter
    def last_connector_id(self, connector_id: int) -> None:
        self._settings.setValue(self.SETTING_LAST_CONNECTOR_ID, connector_id)

    @property
    def recent_tags(self) -> list[str]:
        tags = self._settings.value(self.SETTING_RECENT_TAGS, [])
        if tags is None:
            return []
        if isinstance(tags, str):
            return [tags]
        if isinstance(tags, list):
            return [str(t) for t in tags]
        return []

    @recent_tags.setter
    def recent_tags(self, tags: list[str]) -> None:
        self._settings.setValue(self.SETTING_RECENT_TAGS, tags[: self.MAX_RECENT_TAGS])

    def add_recent_tag(self, tag: str) -> None:
        tags = self.recent_tags
        if tag in tags:
            tags.remove(tag)
        tags.insert(0, tag)
        self.recent_tags = tags

    @property
    def last_mode(self) -> str:
        return str(self._settings.value(self.SETTING_LAST_MODE, ""))

    @last_mode.setter
    def last_mode(self, mode: str) -> None:
        self._settings.setValue(self.SETTING_LAST_MODE, mode)
