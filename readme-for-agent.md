# Contributor map

[English](readme-for-agent.md) · [한국어](readme-for-agent.ko.md)

Start with the README and [setup guide](docs/setup.md). The application is a single-worker FastAPI server, a separate photo worker, and optional llama.cpp/ngrok services. Do not add Uvicorn workers without redesigning camera ownership and job coordination.

## Components

| Path under `src/hw_agent/` | Responsibility |
|---|---|
| `app.py`, `auth.py`, `login_security.py` | Routes, request security, sessions/CSRF, scoped entry points, persistent login policy and challenges |
| `config.py`, `db.py` | Private configuration, SQLite WAL schema and transactions |
| `storage.py`, `file_browser.py` | Filesystem UUID identity, registered-root boundaries, independent SMB and read-only file tree |
| `inventory.py`, `indexing.py`, `extract.py` | Durable discovery queue/checkpoints, SHA-256/stat reuse, FTS5/BM25/TF-IDF and bounded document extraction |
| `preview.py` | Authenticated image/document/video previews, HEIF and FFmpeg proxy caches |
| `photos.py`, `photo_worker.py`, `photo_models.py`, `photo_runtime.py`, `photo_search.py` | Independent photo roots/API, resumable classification, CLIP/YuNet/SFace, worker state and chat filters |
| `chat.py`, `generation.py` | Conversation persistence, structured model routing, incremental answer decoding, verified result cards and proposed actions |
| `smartthings.py`, `oauth.py`, `oauth_gateway.py`, `flows.py` | Capability validation, encrypted token lifecycle, shared callback functions and sequential Flow execution |
| `camera.py`, `motion.py`, `voice.py` | Single camera owner, recording/orientation, temporal detection rules and Korean transcription |
| `resources.py`, `gpu_metrics.py`, `progress.py` | Host telemetry, V3D activity deltas and progress/ETA |
| `i18n.py`, `locales/`, `web/static/locales/` | Request-scoped gettext messages and i18next UI catalogs |
| `web/` | Desktop/panel HTML, plain JavaScript/CSS and local vendor libraries |

`deploy/` contains templates, not directly installable account-specific files. `scripts/render-deployment.py` validates and renders them into ignored `data/deploy/`. `scripts/configure.py` provides EN/KO setup without embedding an installation identity. Install scripts use the rendered helpers/units. The Windows launcher prompts for the Pi account/host and stores no password.

`hardware/enclosure/` contains reproducible CAD source, STL/STEP and VTK previews. Python CAD requirements are separate from the Pi runtime. `docs/` contains user guides, technical notes and public assets. `tests/` contains disposable-data unit/integration checks; `live_*.py` scripts have real-device effects and need their own test targets.

## Invariants

- Resolve a requested file against the registered UUID/root and exclusion policy at access time. Search hits or model output are not access grants. Offline metadata can persist while original downloads remain blocked.
- Commit entry completion and derived search results together. On restart, consume durable jobs instead of deleting them. Bump extractor/model versions only when the output contract changes; reuse unchanged hashes/results.
- Keep file, photo and SMB registrations independent. Storage helpers are root-owned, narrow sudo entry points; the web server runs as the normal account.
- Keep `.env`, databases, conversations, auth cookies, tokens, deployment addresses and original private media out of source/logs/screenshots. Preserve `SESSION_SECRET` for encrypted OAuth tokens.
- OAuth refresh uses a shared file lock. The callback-only process does not call `db.init()` because it would mark another process's active Flows interrupted.
- Require confirmation for chat-proposed physical actions. Validate capabilities/arguments again on the server. Do not automatically retry a physical command after an ambiguous failure.
- Local/remote-desktop input can reset display idle; ordinary server requests cannot. Camera orientation is shared by preview, detection and recording; changing it during recording is rejected.

## English and Korean

One implementation serves both languages. UI selection is saved as `alter-language` in the browser and an `alter_language` cookie for API responses. GNU gettext uses a request-local ContextVar; SSE generation copies the request context into its worker thread. English photo topic/date queries and English answer instructions are supported. Korean voice remains explicitly Korean; user-authored names/messages are never machine-translated on language change.

Add explicit UI strings to both `web/static/locales/en.json` and `ko.json`, preserving interpolation variables. Backend messages use `translate()` and `locales/en/LC_MESSAGES/alter.po`. Run:

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/build-locales.py
```

Commit generated `locales.js` and `.mo` files so no compiler/CDN is needed at runtime. Do not apply blanket DOM translation to filenames, captions or device names. Browser locale controls dates/numbers through the selected app language. Vendored libraries retain adjacent licenses.

## Validation and release

Run tests in separate processes with `PYTHONPATH=src`, disposable `DATA_DIR`, and test dashboard/session environment variables. Some tests initialize module-level state, so combining every test into one Python process is not equivalent. Relevant suites: `test_i18n.py`, `test_oauth.py`, `test_login_security.py`, `test_generation.py`, `test_explorer_camera.py`, `test_photos.py`, `test_recovery.py`, `test_boundaries.py`; resumability changes also require `test_resumable.py` and `test_process_resume.py`.

Check JavaScript syntax, compile translation catalogs, validate rendered shell/systemd/nginx configuration, then test the changed flow in a real browser. Preserve a code backup and private state on deployment; restart only affected services. Update user and component docs when an input/output contract or algorithm changes. Publish only inspected, anonymized assets and reviewed tracked files. A successful test fixture is not a fresh-install, device-accuracy or long-duration performance claim.

Historical NTFS tools are separate Windows maintenance utilities, described in [their guide](docs/ntfs-maintenance.md). They must not run as part of normal startup or publication.

## Storage availability

`storage.registered_path` resolves file and photo roots from a fresh UUID listing and checks exclusions before filesystem access. `StorageUnavailable` is a resumable 409, separate from boundary/permission errors. Root-list APIs include `online`, based on both the volume and the folder. Index status adds `waiting_roots` and `waiting_for_storage`; idle workers recheck after ten seconds. Discovery validates connectivity before acknowledging a missing directory. A disconnected item remains pending instead of being counted as a failed file. Photo classification skips offline roots without increasing per-photo attempts. Recovery rechecks mount state after the helper returns, including when another automounter won the race. Keep those behaviors covered by `test_storage_resume.py`, `test_recovery.py`, and the existing resumability suites.
