# 설치와 운영

## OS와 의존성

검증 환경 Debian13 ARM64/Python3.13.5. `scripts/install.sh`는 apt의 python3-venv/python3-picamera2/ffmpeg/samba/smbclient/OpenBLAS/cmake/g++/curl 개발 헤더를 설치하고 system-site-packages venv를 구성합니다. HEIF 빌드가 필요하면 libheif-dev도 설치합니다. `requirements-pi.lock.txt`는 pip --local 스냅샷이며 OS 패키지까지 고정하지 않습니다.

.env는 root 프로젝트에 두고 chmod600, data는700. 최소 DASHBOARD_USERNAME/DASHBOARD_PASSWORD/32자 이상 무작위 SESSION_SECRET이 필요합니다. 내부망 HTTP 호환을 위해 SECURE_COOKIE=false를 유지하지만 HTTPS 요청으로 발급되는 세션 쿠키는 코드에서 항상 Secure로 설정합니다. Uvicorn은127.0.0.1:18080에만 바인딩하고 nginx가 내부11977/외부8080을 제공합니다. 공유기에서 전달할 포트는8080만이며11977은포워딩하지 않습니다. ngrok을 통해 외부 HTTPS 접근을 제공합니다. ALLOWED_HOSTS에 정확한 ngrok 호스트를 추가하며 Uvicorn은127.0.0.1에서 오는 proxy header만 신뢰합니다. 브라우저 Origin/CSRF 검증은 외부 HTTPS 기준으로 동작합니다. OAuth URL의 코드가 남지 않도록 access log는 끕니다.

## 서비스

| 서비스 | 주소 | 메모리 상한 |
|---|---|---|
| nginx | 내부11977 / 외부8080 → loopback18080 | OS 관리 |
| alter | 127.0.0.1:18080 | 1200MiB + swap256MiB |
| alter-llm | 127.0.0.1:8081 | 5800MiB + swap128MiB |
| alter-oauth | 127.0.0.1:8082 | 256MiB |
| alter-ngrok | 고정 ngrok HTTPS→8080 | 192MiB |

`systemctl status alter alter-llm alter-oauth`, `journalctl -u alter`, `/health`로 확인합니다. 서비스 파일 변경은 root install 후 daemon-reload/restart. 별도 프로세스의 모델은 웹 재시작과 분리합니다. `.env` 변경 후 alter와 alter-oauth 모두 재시작해야 합니다.

초기 Pi 커널 cmdline에 cgroup_disable=memory가 있어 제한이 무효였습니다. `/boot/firmware/cmdline.txt.pre-alter` 백업 후 해당 옵션을 제거하고 cgroup_enable=memory cgroup_memory=1을 추가해 재부팅했습니다. `/sys/fs/cgroup/cgroup.controllers`에 memory가 있는지 확인하세요. cgroup limit은 OOM 가능성을 없애는 보장이 아니며 모델 mmap/cache 귀속에 따라 수치 해석이 달라집니다.

## 모델 설치

llama.cpp 공식 저장소의 검증 커밋은 [모델 기록](models.md)에 기록합니다. data/build/llama.cpp에 clone하고 다음 옵션으로 빌드했습니다:

```bash
cmake -S data/build/llama.cpp -B data/build/llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS -DLLAMA_CURL=ON
cmake --build data/build/llama.cpp/build --target llama-server -j3
```

models에 GGUF를 다운로드하고 기록의 해시를 확인합니다. data/llm-api-key에 무작위 토큰을 생성해 chmod600, deploy/alter-llm.service 설치 후 enable --now. 현재 기본값 Qwen3.5-4B-Q4_K_M, context4096/parallel1/threads3. MediaPipe gesture_recognizer.task는 Google 공식 모델 배포에서 별도 다운로드합니다. 가중치는 Git에 넣지 않습니다.

ngrok은 .env의 NGROK_AUTHTOKEN을 읽고 자동 시작합니다. 계정 고정 개발 도메인을 쓰므로 별도 소유 도메인이 필요하지 않습니다. 무료 사용량 한도와 브라우저 안내는 docs/oauth.md를 참고하세요. 예전 alter-tunnel.service는 Cloudflare 임시 터널용 예제로 보존하며 현재 운용에는 사용하지 않습니다.

## Samba와 외장 저장장치

root helper alter-smb/alter-disk만 sudoers로 허용합니다. 웹은 일반 사용자로 실행합니다. 마운트는 /mnt/alter/<UUID>, nosuid/nodev, FAT계열 UID/GID1000, vfat utf8=1. 강제 unmount는 사용하지 않습니다.

현재 smb.conf 원본은 /etc/samba/smb.conf.pre-alter에 백업되어 있습니다. 운용 구성은 SMB2 이상, guest 금지, 인터페이스 lo와192.168.0.0/24, hosts allow127./192.168.0., `/etc/samba/alter-shares.conf` include입니다. helper가 `/etc/samba/alter.d/` 내 Alter-* 공유만 관리하며 testparm 검증 후 reload합니다. 새 설치에서는 이 include와 LAN 제한을 설정하고 `sudo smbpasswd -a jeongwoo`로 SMB 비밀번호를 설정하세요. 웹 .env 비밀번호 변경이 SMB 비밀번호까지 자동 변경하지 않습니다.

드라이브 분리 전 녹화/파일사용을 종료하세요. 사용 중이면 해제 실패를 보여줍니다. 연결되지 않은 드라이브의 이전 메타데이터는 남지만 원본 제공은 차단됩니다. 자동 부팅 마운트는 현재 fstab에 추가하지 않았으며 대시보드에서 마운트할 수 있습니다.

## 화면·카메라

deploy/alter-panel.desktop을 ~/.config/autostart에 복사합니다. Pi 로컬 세션의 Chromium에서 /panel을 열며 최초 로그인은 필요합니다. 화면 터치 입력은 미검증입니다. 카메라와 제스처는 기본 꺼짐. 녹화는 선택 root/Alter-recordings 아래120초 세그먼트, 여유512MiB 미만 시작 금지/256MiB 미만 중단. 의도적으로 켠 경우만 촬영합니다.

## 백업·배포

`scripts/backup.py`는 SQLite backup API로 data/backups에 일관된 복사본을 만듭니다. 이 DB에도 대화와 암호화 토큰이 있으므로 비공개로 취급하세요. 복원에는 .env의 동일 SESSION_SECRET이 필요합니다. 녹화/원본/모델은 이 백업에 포함되지 않습니다. backup은 현재 기본 data 경로 전용입니다.

Windows `scripts/deploy.py`는 git 추적 소스를 SFTP 전송하고 hash를 비교하며 SSH fingerprint를 고정합니다. 비밀번호는 getpass 입력입니다. 비공개 .env/data/models는 전송/커밋하지 않습니다. 서비스 재시작은 변경 범위에 맞춰 별도 수행합니다.

## 대화 스트리밍과 테마

대화창에서 생성되는 문장이 바로 표시됩니다. 중단 버튼은 연결을 종료하며 부분 응답은 보관하지 않습니다. 모델이 입력을 처리하는 중에는 다음 생성 청크까지 서버의 중단 처리가 늦어질 수 있습니다. 최종 결과를 받기 전에는 기기 실행 버튼이 나타나지 않습니다. 테마는 브라우저별로 저장되고 최초 방문 시 시스템 라이트/다크 설정을 따릅니다.

## 터치 디스플레이 운영

Pi Chromium 시작 주소는 http://127.0.0.1:11977/panel 입니다. 업데이트 후 기존 창을 새로고침하면 전용 터치 UI가 적용됩니다. DSI는720×1280에270도 회전하여 가로1280×720으로 설정되어 있습니다. OS에서 인식되는 마이크가 필요하며, 원격 Chrome에서는 그 컴퓨터의 마이크를 사용합니다. 녹음은 Pi로 전송되고 처리 뒤 삭제됩니다. LAN IP의 HTTP에서는 브라우저 마이크가 제한되므로 ngrok HTTPS 또는 Pi localhost를 사용하세요.

‘음성 입력’은 전사 내용을 확인하고 보내며, ‘얼터 호출 대기’는 호출어와 요청을 함께 인식하면 챗봇으로 전달합니다. 최종 기기 실행 확인은 유지합니다. 처리 중에는 계속 듣지 않으며 6초 녹음과 전사를 반복합니다. 녹음 종료 버튼/호출 대기 끄기/페이지 숨김으로 마이크를 종료합니다. 소음 환경의 호출 오탐률은 검증되지 않았습니다.

## 전원 복귀와 실행 파일

1. Pi 부팅 시 alter, alter-llm, alter-ngrok, alter-oauth, smbd와 alter-recovery가 자동 실행됩니다. 모델 로딩에는 시간이 걸릴 수 있습니다.
2. 확인하려면 프로젝트 루트의 Start-Alter.desktop을 실행합니다. 처음 파일 관리자에서 실행 여부를 물으면 실행을 선택합니다. start.sh --no-browser는 화면 없는 점검입니다.
3. Windows에서는 D:\_rpi-agent\Start-Alter.cmd를 실행하면 SSH 인증 후 같은 점검을 수행합니다. 호스트 키 첫 확인은 실제 Pi 키와 대조하세요.
4. `data/startup-status.json`의 checked_at과 각 ok 값을 확인합니다. 오래된 성공 파일만으로 이번 부팅 성공을 판단하지 마세요. systemctl status alter-recovery와 이번 부팅 journal도 확인합니다.
5. SmartThings 재연결 안내가 나오면 대시보드 스마트홈에서 삼성 계정으로 로그인합니다. 계정 동의나 철회된 권한을 자동 우회할 수는 없습니다.

정상 부팅 때는 수동 클릭 없이도 복구가 수행됩니다. 수동으로 stop한 서비스는 실행 파일에서 관리자 인증을 요구할 수 있습니다. 누락된 USB는 오프라인으로 표시하고, 손상된 DB는 자동 삭제하지 않습니다. 전원 차단으로 매체가 손상되면 이 실행 파일만으로 수리할 수 없습니다.

## 외장하드 재연결 및 밝기

드라이브 화면의 볼륨 ID는 파일시스템 UUID입니다. 같은 USB가 다른 마운트 폴더로 연결되어도 재등록 시 기존 root를 갱신하며 색인을 중복 생성하지 않습니다. 포맷/복제 시 UUID가 바뀌거나 충돌할 수 있습니다. 동일 UUID 장치 여러 개를 함께 연결하지 마세요.

밝기 제어 상태: `systemctl --user status alter-display`. 중지: `systemctl --user stop alter-display`(밝기도 복원). 시작: `systemctl --user start alter-display`. 타이머는 입력 종류를 터치만으로 한정하지 않고 Wayland seat 전체의 무입력을 기준으로 합니다. USB 키보드/마우스/화면 공유 조작도 복원 및 타이머 초기화 대상입니다. data/display-brightness.json에 직전 밝기와 변경 시각을 기록합니다.

서버의 HTTP 요청, 외부 PC 대시보드 조작, 파일 색인·검색·다운로드, 모델 생성, 카메라 스트리밍, SmartThings 통신은 Pi 화면 입력으로 계산하지 않습니다. 밝기 서비스는 서버의 요청량이나 CPU 사용률을 읽지 않으며 Wayland 입력 활동만 관찰합니다. Pi 화면 공유에서 실제 마우스나 키보드 입력을 보내는 경우는 Pi 화면 조작이므로 활동에 포함됩니다.

Windows SMB 접속: 파일 탐색기 주소창에 `\\192.168.0.44` 또는 `\\192.168.0.44\Alter-공유이름`을 입력합니다. Windows 계정 대신 SMB 사용자 jeongwoo와 설치 시 지정한 Samba 비밀번호로 인증합니다. 웹 로그인과 별도 인증입니다. 네트워크 목록 검색을 위해 `sudo apt-get install wsdd2` 및 `sudo systemctl enable --now wsdd2`를 적용했습니다. Windows 네트워크가 Private이고 네트워크 검색이 허용되어야 합니다. SMB1이나 게스트 접근은 활성화하지 않습니다. wsdd2 공식 설명: https://manpages.debian.org/bookworm/wsdd2/wsdd2.8.en.html . 직접 UNC 접근 성공과 탐색기 자동 검색 표시는 별도로 판단하세요.

NTFS 압축과 쓰기 진단: SMB read only, 마운트 rw/ro, 소유권, 기존 연결, 개별 파일 속성을 분리해 확인합니다. 폴더 압축 속성만으로 쓰기 불가를 단정하지 않습니다. NTFS3는 일반 NTFS 압축 읽기/쓰기를 지원합니다(https://docs.kernel.org/filesystems/ntfs3.html). Windows에서 압축 해제는 해당 파일/폴더 속성의 고급 압축 옵션으로 가능하지만 범위를 먼저 확정하고 여유 공간을 확인해야 합니다. 접근 금지 하위 폴더가 있는 볼륨에 전체 재귀 해제를 실행하지 않습니다. 기존 공유 수정은 목록의 설정 변경→읽기 전용 변경→공유 적용 순서입니다. 기존 Windows 연결은 탐색기 창을 닫고 공유 주소로 다시 연결해야 할 수 있습니다.


상시 감지 설치: `.venv/bin/python scripts/install-vision.py`로 공식 두 모델을 검증하고 웹 서비스를 재시작합니다. 대시보드 상시 모션 감지에서 활성 여부·각 Flow·유지/재감지/반복을 저장합니다. 카메라를 독점하는 다른 프로그램이 있으면 먼저 종료해야 합니다. 미리보기 여부와 서버 감지는 독립적이며, 서버의 프레임 처리와 Flow 실행은 디스플레이 입력 활동으로 취급하지 않습니다. 초기 기본값은 꺼짐이나 사용자가 활성 설정을 저장하면 다음 시작에도 복원됩니다.

부하 재검증: `PYTHONPATH=src .venv/bin/python scripts/verify-motion-load.py`. 카메라 설정/Flow 매핑을 임시로 비워 자동 기기 조작 없이 시험하고 종료 시 이전 설정을 복원합니다. 수 분 이상 걸릴 수 있으므로 출력 토큰을 계속 읽어 모니터링하지 말고 프로세스 완료와 data/motion-load-report.json을 확인합니다. 테스트 중 사용자가 감지 설정을 바꾸지 않도록 합니다. 최신 설정은4096문맥이며 실제2048출력 토큰 수와 두 모델 frame 증가, cgroup OOM/재시작을 함께 확인해야 합니다.

## 사진 작업자 설치/갱신

`sudo apt-get install libimage-exiftool-perl` 후 `.venv/bin/pip install -r requirements.txt`, `.venv/bin/python scripts/install-photo-models.py`를 실행합니다. `deploy/alter-photos.service`를 `/etc/systemd/system/`에 설치하고 daemon-reload 후 `systemctl enable --now alter-photos`를 실행합니다. 웹 서비스를 재시작하면 별도 사진 폴더 메뉴가 나타납니다. `start.sh`와 부팅 복구는 사진 서비스/사진 전용 볼륨도 복원합니다. 데이터 관리·오류 처리·API는 [photos.md](photos.md)를 참조하세요.


### 사진 모델 업데이트와 센서

사진 모델은 `scripts/install-photo-models.py`를 Pi venv에서 실행해 FP32 CLIP 두 파일·YuNet·SFace의 고정 SHA256을 검증한 뒤 `alter-photos.service`를 재시작한다. MODEL_VERSION 변경 시 다음 스캔이 자동 점수를 재계산한다. DB state.photo_progress와 data/photo-heartbeat가 진행률/생존 정보이다. 결과를 작은 트랜잭션으로 커밋해 긴 전체 FTS 교체 잠금을 제거했다. private data와 모델은 Git에 올리지 않는다. 완료한 기존 결과는 목록 확인 중에도 계속 제공한다. 새 결과는 메타데이터 단계 후 항목별로 반영한다.

카메라 방향은 설정 화면에서 저장하며 녹화 중에는 먼저 녹화를 중지해야 한다. 서버 재시작 시 DB의 camera_orientation을 복원한다. CPU 온도는 thermal sysfs, RAM 온도는 hwmon의 DIMM/DRAM 레이블이 있는 센서만 사용한다. 현재 Pi의 RAM 센서 없음 표시는 오류가 아니다.


## 색인 진행률과 ETA (2026-10-24)

개요의 파일/사진 카드에 처리 수 / 전체 대상 수, 백분율, 예상 남은 시간을 5초마다 표시합니다. 사전 집계는 등록된 루트만 읽으며 제외 디렉터리·숨김 항목·심볼릭 링크를 진입 전에 건너뜁니다. 집계 중에는 전체가 아직 확정되지 않았으므로 진행 막대와 ETA를 미확정으로 표시합니다. 탐색 도중 파일이 추가·삭제되면 이번 스캔의 분모와 실제 처리 수가 달라질 수 있으며 다음 스캔에서 갱신됩니다.

파일은 이번 검사에서 확인한 파일(변경 없는 파일 포함) / 사전 발견 파일 수입니다. 결과는 항목별로 즉시 반영하고, 마지막 삭제 정리 단계에는 ETA를 계산하지 않습니다. 기존 검색 가능한 파일 수는 큰 숫자로 계속 표시합니다.

사진은 두 단계입니다. 파일 정보 확인은 확인한 미디어 파일 / 사전 발견 미디어 파일 수이며 이 단계의 ETA는 **파일 정보 확인 단계**의 예상치입니다. 주제·얼굴 분류로 전환하면 Live Photo 중복 영상을 제외한 항목 수가 분모이고, 기존 완료 항목 + 이번 시도 항목이 분자입니다. 오류 항목은 확인 필요 수로 따로 표시합니다. ETA는 해당 단계의 실제 경과 시간과 처리 표본으로 계산하며 전체 작업의 고정 마감 시간이 아닙니다. 사진/영상 크기·모델 초기화·동시 작업에 따라 변합니다. 최소 3개/2초 이전에는 계산 중, 일시정지·오류·작업자 단절 시 ETA 대기로 표시합니다.


## 접속 보호와 증분 색인

`bash scripts/install-web-entrypoints.sh`로 nginx 설정을 설치합니다. 기존 기본 사이트 심볼릭 링크만 제거하며 다른 사이트 설정은 보존합니다. nginx 설정 검사 후 재시작합니다. 내부11977의 허용 대역은 현재192.168.0.0/24이며 네트워크를 변경하면 deploy/alter-nginx.conf도 수정해야 합니다. 변경 후 내부11977과 외부8080의 /health 및 로그인 경계를 각각 검증하세요.

공인 IP/DDNS로 접속할 때는 해당 호스트(스킴·포트 제외)를 .env의 ALLOWED_HOSTS에 추가하고 alter를 재시작합니다. 공유기 NAT 설정과 실제 외부망 접속은 별도 검증 대상입니다. 일반 HTTP는 비밀번호·세션을 암호화하지 않습니다. ngrok HTTPS는 기존 OAuth 콜백과 함께 유지되며 외부 CAPTCHA 보호를 사용합니다.

정책, DB 백업/마이그레이션, 최초 해시 생성, 중단 재개와 오류 재시도는 [indexing-security.md](indexing-security.md)를 참조하세요. start.sh는 nginx도 복구하고 내부11977/panel을 엽니다.
