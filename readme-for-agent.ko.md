# 개발 구조 안내

[English](readme-for-agent.md) · [한국어](readme-for-agent.ko.md)

README와 [설치 안내](docs/setup.ko.md)부터 읽습니다. 단일 worker FastAPI, 별도 사진 worker, 선택적인 llama.cpp/ngrok 서비스로 구성됩니다. 카메라 소유와 작업 조정 설계를 바꾸지 않고 Uvicorn worker를 늘리지 않습니다.

## 컴포넌트

아래 경로는 `src/hw_agent/` 기준입니다.

| 파일 | 책임 |
|---|---|
| `app.py`, `auth.py`, `login_security.py` | 라우트·인증·CSRF·내외부 세션·영속 실패 차단·CAPTCHA |
| `config.py`, `db.py` | 비공개 설정·SQLite WAL 스키마·트랜잭션 |
| `storage.py`, `file_browser.py` | UUID 식별·폴더 경계·독립 SMB·읽기 전용 트리 |
| `inventory.py`, `indexing.py`, `extract.py` | DB 발견 큐·체크포인트·해시/stat 재사용·FTS5/BM25/TF-IDF·제한된 문서 추출 |
| `preview.py` | 인증된 미리보기·HEIF·FFmpeg 프록시 캐시 |
| `photos.py`, `photo_worker.py`, `photo_models.py`, `photo_runtime.py`, `photo_search.py` | 사진 전용 폴더/API·재개 가능한 CLIP/YuNet/SFace 분류·작업 상태·대화 검색 |
| `chat.py`, `generation.py` | 대화 저장·구조화 라우팅·답변 스트리밍·결과 카드·실행 제안 |
| `smartthings.py`, `oauth.py`, `oauth_gateway.py`, `flows.py` | 기기 검증·토큰 암호화/갱신·공유 콜백·Flow 순차 실행 |
| `camera.py`, `motion.py`, `voice.py` | 카메라 단독 소유·녹화·방향·시간 기반 트리거·한국어 전사 |
| `resources.py`, `gpu_metrics.py`, `progress.py` | 시스템 계측·V3D 활동 차이·진행률/ETA |
| `i18n.py`, `locales/`, `web/static/locales/` | 요청별 gettext 및 i18next 카탈로그 |
| `web/` | 데스크톱/패널 HTML·JavaScript·CSS·로컬 라이브러리 |

`deploy/`는 설치 템플릿입니다. `scripts/render-deployment.py`가 계정·경로·내부망을 검증해 비공개 `data/deploy/`에 생성하고 설치기가 이를 사용합니다. `configure.py`는 한/영 설정 도우미입니다. Windows 실행기는 계정·호스트를 입력받으며 비밀번호를 저장하지 않습니다. `hardware/enclosure/`의 CAD 의존성은 Pi 런타임과 분리합니다.

## 유지해야 할 경계

- 접근 시 현재 UUID·등록 폴더·제외 정책을 재검증합니다. 검색 결과와 모델 출력은 접근 권한 자체가 아닙니다. 오프라인 메타데이터를 남겨도 원본 접근은 차단합니다.
- 항목 완료와 검색 결과를 함께 커밋합니다. 부팅 시 작업 DB를 비우지 않습니다. 알고리즘 결과 계약이 달라질 때 추출기/모델 버전을 올리고 동일 해시 결과를 재사용합니다.
- 파일 색인·사진 폴더·SMB는 별개입니다. 웹은 일반 계정, 제한된 저장장치 helper만 root 권한을 사용합니다.
- `.env`, DB, 대화, 쿠키, 토큰, 실제 배포 주소, 개인 원본을 소스·로그·캡처에 포함하지 않습니다. 암호화 OAuth 복호화를 위해 `SESSION_SECRET`을 보존합니다.
- OAuth 갱신은 프로세스 공유 잠금을 사용합니다. 콜백 전용 프로세스에서 `db.init()`을 호출하면 다른 프로세스의 실행 중 Flow 상태를 바꿀 수 있으므로 호출하지 않습니다.
- 대화가 제안한 물리 동작은 확인 후 서버에서 다시 검증합니다. 응답이 모호한 실패에서는 자동 재실행하지 않습니다.
- 화면 유휴 타이머에는 실제 로컬/원격 데스크톱 입력만 반영합니다. 카메라 방향은 미리보기·인식·녹화에 공통 적용하며 녹화 중 변경은 거부합니다.

## 한/영 공용 구현

브라우저 선택은 localStorage의 `alter-language`, API 언어는 `alter_language` 쿠키로 전달됩니다. gettext는 요청별 ContextVar를 사용하고 SSE 생성 스레드에 문맥을 복사합니다. 영어 사진 주제·날짜 질의와 영어 답변 지시를 지원합니다. 음성은 현재 한국어이며 개인 이름·파일명·기존 대화는 자동 번역하지 않습니다.

UI 문구는 `web/static/locales/en.json`과 `ko.json`, 서버 문구는 `translate()`와 `locales/en/LC_MESSAGES/alter.po`를 수정합니다. 보간 변수를 보존하고 개발 의존성 설치 후 `scripts/build-locales.py`로 `locales.js`와 `.mo`를 다시 만들어 커밋합니다. 런타임에는 번역 컴파일러나 CDN이 필요하지 않습니다. DOM 전체를 무차별 번역하지 않습니다.

## 변경 검증

`PYTHONPATH=src`, 임시 `DATA_DIR`, 시험용 계정·세션 환경변수를 지정하고 각 테스트를 별도 프로세스로 실행합니다. 모듈 초기 상태가 있어 모두 한 프로세스로 묶으면 같은 조건이 아닙니다. 번역·인증·사진·파일·복구 변경에는 `test_i18n`, `test_oauth`, `test_login_security`, `test_generation`, `test_explorer_camera`, `test_photos`, `test_recovery`, `test_boundaries`를 확인합니다. 작업 재개 변경에는 `test_resumable`, `test_process_resume`도 실행합니다.

JavaScript 구문과 카탈로그·렌더링된 서비스 설정을 검사하고 실제 브라우저에서 변경 동선을 확인합니다. 배포 시 코드 백업·비공개 상태를 보존하며 필요한 서비스만 재시작합니다. 입출력·알고리즘 변경에는 관련 문서를 함께 갱신합니다. 합성 시험을 새 OS 전체 설치나 실제 환경 인식률 검증으로 표현하지 않습니다. `live_*.py`는 실기기 효과가 있어 시험 대상을 별도로 정해야 합니다.

Windows NTFS 도구는 [별도 유지보수 기능](docs/ntfs-maintenance.md)이며 정상 시작이나 공개 작업에서 실행하지 않습니다.
