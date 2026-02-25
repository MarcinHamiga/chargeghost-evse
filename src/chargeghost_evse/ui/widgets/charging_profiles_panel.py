from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from ocpp.v16.enums import ChargingRateUnitType
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
	QFrame,
	QHBoxLayout,
	QLabel,
	QScrollArea,
	QVBoxLayout,
	QWidget,
)

from chargeghost_evse.ui.widgets.icons import get_icon_html

if TYPE_CHECKING:
	from chargeghost_evse.engine.engine import Engine
	from chargeghost_evse.bridge.bridge import Bridge


class ChargingProfilesPanel(QWidget):
	"""Panel displaying active charging profiles and their effective limits."""

	def __init__(self, parent: Optional[QWidget] = None):
		super().__init__(parent)
		self._profile_frames: list[QFrame] = []
		self._limit_frames: list[QFrame] = []
		self._setup_ui()

	def _setup_ui(self) -> None:
		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		# Header
		header = QWidget()
		header_layout = QHBoxLayout(header)
		header_layout.setContentsMargins(16, 16, 16, 8)

		title = QLabel("Charging Profiles")
		title.setObjectName("sectionHeader")
		header_layout.addWidget(title)
		header_layout.addStretch()

		self._profile_count = QLabel("0 profiles")
		self._profile_count.setObjectName("profileCount")
		header_layout.addWidget(self._profile_count)

		layout.addWidget(header)

		# Scrollable content area
		scroll = QScrollArea()
		scroll.setWidgetResizable(True)
		scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
		scroll.setObjectName("profileScrollArea")

		scroll_content = QWidget()
		self._content_layout = QVBoxLayout(scroll_content)
		self._content_layout.setContentsMargins(16, 0, 16, 16)
		self._content_layout.setSpacing(16)

		# Effective Limits section
		self._limits_section = QWidget()
		limits_layout = QVBoxLayout(self._limits_section)
		limits_layout.setContentsMargins(0, 0, 0, 0)
		limits_layout.setSpacing(8)

		limits_title = QLabel("Effective Limits")
		limits_title.setObjectName("subsectionHeader")
		limits_layout.addWidget(limits_title)

		self._limits_container = QVBoxLayout()
		self._limits_container.setSpacing(8)
		limits_layout.addLayout(self._limits_container)

		self._content_layout.addWidget(self._limits_section)

		# Profiles section
		self._profiles_section = QWidget()
		profiles_layout = QVBoxLayout(self._profiles_section)
		profiles_layout.setContentsMargins(0, 0, 0, 0)
		profiles_layout.setSpacing(8)

		profiles_title = QLabel("Active Profiles")
		profiles_title.setObjectName("subsectionHeader")
		profiles_layout.addWidget(profiles_title)

		self._profiles_container = QVBoxLayout()
		self._profiles_container.setSpacing(8)
		profiles_layout.addLayout(self._profiles_container)

		self._content_layout.addWidget(self._profiles_section)

		self._content_layout.addStretch()
		scroll.setWidget(scroll_content)
		layout.addWidget(scroll)

	def update_from_engine(self, engine: "Engine", bridge: "Bridge") -> None:
		"""Update the panel with current profile data."""
		self._clear_frames()

		# Get the charging profile manager from the adapter
		manager = None
		if bridge.runner.adapter and hasattr(bridge.runner.adapter, 'charging_profile_manager'):
			manager = bridge.runner.adapter.charging_profile_manager

		if not manager:
			self._show_no_adapter_message()
			return

		profiles = manager.get_all_profiles()
		self._profile_count.setText(f"{len(profiles)} profile{'s' if len(profiles) != 1 else ''}")

		# Update effective limits for each connector
		self._update_effective_limits(engine, manager)

		# Update profiles list
		self._update_profiles_list(profiles)

	def _show_no_adapter_message(self) -> None:
		"""Show message when adapter is not connected."""
		self._limits_section.setVisible(False)
		self._profile_count.setText("Not connected")
		self._clear_frames()

		frame = QFrame()
		frame.setProperty("card", True)
		frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		layout = QVBoxLayout(frame)
		layout.setContentsMargins(16, 16, 16, 16)

		msg = QLabel("Connect to a CSMS to view charging profiles")
		msg.setObjectName("emptyMessage")
		msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
		layout.addWidget(msg)

		self._profiles_container.addWidget(frame)
		self._profile_frames.append(frame)

	def _update_effective_limits(self, engine: "Engine", manager) -> None:
		"""Update the effective limit cards for each connector."""
		now = datetime.now(timezone.utc)

		for conn in engine.connectors:
			transaction_id = None
			transaction_start = None

			if engine.session and engine.session.connector_id == conn.id:
				transaction_id = engine.session.transaction_id
				transaction_start = datetime.fromtimestamp(
					engine.session.start_time, tz=timezone.utc
				)

			limit = manager.get_composite_limit(
				connector_id=conn.id,
				transaction_id=transaction_id,
				now=now,
				connector_voltage=conn.voltage,
				transaction_start=transaction_start,
				phases=conn.phase,
			)

			frame = self._create_limit_card(conn.id, conn.current, limit)
			self._limits_container.addWidget(frame)
			self._limit_frames.append(frame)

		# Hide limits section if no connectors
		self._limits_section.setVisible(len(engine.connectors) > 0)

	def _create_limit_card(self, connector_id: int, max_current: float,
						   effective_limit: Optional[float]) -> QFrame:
		"""Create a card showing effective limit for a connector."""
		frame = QFrame()
		frame.setProperty("card", True)
		frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

		layout = QHBoxLayout(frame)
		layout.setContentsMargins(12, 10, 12, 10)
		layout.setSpacing(12)

		# Connector ID
		conn_label = QLabel(f"Connector {connector_id}")
		conn_label.setProperty("connectorLabel", True)
		layout.addWidget(conn_label)

		layout.addStretch()

		# Max current
		max_label = QLabel(f"Max: {max_current:.1f}A")
		max_label.setProperty("maxCurrentLabel", True)
		layout.addWidget(max_label)

		# Effective limit
		if effective_limit is not None:
			limit_icon = "arrow_down" if effective_limit < max_current else "check"
			limit_color = "#f59e0b" if effective_limit < max_current else "#1EAD98"
			limit_text = f"{effective_limit:.1f}A"

			limit_label = QLabel(
				f"{get_icon_html(limit_icon, limit_color, 14)} Limit: {limit_text}"
			)
			limit_label.setProperty("limitLabel", True)
			if effective_limit < max_current:
				limit_label.setProperty("limited", True)
		else:
			limit_label = QLabel(
				f"{get_icon_html('infinity', '#6e7681', 14)} No limit"
			)
			limit_label.setProperty("noLimitLabel", True)

		layout.addWidget(limit_label)

		return frame

	def _update_profiles_list(self, profiles: list) -> None:
		"""Update the list of active profile cards."""
		if not profiles:
			frame = QFrame()
			frame.setProperty("card", True)
			frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
			layout = QVBoxLayout(frame)
			layout.setContentsMargins(16, 16, 16, 16)

			msg = QLabel("No charging profiles configured")
			msg.setObjectName("emptyMessage")
			msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
			layout.addWidget(msg)

			self._profiles_container.addWidget(frame)
			self._profile_frames.append(frame)
			return

		# Sort profiles by connector_id, then by profile_id
		sorted_profiles = sorted(profiles, key=lambda p: (p[0], p[1].charging_profile_id))

		for connector_id, profile in sorted_profiles:
			frame = self._create_profile_card(connector_id, profile)
			self._profiles_container.addWidget(frame)
			self._profile_frames.append(frame)

	def _create_profile_card(self, connector_id: int, profile) -> QFrame:
		"""Create a card showing profile details."""
		frame = QFrame()
		frame.setProperty("card", True)
		frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

		layout = QVBoxLayout(frame)
		layout.setContentsMargins(12, 10, 12, 10)
		layout.setSpacing(6)

		# Header row: ID and purpose
		header_layout = QHBoxLayout()

		id_label = QLabel(f"Profile {profile.charging_profile_id}")
		id_label.setProperty("profileIdLabel", True)
		header_layout.addWidget(id_label)

		header_layout.addStretch()

		# Purpose badge
		purpose_map = {
			"ChargePointMaxProfile": ("CP Max", "#3b82f6"),
			"TxDefaultProfile": ("Tx Default", "#8b5cf6"),
			"TxProfile": ("Tx Profile", "#1EAD98"),
		}
		purpose_text = profile.charging_profile_purpose.value
		badge_text, badge_color = purpose_map.get(purpose_text, (purpose_text, "#6e7681"))

		purpose_label = QLabel(
			f"{get_icon_html('tag', badge_color, 12)} {badge_text}"
		)
		purpose_label.setProperty("purposeBadge", True)
		header_layout.addWidget(purpose_label)

		layout.addLayout(header_layout)

		# Details row
		details_layout = QHBoxLayout()
		details_layout.setSpacing(16)

		# Connector
		conn_text = "All" if connector_id == 0 else f"Conn {connector_id}"
		conn_label = QLabel(f"{get_icon_html('plug', '#8b949e', 12)} {conn_text}")
		conn_label.setProperty("profileDetail", True)
		details_layout.addWidget(conn_label)

		# Kind
		kind_map = {
			"Absolute": ("absolute", "#8b949e"),
			"Recurring": ("recurring", "#f59e0b"),
			"Relative": ("relative", "#6e7681"),
		}
		kind_text = profile.charging_profile_kind.value
		kind_badge, kind_color = kind_map.get(kind_text, (kind_text.lower(), "#6e7681"))
		kind_label = QLabel(
			f"{get_icon_html('clock', kind_color, 12)} {kind_badge}"
		)
		kind_label.setProperty("profileDetail", True)
		details_layout.addWidget(kind_label)

		# Stack level
		stack_label = QLabel(
			f"{get_icon_html('layers', '#8b949e', 12)} Stack {profile.stack_level}"
		)
		stack_label.setProperty("profileDetail", True)
		details_layout.addWidget(stack_label)

		# Transaction ID (if TxProfile)
		if profile.transaction_id is not None:
			tx_label = QLabel(
				f"{get_icon_html('hash', '#1EAD98', 12)} Tx {profile.transaction_id}"
			)
			tx_label.setProperty("profileDetail", True)
			details_layout.addWidget(tx_label)

		details_layout.addStretch()
		layout.addLayout(details_layout)

		# Schedule periods row
		schedule = profile.charging_schedule
		periods = schedule.charging_schedule_period

		if periods:
			periods_layout = QHBoxLayout()
			periods_layout.setSpacing(4)

			periods_title = QLabel("Schedule:")
			periods_title.setProperty("scheduleTitle", True)
			periods_layout.addWidget(periods_title)

			# Show first few periods
			max_show = 3
			for i, period in enumerate(periods[:max_show]):
				unit = "A" if schedule.charging_rate_unit == ChargingRateUnitType.amps else "W"
				period_text = f"{period.limit:.1f}{unit}"
				if period.start_period > 0:
					period_text = f"+{period.start_period}s→{period_text}"

				period_label = QLabel(period_text)
				period_label.setProperty("periodBadge", True)
				periods_layout.addWidget(period_label)

				if i < min(len(periods), max_show) - 1:
					sep = QLabel("→")
					sep.setProperty("periodSeparator", True)
					periods_layout.addWidget(sep)

			if len(periods) > max_show:
				more = QLabel(f"+{len(periods) - max_show} more")
				more.setProperty("morePeriods", True)
				periods_layout.addWidget(more)

			periods_layout.addStretch()
			layout.addLayout(periods_layout)

		return frame

	def _clear_frames(self) -> None:
		"""Clear all profile and limit frames."""
		for frame in self._profile_frames + self._limit_frames:
			frame.setParent(None)
			frame.deleteLater()
		self._profile_frames.clear()
		self._limit_frames.clear()
