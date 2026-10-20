# 라이브러리 검토

조사 기준 2026-10-20. 초기 후보 검토표입니다. 실제 설치·채택 목록은 requirements.txt와 requirements-pi.lock.txt가 기준입니다. Jinja2/pydantic-settings/Kiwi/watchdog/python-docx는 현재 채택하지 않았습니다. 현재 설정은 python-dotenv, 한국어는 bigram, 파일 감시는 60초 대조, DOCX는 제한된 XML 추출입니다. OAuth는 Authlib와 cryptography를 채택했습니다.
존재하는 라이브러리를 먼저 평가하고 부족한 업무 로직만 자체 구현한다.

| 영역 | 후보 / 공식 자료 | 결정·검증 사항 |
|---|---|---|
| 웹/API | [FastAPI](https://fastapi.tiangolo.com/), Uvicorn, Jinja2 | Python 중심 서버 렌더링, 별도 프런트엔드 빌드 의존 최소화 |
| 설정 | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | .env 검증, 비밀 필드 로그 금지 |
| 검색 | [SQLite FTS5](https://www.sqlite.org/fts5.html) | 표준 sqlite3에서 FTS5 활성 여부 확인, bm25 점수는 작은 값이 상위 |
| 한국어 | [Kiwi/kiwipiepy](https://github.com/bab2min/kiwipiepy) | Python 3.13 ARM64 wheel과 메모리 확인 |
| 재정렬 | [scikit-learn](https://scikit-learn.org/stable/modules/feature_extraction.html#text-feature-extraction) | 제한 후보 TF-IDF; 전체 코퍼스 dense 행렬 금지 |
| 파일 감시 | [watchdog](https://github.com/gorakhargosh/watchdog) | inotify 누락/USB 재연결은 전체 대조로 보완 |
| DOCX | [python-docx](https://python-docx.readthedocs.io/) | 표·문단 추출, ZIP 입력 제한 |
| HWPX | [defusedxml](https://github.com/tiran/defusedxml) + zipfile | XML 외부 엔티티·압축 크기 제한, 섹션 순서 유지 |
| 구형 HWP | [pyhwp](https://github.com/mete0r/pyhwp) | 오래된 런타임 호환성 우선 검증; 지원 불가면 명시 |
| PDF | [pypdf](https://pypdf.readthedocs.io/) | 텍스트 PDF 우선, OCR와 구분 |
| HEIF | [pillow-heif](https://pillow-heif.readthedocs.io/) | libheif와 ARM64 지원, EXIF 회전 확인 |
| 영상 | [FFmpeg](https://ffmpeg.org/documentation.html) | 시스템 패키지; 실제 MOV/HEVC 코덱 확인 |
| SMB | [Samba](https://www.samba.org/samba/docs/) | testparm 검증 후 적용, 기존 구성 보존 |
| LLM | [llama.cpp](https://github.com/ggml-org/llama.cpp) | ARM CPU 실행, 런타임 커밋 고정, 프로세스 격리 |
| 모델 | [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) | 비교 출발 후보; 한국어 최우수/최신 확정 아님 |
| 스마트홈 | [SmartThings REST](https://developer.smartthings.com/docs/getting-started/authorization-and-permissions), [HTTPX](https://www.python-httpx.org/) | 공식 API 스키마 기반; OAuth 갱신과 PAT 만료 처리 |
| 카메라 | [Picamera2](https://github.com/raspberrypi/picamera2) | 현재 OS 패키지 설치됨; apt/libcamera와 호환 유지 |
| 제스처 | [MediaPipe](https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer/python) | 다섯 canned gesture 사용, ARM64/Python 버전 검증 |
| 음성 | [whisper.cpp](https://github.com/ggml-org/whisper.cpp), [Vosk](https://alphacephei.com/vosk/) | 마이크 도입 후 한국어 지연·정확도 비교 |
| CLI 진행률 | [tqdm](https://tqdm.github.io/) | 스캔/배포 등 장기 CLI 작업 |

## 의존성 재현 정책

`requirements.txt`는 실제로 import하는 직접 의존성만 버전 범위 또는 검증 버전으로 기재한다.
간접 의존성의 재현성은 별도 lock/constraints로 관리한다.
OS 패키지·Python 버전·모델 리비전·런타임 빌드 옵션은 배포 문서에 기록한다.
라이브러리 선택만으로 성능, 보안, ARM64 호환성, 유지보수 신뢰도가 검증되었다고 쓰지 않는다.
