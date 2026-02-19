import asyncio
import hashlib
import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import aiohttp
from ocpp.v16.enums import DiagnosticsStatus, FirmwareStatus

from chargeghost_evse.util.event import Event
from chargeghost_evse.util.subscriber import Subscriber


logger = logging.getLogger(__name__)


@dataclass
class DiagnosticsUploadTask:
    location: str
    start_time: Optional[datetime] = None
    stop_time: Optional[datetime] = None
    retries: int = 0
    retry_interval: int = 0
    status: DiagnosticsStatus = DiagnosticsStatus.idle


@dataclass
class FirmwareUpdateTask:
    location: str
    retrieve_date: datetime
    retries: int = 0
    retry_interval: int = 0
    status: FirmwareStatus = FirmwareStatus.idle
    file_name: Optional[str] = None
    file_hash: Optional[str] = None


class FirmwareManager(Subscriber):
    def __init__(self, log_dir: Optional[Path] = None):
        super().__init__()
        self.log_dir: Path = (
            log_dir or Path(tempfile.gettempdir()) / "chargeghost" / "logs"
        )
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.diagnostics_task: Optional[DiagnosticsUploadTask] = None
        self.firmware_task: Optional[FirmwareUpdateTask] = None

        self.on_diagnostics_status_changed: Event = Event()
        self.on_firmware_status_changed: Event = Event()
        self.on_log: Event = Event()

        self._diagnostics_upload_callback: Optional[Callable] = None
        self._firmware_update_callback: Optional[Callable] = None

    def _log(self, message: str) -> None:
        self.on_log.emit(message=message)

    def set_diagnostics_upload_callback(self, callback: Optional[Callable]) -> None:
        self._diagnostics_upload_callback = callback

    def set_firmware_update_callback(self, callback: Optional[Callable]) -> None:
        self._firmware_update_callback = callback

    def start_diagnostics_upload(
        self,
        location: str,
        retries: int = 0,
        retry_interval: int = 0,
        start_time: Optional[str] = None,
        stop_time: Optional[str] = None,
    ) -> None:
        parsed_start: Optional[datetime] = None
        parsed_stop: Optional[datetime] = None

        if start_time:
            try:
                parsed_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                self._log(
                    f"[yellow]Diagnostics:[/yellow] Invalid start_time: {start_time}"
                )

        if stop_time:
            try:
                parsed_stop = datetime.fromisoformat(stop_time.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                self._log(
                    f"[yellow]Diagnostics:[/yellow] Invalid stop_time: {stop_time}"
                )

        self.diagnostics_task = DiagnosticsUploadTask(
            location=location,
            start_time=parsed_start,
            stop_time=parsed_stop,
            retries=retries,
            retry_interval=retry_interval,
            status=DiagnosticsStatus.idle,
        )

        self._log(f"[yellow]Diagnostics:[/yellow] Upload task created for {location}")

        if self._diagnostics_upload_callback:
            self._diagnostics_upload_callback(self.diagnostics_task)

    def set_diagnostics_status(self, status: DiagnosticsStatus) -> None:
        if self.diagnostics_task:
            self.diagnostics_task.status = status
            self._log(f"[yellow]Diagnostics:[/yellow] Status changed to {status.value}")
            self.on_diagnostics_status_changed.emit(status=status)

    def get_diagnostics_status(self) -> DiagnosticsStatus:
        if self.diagnostics_task:
            return self.diagnostics_task.status
        return DiagnosticsStatus.idle

    async def simulate_diagnostics_upload(self) -> Optional[str]:
        if not self.diagnostics_task:
            return None

        self.set_diagnostics_status(DiagnosticsStatus.uploading)
        self._log("[yellow]Diagnostics:[/yellow] Generating diagnostics file...")

        diagnostics_file = self._generate_diagnostics_file()
        if not diagnostics_file:
            self.set_diagnostics_status(DiagnosticsStatus.upload_failed)
            self._log("[yellow]Diagnostics:[/yellow] Failed to generate file")
            return None

        file_path = self.log_dir / diagnostics_file

        location = self.diagnostics_task.location
        if self._is_uploadable_url(location):
            self._log(f"[yellow]Diagnostics:[/yellow] Uploading to {location}...")
            success = await self._upload_file(file_path, location)
            if success:
                self.set_diagnostics_status(DiagnosticsStatus.uploaded)
                self._log("[yellow]Diagnostics:[/yellow] Upload complete")
                return diagnostics_file
            else:
                self.set_diagnostics_status(DiagnosticsStatus.upload_failed)
                self._log("[yellow]Diagnostics:[/yellow] Upload failed")
                return None
        else:
            await asyncio.sleep(2)
            self.set_diagnostics_status(DiagnosticsStatus.uploaded)
            self._log(
                f"[yellow]Diagnostics:[/yellow] File ready at {file_path} (no upload URL)"
            )
            return diagnostics_file

    def _is_uploadable_url(self, url: str) -> bool:
        if not url:
            return False
        return url.startswith(("http://", "https://", "ftp://"))

    async def _upload_file(self, file_path: Path, url: str) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                file_name = file_path.name
                with open(file_path, "rb") as f:
                    data = aiohttp.FormData()
                    data.add_field(
                        "file", f, filename=file_name, content_type="text/plain"
                    )

                    async with session.post(
                        url, data=data, timeout=aiohttp.ClientTimeout(total=60)
                    ) as response:
                        if response.status >= 200 and response.status < 300:
                            self._log(
                                f"[yellow]Diagnostics:[/yellow] Server responded {response.status}"
                            )
                            return True
                        else:
                            self._log(
                                f"[yellow]Diagnostics:[/yellow] Upload failed with status {response.status}"
                            )
                            return False
        except asyncio.TimeoutError:
            self._log("[yellow]Diagnostics:[/yellow] Upload timed out")
            return False
        except aiohttp.ClientError as e:
            self._log(f"[yellow]Diagnostics:[/yellow] Upload error: {e}")
            return False
        except (OSError, IOError) as e:
            self._log(f"[yellow]Diagnostics:[/yellow] File read error: {e}")
            return False

    def _generate_diagnostics_file(self) -> Optional[str]:
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            file_name = f"diagnostics_{timestamp}.log"
            file_path = self.log_dir / file_name

            content = self._collect_diagnostics_content()

            with open(file_path, "w") as f:
                f.write(content)

            self._log(f"[yellow]Diagnostics:[/yellow] Generated {file_name}")
            return file_name
        except (OSError, IOError) as e:
            self._log(f"[yellow]Diagnostics:[/yellow] Failed to generate file: {e}")
            return None

    def _collect_diagnostics_content(self) -> str:
        lines = [
            "=" * 60,
            "ChargeGhost EVSE Diagnostics Report",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "=" * 60,
            "",
            "System Information:",
            f"  Log Directory: {self.log_dir}",
            "",
        ]

        if self.diagnostics_task:
            lines.extend(
                [
                    "Diagnostics Task:",
                    f"  Location: {self.diagnostics_task.location}",
                    f"  Status: {self.diagnostics_task.status.value}",
                    "",
                ]
            )

        if self.firmware_task:
            lines.extend(
                [
                    "Firmware Task:",
                    f"  Location: {self.firmware_task.location}",
                    f"  Status: {self.firmware_task.status.value}",
                    "",
                ]
            )

        lines.extend(
            [
                "=" * 60,
                "End of Report",
                "=" * 60,
            ]
        )

        return "\n".join(lines)

    def start_firmware_update(
        self,
        location: str,
        retrieve_date: str,
        retries: int = 0,
        retry_interval: int = 0,
    ) -> None:
        parsed_date: datetime
        try:
            parsed_date = datetime.fromisoformat(retrieve_date.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            parsed_date = datetime.now(timezone.utc)
            self._log(
                f"[cyan]Firmware:[/cyan] Invalid retrieve_date, using now: {retrieve_date}"
            )

        self.firmware_task = FirmwareUpdateTask(
            location=location,
            retrieve_date=parsed_date,
            retries=retries,
            retry_interval=retry_interval,
            status=FirmwareStatus.idle,
        )

        file_name = Path(location).name
        self.firmware_task.file_name = file_name

        self._log(f"[cyan]Firmware:[/cyan] Update task created for {location}")

        if self._firmware_update_callback:
            self._firmware_update_callback(self.firmware_task)

    def set_firmware_status(self, status: FirmwareStatus) -> None:
        if self.firmware_task:
            self.firmware_task.status = status
            self._log(f"[cyan]Firmware:[/cyan] Status changed to {status.value}")
            self.on_firmware_status_changed.emit(status=status)

    def get_firmware_status(self) -> FirmwareStatus:
        if self.firmware_task:
            return self.firmware_task.status
        return FirmwareStatus.idle

    async def simulate_firmware_update(self) -> bool:
        if not self.firmware_task:
            return False

        self.set_firmware_status(FirmwareStatus.downloading)
        self._log("[cyan]Firmware:[/cyan] Simulating firmware download...")

        await asyncio.sleep(3)

        if self.firmware_task.file_name:
            fake_content = b"SIMULATED_FIRMWARE_BINARY_DATA"
            self.firmware_task.file_hash = hashlib.sha256(fake_content).hexdigest()[:16]

        self.set_firmware_status(FirmwareStatus.downloaded)
        self._log("[cyan]Firmware:[/cyan] Download complete")

        await asyncio.sleep(1)

        self.set_firmware_status(FirmwareStatus.installing)
        self._log("[cyan]Firmware:[/cyan] Simulating installation...")

        await asyncio.sleep(2)

        self.set_firmware_status(FirmwareStatus.installed)
        self._log("[cyan]Firmware:[/cyan] Installation complete")

        return True

    def cancel_firmware_update(self) -> None:
        if self.firmware_task:
            self.set_firmware_status(FirmwareStatus.idle)
            self._log("[cyan]Firmware:[/cyan] Update cancelled")
            self.firmware_task = None

    def cancel_diagnostics_upload(self) -> None:
        if self.diagnostics_task:
            self.set_diagnostics_status(DiagnosticsStatus.idle)
            self._log("[yellow]Diagnostics:[/yellow] Upload cancelled")
            self.diagnostics_task = None
