# 설치와 운영

## OS와 의존성

검증 환경 Debian13 ARM64/Python3.13.5. `scripts/install.sh`는 apt의 python3-venv/python3-picamera2/ffmpeg/samba/smbclient/OpenBLAS/cmake/g++/curl 개발 헤더를 설치하고 system-site-packages venv를 구성합니다. HEIF 빌드가 필요하면 libheif-dev도 설치합니다. `requirements-pi.lock.txt`는 pip --local 스냅샷이며 OS 패키지까지 고정하지 않습니다.

.env는 root 프로젝트에 두고 chmod600, data는700. 최소 DASHBOARD_USERNAME/DASHBOARD_PASSWORD/32자 이상 무작위 SESSION_SECRET이 필요합니다. 현재 HTTP 내부망이므로 SECURE_COOKIE=false입니다. HTTPS 대시보드로 전환하면 true로 바꾸세요. 서비스는 전체 인터페이스8080에 바인딩하며 인터넷 포트포워딩을 설정하지 않습니다.

## 서비스

| 서비스 | 주소 | 메모리 상한 |
|---|---|---|
| alter | 내부망8080 | 1200MiB + swap256MiB |
| alter-llm | 127.0.0.1:8081 | 5800MiB + swap128MiB |
| alter-oauth | 127.0.0.1:8082 | 256MiB |
| alter-ngrok | 고정 ngrok HTTPS→8082 | 192MiB |

`systemctl status alter alter-llm alter-oauth`, `journalctl -u alter`, `/health`로 확인합니다. 서비스 파일 변경은 root install 후 daemon-reload/restart. 별도 프로세스의 모델은 웹 재시작과 분리합니다. `.env` 변경 후 alter와 alter-oauth 모두 재시작해야 합니다.

초기 Pi 커널 cmdline에 cgroup_disable=memory가 있어 제한이 무효였습니다. `/boot/firmware/cmdline.txt.pre-alter` 백업 후 해당 옵션을 제거하고 cgroup_enable=memory cgroup_memory=1을 추가해 재부팅했습니다. `/sys/fs/cgroup/cgroup.controllers`에 memory가 있는지 확인하세요. cgroup limit은 OOM 가능성을 없애는 보장이 아니며 모델 mmap/cache 귀속에 따라 수치 해석이 달라집니다.

## 모델 설치

llama.cpp 공식 저장소의 검증 커밋은 [모델 기록](models.md)에 기록합니다. data/build/llama.cpp에 clone하고 다음 옵션으로 빌드했습니다:

```bash
cmake -S data/build/llama.cpp -B data/build/llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS -DLLAMA_CURL=ON
cmake --build data/build/llama.cpp/build --target llama-server -j3
```

models에 GGUF를 다운로드하고 기록의 해시를 확인합니다. data/llm-api-key에 무작위 토큰을 생성해 chmod600, deploy/alter-llm.service 설치 후 enable --now. 현재 기본값 Qwen3.5-4B-Q4_K_M, context2048/parallel1/threads3. MediaPipe gesture_recognizer.task는 Google 공식 모델 배포에서 별도 다운로드합니다. 가중치는 Git에 넣지 않습니다.

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
