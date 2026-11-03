# ngrok과 SmartThings OAuth

[English](oauth.md) · [한국어](oauth.ko.md)

각 설치자는 본인의 삼성 계정, 사용 가능한 SmartThings API Access App, ngrok 계정을 준비합니다. 공용 OAuth 클라이언트나 다른 설치자의 기기를 공유하지 않습니다.

## 등록 조건

2026년 11월 4일부터 새 OAuth 앱 생성·수정에는 지원되는 유료 SmartThings API 요금제가 필요하며 국가별 제공 조건도 있습니다. 기존 연동에는 별도 전환 일정이 적용됩니다. [삼성의 현재 정책](https://blog.smartthings.com/smartthings-updates/smartthings-api-additional-details-for-developers-and-business-partners/)을 먼저 확인하세요. ngrok 무료 플랜은 SmartThings API 이용료를 대신하지 않습니다.

## 연결 순서

1. ngrok 대시보드에서 본인에게 할당된 개발 도메인과 실제 Authtoken을 확인합니다. 자격증명 ID와 Authtoken은 다르며 토큰은 비공개로 보관합니다.
2. [공식 SmartThings CLI](https://github.com/SmartThingsCommunity/smartthings-cli)를 설치하고 로그인한 후 [공식 앱 등록 안내](https://developer.smartthings.com/docs/getting-started/quickstart)를 따릅니다. 현재 안내는 `smartthings smartapps:create`, 구버전은 `apps:create`이므로 설치한 CLI의 도움말을 확인합니다.
3. `https://<본인에게-할당된-도메인>/oauth/callback`을 정확히 등록합니다. Alter에 필요한 위치·기기 읽기 및 실행 권한은 `r:locations:*`, `r:devices:*`, `x:devices:*`입니다. 발급된 client ID/secret을 비공개로 보관합니다.
4. `~/hw-agent`에서 `.venv/bin/python scripts/configure.py --smartthings --lang ko`를 실행합니다. HTTPS 주소·Authtoken·OAuth 정보를 입력하면 `.env`와 허용 호스트를 갱신하며 기존 세션 키는 보존합니다.
5. `bash scripts/install-ngrok.sh` 후 `sudo systemctl restart alter alter-oauth`를 실행합니다. 공식 ngrok apt 저장소를 사용하며 요청 inspection을 끄고 loopback 8080으로 전달합니다.
6. 내부망 Alter 로그인 → **스마트홈 → 삼성 계정 연결** → ngrok 안내가 있으면 통과 → 위치·기기 선택과 인가 → Alter에서 연결 상태 확인 순서로 진행합니다. 과거 인가 링크를 재사용하지 않습니다.

`DASHBOARD_URL`은 연결 후 복귀 주소입니다. 로컬 설정에서는 내부망 주소를, 원격 설정에서는 본인의 HTTPS 주소를 사용할 수 있습니다. 도메인을 바꾸면 등록 앱·`.env`·`ALLOWED_HOSTS`를 모두 갱신하고 서비스를 재시작한 뒤 새 인증을 시작합니다.

## 인증과 운영

로그인 세션에 묶인 일회용 ticket과 OAuth state/cookie를 검증합니다. 토큰은 `SESSION_SECRET`에서 파생한 키로 SQLite에 암호화하며 프로세스 간 잠금으로 갱신을 직렬화합니다. 인증 실패 후 기기 명령을 자동 재전송하지 않습니다. 연결 해제는 로컬 정보를 지우며 삼성 측 권한 철회는 SmartThings에서 별도로 수행합니다.

ngrok 무료 개발 도메인은 고정 HTTPS 주소를 제공하지만 [현재 제한](https://ngrok.com/docs/pricing-limits/free-plan-limits)은 월 송신 1GB·HTTP 20,000회입니다. 장시간 카메라 스트리밍에는 부족할 수 있습니다. DDNS도 유효한 HTTPS 프록시와 외부에서 도달 가능한 포트를 갖추면 사용할 수 있지만 DDNS 자체는 인증서를 제공하지 않습니다.

파일·카메라·기기 API는 대시보드 인증을 유지합니다. 외부 8080에는 CAPTCHA와 실패 차단이 추가됩니다. OAuth 진입·콜백은 대시보드 로그인 대신 일회용 ticket/state 검증을 적용합니다. PAT는 단기 시험용이며 장기 연동은 OAuth를 사용합니다.

진단에는 서비스·HTTP 상태를 사용하고 `.env`, 인가 URL, 쿠키, 토큰, 계정·위치·기기 ID와 개인 설정 화면을 공개하지 않습니다. 철회된 권한은 자동 갱신으로 복구할 수 없으므로 브라우저에서 다시 연결해야 합니다.
