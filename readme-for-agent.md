# Alter 유지보수 안내

## 먼저 읽을 파일

README.md는 실제 제공 기능과 사용자 동선, docs/acceptance.md는 검증 범위, docs/operations.md는 배포/복구, docs/oauth.md는 OAuth 운영입니다. 과거 계획을 구현 사실로 해석하지 마세요. .env·data·모델·사용자 파일은 읽기/로그/커밋 범위를 최소화합니다. 사용자 비밀을 출력하지 않습니다.

## 디렉터리 지도

| 파일/폴더 | 책임과 변경 시 함께 확인할 대상 |
|---|---|
| src/hw_agent/app.py | FastAPI 라우트, Pydantic 입력 모델, 인증/CSRF/Origin, lifespan; UI/API 테스트와 문서 |
| config.py | .env와 private data 경로, 모델 HTTP 인증; .env.example/운영 문서 |
| auth.py | 로그인 속도 제한, 서버 세션/CSRF, 자격증명 fingerprint; 경계 테스트 |
| db.py | SQLite WAL 스키마/트랜잭션; 재시작 시 실행 중 Flow를 interrupted로 전환 |
| storage.py | 외장 파티션/폴더 경계, UUID 기준 루트 재연결, SMB 복원; alter-disk/alter-smb |
| indexing.py | 60초 대조, 72시간 재생성, staging 원자 교체, FTS5 BM25/TF-IDF; 추출기 버전 |
| extract.py | 자원 제한된 별도 프로세스 문서 추출; XML/ZIP 제한과 HWP subprocess |
| preview.py | HEIF/Pillow와 FFmpeg 프록시, 캐시 한도/만료; 미디어 API/UI |
| chat.py | 세션/히스토리, JSON intent, 검색 카드/확인 제안, 명시 날짜·확장자 규칙 |
| smartthings.py | OAuth/PAT 토큰 선택, REST 오류, capability/인수 검증 |
| oauth.py | ticket/state/cookie 바인딩, 세션 검증, 암호화 저장, 파일 잠금과 갱신 |
| oauth_gateway.py | 공개 HTTPS 콜백만; dashboard API를 이 앱에 추가하지 않음 |
| flows.py | 저장된 단계 순차 실행, 중복 요청/쿨다운, 실패 시 중단/기록 |
| camera.py | 단일 Picamera2 소유, MJPEG, FFmpeg 분할 녹화, MediaPipe 제스처 |
| web/ | HTML, vanilla JS, CSS, 공식 로고. 프런트엔드 빌드 도구 없음 |
| deploy/ | systemd와 root 소유의 제한된 권한 helper, Pi 화면 autostart |
| scripts/ | 설치, 추적 파일 배포, SQLite backup, 모델 비교 |
| tests/ | 순수 경계/OAuth 시험과 실제 USB/카메라 통합 시험 |

## 실행·데이터 흐름

웹은 단일 Uvicorn worker입니다. lifespan에서 DB 초기화, 색인 스레드와 OAuth 갱신 스레드를 시작합니다. 여러 worker는 카메라 소유/색인 동시성 전제를 깨므로 임의 증설하지 마세요. `/panel`은 같은 인증/백엔드를 사용하는 화면 모드입니다.

파일 접근은 등록 root의 현재 UUID 마운트를 확인하고 resolve한 경로가 그 안에 있는지 검증합니다. 색인 경로/LLM 출력은 파일 접근 허가 자체가 아닙니다. 오프라인 장치 메타데이터는 보존하지만 다운로드/미리보기는 차단합니다. 재연결 때 UUID와 상대경로로 복원합니다. 마운트 지점 변경은 SMB 경로에도 반영합니다.

추출기는 별도 Python subprocess로 실행하며 입력/압축 해제/메모리/시간을 제한합니다. staging 테이블의 완성된 루트만 활성 색인과 FTS에 반영합니다. 기존 파일 원문을 삭제하는 로직을 색인 보존기간과 혼동하지 마세요. 추출 알고리즘 변경 시 EXTRACTOR_VERSION을 올려 기존 내용도 재추출합니다.

LLM은 별도 llama-server 프로세스입니다. 대화는 전체 저장하지만 현재 추론에는 최근 두 메시지(각 250자)와 최대 1200자 요청을 전달합니다. 모델별 2048 context 제약을 고려한 제한이며 장기 기억 요약 기능은 없습니다. 모델 실패 시 keyword_fallback을 명시합니다. 파일/기기/Flow의 실제 실행 권한을 모델에 맡기지 않고, UI에서 확인 후 API가 재검증합니다.

OAuth callback 서버는 db.init을 호출하지 않습니다. 그렇지 않으면 독립 프로세스 시작 때 웹에서 실행 중인 Flow가 interrupted로 바뀝니다. 일회용 refresh token 때문에 웹/콜백 양쪽은 동일 파일 flock을 사용합니다. SESSION_SECRET 교체는 기존 로그인과 암호화 토큰에 영향을 줍니다. 토큰은 복호화한 값을 API 응답/로그에 넣지 마세요.

Flow는 실행 결과를 저장하고 실패 단계에서 멈춥니다. 물리 동작은 실패 응답이 있어도 이미 전달됐을 수 있으므로 자동 재시도하지 않습니다. 새 실행 요청 ID를 발급하면 새로운 물리 동작입니다. 스마트홈 실기기 시험은 사용자가 지정한 기기에 한정합니다.

## 변경 절차

1. `git status`와 관련 컴포넌트 문서 확인. 사용자 변경을 덮어쓰지 않습니다.
2. 직접 의존성만 requirements.txt에 추가. 간접 패키지는 검증 환경 lock에 기록.
3. 코드 I/O/동작 변경 시 README·운영 가이드·해당 테스트 함께 갱신.
4. Pi에서 boundary/OAuth 테스트, 영향을 받은 실제 API 시험. UI 변경은 Chrome 확인.
5. secrets/실제 사용자 파일이 없는지 확인 후 commit/push. 배포는 tracked source만 전송하고 .env/data/models 보존.
6. 서비스 health, 모델 health, Git 원격 HEAD, 실제 배포 파일 hash 확인.

현재 root helper는 jeongwoo UID/GID1000 전용입니다. 외장 vfat에는 utf8=1 옵션이 필요합니다. Windows 편집 뒤 helper/shebang 파일이 CRLF가 되지 않도록 .gitattributes와 배포 bytes를 확인하세요. `sudo` 전체 권한을 웹에 부여하지 않습니다.
