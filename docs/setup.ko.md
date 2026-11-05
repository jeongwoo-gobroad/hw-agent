# 설치 안내

[English](setup.md) · [한국어](setup.ko.md) · [개요](../README.ko.md)

## 기본 설치

Pi 5와 64비트 Raspberry Pi OS를 사용합니다. 검증한 환경은 8GB RAM, Debian 13, Python 3.13입니다. 온디바이스 패널에는 데스크톱 환경이 필요합니다. 화면·카메라의 OS 설정은 실제 커넥터 연결과 맞춰야 하며 설치 스크립트는 부트 펌웨어나 오버레이를 변경하지 않습니다.

`~/hw-agent`에 clone한 후 일반 계정으로 `ALTER_LANGUAGE=ko bash scripts/install.sh`를 실행합니다. OS 패키지, Picamera2를 사용할 가상환경, Python 직접 의존성, 해시를 확인한 비전·사진 모델을 설치하고 대시보드 계정과 내부망 CIDR을 입력받아 웹·사진 서비스와 nginx를 구성합니다.

대시보드에는 고유하고 긴 비밀번호를 사용하세요. `.env`는 600, `data/`는 700 권한입니다. `ALLOWED_HOSTS`에는 실제 사용하는 호스트/IP를, `LAN_CIDR`에는 본인의 내부망 대역을 지정합니다. 재설정은 `.venv/bin/python scripts/configure.py --lang ko` 후 서비스를 재시작합니다. `SESSION_SECRET`을 바꾸면 로그인과 기존 OAuth 토큰 복호화에 영향을 주므로 보존해야 합니다.

`deploy/`는 템플릿입니다. **그대로 시스템에 복사하지 마세요.** 설치기는 현재 계정·UID/GID·내부망으로 `data/deploy/`에 렌더링한 파일을 사용합니다.

## 선택 기능

| 기능 | 설치와 설정 |
|---|---|
| 로컬 대화 | `bash scripts/install-llm.sh`. 고정 llama.cpp 리비전과 해시 검증한 Qwen3.5 4B Q4_K_M을 사용합니다. 빌드와 가중치 공간이 수 GB 필요합니다. 메모리 제한은 8GB 기준이며 OOM 방지를 보장하지 않습니다. |
| 시작 복구·화면 | Pi 데스크톱 계정에서 `bash scripts/install-startup.sh`. 준비된 서비스를 부팅 시 시작하고 `/panel` 자동 실행과 바탕화면의 화면 열기를 설치합니다. 프로젝트의 `Start-Alter.desktop`은 서비스 준비를 확인합니다. |
| 한국어 음성 | `bash scripts/install-voice.sh` 후 OS에서 인식되는 마이크를 연결합니다. HTTPS 또는 localhost에서 권한을 허용합니다. 영어 UI에서도 현재 음성 전사는 한국어입니다. |
| 외부 HTTPS·SmartThings | [OAuth 안내](oauth.ko.md)에 따라 본인 계정을 연결합니다. |

## SMB

`sudo smbpasswd -a "$USER"`로 Samba 비밀번호를 별도로 설정합니다. 기존 `/etc/samba/smb.conf`를 백업하고 `[global]`에서 게스트를 금지하며 SMB2 이상과 내부망 접근 제한을 적용하세요. 다음 include를 추가합니다.

```ini
include = /etc/samba/alter-shares.conf
```

include가 없으면 `sudo touch /etc/samba/alter-shares.conf`로 만들고 `sudo testparm -s` 검증 후 `smbd`를 재시작합니다. 드라이브 화면에서 SMB 공유를 등록한 후 Windows 탐색기의 `\\<pi-host>\Alter-<share-name>`로 접속합니다. 웹 비밀번호와 Samba 비밀번호는 별개입니다. `wsdd2`가 자동 검색을 담당하며 검색되지 않으면 UNC 주소로 직접 연결할 수 있습니다.

파일 색인·사진 폴더·SMB는 독립적입니다. 드라이브 식별은 파일시스템 UUID를 사용합니다. NTFS 문제는 먼저 권한·여유 공간·드라이버를 확인하고 [유지보수 안내](ntfs-maintenance.md)를 참고하세요.

## 화면과 접근 보호

5분 밝기 제어는 로컬 입력과 원격 데스크톱 입력을 감지합니다. 서버 요청은 화면 활동으로 취급하지 않습니다. 백라이트와 호환되는 Wayland 세션이 필요합니다. 카메라 화면의 **좌우 반전** 버튼으로 즉시 켜고 끌 수 있습니다. 회전·상하 반전 값은 유지하며 저장된 상태는 미리보기·인식·이후 녹화에 함께 적용됩니다. 녹화 중에는 버튼이 비활성화됩니다. 회전·상하 반전은 Alter 설정에서, 디스플레이 회전은 OS에서 지정합니다.

호출 대기는 6초 녹음과 전사를 반복하므로 처리 중 청취 공백이 있습니다. 전용 상시 wake-word 모델은 아니며 기기 조작은 확인 절차를 유지합니다.

11977은 내부망용이고 8080은 CAPTCHA와 로그인 실패 차단을 적용하는 외부 진입점입니다. 백엔드·모델 포트를 직접 노출하지 마세요. 인터넷에서 일반 HTTP는 비밀번호를 암호화하지 않으므로 HTTPS를 사용합니다.

## 설치 후 확인

11977에서 로그인·언어·테마 전환과 실시간 상태를 확인합니다. 합성 파일을 넣은 시험 폴더로 색인·검색·미리보기를, 별도 SMB 시험 공유로 생성·읽기·추가 저장·삭제를 검증하세요. 카메라는 촬영할 의도가 있을 때 켭니다. SmartThings는 지정한 기기를 시험하고 원래 상태로 되돌립니다. health 응답만으로 하드웨어와 계정 연동이 검증되지는 않습니다.

[업데이트·복구](operations.md) · [개발 및 테스트](../readme-for-agent.ko.md)

현재 밝기 서비스는 `/sys/class/backlight/panel_backlight@1`을 사용합니다. OS가 다른 백라이트 이름을 표시하면 서비스의 조건과 `scripts/display_brightness.py`의 `PANEL`을 맞추세요. 데스크톱 계정에는 OS 장치 권한을 통해 `brightness` 쓰기 권한이 있어야 합니다. 대시보드를 root로 실행하지 마세요.
