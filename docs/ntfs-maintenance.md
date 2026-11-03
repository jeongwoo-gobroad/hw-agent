# NTFS maintenance tools

These are separate Windows maintenance utilities, not part of normal Alter startup. They support controlled NTFS decompression/progress inspection and a temporary read-only browser while a compatible conversion supervisor owns the volume. They do not make simultaneous Windows/Linux filesystem mounting safe.

## Boundaries

Use one filesystem owner at a time. For remote block access, unmount on the Pi before Windows takes ownership; after native conversion, flush/offline/disconnect on Windows and verify no block sessions remain before remounting on the Pi. Do not infer that a native conversion is stuck solely from an unchanged per-file JSON timestamp. A large stream can take a long time. Keep individual paths and work databases private.

NTFS compression and SMB transport compression are different. Check mount driver, permissions, free space and kernel errors first. The observed Linux compressed-read stalls do not prove all compressed files are corrupt. Use synthetic files for content verification. Do not automatically restore quarantined files or weaken endpoint security.

## Components

| Component | Purpose |
|---|---|
| `scripts/ntfs_state.py` | Atomic progress JSON replacement, bounded retry on transient Windows reader locks |
| `scripts/ntfs_progress_snapshot.py` | Read-only SQLite counts and byte totals without per-file paths |
| `scripts/ntfs_progress_eta.py` | Recent completed-byte throughput and current-stage ETA range; retries/recovery are excluded |
| `scripts/watch-ntfs-progress.ps1` | PowerShell progress/ETA view using explicit private state directory and disk identity |
| `scripts/read-ntfs-files.py`, `open-ntfs-reader.ps1` | Loopback-only temporary viewer, private configuration and session token |
| `scripts/ntfs_reader/` | Read-only catalog, Windows handle/identity checks, authenticated range serving and UI |

The reader exposes completed/uncompressed entries only, rejects unsafe paths/reparse points/hardlinks, and rechecks the maintenance gate and file identity during reads. It does not run bulk thumbnailing or content search. A stale supervisor heartbeat, ownership transition or lifetime limit closes access. Preserve the same ownership rules even while a reader is open.

ETA is an estimate from committed progress, not combined disk read/write bandwidth. Interrupted, stale or inconsistent state resets/withholds ETA. Source contents and conversion databases remain unchanged by the progress viewer. The `test_ntfs_*` suites use synthetic data to check these contracts.

## 한국어 요약

이 도구는 정상 부팅과 분리된 Windows 유지보수용입니다. NTFS 볼륨은 한 OS만 소유해야 하며 Pi 마운트 해제 → Windows 처리 → 정상 분리와 연결 부재 확인 → Pi 재마운트 순서를 지킵니다. 파일 하나의 진행 JSON이 오래 그대로여도 네이티브 처리가 멈췄다고 단정하지 않습니다.

진행률은 비공개 DB의 확정 상태를 읽고, ETA는 최근 완료 용량 증가율로 계산합니다. 임시 웹 창은 처리 완료 파일만 읽기 전용으로 제공하며 상태·파일 정체성을 계속 확인합니다. 개인 경로·내용·자격증명을 공개하지 않고 합성 파일로 동작을 검증합니다. 유지보수 도구를 설치·공개 작업에서 자동 실행하지 않습니다.
