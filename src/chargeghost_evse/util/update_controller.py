"""Update lifecycle controller.

Owns the entire update check, download, and handover flow.
MainWindow connects to its signals for UI updates.
"""

import asyncio
import os
import platform
import sys
import tempfile
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal

from chargeghost_evse.util.handover_manager import HandoverManager
from chargeghost_evse.util.update_manager import UpdateManager

if TYPE_CHECKING:
	from chargeghost_evse.util.config import SimulationConfig


class UpdateController(QObject):
	"""Manages the update check, download, and handover lifecycle."""

	# Emitted when an update is available (tag_name, body)
	update_available = Signal(str, str)
	# Emitted with download progress 0-100
	download_progress = Signal(int)
	# Emitted when handover script is launched and app should quit
	ready_to_restart = Signal()
	# Emitted on any error
	error_occurred = Signal(str)

	def __init__(
		self,
		current_version: str,
		config: "SimulationConfig",
		parent: Optional[QObject] = None,
	) -> None:
		super().__init__(parent)
		self._current_version = current_version
		self._config = config
		self._update_manager = UpdateManager(
			current_version=current_version, config=config
		)
		self._latest_release_info = None

	def start_check(self) -> None:
		"""Start background update check. Non-blocking."""
		Thread(target=self._check_updates, daemon=True).start()

	def trigger_download(self) -> None:
		"""Start background download of the latest release. Non-blocking."""
		if self._latest_release_info is None:
			self.error_occurred.emit("No release info available")
			return
		Thread(
			target=self._download_and_handover,
			args=(self._latest_release_info,),
			daemon=True,
		).start()

	def ignore_version(self, tag_name: str) -> None:
		"""Mark this version as ignored and save config."""
		self._config.ignored_version = tag_name
		self._config.save()

	def _check_updates(self) -> None:
		loop = asyncio.new_event_loop()
		try:
			release_info = loop.run_until_complete(
				self._update_manager.fetch_latest_release()
			)
			if (
				self._update_manager.is_update_available(
					self._current_version, release_info.tag_name
				)
				and release_info.tag_name != self._config.ignored_version
			):
				self._latest_release_info = release_info
				self.update_available.emit(
					release_info.tag_name, release_info.body or ""
				)
		except Exception:
			pass  # Update check failure is non-critical
		finally:
			loop.close()

	def _download_and_handover(self, release_info) -> None:
		loop = asyncio.new_event_loop()
		try:
			system_name = platform.system()
			asset = self._update_manager.select_asset_for_platform(
				system_name, release_info.assets
			)
			if not asset:
				self.error_occurred.emit("No update available for your platform")
				return

			temp_dir = Path(tempfile.mkdtemp())
			download_url = asset["browser_download_url"]
			filename = Path(urlparse(download_url).path).name
			temp_file = temp_dir / filename

			last_reported = [-1]

			def progress_callback(percent: int) -> None:
				milestone = (percent // 10) * 10
				if milestone > last_reported[0]:
					last_reported[0] = milestone
					self.download_progress.emit(milestone)

			loop.run_until_complete(
				self._update_manager.download_update(
					download_url, temp_file, progress_callback
				)
			)

			if not getattr(sys, "frozen", False):
				self.error_occurred.emit(
					"Update downloaded. In development mode, please update manually."
				)
				return

			current_exe = Path(sys.executable)
			handover_manager = HandoverManager(temp_dir)

			if system_name == "Windows":
				script_content = handover_manager.build_windows_script(
					pid=os.getpid(),
					new_path=str(temp_file),
					old_path=str(current_exe),
				)
				script_path = temp_dir / "update.bat"
			else:
				script_content = handover_manager.build_macos_script(
					pid=os.getpid(),
					new_path=str(temp_file),
					old_path=str(current_exe),
				)
				script_path = temp_dir / "update.sh"

			with open(script_path, "w") as f:
				f.write(script_content)

			handover_manager.launch_handover(script_path)
			self.ready_to_restart.emit()

		except Exception as e:
			self.error_occurred.emit(f"Update failed: {e}")
		finally:
			loop.close()
