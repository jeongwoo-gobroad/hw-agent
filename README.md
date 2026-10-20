# Alter / 얼터 — Raspberry Pi Personal Agent

Raspberry Pi 5에서 외장 파일 검색, 한국어 대화, SmartThings와 카메라를 통합하는 Python 로컬 에이전트입니다. 기기 동작 프리셋을 **Flow**라고 부릅니다.

현재 Raspberry Pi에 웹 서비스가 배포되어 있습니다. 2026-10-20 기준 SmartThings OAuth 연결, 실제 기기 조회, 사용자가 허용한 조명의 상태 변경과 원상복구, 갱신 토큰 교체까지 검증했습니다. 기능별 검증 범위와 미완료 항목은 [검증 기록](docs/acceptance.md)에 구분합니다.

## 시작하기

외부 대시보드: https://novella-lappeted-september.ngrok-free.dev/

내부망 대시보드: `http://192.168.0.44:8080`. 프로젝트 루트 `.env`의 ID/PW로 로그인합니다. 비밀번호는 저장소에 공개하지 않습니다.

1. **드라이브**에서 USB/NVMe 장치의 폴더를 선택해 색인에 등록합니다. 마운트·안전 해제, 선택 폴더의 SMB 공유와 읽기 전용 설정을 제공합니다.
2. **파일 탐색**에서 키워드, 확장자, 폴더, 수정/생성 날짜로 검색합니다. 결과 카드에서 문서·사진·영상을 미리 보고 필요할 때 원본을 내려받습니다.
3. **얼터와 대화**에서 자연어로 파일을 찾거나 등록된 기기/Flow 실행을 제안받습니다. 기기 명령은 확인 버튼을 눌러 실행합니다. 대화별 생성·이름 변경·삭제·JSON 내보내기를 제공합니다.
4. **스마트홈 · Flow**에서 삼성 계정으로 연결하고 기기를 불러옵니다. Flow는 기기 명령과 대기 단계를 조합하고 실행 기록을 남깁니다.
5. **카메라**에서 실시간 영상을 켜고 등록된 외장 폴더에 녹화합니다. 제스처 기능은 별도로 켜고 동작을 Flow 또는 대시보드 알림에 연결합니다.

## 구현된 기능과 경계

| 영역 | 현재 동작 |
|---|---|
| 인증 | .env ID/PW, 해시된 서버 세션, 로그인 속도 제한, CSRF/Origin 검증, 12시간 만료 |
| 드라이브 | lsblk USB/NVMe 파티션, UUID 추적, 제한된 sudo 도우미로 마운트/해제/SMB 관리 |
| 색인 | 60초마다 변경 대조, 72시간마다 내용 재추출 후 이전 활성 색인 교체; 원본 파일은 삭제하지 않음 |
| 검색 | SQLite FTS5 BM25, 한국어 문자 bigram, 최대 100개 후보의 선택적 문자 TF-IDF 재정렬 |
| 문서 | TXT/일반 텍스트, DOCX/HWPX XML, 구형 HWP(pyhwp), 텍스트 PDF(pypdf); OCR 미지원 |
| 미리보기 | Pillow/HEIF 사진 변환, FFmpeg MOV 등 영상 프록시, 문서의 추출 텍스트 |
| AI | llama.cpp GGUF 로컬 추론, 대화 저장, 파일 카드, 기기/Flow 확인 제안; 최근 일부 대화만 추론 문맥에 포함 |
| SmartThings | OAuth 인가 코드, 상태값/브라우저 바인딩, 암호화 토큰, 자동 갱신/회전, 연결 해제 |
| 기기 명령 | switch, switchLevel, audioVolume, colorTemperature 허용 목록; 전체 SmartThings capability를 지원하는 것은 아님 |
| Flow | 생성/편집/복제/삭제, 순차 실행, 실패 즉시 중단, 요청 중복 방지, 실행 기록 |
| 카메라 | Picamera2 IMX708 640×480 10fps MJPEG, FFmpeg MP4 120초 분할, 잔여 공간 검사 |
| 제스처 | MediaPipe 손바닥/주먹/V/엄지 위/엄지 아래, 신뢰도·유지시간·쿨다운, 기본 비활성 |
| 화면 | `/panel`과 Pi Chromium 자동 시작 설정; 실제 터치 조작 검증은 별도 |
| 음성 | 미구현. 현재 캡처용 마이크가 없으며 한국어 호출어/STT 실장비 검증이 필요 |

생성일은 파일시스템에서 실제 birth time을 제공할 때만 저장하며, Linux ctime을 생성일로 오인하지 않습니다. 현재 테스트 FAT32 마운트에서는 생성일이 없을 수 있습니다. 문서 미리보기는 원본 레이아웃 렌더러가 아닙니다. Apple 기기에서 촬영한 모든 코덱 조합의 재생을 보장하지 않습니다.

## 장비와 배치

- Raspberry Pi 5 8GB, Cortex-A76 4코어, Debian 13 ARM64, Python 3.13.5.
- 소스/설치: Pi `~/hw-agent`, Windows `D:\_rpi-agent`.
- 웹 8080(내부망 + ngrok HTTPS), 모델 8081(loopback), 독립 OAuth 콜백 앱 8082(loopback, 대체 구성용).
- USB SanDisk 약 28.7GiB: 기존 파일을 보존하고 `Alter-test` 폴더만 검증에 사용했습니다.
- IMX708 카메라, DSI 화면. 기존 팬 서비스 유지.
- `.env`, SQLite, 토큰, 대화, 캐시, 녹화, 모델은 Git에서 제외합니다.

## 설치·복원

[운영 가이드](docs/operations.md)에 OS 의존성, 서비스, Samba, 모델, cgroup, 백업 절차를 정리했습니다. `requirements.txt`는 직접 의존성, `requirements-pi.lock.txt`는 검증 환경의 추가 설치 패키지 스냅샷입니다. Picamera2/libcamera는 apt 환경을 사용하므로 venv에 `--system-site-packages`가 필요합니다.

```bash
git clone https://github.com/jeongwoo-gobroad/hw-agent ~/hw-agent
cd ~/hw-agent
cp .env.example .env
# ID/PW와 충분히 긴 무작위 SESSION_SECRET을 설정
bash scripts/install.sh
```

설치 스크립트는 현재 계정 `jeongwoo`와 설치 경로에 맞춰져 있습니다. 다른 환경에서는 systemd 경로/계정과 허용 호스트부터 수정하세요. 모델·제스처 가중치와 Samba 설정은 운영 가이드의 별도 절차가 필요합니다.

## SmartThings OAuth

[OAuth 가이드](docs/oauth.md)에 앱 등록, HTTPS 콜백, 로그인, 재인증과 장애 복구를 설명합니다. ngrok 무료 플랜의 계정 고정 개발 도메인과 자동 HTTPS 인증서를 사용합니다. 별도 소유 도메인은 필요하지 않습니다. 무료 브라우저 안내와 사용량 한도는 적용됩니다. 이미 연결된 토큰의 자동 갱신은 콜백 주소의 상시 가용성과 별개입니다. 사용자 요청에 따라 ngrok은 현재 대시보드8080을 제공합니다. ID/PW 인증과 CSRF 검증을 유지하며 외부 HTTPS 세션 쿠키에는 Secure를 설정합니다. OAuth 콜백도 같은 도메인에서 처리합니다. 로그인 전에는 파일 검색·다운로드·카메라 API에 접근할 수 없습니다.

## 개발·검증

```bash
PYTHONPATH=src .venv/bin/python tests/test_boundaries.py
PYTHONPATH=src .venv/bin/python tests/test_oauth.py
# 실제 USB에 테스트 파일을 생성하고 카메라 녹화를 수행하는 통합 시험
.venv/bin/python tests/live_smoke.py
```

실기기 시험은 [검증 기록](docs/acceptance.md)을 먼저 읽으세요. 저장장치 시험은 등록 USB를 실제로 해제/재마운트합니다. 소스 변경 시 관련 문서와 검증 결과도 갱신합니다. 에이전트용 구조 안내는 [readme-for-agent.md](readme-for-agent.md)입니다.

## 라이선스

자체 코드 GPL-3.0-or-later. 외부 라이브러리·모델은 각 라이선스를 따릅니다. Raspberry Pi 공식 로고는 상표이며 GPL 대상이 아닙니다. [자산 출처](src/hw_agent/web/static/ASSETS.md)를 참고하세요. 공식 Raspberry Pi 제품이나 후원 프로젝트라는 의미는 아닙니다.

## 실시간 대화와 화면 테마

답변은 llama.cpp의 실제 생성 이벤트를 SSE로 전달해 완료 전부터 표시합니다. 생성 준비/경과 시간과 중단 버튼을 제공하며, 기기·Flow 명령은 완성된 응답을 검증한 뒤 사용자 확인을 거칩니다. 검색 후보는 검색 완료 후 카드로 표시합니다. 상단 테마 버튼에서 연보라·아이보리 라이트 모드와 짙은 보라 다크 모드를 전환할 수 있으며 브라우저에 선택을 저장합니다. 로그인·대시보드·터치 패널에 같은 테마를 적용합니다.

## 내장 디스플레이와 음성

`/panel`은 큰 터치 버튼의 스마트홈/Flow와 챗봇을 제공하며 챗봇을 누르면 두벌식 한글·영문 팝업 키보드가 열립니다. 새 대화/대화 목록, 연보라·아이보리 테마를 지원합니다. USB 또는 OS에서 오디오 입력으로 인식되는 GPIO 마이크를 연결한 뒤 ‘음성 입력’을 누르세요. HTTPS 또는 Pi localhost에서 브라우저 마이크 권한이 필요합니다. 음성 파일 입력도 지원합니다.

음성은 Pi의 whisper.cpp v1.8.3 + Whisper tiny 다국어 모델에서 한국어로 처리합니다. `sh scripts/install-voice.sh`로 설치하며 Python 추가 의존성은 없습니다(cmake/C++/ffmpeg/curl 필요). 오디오는 처리 후 임시 파일과 함께 삭제됩니다. ‘얼터 호출 대기’를 켜면 6초 녹음 → 한국어 전사 → 호출어 확인을 반복합니다. ‘얼터, 회의 문서를 찾아줘’처럼 한 문장으로 말하세요. 호출되면 챗봇에 전달하지만 물리 기기·Flow는 최종 확인이 필요합니다. 전용 저지연 wake-word 엔진이 아니므로 처리 사이에 청취 공백이 있고, 상시 대기는 기본 꺼짐입니다. 페이지가 숨겨지면 마이크가 종료됩니다.

현재 Pi에 마이크가 없어 실제 사람의 음성/호출 인식률은 미검증입니다. 합성 한국어 음성을 실제 Pi 엔진으로 처리하는 것은 검증했습니다.

웹 전체의 동작 아이콘은 Lucide SVG이며 텍스트 설명과 함께 사용합니다. 색상은 currentColor로 라이트/다크 테마를 따릅니다. 아이콘·키보드 라이브러리는 로컬에서 제공하므로 CDN 연결이 필요하지 않습니다.

## 재부팅 후 실행·복구

Pi 프로젝트 최상위 `Start-Alter.desktop`(Alter 시작 및 복구)을 실행하세요. 터미널에서는 `./start.sh` 또는 브라우저 없이 `./start.sh --no-browser`입니다. Windows 백업 폴더의 `Start-Alter.cmd`는 SSH로 같은 복구를 실행합니다(PC의 SSH 인증이 필요하며 비밀번호를 파일에 저장하지 않습니다).

서버·언어 모델·ngrok·OAuth·SMB는 부팅 자동 시작으로 등록되고, alter-recovery가 웹/모델 준비, 등록된 외장 드라이브 UUID, SMB 경로, 공개 HTTPS, 저장된 SmartThings 인증을 확인합니다. 재실행은 이미 실행 중인 서비스를 재시작하지 않습니다. 정상 부팅 후 클릭은 별도 관리자 인증 없이 점검·대시보드 열기를 수행합니다. 관리자가 서비스를 완전히 중지한 경우에는 Pi 계정 암호를 요청할 수 있습니다. 삼성에서 권한을 철회했거나 refresh token이 만료·손상된 경우 삼성 계정 재로그인은 필요합니다.

기존 설치에 적용: `bash scripts/install-startup.sh`. 결과는 private `data/startup-status.json`, 부팅 로그는 `journalctl -u alter-recovery -b`에서 확인합니다. 전원 손실로 파일시스템·SD카드·DB가 손상된 경우 자동 초기화하지 않으며 백업 복구가 필요합니다.

## 드라이브 식별과 화면 절전

색인 폴더는 **파일시스템 UUID + 드라이브 내부 상대경로**로 식별합니다. 마운트 이름이나 /dev/sda 순서가 바뀌어도 같은 폴더/파일 ID를 유지합니다. USB 일련번호는 장치 정보이고 여러 파티션을 구별하는 색인 키는 아닙니다. 포맷으로 UUID가 바뀌면 새 볼륨이며, 동일 UUID의 복제 볼륨을 동시에 연결하면 오인 연결을 차단합니다.

내장 DSI 디스플레이는 5분 동안 입력이 없으면 밝기1/31로 낮아지고 터치·키보드·마우스 입력 시 직전 밝기로 복원됩니다. 화면을 끄거나 서버를 중단하지 않습니다. Raspberry Pi Connect의 원격 입력도 활동으로 처리됩니다. 이미 설치된 swayidle과 기존 video 그룹 권한을 사용하며 별도 관리자 권한을 추가하지 않습니다.

파일 검색·다운로드, AI 생성, 카메라 스트리밍, SmartThings 통신 등 서버 작업과 외부 PC의 대시보드 사용은 디스플레이 활동으로 계산하지 않습니다.

색인과 SMB는 드라이브 화면의 별도 버튼으로 폴더를 선택합니다. SMB만 등록해도 검색 색인에 추가되지 않으며, 색인 등록 해제와 공유 해제는 서로 영향을 주지 않습니다. 공유 전용 볼륨도 UUID로 부팅 시 복구합니다. Windows 탐색기 주소창에 `\\192.168.0.44`를 입력하고 SMB 계정 `jeongwoo`로 로그인하세요. 네트워크 자동 검색은 Debian 패키지 `wsdd2`가 담당합니다.
