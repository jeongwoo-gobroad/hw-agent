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

`alter-oauth.service`는 127.0.0.1:8082의 `/health`, `/oauth/start`, `/oauth/callback`만 제공합니다. 파일/카메라/기기 API는 공개하지 않습니다. access log를 꺼 인가 코드가 URL 로그에 남지 않도록 합니다.

실증용 `alter-tunnel.service`는 공식 cloudflared를 사용하며 자동 부팅 활성화하지 않습니다. 임시 터널 주소는 재시작할 때 달라집니다. 주소가 바뀌면:

1. `journalctl -u alter-tunnel`에서 새 HTTPS 호스트 확인.
2. SmartThings CLI `apps:oauth:update <app-id> --input <private-json>`으로 redirectUris 변경. JSON에는 clientName, scope, redirectUris를 포함합니다.
3. Pi `.env`의 SMARTTHINGS_REDIRECT_URI 변경 후 `sudo systemctl restart alter alter-oauth`.
4. 대시보드에서 새 연결 시작. 이전 ticket/인가 URL을 재사용하지 않습니다.

영구 배포에서는 소유한 도메인에 named tunnel 또는 HTTPS 리버스 프록시를 연결하고 같은 callback URI를 유지하세요. 도메인/Cloudflare 계정은 아직 설정되지 않았습니다. 기존 OAuth 토큰은 내부망 연결 후 터널이 중단돼도 SmartThings API에 직접 갱신할 수 있습니다.

## 검증

2026-10-20 실제 삼성 계정 인가, 토큰 교환, 27개 기기 조회, 허용된 메인 조명 on→off→on 상태 복원, 실제 refresh token 회전과 이후 조회 성공. `tests/test_oauth.py`는 위조 쿠키, 일회성 상태, 로그아웃 세션, 암호화, 갱신 재사용 방지와 공개 표면 제한을 네트워크 없이 검사합니다. 실제 만료 24시간 이후의 장기 운용은 아직 관찰하지 않았습니다.
