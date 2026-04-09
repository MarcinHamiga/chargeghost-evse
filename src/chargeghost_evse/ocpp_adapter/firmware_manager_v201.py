import asyncio
import hashlib
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from ocpp.v201.enums import (
    FirmwareStatusEnumType,
    PublishFirmwareStatusEnumType,
)

from chargeghost_evse.util.event import Event
from chargeghost_evse.util.subscriber import Subscriber


logger = logging.getLogger(__name__)


@dataclass
class FirmwareUpdateTaskV201:
    location: str
    retrieve_date_time: datetime
    request_id: int = 0
    retries: int = 0
    retry_interval: int = 0
    status: FirmwareStatusEnumType = FirmwareStatusEnumType.idle
    install_date_time: Optional[datetime] = None
    signing_certificate: Optional[str] = None
    signature: Optional[str] = None
    file_name: Optional[str] = None
    file_hash: Optional[str] = None


@dataclass
class PublishFirmwareTask:
    location: str
    checksum: str
    request_id: int = 0
    retries: int = 0
    retry_interval: int = 0
    status: PublishFirmwareStatusEnumType = PublishFirmwareStatusEnumType.idle


class FirmwareManagerV201(Subscriber):
    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.RLock()

        self.firmware_task: Optional[FirmwareUpdateTaskV201] = None
        self.publish_task: Optional[PublishFirmwareTask] = None

        self.on_firmware_status_changed: Event = Event()
        self.on_publish_firmware_status_changed: Event = Event()

        self.logger = logging.getLogger("chargeghost.ocpp.firmware")

        self._firmware_update_callback: Optional[Callable] = None
        self._publish_firmware_callback: Optional[Callable] = None

    def _log(self, message: str, *, level: int = logging.INFO) -> None:
        self.logger.log(level, message, extra={"source": "ocpp"})

    def set_firmware_update_callback(self, callback: Optional[Callable]) -> None:
        self._firmware_update_callback = callback

    def set_publish_firmware_callback(self, callback: Optional[Callable]) -> None:
        self._publish_firmware_callback = callback

    def start_firmware_update(
        self,
        location: str,
        retrieve_date_time: str,
        request_id: int = 0,
        retries: int = 0,
        retry_interval: int = 0,
        install_date_time: Optional[str] = None,
        signing_certificate: Optional[str] = None,
        signature: Optional[str] = None,
    ) -> None:
        with self._lock:
            parsed_retrieve: datetime
            try:
                parsed_retrieve = datetime.fromisoformat(
                    retrieve_date_time.replace("Z", "+00:00")
                )
            except (TypeError, ValueError):
                parsed_retrieve = datetime.now(timezone.utc)
                self._log(
                    f"[cyan]Firmware:[/cyan] Invalid retrieve_date_time, "
                    f"using now: {retrieve_date_time}"
                )

            parsed_install: Optional[datetime] = None
            if install_date_time:
                try:
                    parsed_install = datetime.fromisoformat(
                        install_date_time.replace("Z", "+00:00")
                    )
                except (TypeError, ValueError):
                    self._log(
                        f"[cyan]Firmware:[/cyan] Invalid install_date_time: "
                        f"{install_date_time}"
                    )

            self.firmware_task = FirmwareUpdateTaskV201(
                location=location,
                retrieve_date_time=parsed_retrieve,
                request_id=request_id,
                retries=retries,
                retry_interval=retry_interval,
                status=FirmwareStatusEnumType.idle,
                install_date_time=parsed_install,
                signing_certificate=signing_certificate,
                signature=signature,
            )

            from pathlib import Path

            self.firmware_task.file_name = Path(location).name

            self._log(
                f"[cyan]Firmware:[/cyan] Update task created for {location}, "
                f"request_id={request_id}"
            )

            if self._firmware_update_callback:
                self._firmware_update_callback(self.firmware_task)

    def start_publish_firmware(
        self,
        location: str,
        checksum: str,
        request_id: int = 0,
        retries: int = 0,
        retry_interval: int = 0,
    ) -> None:
        with self._lock:
            self.publish_task = PublishFirmwareTask(
                location=location,
                checksum=checksum,
                request_id=request_id,
                retries=retries,
                retry_interval=retry_interval,
                status=PublishFirmwareStatusEnumType.idle,
            )

            self._log(
                f"[cyan]Firmware:[/cyan] Publish task created for {location}, "
                f"request_id={request_id}"
            )

            if self._publish_firmware_callback:
                self._publish_firmware_callback(self.publish_task)

    def set_firmware_status(self, status: FirmwareStatusEnumType) -> None:
        with self._lock:
            if self.firmware_task:
                self.firmware_task.status = status
                self._log(f"[cyan]Firmware:[/cyan] Status changed to {status.value}")
                self.on_firmware_status_changed.emit(status=status)

    def get_firmware_status(self) -> FirmwareStatusEnumType:
        with self._lock:
            if self.firmware_task:
                return self.firmware_task.status
            return FirmwareStatusEnumType.idle

    def set_publish_status(self, status: PublishFirmwareStatusEnumType) -> None:
        with self._lock:
            if self.publish_task:
                self.publish_task.status = status
                self._log(
                    f"[cyan]Firmware:[/cyan] Publish status changed to {status.value}"
                )
                self.on_publish_firmware_status_changed.emit(status=status)

    def get_publish_status(self) -> PublishFirmwareStatusEnumType:
        with self._lock:
            if self.publish_task:
                return self.publish_task.status
            return PublishFirmwareStatusEnumType.idle

    def get_retrieve_delay_seconds(self, now: Optional[datetime] = None) -> float:
        with self._lock:
            if not self.firmware_task:
                return 0.0

            current_time = now or datetime.now(timezone.utc)
            delay = (
                self.firmware_task.retrieve_date_time - current_time
            ).total_seconds()
            return max(delay, 0.0)

    async def wait_until_retrieve_date(self) -> None:
        delay = self.get_retrieve_delay_seconds()
        if delay <= 0:
            return

        self._log(
            "[cyan]Firmware:[/cyan] Waiting until scheduled retrieve_date_time "
            "before download"
        )
        await asyncio.sleep(delay)

    async def simulate_firmware_update(self) -> bool:
        with self._lock:
            task = self.firmware_task
            if task is None:
                return False

        self.set_firmware_status(FirmwareStatusEnumType.download_scheduled)
        self._log("[cyan]Firmware:[/cyan] Firmware update scheduled")
        await asyncio.sleep(1)

        self.set_firmware_status(FirmwareStatusEnumType.downloading)
        self._log("[cyan]Firmware:[/cyan] Simulating firmware download...")
        await asyncio.sleep(3)

        with self._lock:
            if task.file_name:
                fake_content = b"SIMULATED_FIRMWARE_BINARY_DATA"
                task.file_hash = hashlib.sha256(fake_content).hexdigest()[:16]

        self.set_firmware_status(FirmwareStatusEnumType.downloaded)
        self._log("[cyan]Firmware:[/cyan] Download complete")
        await asyncio.sleep(1)

        if task.signature:
            self._log("[cyan]Firmware:[/cyan] Verifying firmware signature...")
            self.set_firmware_status(FirmwareStatusEnumType.signature_verified)
            await asyncio.sleep(1)

        self.set_firmware_status(FirmwareStatusEnumType.install_scheduled)
        self._log("[cyan]Firmware:[/cyan] Installation scheduled")
        await asyncio.sleep(1)

        self.set_firmware_status(FirmwareStatusEnumType.installing)
        self._log("[cyan]Firmware:[/cyan] Simulating installation...")
        await asyncio.sleep(2)

        self.set_firmware_status(FirmwareStatusEnumType.installed)
        self._log("[cyan]Firmware:[/cyan] Installation complete")

        return True

    async def simulate_publish_firmware(self) -> bool:
        with self._lock:
            task = self.publish_task
            if task is None:
                return False

        self.set_publish_status(PublishFirmwareStatusEnumType.download_scheduled)
        self._log("[cyan]Firmware:[/cyan] Publish download scheduled")
        await asyncio.sleep(1)

        self.set_publish_status(PublishFirmwareStatusEnumType.downloading)
        self._log("[cyan]Firmware:[/cyan] Simulating publish download...")
        await asyncio.sleep(2)

        self.set_publish_status(PublishFirmwareStatusEnumType.downloaded)
        self._log("[cyan]Firmware:[/cyan] Publish download complete")
        await asyncio.sleep(1)

        self.set_publish_status(PublishFirmwareStatusEnumType.published)
        self._log("[cyan]Firmware:[/cyan] Firmware published")

        return True

    def cancel_firmware_update(self) -> None:
        with self._lock:
            if self.firmware_task:
                self.set_firmware_status(FirmwareStatusEnumType.idle)
                self._log("[cyan]Firmware:[/cyan] Update cancelled")
                self.firmware_task = None

    def unpublish_firmware(self) -> bool:
        with self._lock:
            if self.publish_task is None:
                return False

            self.publish_task = None
            self._log("[cyan]Firmware:[/cyan] Firmware unpublished")

        return True
