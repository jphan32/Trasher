# 전시 부스 운영 런북 (Booth Runbook)

무인 전시/체험 부스에서 **AI 쓰레기 자동 분류기**를 운영하기 위한 실전 절차서.
설치 상세는 [`pi-setup.md`](pi-setup.md), 통신 계약은 [`protocol.md`](protocol.md) 참조.
이 문서는 **현장 진행자(운영자)** 용 — 시작/종료/복구/트러블슈팅에 집중한다.

> 참가자 인터랙션은 **iPad 터치 없이** 동작한다(자동 진행). 진행자만 설정/연결/복구 시 터치한다
> (iPad 좌상단 **3초 길게 누르기** → 운영자 화면).

---

## 1. 구성 한눈에

```
[참가자] → 쓰레기 투입 → [Pi 카메라 감지·촬영] ──BLE 사진준비──▶ [iPad]
                                  ▲                              │ 사진 HTTP GET
                                  │ BLE 분류결과(페트/캔/기타)     │ POST /classify(Pi가 Gemini 호출)
                                  └──────────────────────────────┘
[Pi] 서보·벨트로 분리수거함 이동   [iPad] 에코포인트·CO₂·막대사탕 연출
```

- **Pi(`sorter-01`)**: BLE Peripheral + 카메라 + 서보/벨트 + HTTP(사진/분류) + Gemini 호출. 상태머신 소유.
- **iPad**: BLE Central + 화면 연출. 인테이크 타이밍 통제(보상 중 `stop`, 어트랙트 복귀 시 `start`).
- **라우터**: Pi·iPad 같은 WiFi(인터넷 必, Gemini용). AP/Client Isolation **OFF**.

---

## 2. 매일 시작 절차 (Power-on)

1. **라우터 전원** → 인터넷 연결 확인.
2. **모터 외부전원** ON (Pi 5V 직급전 금지 — 공통 GND 확인).
3. **Pi 전원** → 부팅(~40초). 자동기동(systemd) 시 `trash-sorter`가 자동 실행.
4. **확인**(SSH 또는 진행자 노트북):
   ```bash
   ssh rp4b 'systemctl is-active trash-sorter; bluetoothctl show | grep Powered'
   # 기대: active / Powered: yes
   ```
5. **iPad** 전원 → **Trasher 앱** 실행 → 자동으로 `sorter-01` 스캔·연결.
   - 화면이 "연결 중" → **어트랙트(쓰레기를 넣어주세요)** 로 바뀌면 정상.
6. **테스트 투입 1회** — 페트병 등으로 전 사이클(촬영→분류→이동→보상) 확인.
7. **막대사탕/굿즈** 디스펜서 채우기.

---

## 3. 종료 절차

1. iPad 앱 종료(또는 운영자 화면 → 감지 정지).
2. `ssh rp4b 'sudo systemctl stop trash-sorter'` (자동기동이면 정지만; 다음 부팅 시 재기동).
3. 모터 외부전원 OFF → Pi 정상 종료(`sudo shutdown -h now`) → 라우터.

---

## 4. 트러블슈팅 (증상 → 원인 → 조치)

| 증상 | 원인 | 조치 |
|---|---|---|
| iPad가 계속 "연결 중" | Pi BLE 미광고 | 아래 **BLE 복구** |
| iPad가 **매 연결마다 페어링** 요구 + 사진 안 뜸 | 본딩 미영속 → 브링업(구독/start) 차단 | `systemctl is-active bt-agent` 확인(없으면 pi-setup §7.1 적용). `bluetoothctl devices Bonded`에 iPad 표시돼야 정상 |
| `bluetoothctl show` = `Powered: no`, 광고 실패 | **rfkill 소프트 블록**(systemd-rfkill 복원) | `sudo rfkill unblock bluetooth` + `echo 0 > /var/lib/systemd/rfkill/platform-soc-amba-fe201000.serial:bluetooth` 후 `bluetoothctl power on` |
| 분류가 항상 회전/엉뚱(이미지 무관) | Gemini 키 없음 → **MockClassifier** | `/etc/trash-sorter.env`에 `TRASH_GEMINI_CREDENTIALS` 설정 확인, 서비스 재시작 |
| 분류 시 429/"credits depleted" | **Gemini 결제/쿼터 소진** | AI Studio에서 크레딧 충전 또는 다른 SA 키로 교체(`secret/gemini-api-key.json`) |
| `Address already in use :8080` / 광고 충돌 | **orphan 프로세스**(수동 `uv run` 잔존) | `pkill -9 -f "[b]in/trash-sorter"` 후 서비스 재시작 |
| 재배포 후 `import gpiozero/cv2` 실패 | **`uv sync`가 하드웨어 의존 prune** | `uv sync --inexact` 사용 또는 `uv pip install -r requirements-pi.txt` 재실행 |
| 서보 지터 / `PWMSoftwareFallback` 경고 | lgpio 소프트 PWM(Trixie 기본, pigpio 데몬 없음) | **무시 가능** — 연속회전 서보는 미세 지터 영향 없음. `GPIOZERO_PIN_FACTORY`는 설정 안 함(lgpio 자동) |
| iPad 연결 끊김 반복 | WiFi/BLE 간섭, 절전 | `sudo iw wlan0 set power_save off`(영구화: §pi-setup §9), 라우터 채널 분리 |
| 카메라 인식 안 됨 | 리본/오버레이 | `rpicam-hello --list-cameras` 확인, 케이블 재결합 |
| 결과는 받는데 화면 안 바뀜 | cycle 불일치 폐기(정상 방어) 또는 BLE notify 누락 | 재투입; 지속 시 앱 재시작 |

### BLE 복구 (가장 흔함)
```bash
ssh rp4b
sudo rfkill unblock bluetooth
bluetoothctl power on            # Powered: yes 확인
sudo systemctl restart trash-sorter
```
> 영구화돼 있으면 리부트 후에도 유지된다(이 프로젝트는 적용 완료). 재발 시 위 절차 + `/var/lib/systemd/rfkill/...:bluetooth`를 `0`으로.

---

## 5. 알려진 주의사항 (Gotchas)

- **`uv sync`는 단독 실행 금지** — `requirements-pi.txt`의 `gpiozero/opencv`를 prune해 런타임이 깨진다. 항상 `uv sync --inexact` 또는 직후 `uv pip install -r requirements-pi.txt`.
- **venv는 시스템 Python 3.13 + `--system-site-packages`** 고정 — apt `python3-picamera2`/`libcamera`를 쓰기 위함. pyenv 등 다른 Python 불가(libcamera 바인딩 ABI 불일치). 상세 `pi-setup.md` §4/§10.
- **Gemini 키**는 `secret/`(gitignore)에 두고 `TRASH_GEMINI_CREDENTIALS`로 지정. 키에 **결제/쿼터**가 있어야 실분류 동작.
- **수동 `uv run trash-sorter &`는 orphan을 남긴다** — 무인 운영은 반드시 **systemd 서비스**로(수명/재시작 관리). 진단 시엔 포그라운드로 실행하고 끝나면 종료 확인.
- **타임아웃/실패는 안전하게 `other`로 폴백** — 분류·HTTP·결과 타임아웃 시 양쪽 모두 `other` 처리하므로 사이클이 멈추지 않는다.

---

## 6. 운영 전 점검 체크리스트

- [ ] 라우터 인터넷 OK, AP격리 OFF, Pi·iPad 같은 서브넷
- [ ] `systemctl is-active trash-sorter` = active (자동기동)
- [ ] `bluetoothctl show` = Powered: yes (rfkill 영구 해제)
- [ ] 서보 = lgpio 기본 팩토리(Trixie — `GPIOZERO_PIN_FACTORY` 미설정, pigpio 데몬 없음)
- [ ] `/etc/trash-sorter.env`에 Gemini 키 경로, 키 쿼터 정상
- [ ] `rpicam-hello --list-cameras` 카메라 인식
- [ ] 모터 외부전원 + 공통 GND (Pi 5V 직급전 금지)
- [ ] iPad 앱 연결 → 어트랙트 화면, 테스트 투입 1회 정상
- [ ] 막대사탕/굿즈 충전
