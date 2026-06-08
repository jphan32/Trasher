"""BLE Peripheral 계층. docs/protocol.md §1, §3.

Pi = Peripheral(GATT 서버). 6개 특성을 노출하고 iPad(Central)의 read/write/notify를 중개한다.
실 전송은 bless(Linux 전용) → 인터페이스 뒤. macOS/CI는 MockBleServer로 통합테스트.
"""

from .base import BleServer
from .mock import MockBleServer

__all__ = ["BleServer", "MockBleServer"]
