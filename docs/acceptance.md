# 실기기 검증 기록

기준 2026-10-20. 실제 Pi5 8GB, 테스트 USB SanDisk FAT32, IMX708, Windows Chrome. 결과 파일은 Pi data에 비공개 보관하며 사용자 기기 식별자/토큰/영상은 Git에 공개하지 않습니다.

## 통과

- `tests/test_boundaries.py`: 9개. 명시 날짜/확장자 보완, symlink 탈출, 오프라인 활성 색인 보존, 72시간 재추출, 생성일/ctime 구분, Flow 실패/중복, 비밀번호 변경 세션 무효화, SmartThings429/401 처리.
- `tests/test_oauth.py`: 4개. 잘못된 브라우저 바인딩, state/ticket 재사용, 로그아웃 세션, 암호화와 갱신, callback 앱 API 제한.
- `tests/live_smoke.py`: 최종 결과44항목(43개 assertion + 모델 mode 관측). 비인증 차단/로그인/CSRF/Origin, 외장 폴더 등록, 한국어 TXT/DOCX/HWPX BM25, 날짜/확장자/TF-IDF, 미리보기/다운로드, 생성·수정·삭제 추적, Flow/중복 요청, 대화 저장, 실제 카메라 스트림/6초 녹화/ffprobe, MediaPipe 초기화, 로그아웃.
- `tests/live_storage.py`: 실제 해제/UUID 재마운트, 오프라인 메타데이터 보존/다운로드 차단, SMB 경로 복원. FAT32 한글 파일명 문제가 발견되어 utf8=1 옵션으로 수정 후 재검증.
- Windows SMB 접속, 디렉터리 조회, 읽기 전용 쓰기 거부. Pi smbclient로 별도 쓰기 허용 테스트 공유에 업로드→다운로드 내용 일치→테스트 파일 삭제까지 성공하고 테스트 공유를 제거했습니다.
- 실제 구형 HWP pyhwp upstream fixture에서 한국어 텍스트 추출. 스캔 PDF OCR/모든 HWP 변종 지원 시험은 아님.
- 실제 삼성 OAuth 인가/교환, 27개 기기 목록, 허용된 메인 등 on→off→on 상태 확인, refresh token 실제 회전과 이후 API 성공.
- Chrome 로그인, 한국어 검색/문서 미리보기/Flow 생성, SmartThings 연결 표시와 메인 등 카드, HEIC320×240 디코딩, MOV960×720 2초 영상 readyState4, 카메라640×480 스트림 수신.
- 커널 memory cgroup 활성화 후 재부팅, 웹/모델 서비스 복구. 기존 팬 서비스 유지.

## 한계와 남은 검증

실제 사람의 다섯 손동작 인식률과 오탐은 시험하지 않았습니다. 제스처 엔진 초기화가 동작 정확도 검증을 대신하지 않습니다. Pi 화면 자동 시작 프로세스는 설정했으나 터치 입력/실화면 usability는 확인하지 않았습니다. 마이크가 없어 음성 wake word/STT는 미구현입니다.

HEIC/MOV는 합성 fixture 기반입니다. 실제 Apple 촬영 원본의 HDR/회전/다양한 코덱 조합은 별도 검증 대상입니다. DOCX/HWPX 간단 XML fixture는 전체 문서 포맷 호환성 보장이 아닙니다. 장시간 동시 부하/전원 차단/대규모 코퍼스/장기 토큰 만료 시험도 남았습니다.

모델 세 후보의 제한된 비교는 models.md를 참고하세요. 자동 시험의 `chat returns search cards`는 자료형 검사이므로 모델 답변 품질의 충분조건이 아닙니다. Chrome에서 실제 검색 결과 카드도 별도로 확인했습니다. 테스트에서 생성한 대화/Flow와 USB Alter-test 데이터는 기능 확인용으로 남아 있습니다.

추가 실증: 허용 조명에서 기기 변경→2초 대기→원상복구 3단계 Flow 완료. 카메라가 실행 중인 상태에서 Qwen4B가 “메인 등 꺼줘”를 실제 연결 기기의 확인 제안으로 반환(44.31초), 자동 실행하지 않음. 이후 카메라를 종료했습니다.

2026-10-20 ngrok 전환: 무료 계정 고정 개발 도메인/HTTPS, 에이전트 재시작 시 동일 주소 유지, 공개 health200/API404/위조 callback400, Chrome 안내 페이지→삼성 재인가→ngrok 연결 완료, 기기 조회 성공. alter-ngrok 자동 시작 활성화, 기존 임시 Cloudflare 서비스 중지.
