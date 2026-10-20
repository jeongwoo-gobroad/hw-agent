# 로컬 모델 선택 기록

2026-10-20 Pi5 8GB CPU에서 직접 비교. 이 실험은 세 개의 한국어 routing 질의이며 한국어 종합 벤치마크나 세계 최고 모델 선정이 아닙니다. 모델 출력의 intent 일치만 passed로 기록하므로 true가 날짜/스키마/답변 전체의 정답을 의미하지 않습니다. 원문 JSON을 함께 검토해야 합니다.

| 후보 Q4_K_M | 검색/일상/Flow 응답 초 | 관찰 |
|---|---|---|
| Qwen3.5 4B | 16.73 / 26.76 / 10.72 | 세 intent 일치, 한국어 답변. 명시 PDF/날짜 누락 |
| Kanana1.5 8B instruct2505 | 66.31 / 46.37 / 17.70 | 일반 대화 JSON 미준수, ext 객체 출력. llama parser 우회 필요 |
| Qwen3.5 9B | 83.81 / 25.57 / 21.51 | 세 intent 일치하나 날짜 연도 오답, 일반 대화 answer 빈 문자열 |

기본값은 Qwen3.5-4B-Q4_K_M입니다. 더 큰 두 후보는 실행됐지만 현재 앱의 JSON routing/지연 기준에서 이점이 확인되지 않았습니다. 날짜·확장자 명시 조건은 앱 규칙으로 보완했습니다. 9B 시험에서 cgroup limit 약5.8GiB에 근접했고 memory.max pressure 이벤트가 발생했지만 oom/oom_kill=0이었습니다. 4B 비교 관측 peak cgroup 약4.16–4.38GB. mmap 파일 캐시의 cgroup 귀속과 MemAvailable의 reclaimable cache 때문에 이를 모델 전체 메모리 사용량으로 해석하지 마세요. 범용 OOM 부재를 보장하지 않습니다.

런타임 [llama.cpp](https://github.com/ggml-org/llama.cpp) commit `704366d76f8748cf9ad3df62a464bfcc8d1ae6ad`. CPU/OpenBLAS, context2048, parallel1, threads3, batch128/ubatch64, no-warmup. Kanana는 별도 비교에서 skip-chat-parsing 필요. 실제 앱과 benchmark prompt는 다릅니다.

## 가중치 출처·SHA256

- [unsloth/Qwen3.5-4B-GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF), 확인 리비전 `e87f176479d0855a907a41277aca2f8ee7a09523`, Qwen3.5-4B-Q4_K_M.gguf: `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`.
- [unsloth/Qwen3.5-9B-GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF), revision `3885219b6810b007914f3a7950a8d1b469d598a5`: `03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8`.
- [Mungert/kanana-1.5-8b-instruct-2505-GGUF](https://huggingface.co/Mungert/kanana-1.5-8b-instruct-2505-GGUF), revision `ee4a4662ddd405116d52e5998f9c6dd0c55df1b4`: `a7d247fe117a43d35558eb91bc6c457e524e8aec5785955194d74f436954768b`.
- [Google GestureRecognizer](https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task): `97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482`.

모델은 외부 양자화 배포본이며 자체 학습/검증된 공식 양자화라는 의미가 아닙니다. 다운로드 재현 시 리비전과 로컬 해시를 비교하고 각 모델 라이선스를 따르세요. 원시 결과: benchmark-qwen35-4b.json, benchmark-kanana15-8b.json, benchmark-qwen35-9b.json.
