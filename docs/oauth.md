# SmartThings OAuth 운영

## 구성

공식 [OAuth-In Quickstart](https://developer.smartthings.com/docs/getting-started/quickstart)를 사용합니다. SmartThings CLI 2.1.2로 API_ONLY / CONNECTED_SERVICE / LOCATION 앱을 등록했습니다. 권한은 `r:locations:*`, `r:devices:*`, `x:devices:*`입니다. 삼성 로그인과 위치 선택/인가 동의는 사용자 브라우저에서 진행합니다.

`.env` 설정:

- `SMARTTHINGS_CLIENT_ID`, `SMARTTHINGS_CLIENT_SECRET`: 등록 시 발급. Git/로그에 넣지 않습니다.
- `SMARTTHINGS_REDIRECT_URI`: 등록된 HTTPS 주소 + `/oauth/callback`.
- `SMARTTHINGS_OAUTH_BASE`: 현재 `https://api.smartthings.com/oauth`.
- `DASHBOARD_URL`: 로그인 완료 후 돌아갈 내부망 주소.
- `SESSION_SECRET`: 토큰 암호화 키 파생에도 사용하므로 보존해야 합니다. 변경하면 재연결이 필요합니다.

`SMARTTHINGS_PAT`는 대체 인증이며 OAuth 연결이 있으면 OAuth를 우선합니다. 예전 평문 refresh-token 환경변수 경로는 사용하지 않습니다.

## 브라우저에서 연결

1. 내부망 대시보드 로그인 → 스마트홈 · Flow → 삼성 계정으로 연결.
2. 서버는 현재 대시보드 세션에 묶인 10분짜리 일회용 ticket을 생성합니다.
3. 콜백 서버는 ticket을 소모하고 새 state와 Secure/HttpOnly/Lax 브라우저 쿠키를 발급합니다.
4. 삼성 계정으로 로그인하고 위치/기기 권한에 동의합니다.
5. 콜백은 state, 브라우저 쿠키, 원래 세션의 생존/자격증명 fingerprint를 검사합니다. 인가 코드는 한 번만 교환합니다.
6. 대시보드로 돌아가 연결 확인을 누르면 기기를 조회합니다.

토큰은 SQLite state에 Fernet 암호화하여 저장합니다. 만료 5분 전 갱신하며 웹/콜백 프로세스가 파일 잠금을 공유해 refresh token 중복 사용을 막습니다. 새 access/refresh 쌍은 한 트랜잭션으로 저장합니다. 기기 명령은 인증 실패 때 자동 재전송하지 않습니다. 연결 해제는 로컬 토큰과 미완료 상태를 삭제하며, 삼성 측 권한 철회는 사용자가 SmartThings에서 별도로 수행합니다.

## HTTPS 콜백

현재 외부 진입점은 ngrok → 127.0.0.1:8080입니다. 웹 앱이 `/oauth/start`, `/oauth/callback`을 인증 없이 제공하되 OAuth ticket/state/쿠키 검증은 그대로 적용합니다. 나머지 파일/카메라/기기 API는 ID/PW 세션 인증이 필요합니다. 독립 `alter-oauth.service`의8082 콜백 앱은 대체 구성으로 보존합니다. 두 Uvicorn 서비스의 access log를 꺼 인가 코드가 URL 로그에 남지 않도록 합니다.

실증용 `alter-tunnel.service`는 공식 cloudflared를 사용하며 자동 부팅 활성화하지 않습니다. 임시 터널 주소는 재시작할 때 달라집니다. 주소가 바뀌면:

1. `journalctl -u alter-tunnel`에서 새 HTTPS 호스트 확인.
2. SmartThings CLI `apps:oauth:update <app-id> --input <private-json>`으로 redirectUris 변경. JSON에는 clientName, scope, redirectUris를 포함합니다.
3. Pi `.env`의 SMARTTHINGS_REDIRECT_URI 변경 후 `sudo systemctl restart alter alter-oauth`.
4. 대시보드에서 새 연결 시작. 이전 ticket/인가 URL을 재사용하지 않습니다.

고정 콜백에는 ngrok 무료 개발 도메인도 사용할 수 있습니다. 별도 소유 도메인이 반드시 필요한 것은 아닙니다. 기존 OAuth 토큰은 내부망 연결 후 터널이 중단돼도 SmartThings API에 직접 갱신할 수 있습니다.

### ngrok 무료 플랜

[공식 무료 플랜 안내](https://ngrok.com/docs/pricing-limits/free-plan-limits) 기준, 계정에 할당된 고정 개발 도메인 1개와 인증서가 자동 관리되는 HTTPS endpoint를 제공합니다. endpoint의 강제 시간 만료는 없지만 무료 사용량 한도는 적용됩니다. 현재 월 1GB 송신/HTTP 20,000회 한도가 있어 저빈도 OAuth 콜백에 적합합니다. 무료 브라우저 안내 페이지에서 Visit을 누르면 해당 도메인에 7일간 안내가 생략됩니다. OAuth 진입 과정에서 안내를 통과한 뒤 삼성 인증을 진행할 수 있습니다.

1. 공식 ARM64 ngrok 에이전트를 `/usr/local/bin/ngrok`에 설치합니다. 이 Pi에는 3.39.11을 준비했습니다.
2. 프로젝트 `.env`에 `NGROK_AUTHTOKEN`을 설정합니다. 자격증명 ID가 아니라 [Your Authtoken](https://dashboard.ngrok.com/get-started/your-authtoken)의 실제 토큰이 필요합니다.
3. `deploy/alter-ngrok.service`를 systemd에 설치하고 시작합니다. 이 서비스는 인증된 대시보드8080을 연결하며 로컬 요청 inspection을 끕니다.
4. loopback `http://127.0.0.1:4040/api/tunnels`에서 할당된 HTTPS 주소를 확인합니다. 이 주소의 `/oauth/callback`을 SmartThings 앱과 `.env` 양쪽에 등록합니다.
5. alter/alter-oauth 재시작 후 HTTPS health, 잘못된 state 거부, 대시보드에서 새 OAuth 연결을 검증합니다.
6. ngrok 재시작 뒤 도메인이 유지되는지 확인한 후 `systemctl enable alter-ngrok`을 적용하고 기존 alter-tunnel을 중지합니다.

2026-10-20: 실제 Authtoken으로 연결 후 ngrok 고정 HTTPS 주소를 SmartThings 앱과 Pi 설정에 등록했습니다. 에이전트 재시작 후 같은 주소 유지, HTTPS health200, 잘못된 OAuth state400, 당시 콜백 전용 구성에서 기기 API404와 기존 SmartThings 27개 기기 조회를 확인했습니다. Chrome에서 무료 안내 페이지를 거쳐 동일 삼성 계정/권한으로 재인가한 뒤 ngrok 콜백의 연결 완료를 확인했습니다. ngrok 자동 시작을 활성화하고 기존 Cloudflare 임시 터널은 중지했습니다. 토큰은 Pi .env에만 저장하며 Git에 포함하지 않습니다.

### ipTIME DDNS

DDNS는 변하는 공인 IP에 도메인을 연결하는 기능이며 HTTPS 인증서를 대신하지 않습니다. ipTIME DDNS 이름에 유효한 인증서를 발급·갱신하는 리버스 프록시와 공유기 포트포워딩을 구성하면 같은 OAuth 콜백을 제공할 수 있습니다. 이 방식은 외부에서 접근 가능한 회선/포트 조건이 필요합니다. ngrok 무료 플랜에서는 ipTIME DDNS를 사용자 지정 도메인으로 연결하는 대신, 계정에 할당된 ngrok 도메인을 사용합니다.

## 검증

2026-10-20 실제 삼성 계정 인가, 토큰 교환, 27개 기기 조회, 허용된 메인 조명 on→off→on 상태 복원, 실제 refresh token 회전과 이후 조회 성공. `tests/test_oauth.py`는 위조 쿠키, 일회성 상태, 로그아웃 세션, 암호화, 갱신 재사용 방지와 공개 표면 제한을 네트워크 없이 검사합니다. 실제 만료 24시간 이후의 장기 운용은 아직 관찰하지 않았습니다.

외부 대시보드 전환 후: 비로그인 파일/카메라 API401, 로그인 후 검색/문서 미리보기/MJPEG 수신을 Windows와 Chrome에서 확인했습니다. 무료 플랜의 월1GB 송신 한도는 영상 스트리밍으로 빠르게 소진될 수 있으므로 장시간 원격 감시에는 적합하지 않을 수 있습니다.
