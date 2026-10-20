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
| oauth_gateway.py | 콜백 함수/독립 콜백 앱. app.py가 같은 함수를 /oauth/*에 등록해 ngrok 대시보드와 경로 공유 |
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

## 외부 HTTPS 진입점

현재 alter-ngrok은127.0.0.1:8080으로 연결합니다. app.py에서 정확히 GET /oauth/start와 /oauth/callback만 인증 예외로 허용합니다. HTTPS 세션 쿠키는 Secure이며 내부망 HTTP 세션과 호스트가 분리됩니다. forwarded header 신뢰는 loopback으로 제한합니다. tests/live_external.py를 Windows에서 공개 URL 대상으로 실행하면 로그인·CSRF·파일 검색/문서 미리보기·실제 카메라 프레임·로그아웃 차단을 검사합니다. 카메라 테스트는 시작 전 꺼져 있었다면 종료 후 다시 끕니다.

## 스트리밍과 UI 구성

`generation.py`는 llama.cpp SSE를 읽고 부분 JSON에서 answer/query 문자열만 안전하게 추출합니다. `chat.respond`의 선택적 on_delta/cancelled 인자를 통해 전달하며 최종 JSON 검증·DB 저장은 기존 경로를 유지합니다. `POST /api/sessions/{id}/messages/stream`은 status/delta/result/error 이벤트와 heartbeat를 반환합니다. delta.text는 누적 문자열이며 이어 붙이지 않고 교체합니다. 기존 messages POST는 호환성을 위해 유지합니다. 인증·CSRF는 두 경로 모두 적용됩니다. 연결 종료 시 취소를 전달하지만 모델 prefill 중에는 다음 청크까지 취소가 지연될 수 있습니다. 취소된 부분 답변은 저장하지 않습니다.

`web/static/stream.js`는 fetch 스트림과 UTF-8 청크 경계를 처리합니다. `theme.js`는 초기 시스템 설정 또는 localStorage 선택을 적용하고 라이트/다크 전환을 담당합니다. 색상은 style.css 변수로 관리합니다. app.js는 활성 대화, 생성 중 입력 잠금, 빈 상태, 파일 페이지 누적 로드, 카메라 상태별 버튼과 폴더 선택을 관리합니다. storage.devices는 파티션에 부모 모델명을 상속하여 드라이브 식별을 돕습니다.

검증: tests/test_generation.py는 부분 문자열·다중 이벤트·취소를 검사합니다. tests/live_stream.py는 공개 URL에서 첫 delta와 완료 시각, 실제 로컬 모델 및 영구 저장을 검사합니다.

## 터치 패널·음성 컴포넌트

`web/static/panel.js`와 panel.css는 /panel에서만 활성화합니다. 대시보드의 인증·스마트홈·대화 API를 그대로 사용하며 큰 하단 메뉴, 키보드, 음성 수집을 제공합니다. simple-keyboard 3.8.196 / Hangul.js 0.2.6은 static/vendor에 라이선스와 함께 포함합니다. 한글 조합은 Hangul.disassemble/assemble을 사용합니다.

`voice.py`는 whisper.cpp CLI를 격리된 임시 폴더에서 실행합니다. GET /api/voice는 준비 상태, POST /api/voice/transcribe는 {audio: base64}를 받고 {text, language, silent}를 반환합니다. 인증/CSRF 필수, 해당 경로만 요청 본문 한도를 2,000,100바이트로 확장합니다. 디코딩 후 1.5MB, ffmpeg15초/mono16kHz, 변환20초/추론90초 제한, 단일 요청 lock, 무음 RMS 필터를 적용합니다. 입력과 텍스트를 로그로 남기지 않습니다. WHISPER_BINARY/WHISPER_MODEL로 경로를 재정의할 수 있습니다. 모델/바이너리는 tools와 models에 두며 git에 넣지 않습니다.

브라우저 MediaRecorder로 한 번 최대12초, 호출 대기는6초씩 녹음합니다. STT는 전부 Pi에서 수행합니다. 호출어 검출은 한국어 전사 문자열에서 ‘얼터’ 변형을 확인하는 방식이며 전용 wake 모델은 아닙니다. 마이크가 없는 Pi는 버튼 오류 안내와 음성 파일 입력을 제공합니다. 실제 마이크 시험과 합성 파일 시험을 구분하세요.

`static/icons.js`는 메뉴/동작 이름을 Lucide SVG에 매핑합니다. 동적으로 추가된 검색·기기·대화 버튼에도 적용하며 키보드 문자 키는 제외합니다. MutationObserver 작업 중 관찰을 끊어 자기 변경에 의한 반복을 방지합니다. SVG는 aria-hidden/currentColor이며 기존 텍스트 라벨이 접근성 이름입니다. 라이브러리 버전·라이선스는 vendor/README.md에 기록합니다. /panel 비인증 리디렉션은 /login?next=/panel, 로그인 스크립트는 허용된 /panel 값만 복귀 경로로 사용합니다.

## 시작·부팅 복구

최상위 start.sh는 서비스가 active/activating/reloading이면 그대로 두고 중지된 서비스만 sudo로 시작합니다. 새로운 무암호 sudo 권한은 부여하지 않습니다. Start-Alter.desktop은 Pi, Start-Alter.cmd는 Windows SSH 진입점입니다. scripts/install-startup.sh는 root-owned systemd unit을 설치·enable합니다.

scripts/recover.py는 데이터 초기화(db.init)를 호출하지 않습니다. flock으로 부팅/수동 복구 중복을 막고, 웹/모델 health를 기다린 뒤 DB quick_check와 등록된 UUID만 마운트합니다. 기존 제한된 alter-disk helper를 재사용하고 임의 디스크는 건드리지 않습니다. UDisks가 먼저 다른 경로로 마운트하면 해당 경로를 사용하고 SMB 경로를 복원합니다. ngrok 로컬 터널 API와 공개 health를 모두 확인하며 저장된 토큰은 smartthings.devices/access_token 경로로 필요할 때 갱신합니다. 토큰은 출력하지 않습니다.

종료0=성공,1=일시적/설정 오류,2=SmartThings 재로그인 필요. alter-recovery.service는 실패1을60초 후 재시도하며2는 자동 재시도하지 않습니다. 결과 JSON은 임시 파일+replace로 갱신됩니다. 핵심 서비스의 StartLimitIntervalSec=0은 장기 네트워크 장애 뒤에도 재시도가 정지되지 않게 합니다. 재시도 간격은 기존 RestartSec를 따릅니다. 복구는 원본 삭제/포맷/자격증명 교체를 수행하지 않습니다.

## 볼륨 ID와 디스플레이 절전

roots.relative_path와 UNIQUE(uuid,relative_path)가 등록의 영구 식별자입니다. path/mount는 현재 위치 캐시입니다. db.init에서 기존 스키마를 트랜잭션으로 옮기며 root ID와 files의 ID/root/상대 키를 보존합니다. 기존 중복 등록은 자동 삭제하지 않고 마이그레이션 오류로 중지합니다. 운영 DB 백업을 먼저 생성하세요. storage.device_for_uuid는 복제 UUID의 모호한 연결을 거부합니다. index scan은 오프라인 root를 건너뛰되 기존 색인을 보존하고 다른 root를 계속 처리합니다. 일부 root가 누락되면 전체 재색인 완료 시각을 갱신하지 않습니다.

사용자 서비스 deploy/alter-display.service는 swayidle timeout300/resume으로 scripts/display_brightness.py를 호출합니다. 고정 대상은 실제 확인된 /sys/class/backlight/panel_backlight@1입니다. dim은 최초 현재 밝기를 저장하고1로 설정, restore는 저장값을1..max 범위로 복원합니다. flock과 atomic replace로 중복 dim과 상태 파일 경합을 방지합니다. 서비스 중단 시에도 원래 밝기를 복원합니다. 사용자 default.target enable 및 XDG autostart로 재로그인 후 실행합니다. 새로운 sudoers/그룹 권한은 만들지 않습니다. 화면 공유 픽셀은 백라이트 밝기를 반영하지 않으므로 sysfs 실제값도 검증해야 합니다.

서버 요청 처리와 화면 활동은 독립적입니다. API/웹소켓/모델 토큰/색인/카메라/SmartThings 이벤트에서 밝기 복원이나 idle reset을 호출하지 않습니다. PC의 일반 대시보드 사용도 제외하며, Pi Wayland seat로 전달되는 터치·마우스·키보드(화면 공유 입력 포함)만 입력 활동입니다.
