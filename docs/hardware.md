# 실기기 조사 — 2026-10-20

SSH 연결과 읽기 전용 명령으로 확인했다. 비밀번호, 머신 ID, 부트 ID는 기록하지 않는다.

| 명령 | 결과 |
|---|---|
| hostnamectl / device-tree model | Debian 13, kernel 6.18.50+rpt-rpi-2712, Raspberry Pi 5 Rev 1.1 |
| lscpu | aarch64, Cortex-A76, 4 CPU, 최대 2400MHz |
| free -h | RAM 7.9GiB, available 7.4GiB, swap 2GiB |
| lsblk / df | microSD 57.6GiB; root 여유 37GiB; USB 28.7GiB vfat 여유 25GiB |
| lsusb | SanDisk 3.2Gen1이 Bus 004 USB 3 root hub에 연결 |
| rpicam-hello --list-cameras | IMX708 4608×2592, 1536×864/2304×1296/4608×2592 모드 |
| wlr-randr | DSI-2 720×1280@60.038Hz, Transform 270, enabled |
| /proc/asound/cards | HDMI 2개, 마이크 미확인 |
| vcgencmd | 온도 54.3°C, get_throttled=0x0 |
| python3 --version | 3.13.5 |
| dpkg-query | python3-picamera2 0.3.38-1 |
| command -v ffmpeg | /usr/bin/ffmpeg |
| sudo -n true | 비밀번호 없는 sudo 불가 |

## 제약과 보존 대상

- 테스트 USB는 `/media/jeongwoo/ESD-USB`에 마운트되어 있다. Windows 설치 파일 약 4.4GiB가 이미 들어 있다.
- USB 3 허브 연결을 확인했지만 실제 순차 읽기/쓰기 속도와 동시 녹화 성능은 측정하지 않았다.
- 마운트 경로는 운영 시 변할 수 있다. 제품은 UUID와 실제 mount 상태로 식별해야 한다.
- FAT32에는 4GiB 단일 파일 제한이 있어 녹화 분할이 필요하다.
- 커스텀 `rasp-geb-fan.service`가 실행 중이다. 설치 작업에서 이를 중지·교체하지 않는다.
- display manager/Wayland 세션이 실행 중이다. 키오스크 설정 전 기존 데스크톱 시작 구성을 보존한다.
- NVMe 저장장치는 lsblk에 나타나지 않았다. PCIe NVMe 기능은 실제 장치 연결 후 별도 시험한다.
- OOM, 장시간 열 안정성, 카메라 캡처/녹화, 터치 입력, 제스처, 음성, Samba 접속은 이번 읽기 전용 조사에서 검증하지 않았다.

## 구현 후 변경

메모리 cgroup 커널 옵션을 활성화하고 재부팅했습니다. USB는 대시보드 helper에서 /mnt/alter/72FB-1A24로 재마운트하며 vfat UTF-8을 지정합니다. 웹/모델/콜백 systemd 서비스와 Pi Chromium 자동 시작을 추가했습니다. 카메라 캡처·녹화 실증은 acceptance.md 참조. 기존 팬 서비스를 유지했습니다.
