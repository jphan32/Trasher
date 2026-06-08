"""실기기 BLE Peripheral (bless / BlueZ). Raspberry Pi(Linux)에서만 동작.

bless는 asyncio 기반이므로 전용 스레드에서 이벤트 루프를 돌리고, 동기 publish_*는
run_coroutine_threadsafe로 그 루프에 넘긴다.

⚠️ 실 BLE 하드웨어가 필요해 CI에서 검증 불가(pragma: no cover). 실기기에서 검증 필요.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from ..protocol import (
    CHAR_CLASSIFICATION_RESULT,
    CHAR_COMMAND,
    CHAR_COMMAND_ACK,
    CHAR_DEVICE_INFO,
    CHAR_PHOTO_READY,
    CHAR_STATUS,
    LOCAL_NAME,
    SERVICE_UUID,
    ClassificationResult,
    Command,
    CommandAck,
    DeviceInfo,
    PhotoReady,
    Status,
)
from .base import BleServer


class BlessBleServer(BleServer):  # pragma: no cover - 실 BLE 하드웨어 필요
    def __init__(self, name: str = LOCAL_NAME) -> None:
        super().__init__()
        self._name = name
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._server: Any = None
        self._device_info = b"{}"

    # --- 생명주기 ----------------------------------------------------------
    def start(self) -> None:
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self._setup(), self._loop).result(timeout=20)

    def stop(self) -> None:
        if self._server is not None:
            asyncio.run_coroutine_threadsafe(self._server.stop(), self._loop).result(timeout=10)
        self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _setup(self) -> None:
        from bless import (  # type: ignore[import-not-found]
            BlessServer,
            GATTAttributePermissions,
            GATTCharacteristicProperties,
        )

        server = BlessServer(name=self._name, loop=self._loop)
        server.read_request_func = self._on_read
        server.write_request_func = self._on_write
        await server.add_new_service(SERVICE_UUID)

        read = GATTCharacteristicProperties.read
        notify = GATTCharacteristicProperties.notify
        write = GATTCharacteristicProperties.write
        r_perm = GATTAttributePermissions.readable
        w_perm = GATTAttributePermissions.writeable

        async def add(uuid: str, props: Any, perms: Any) -> None:
            await server.add_new_characteristic(SERVICE_UUID, uuid, props, None, perms)

        await add(CHAR_DEVICE_INFO, read, r_perm)
        await add(CHAR_STATUS, read | notify, r_perm)
        await add(CHAR_PHOTO_READY, notify, r_perm)
        await add(CHAR_COMMAND_ACK, notify, r_perm)
        await add(CHAR_CLASSIFICATION_RESULT, write, w_perm)
        await add(CHAR_COMMAND, write, w_perm)

        self._server = server
        await server.start()

    # --- 읽기/쓰기 콜백 -----------------------------------------------------
    def _on_read(self, characteristic: Any, **_: Any) -> bytearray:
        if characteristic.uuid.lower() == CHAR_DEVICE_INFO.lower():
            return bytearray(self._device_info)
        return bytearray(characteristic.value or b"")

    def _on_write(self, characteristic: Any, value: bytearray, **_: Any) -> None:
        uuid = characteristic.uuid.lower()
        raw = bytes(value)
        if uuid == CHAR_CLASSIFICATION_RESULT.lower():
            self._dispatch_result(ClassificationResult.from_json(raw))
        elif uuid == CHAR_COMMAND.lower():
            self._dispatch_command(Command.from_json(raw))

    # --- publish (동기 → 루프) ---------------------------------------------
    def set_device_info(self, info: DeviceInfo) -> None:
        self._device_info = info.to_json().encode()

    def publish_status(self, status: Status) -> None:
        self._notify(CHAR_STATUS, status.to_json().encode())

    def publish_photo_ready(self, photo: PhotoReady) -> None:
        self._notify(CHAR_PHOTO_READY, photo.to_json().encode())

    def publish_command_ack(self, ack: CommandAck) -> None:
        self._notify(CHAR_COMMAND_ACK, ack.to_json().encode())

    def _notify(self, char_uuid: str, payload: bytes) -> None:
        if self._server is None:
            return

        def _do() -> None:
            char = self._server.get_characteristic(char_uuid)
            char.value = bytearray(payload)
            self._server.update_value(SERVICE_UUID, char_uuid)

        self._loop.call_soon_threadsafe(_do)
