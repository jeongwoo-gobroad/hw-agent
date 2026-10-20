# 에이전트 개발 안내

## 현재 상태

2026-10-20: SSH 하드웨어 조사 및 설계 수립. 애플리케이션은 아직 구현하지 않았다.
README의 목표를 구현 완료 사실로 인용하지 않는다.
현재 존재하는 파일은 README, 이 안내, docs 문서, 직접 의존성 정책 파일, 환경 예제와 라이선스다.
아래 트리는 **예정 구조**이며 모든 경로가 현재 존재한다는 뜻이 아니다.

## 경로와 배포

- Windows 기준 소스: `D:\_rpi-agent`
- Pi 실행 경로: `/home/jeongwoo/hw-agent`
- 소스 공개 저장소: `jeongwoo-gobroad/hw-agent`
- `.env`와 `data/`는 장치별 비공개 상태. 배포 시 덮어쓰지 않는다.
- 변경 → 관련 문서 갱신 → 의미 있는 검증 → 비밀정보 검사 → commit/push → Pi 배포 → smoke test 순서.
- dependency lock은 검증한 ARM64 Python 환경에서 생성하고 최상위 requirements와 구분한다.
- SSH 비밀번호를 코드, 명령 기록 파일, 문서 또는 배포 스크립트에 저장하지 않는다.

## 예정 컴포넌트

```text
src/hw_agent/
  app.py                   # 앱 조립, lifespan, route 등록
  config.py                # .env 로드와 검증, 로그 마스킹
  auth/                    # 로그인, 세션 저장소, CSRF, rate limit
  api/                     # HTTP/WebSocket 입력 검증; 업무 로직은 services로 전달
  storage/
    devices.py             # lsblk/udisks 장치 식별 및 상태
    roots.py               # UUID와 허용 폴더, 경로 접근 정책
    smb.py                 # 제한된 Samba 헬퍼 호출
  indexing/
    scanner.py             # 제한된 재귀 스캔과 이벤트 대조
    extractors/            # txt/docx/hwpx/pdf/hwp별 추출 어댑터
    generations.py         # 72시간 세대 교체, 실패 복구
    search.py              # FTS5 BM25, 필터, 후보 재정렬
  preview/                 # 이미지/HEIF/영상 프록시, 캐시 제한
  chat/
    sessions.py            # 세션/메시지 저장·삭제·내보내기
    inference.py           # 로컬 LLM 서버 어댑터와 자원 제한
    tools.py               # 스키마 검증된 검색/기기/Flow 호출
  smartthings/             # OAuth, 기기 capability, 명령 API
  flows/                   # 프리셋, 실행 상태, 중복 방지, 단계 로그
  camera/                  # 단일 Picamera2 소유, 스트림과 분할 녹화
  gestures/                # 모델 어댑터, 안정화, 매핑과 쿨다운
  voice/                   # 향후 마이크, 호출어, STT, 의도 이벤트
  db/                      # migration, repositories, transaction 경계
  web/templates/           # 데스크톱 및 /panel 터치 레이아웃
  web/static/              # 스타일, 스크립트, 출처 명시된 자산
scripts/                   # 설치/배포/백업, 비밀정보 미포함
deploy/                    # systemd, 제한된 권한 helper, Samba 템플릿
tests/                     # 경로/auth/세대 교체/Flow 등 경계 테스트
data/                      # 비공개 DB·캐시·로그; Git 제외
models/                    # 가중치; Git 제외
```

## 흐름과 경계

1. 로그인 후 API가 입력을 스키마 검증한다. 파일 접근은 반드시 `storage.roots`를 통과한다.
2. 인덱서는 원본 파일을 읽기만 한다. 추출 worker는 시간·메모리·압축 크기를 제한한다.
3. SQLite에는 파일 메타데이터/FTS, 색인 세대, 세션/메시지, Flow/실행, 제스처 매핑을 저장한다. SQLite WAL, migration과 백업 일관성을 고려한다.
4. LLM은 실행 계획을 제안하고 도구 dispatcher가 권한과 실제 존재하는 ID를 검증한다.
5. UI·음성·제스처는 동일한 Flow 서비스를 호출한다. 세 입력 경로에 별도 기기 제어 로직을 복제하지 않는다.
6. 카메라 접근과 영상 인코딩을 여러 요청마다 새로 시작하지 않는다. 구독자와 녹화 작업을 중앙 관리한다.
7. root 작업은 좁은 IPC/헬퍼로 격리한다. 사용자 입력을 셸 문자열로 조립하지 않는다.

## 변경 규칙

- 입출력, 알고리즘, 실행 방식 변경 시 README와 관련 docs를 함께 수정한다.
- 과한 print·이모지를 넣지 않는다. 긴 CLI 작업에는 tqdm을 사용한다.
- 핵심 변수와 알고리즘만 간단한 구어체 주석을 단다.
- requirements에는 직접 의존성만 기록한다. OS libcamera, Samba, FFmpeg는 Python requirements에 쓰지 않는다.
- 원본 USB에 테스트 파일을 쓸 때 전용 임시 폴더를 사용한다. 기존 설치 파일은 건드리지 않는다.
- 테스트 결과는 확인 날짜, 명령/조건, 결과, 미검증 범위를 남긴다. 하드웨어 열거를 기능 완료라고 쓰지 않는다.
- GPL 코드와 모델/로고/외부 라이브러리 라이선스를 분리한다.

## 다음 개발 시작점

`docs/plan.md`의 P1부터 구현한다. 먼저 장치 인증·허용 경로·DB migration과 서비스 설치를 검증한다.
모델 다운로드나 전체 USB 색인을 시작하기 전에 자원 한도와 취소·복구를 구현한다.
SmartThings 토큰과 실제 테스트 기기, 마이크가 없는 작업은 외부 조건 미충족으로 남긴다.
