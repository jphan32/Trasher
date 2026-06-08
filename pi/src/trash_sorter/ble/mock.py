"""Mock BLE 서버. macOS/CI 통합테스트용.

publish_*는 이력에 기록하고, simulate_*는 iPad의 write를 흉내내 핸들러를 호출한다.
"""

from __future__ import annotations

from ..protocol import (
    ClassificationResult,
    Command,
    CommandAck,
    DeviceInfo,
    PhotoReady,
    Status,
)
from .base import BleServer


class MockBleServer(BleServer):
    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self.device_info: DeviceInfo | None = None
        self.statuses: list[Status] = []
        self.photos: list[PhotoReady] = []
        self.acks: list[CommandAck] = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def set_device_info(self, info: DeviceInfo) -> None:
        self.device_info = info

    def publish_status(self, status: Status) -> None:
        self.statuses.append(status)

    def publish_photo_ready(self, photo: PhotoReady) -> None:
        self.photos.append(photo)

    def publish_command_ack(self, ack: CommandAck) -> None:
        self.acks.append(ack)

    # --- 테스트에서 iPad write 시뮬레이션 ------------------------------------
    def simulate_result(self, result: ClassificationResult) -> None:
        self._dispatch_result(result)

    def simulate_command(self, command: Command) -> None:
        self._dispatch_command(command)

    def simulate_disconnect(self) -> None:
        self._dispatch_disconnect()

    # 편의 조회
    @property
    def last_status(self) -> Status | None:
        return self.statuses[-1] if self.statuses else None
