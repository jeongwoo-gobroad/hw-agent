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

## Media failures and startup logs / 미디어 오류와 시작 로그

File read and document-extraction failures have a separate SQLite `file_retries` queue. Attempts and deadlines survive restarts and new scan generations. Retries start after five minutes, double to a maximum one-day interval, and continue until recovery or removal. They run between discovery/processing batches and while idle, without waiting for a whole drive scan. These are earliest retry times: a long current operation can delay them. A disconnected root does not consume attempts. Changed file metadata bypasses the old delay on discovery; successful recovery removes the queue entry. Unsupported formats, size limits, partial extraction and policy-denied paths are not retryable failures.

파일 읽기·문서 추출 오류는 별도 SQLite `file_retries` 큐에 기록합니다. 재시작과 새 검사에서도 횟수·시각을 보존하고 5분부터 최대 하루 간격으로 재시도합니다. 전체 드라이브 검사가 끝나기 전에 배치 사이와 유휴 시간에 처리하며, 큰 파일 처리 중이면 예정 시각보다 늦어질 수 있습니다. 연결 대기는 횟수를 소모하지 않습니다. 변경된 파일은 다음 발견 시 기존 대기를 건너뛰고, 성공하면 큐에서 제거합니다. 미지원 형식·크기 제한·부분 추출·접근 정책 차단은 재시도 대상이 아닙니다.

An unchanged hash never makes a failed extraction reusable. The last successful text stays searchable until recovery; a newly failed document still has searchable metadata. The dashboard reports pending retries separately from completed work. Historical aggregate errors without item records cannot be reconstructed; legacy failed extraction rows are repaired when encountered by the next normal scan. No full index reset is required. See [queue and status details](indexing-security.md).

같은 해시여도 실패한 추출 결과를 재사용하지 않습니다. 복구 전까지 마지막 정상 텍스트를 보존하며, 처음 실패한 문서는 이름 등 메타데이터로 검색할 수 있습니다. 대시보드는 재시도 대기를 별도로 표시합니다. 과거에 합계만 남은 오류는 항목별로 복원할 수 없으며, 기존 추출 실패 행은 다음 일반 검사에서 처리합니다. 전체 색인을 초기화할 필요는 없습니다.

Video classification samples the video stream's duration, skips empty or failed individual seeks, and tries the beginning if every seek fails. A clip with no decodable frame remains a failed item. Valid samples from a short clip can still classify its paired Live Photo. Failed media retries use a five-minute exponential delay capped at one day; success clears the counter. Disconnected storage does not consume retries. Existing successful classifications and model versions are preserved.

영상 분류는 영상 스트림 길이를 기준으로 프레임을 추출합니다. 일부 구간을 읽지 못해도 정상 프레임을 사용하며, 모든 구간이 실패하면 시작 부분을 한 번 더 확인합니다. 읽을 수 있는 프레임이 전혀 없으면 실패 상태를 유지합니다. 반복 실패의 재시도 간격은 5분부터 늘어나 최대 하루가 되며, 성공하면 횟수를 초기화합니다. 연결이 끊긴 저장장치는 재시도 횟수를 소모하지 않습니다. 기존 성공 분류와 모델 버전은 유지합니다.

Still images are reduced to fit 1920 × 1920 before EXIF rotation. The source pixel buffer is closed before model inference, avoiding a full-resolution copy being retained alongside the models. This uses Pillow's `thumbnail`, `exif_transpose(in_place=True)` and `close`; it does not modify originals or raise the worker's memory limit.

사진은 1920 × 1920 안에 들어오도록 먼저 축소한 뒤 EXIF 방향을 적용합니다. 모델 추론 전에 원본 픽셀 버퍼를 닫아 고해상도 복사본과 모델이 동시에 메모리를 차지하지 않도록 합니다. Pillow의 축소·방향 보정·버퍼 해제 기능을 사용하며 원본이나 작업자의 메모리 한도를 바꾸지 않습니다.

After committing each classification, the worker checks its resident memory. At 850MiB it ends that batch and lets the supervisor start a fresh process for pending items. This releases buffers retained by native libraries while preserving the completed result, scan generation and queue; it is not a full rescan. The 1200MiB service limit also includes the supervisor and media subprocesses, so a single unusually large item can still reach that limit and be deferred for retry.

각 항목을 저장한 뒤 작업자의 실제 상주 메모리를 확인합니다. 850MiB 이상이면 해당 배치를 마치고 다음 프로세스에서 대기 항목을 이어서 처리해 네이티브 라이브러리의 잔류 버퍼를 회수합니다. 완료 결과·색인 세대·대기열을 유지하며 전체 재색인을 하지 않습니다. 서비스의 1200MiB 한도에는 관리 프로세스와 미디어 처리도 포함되므로, 단일 항목이 지나치게 크면 여전히 한도에 도달해 재시도 대상으로 남을 수 있습니다.

The display idle service waits up to ninety seconds for the Wayland socket before starting its five-minute idle timer. Ordinary server traffic cannot reset that timer. This startup check does not send pointer, keyboard or touch events.

화면 유휴 서비스는 Wayland 연결을 최대 90초 기다린 뒤 5분 유휴 타이머를 시작합니다. 서버 요청은 타이머를 초기화하지 않으며, 준비 확인 과정도 마우스·키보드·터치 입력을 보내지 않습니다.

Inspect `journalctl -u alter -u alter-photos -b` for current-boot worker warnings. New item-failure warnings contain internal IDs and exception classes, without original paths or exception messages. Keep raw system logs private: other OS components may record installation details.

현재 부팅의 작업 오류는 `journalctl -u alter -u alter-photos -b`에서 확인합니다. 새 항목별 오류 기록에는 내부 ID와 예외 종류만 남깁니다. 다른 OS 구성 요소는 설치 정보를 기록할 수 있으므로 원본 시스템 로그를 공개하지 않습니다.

On systems using volatile journals, earlier boots cannot be inspected after a reboot. An administrator can opt into bounded persistent logging with `/etc/systemd/journald.conf.d/99-alter-history.conf`:

휘발성 로그를 사용하는 OS에서는 재부팅 전 기록을 확인할 수 없습니다. 아래 설정으로 디스크 사용량을 제한해 이후 로그를 보존할 수 있습니다. 이미 사라진 로그가 복구되지는 않습니다.

```ini
[Journal]
Storage=persistent
SystemMaxUse=128M
SystemKeepFree=1G
RuntimeMaxUse=32M
MaxRetentionSec=14day
```

After applying it, restart `systemd-journald` and run `journalctl --flush`. Check for journal files under `/var/log/journal`; configuration alone is not proof that logs were persisted. See [journald settings](https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html) and [journal flushing](https://www.freedesktop.org/software/systemd/man/latest/journalctl.html).

적용 후 `systemd-journald`를 재시작하고 `journalctl --flush`를 실행합니다. `/var/log/journal`에 실제 기록 파일이 생성되는지 확인해야 합니다.
