# Updates and recovery / 업데이트와 복구

New installation: [English](setup.md) / [한국어](setup.ko.md). OAuth: [English](oauth.md) / [한국어](oauth.ko.md).

Keep `.env`, `data/`, `models/` and originals outside Git. Back up SQLite with `scripts/backup.py` (SQLite backup API), and preserve the matching `SESSION_SECRET` privately. Databases include conversations and encrypted tokens. The backup does not include original media, recordings or weights.

업데이트 전 SQLite backup API로 일관된 DB 복사본을 만들고 같은 `SESSION_SECRET`을 비공개로 보관합니다. 원본·녹화·가중치는 별도 백업 대상입니다. 예제 설정으로 실제 `.env`를 덮어쓰지 않습니다.

| Service | Role |
|---|---|
| `nginx` | LAN11977 / public8080 → loopback18080 |
| `alter` | Single web/camera/index owner |
| `alter-photos` | Resumable photo worker |
| `alter-llm` | Optional authenticated loopback8081 llama.cpp |
| `alter-oauth` | Alternate callback-only loopback8082 app |
| `alter-ngrok` | Optional HTTPS → public8080 |
| `alter-recovery` | Registered-volume/share restoration and configured-service readiness |

`git pull --ff-only` updates tracked source. Install changed direct dependencies in `.venv` and run relevant tests. Render changed deployment templates through the installer, not by copying `deploy/` directly. For a web-only update restart `alter`; for photo-worker changes also restart `alter-photos`. `.env` changes affecting OAuth require restarting both `alter` and `alter-oauth`. Do not restart a camera recording without stopping it normally first.

웹만 바뀌면 `alter`, 사진 worker가 바뀌면 `alter-photos`도 재시작합니다. 설정 변경은 관련 프로세스에 적용하며 모델·드라이버를 불필요하게 재설치하지 않습니다. 녹화 중에는 먼저 정상 종료합니다.

`Start-Alter.desktop` or `./start.sh` starts enabled services and checks readiness; `--no-browser` skips opening Chromium. Optional, unconfigured integrations are skipped. Existing OAuth refresh credentials can be reused, but revoked permissions require browser login. The desktop **Open Alter dashboard** link opens `http://127.0.0.1:11977/panel` without restarting servers.

`Start-Alter.desktop`은 활성화된 서비스를 준비하고 상태를 확인합니다. 선택 기능을 설정하지 않았으면 건너뜁니다. 바탕화면의 화면 열기는 서버를 재시작하지 않습니다. 상태는 비공개 `data/startup-status.json`, 로그는 `journalctl -u alter-recovery -b`에 있습니다.

File/photo queues persist in SQLite. Startup does not delete indexes or force complete reclassification. UUID plus volume-relative paths survive mount-path changes; a reformatted volume has a new UUID. Full database diagnostics are explicit (`PYTHONPATH=src .venv/bin/python scripts/recover.py --check-database`), not a boot-time scan of every media row.

파일·사진 DB와 작업 위치를 보존하며 재부팅 때문에 전체 재색인하지 않습니다. 손상된 파일시스템이나 DB를 자동 초기화하지 않습니다. 정상 부팅·화면·SMB·카메라는 각각 검증해야 합니다.

When a registered drive or folder is unavailable, indexing shows **Waiting for drive** and checks again every ten seconds while idle. It resumes the saved queue after reconnection and retains completed extraction and classification. Offline photo roots do not consume per-photo classification retries. Folder status checks the folder itself as well as its volume. A renamed folder requires an updated registration; a different drive at the old mount path is never substituted.

Boot recovery waits up to thirty seconds for registered volumes to appear. If desktop automount wins a mount race, recovery checks the current UUID/mount and uses that connection. It does not unmount a working volume. Earlier-boot journal history depends on the OS logging configuration.

등록 드라이브·폴더가 준비되지 않으면 **드라이브 연결 대기**로 표시하고, 유휴 상태에서는 10초마다 확인해 저장된 작업 위치에서 재개합니다. 완료한 추출·사진 분류는 유지하며, 오프라인 사진 폴더 때문에 개별 사진의 재시도 횟수를 소모하지 않습니다. 폴더 상태는 볼륨 연결뿐 아니라 해당 폴더의 존재도 확인합니다. 폴더 이름을 바꿨다면 등록을 수정해야 하며, 이전 경로에 다른 드라이브가 연결되어도 대체 사용하지 않습니다.

부팅 복구는 등록 볼륨이 나타나기를 최대 30초 기다립니다. 데스크톱 자동 마운트와 겹치면 현재 UUID·마운트 상태를 다시 확인해 이미 정상 연결된 볼륨을 사용합니다. 정상 연결을 해제하지 않습니다. 이전 부팅의 로그 보존 여부는 OS 설정에 따라 다릅니다.

Source deployment helper: `python scripts/deploy.py --host <pi-host> --user <pi-user> --fingerprint <verified-SHA256-base64>`. It uploads tracked sources, checks hashes, prompts for the SSH password and preserves ignored private state. Verify the host key out of band. It does not install dependencies or restart services.
