"""BLE GATT 서버 인터페이스. docs/protocol.md §3 특성 ↔ 메시지 매핑.

Pi→iPad: DeviceInfo(read), Status(read+notify), PhotoReady(notify), CommandAck(notify)
iPad→Pi: ClassificationResult(write), Command(write)

오케스트레이터(app.py)는 publish_*로 내보내고, on_result/on_command 핸들러로 수신한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from ..protocol import (
    ClassificationResult,
    Command,
    CommandAck,
    DeviceInfo,
    PhotoReady,
    Status,
)

ResultHandler = Callable[[ClassificationResult], None]
CommandHandler = Callable[[Command], None]


class BleServer(ABC):
    def __init__(self) -> None:
        # 오케스트레이터가 설정하는 수신 핸들러(iPad → Pi write).
        self.on_result: ResultHandler | None = None
        self.on_command: CommandHandler | None = None

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def set_device_info(self, info: DeviceInfo) -> None:
        """DeviceInfo(read) 특성 값 설정. 보통 연결 전 1회."""

    @abstractmethod
    def publish_status(self, status: Status) -> None:
        """Status 특성 갱신 + 구독자에게 notify."""

    @abstractmethod
    def publish_photo_ready(self, photo: PhotoReady) -> None:
        """PhotoReady notify."""

    @abstractmethod
    def publish_command_ack(self, ack: CommandAck) -> None:
        """CommandAck notify."""

    # --- 구현체가 write 수신 시 호출하는 헬퍼 ---------------------------------
    def _dispatch_result(self, result: ClassificationResult) -> None:
        if self.on_result:
            self.on_result(result)

    def _dispatch_command(self, command: Command) -> None:
        if self.on_command:
            self.on_command(command)
