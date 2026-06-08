"""엔트리포인트. HTTP·BLE 시작 → DeviceInfo 광고 → 사이클 루프.

`--simulate`: 하드웨어 없이 모의 사이클 구동(로깅/QA). 자세히는 sim.py.
"""

from __future__ import annotations

import logging
import sys

from .config import load_settings
from .factory import build_app, device_info


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("trash_sorter")

    if "--simulate" in sys.argv:
        from .sim import Simulation

        log.info("시뮬레이션 모드 — 하드웨어 없이 사이클 구동 (Ctrl+C로 종료)")
        try:
            Simulation().run()
        except KeyboardInterrupt:
            log.info("시뮬레이션 종료")
        return

    settings = load_settings()
    ctx = build_app(settings)

    ctx.photo_server.start()
    ctx.ble.set_device_info(device_info(settings, ctx.photo_server.port))
    ctx.ble.start()
    log.info("시작됨: HTTP :%d, BLE %s", ctx.photo_server.port, settings.device_name)

    try:
        ctx.orchestrator.run()
    except KeyboardInterrupt:
        log.info("종료 신호 수신")
    finally:
        ctx.orchestrator.stop_running()
        ctx.ble.stop()
        ctx.photo_server.stop()
        ctx.hardware.stop_all()
        ctx.camera.close()
        ctx.hardware.close()


if __name__ == "__main__":
    main()
