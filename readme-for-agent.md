# Alter 유지보수 안내

## 먼저 읽을 파일

README.md는 실제 제공 기능과 사용자 동선, docs/acceptance.md는 검증 범위, docs/operations.md는 배포/복구, docs/oauth.md는 OAuth 운영입니다. 과거 계획을 구현 사실로 해석하지 마세요. .env·data·모델·사용자 파일은 읽기/로그/커밋 범위를 최소화합니다. 사용자 비밀을 출력하지 않습니다.

NTFS 압축/SMB 읽기 유지보수는 `docs/ntfs-maintenance.md`를 먼저 확인합니다. 합성 시험 결과와 운영 적용 상태를 구분하고, 저장 장치의 단독 소유와 정상 마운트 해제를 확인합니다.

운영 NTFS 변환은 현재 진행 중이며 공유 복구 후 검증이 남아 있습니다. 큰 파일의 네이티브 변환 중에는 파일별 진행 기록이 멈춰 보일 수 있습니다. 기존 관리자 세션과 로컬 작업 기록을 재사용하고, 새 작업이나 마운트를 중복 시작하지 않습니다. Windows 분리와 iSCSI 대상의 연결 부재를 모두 확인한 후에만 Pi 소유권을 복구합니다.

Windows 조회 화면은 `scripts/watch-ntfs-progress.ps1`, 집계는 `scripts/ntfs_progress_snapshot.py`입니다. 상태 폴더와 디스크 일련번호를 인자로 받고, SQLite를 읽기 전용으로 조회해 개별 경로 없이 처리 수·완료 용량을 표시합니다. `scripts/ntfs_progress_eta.py`는 최근 약 2시간의 완료 용량 증가율과 대기 용량으로 현재 변환 단계의 ETA 범위를 계산합니다. 왼쪽 ETA만 진행 중인 한 스트림 크기 이내에서 경과 시간을 추정 반영하고, 확정 진행률은 바꾸지 않습니다. 오류 재시도와 복구 시간은 제외합니다. `progress-eta-history.json`에는 실행 식별자·시간·집계 용량만 보존하며 원본 파일이나 변환 DB는 수정하지 않습니다. 재시작·기록 불일치·오래된 상태에서는 ETA를 초기화하거나 보류합니다. 디스크 속도는 별도 지표이며 읽기·쓰기를 합산해 ETA로 사용하지 않습니다. `tests/test_ntfs_eta.py`가 계산·재개·중단·개인정보 비노출을 검사합니다. `tests/test_ntfs_progress.py`는 미확정 DB 변경의 비노출과 경로 비노출, 없는 DB를 생성하지 않는 동작을 검사합니다.

`scripts/ntfs_state.py`는 유지보수 JSON을 원자적으로 갱신할 때 Windows의 일시적인 독자 잠금을 최대 10초 동안 재시도합니다. 영구 실패 시 기존 JSON을 보존하고 오류를 반환합니다. 변환 기록의 기준은 먼저 커밋된 SQLite이며 표시 파일의 갱신 실패를 처음부터 재변환하는 이유로 삼지 않습니다. `tests/test_ntfs_state.py`는 실제 Windows 읽기 핸들에 의한 교체 충돌과 지속적인 거부에서 기존 상태 보존을 검사합니다. 운영 중간 복구에서 NTFS-3G 마운트·11977 응답·SMB 합성 파일 읽기/쓰기를 확인했지만 전체 변환 및 최종 검증은 별개입니다.

유지보수 중 접근 거부는 첫 변환 후 Windows 기본 도구로 제한적으로 재시도하고, 보안 프로그램 차단은 별도 미해결 항목으로 남깁니다. 재시도·분리·복구는 기존 관리자 세션과 단독 마운트 원칙을 유지합니다. 보안 설정 변경이나 격리 파일 자동 복원은 수행하지 않습니다. 자세한 검증 범위는 `docs/ntfs-maintenance.md`를 확인합니다.

## 디렉터리 지도

| 파일/폴더 | 책임과 변경 시 함께 확인할 대상 |
|---|---|
| src/hw_agent/app.py | FastAPI 라우트, Pydantic 입력 모델, 인증/CSRF/Origin, lifespan; UI/API 테스트와 문서 |
| config.py | .env와 private data 경로, 모델 HTTP 인증; .env.example/운영 문서 |
| auth.py | 로그인 속도 제한, 서버 세션/CSRF, 자격증명 fingerprint; 경계 테스트 |
| db.py | SQLite WAL 스키마/트랜잭션; 재시작 시 실행 중 Flow를 interrupted로 전환 |
| storage.py | 외장 파티션/폴더 경계, UUID 기준 루트 재연결, SMB 복원; alter-disk/alter-smb |
| indexing.py | 10분 대조, SHA-256/정밀 stat 비교, 항목 단위 DB/FTS 커밋, FTS5 BM25/TF-IDF; 추출기 버전 |
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

추출기는 별도 Python subprocess로 실행하며 입력/압축 해제/메모리/시간을 제한합니다. scan_entries 완료 표시와 files/FTS 갱신을 한 트랜잭션으로 커밋합니다. 기존 staging은 최초 이관 시 캐시로 소비하며 시작 시 비우지 않습니다. 기존 파일 원문을 삭제하는 로직을 색인 보존기간과 혼동하지 마세요. 추출 알고리즘 변경 시 EXTRACTOR_VERSION을 올려 기존 내용도 재추출합니다.

LLM은 별도 llama-server 프로세스입니다. 대화는 전체 저장하지만 현재 추론에는 최근 두 메시지(각 250자)와 최대 1200자 요청을 전달합니다. 초기 2048 context 설정을 고려한 제한이며 장기 기억 요약 기능은 없습니다. 모델 실패 시 keyword_fallback을 명시합니다. 파일/기기/Flow의 실제 실행 권한을 모델에 맡기지 않고, UI에서 확인 후 API가 재검증합니다.

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

SMB/색인 선택 분리: app.js browse(path,target)는 index/share별 독립 컨테이너를 사용합니다. loadRoots는 SMB 폼을 변경하지 않습니다. roots 테이블은 검색 대상, state.shares는 공유 대상이며 API는 각각 독립입니다. recover.restore_storage는 roots와 shares의 UUID 합집합만 마운트합니다. 설치 시 wsdd2를 활성화하여 Windows WSD 검색을 지원합니다.

오프라인 해제: SMB remove는 이름 검증 후 설정 파일만 제거하며 external_path/lsblk를 호출하지 않습니다. DELETE shares의 path는 하위 호환용 선택 인자입니다. roots 삭제는 다른 색인 작업 때문에 차단하지 않습니다. scanner는 각 디렉터리 배치 및 항목 커밋 전에 root 존재를 확인하며, 저장/게시 검사는 BEGIN IMMEDIATE로 삭제와 직렬화합니다. 해당 root에 카메라 녹화 중이면 삭제를 차단합니다. EXCLUDED_DIRECTORY_NAMES는 casefold 폴더명 집합으로 resolve 및 os.walk 하강 전에 차단합니다. 배포 장비의 금지 이름은 private .env에서 관리하며 진단에서 해당 하위 경로를 순회하면 안 됩니다.


## 상시 감지 구조

- motion.py: MediaPipe GestureRecognizer/BlazeFace 모델을 한 번 로드하고 카메라 프레임 하나를 두 모델에 전달합니다. 두 모델을 메모리에 함께 유지하며 프레임 내 추론은 순차 실행해 CPU 경합을 줄입니다. PresenceGate가 여섯 감지 종류의 hold/release/cooldown/repeat 상태를 독립 관리합니다. 신뢰도 기준은0.7입니다. Frame timestamp는 monotonic, UI 기록은 wall clock입니다.
- camera.py: Picamera2를 단독 소유하며 640×480·10fps 촬영, 감지는 약0.3초 이상 간격입니다. 기존 제스처 API와 상시 감지는 같은 손동작 모델 인스턴스를 공유합니다. 상시 감지 활성 시 이전 제스처 실행은 비활성화합니다. 별도 카메라 프로세스를 추가하지 않습니다.
- GET/POST /api/motion: enabled, mappings(감지 키→Flow ID 또는 빈 문자열), rules(hold_seconds, release_seconds, repeat_seconds, repeat)를 관리합니다. 알 수 없는 감지 키, 시간 범위, 활성화 시 없는 Flow를 거부합니다. 인증·CSRF는 기존 미들웨어를 그대로 적용합니다.
- DB state.motion_config: 활성 여부·매핑·여섯 규칙을 보관합니다. lifespan에서 복원하며 모델/카메라 실패는 UI error로 노출합니다. 정상 프로세스 종료는 enabled 저장값을 바꾸지 않습니다.
- dispatch_lock: 감지 기원 Flow는 최대1개만 실행합니다. 겹치는 이벤트는 skipped_busy입니다. Flow 자체의 중복/쿨다운/기기 검증도 유지합니다. 영상·얼굴 임베딩·신원 데이터는 저장하지 않습니다.
- scripts/verify-motion-load.py: 실제 카메라의 두 모델과 llama.cpp 2048 generated tokens를 함께 실행하고 cgroup memory.events/PID/최대사용량/가용메모리를 data/motion-load-report.json에 기록합니다. 모델 출력 본문은 저장하지 않습니다. EOS 무시와4096문맥은 완료 토큰 수 확인용입니다. 일반 대화 출력 제한을 무조건2048로 늘리는 변경은 아닙니다.
- tests/test_motion.py, tests/live_motion.py, tests/vision_fixtures.py: 유지/재진입/반복/동시실행, 인증 API/실제 카메라, 공식 양성 표본과 음성 표본을 각각 검사합니다. 표본 성공은 실제 사용자의 여섯 동작 정확도 측정과 구분합니다.

repeat_seconds는 실행 시작 간격이 아니라 Flow 완료 후 최소 대기입니다. 비동기 run 종료 시 해당 gate.last_fire를 monotonic으로 갱신해 Flow 자체의3초 쿨다운보다 먼저 재시도하지 않습니다.

## 사진 보관함 컴포넌트

- `photos.py`: 독립 photo_roots UUID 등록·안전한 원본 해석·사진/앨범/사람 검색·수정 API. 일반 roots/SMB를 변경하지 않는다.
- `photo_worker.py`: 별도 systemd 프로세스의 10분 주기 파일 발견, ExifTool 촬영일·Live 연결, 증분 분류, 체크포인트 진행률. 작업 자식 종료로 모델 메모리 반환.
- `photo_models.py`: CLIP ONNX FP32 다중 주제 + YuNet/SFace 특징 추출. PC GPU 및 원격 추론 없음.
- `resources.py`: /proc CPU/RAM 차분과 지원되는 DRM GPU 카운터. 미지원값은 null.
- `web/static/photos.js`: 보관함/사람들/별도 폴더 메뉴·검색·미디어·수동 수정. 공통 status 5초 polling으로 진행률과 처리된 썸네일 갱신.
- `deploy/alter-photos.service`, `scripts/install-photo-models.py`: 독립 자원 제한과 리비전/SHA256 고정 모델 설치.
- 상세 DB·API·제한·검증은 [docs/photos.md](docs/photos.md). 모델/문서 변경 시 함께 갱신한다. 사진 DB/얼굴 특징/이름/시험 이미지/원본은 Git에 넣지 않는다.

## Files / 사진 검색 / 센서 / 카메라 방향

- `file_browser.py`: 인증된 `/api/library/entries` GET(root, path, offset, folders_only; 200개 페이지), `/preview` GET(root, path, download). 일반 `roots`만 허용하며 UUID 마운트·제외 이름·상대경로·심볼릭 링크를 검증합니다. 제외 이름은 resolve/stat보다 먼저 검사합니다. `files.js`가 지연 로딩 트리와 디렉터리 목록을 담당합니다.
- `preview.py`: PDF inline, 코드/텍스트 최대 2MiB를 UTF-8 또는 CP949로 읽고 text/plain 캐시로 표시합니다. HTML 코드를 실행하지 않습니다. 기존 이미지/영상 변환 경로를 공유합니다.
- `photo_search.py`: chat의 photo_search intent를 등록된 주제·사용자가 붙인 얼굴 이름·촬영 날짜에 연결합니다. 결과 JSON은 photos(최대8), photo_total, photo_filters를 추가하고 files는 비웁니다. photos.js의 photoChatCards가 기존 사진 상세 뷰어를 재사용합니다. 멀티모달 LLM 추론은 아닙니다.
- `resources.py`: CPU 사용률/RAM 사용률과 cpu_temperature/ram_temperature(섭씨 또는 null), ram_temperature_note를 반환합니다. Pi RAM 센서 미지원은 null로 유지합니다.
- `/api/camera/orientation` POST: rotation(strict int 0/90/180/270), mirror_horizontal/mirror_vertical(strict bool). camera_orientation DB 상태에 저장합니다. 녹화 중409, 잘못된 회전400, 타입오류422. 프레임 변환 후 MJPEG·녹화·motion에 동일 프레임을 전달합니다. 방향 변경 시 hold 누적을 지우지만 기존 실행 쿨다운은 유지합니다.
- `photo_runtime.py`: SQLite state 진행률과 파일 heartbeat. `photo_worker.py`는 DB 디렉터리/파일 큐, 변경 파일만 ExifTool 호출, 주제·얼굴 항목별 버전/완료 상태, 128개 이하 분류 자식 프로세스. FP32 CLIP 모델 파일과 고정 해시는 install-photo-models.py에서 관리합니다.
- 회귀 검증: tests/test_explorer_camera.py, tests/test_photos.py. 실제 사용자 사진/얼굴 점검물은 data 또는 Git 밖에만 두고 커밋하지 않습니다.


## 진행률 계측

`progress.py`는 보호 경계를 지키는 사전 파일 개수 집계와 현재 작업 표본 기반 Estimate를 제공합니다. 파일 indexing.status에는 stage, total, total_known, files, eta_seconds가 추가됩니다. 사진 진행 파일에는 inventory_total, discovery_complete, processed_base, media_total, eta_seconds가 추가됩니다. 사진 discover의 discovered_offset은 여러 루트의 누적 발견 수를 유지합니다. 사진 분류 분자는 processed_base+done, 분모는 media_total이며 Live 연결 영상은 별도 항목으로 세지 않습니다. photos.js가 두 카드의 백분율/ETA와 미확정·중단 상태를 렌더링합니다. ETA는 단계 단위이고 FTS 반영 시간의 확정 예측이 아닙니다. 기존 done/total API 필드는 이번 분류 작업 수 의미를 유지합니다. `tests/test_progress.py`가 제외 경계·확장자·심볼릭 링크·중단·ETA 초기 표본과 계산을 검사합니다.

사진 상태 집계/목록의 Live Photo 제외 NOT EXISTS 조인은 photos_live_pair(root,live_relative) 인덱스가 필요합니다. 이 인덱스가 없으면 대형 라이브러리 상태 조회가 제곱 규모로 느려져 대시보드 polling이 밀립니다.

## DB 증분 작업과 접속 분리 (2026-10-26)

- `inventory.py`: 작업/디렉터리/파일 큐, UUID+상대경로 정체성, SHA-256 스트리밍과 전후 stat 검증. scan_entries 완료와 결과 저장은 같은 DB 트랜잭션이다. 재시작 시 완료 디렉터리/파일을 다시 처리하지 않는다. 금지 폴더 이름은 stat·symlink 검사 전에 제외한다.
- `photo_worker.py`: 메타데이터 검사와 분류를 분리한다. 해시 동일 시 EXIF·주제·얼굴 재사용, 변경 시 해당 사진만 무효화. analysis_version으로 모델 변경을 감지한다. 재시도 시각과 활성 항목을 DB에 저장한다. 사진이 크거나 모델이 실패해 자식이 종료되면 해당 항목은 지연 재시도하고 다음 항목을 진행한다.
- `photo_models.py`: 고정 주제 문장 특징은 버전+문장 해시별 NumPy 캐시, 최초 계산 배치4. 이미지 분석 모델/임계값은 유지한다.
- `login_security.py`: SQLite login_failures/login_challenges, HMAC 클라이언트 키와 CAPTCHA 답, 서버 발급 일회용 이미지(3분), 정책 state.login_policy. settings API는 인증/CSRF/정수 범위 검증을 유지한다.
- `deploy/alter-nginx.conf`: 11977은127.0.0.1/192.168.0.0/24만, 8080은외부용. 단일127.0.0.1:18080 앱으로 프록시. X-Alter-Exposure는 항상 덮어쓴다. 8080의 전달 IP/HTTPS는 로컬 ngrok 프로세스에서 온 경우만 신뢰한다. 백엔드를 LAN에 직접 바인딩하면 안 된다.
- `web/static/settings.js`: 보안 설정 조회/저장과 카메라 설정 로딩. `login.js`는 외부 CAPTCHA·만료/실패 재발급·429 대기 안내. 내부 alter_session과 외부 alter_public_session은 DB scope까지 검증한다.
- 회귀시험: test_resumable.py, test_process_resume.py(실제 별도 프로세스 즉시 종료), test_login_security.py. 운영 진입점은11977을 사용한다. 외부 실제 로그인 테스트에는 사람이 확인한 CAPTCHA 값이 필요하며 자동 해독하지 않는다.

상세 스키마·복구·한계는 docs/indexing-security.md. 기존 JSON 진행률은 더 이상 기록/조회하지 않으며 DB state가 원본이다. 외부 드라이브 파일과 사용자 DB를 Git에 넣지 않는다.

NTFS 읽기 유지보수: `deploy/alter-disk`는 NTFS-3G와 `nocompression`을 명시합니다. 운영 장비에서 관측한 NTFS3 압축 읽기 교착을 회피하기 위한 선택이며 기존 압축 해제와는 별개입니다. root 소유 유지보수 마커가 있으면 장치 조회/마운트 전에 거부합니다. `tests/test_disk_maintenance.py`는 이 경계를 검사합니다.
