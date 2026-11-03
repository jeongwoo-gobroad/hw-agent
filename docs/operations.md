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

Source deployment helper: `python scripts/deploy.py --host <pi-host> --user <pi-user> --fingerprint <verified-SHA256-base64>`. It uploads tracked sources, checks hashes, prompts for the SSH password and preserves ignored private state. Verify the host key out of band. It does not install dependencies or restart services.
