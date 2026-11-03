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


## 상시 감지 모델 (2026-10-24)

기존 GestureRecognizer(약8MB)와 [BlazeFace Short Range](https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite)(약225KB)를 동시에 적재합니다. BlazeFace SHA256: `b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f`. 재현 설치는 scripts/install-vision.py입니다. Python 의존성 mediapipe==1.1.1을 재사용하며 별도 학습 런타임은 추가하지 않습니다.

[MediaPipe 공식 손동작 목록](https://developers.google.com/edge/api/mediapipe/js/tasks-vision.gesturerecognizeroptions)에 다섯 동작이 모두 포함됩니다. [BlazeFace 공식 모델 설명](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/face_detection.md)은 근거리 모델을 약2m 이내에 권장합니다. 이 기능은 얼굴 검출이며 얼굴 신원 인식이나 보안 인증용이 아닙니다.

이번 동시 부하 시험부터 Qwen3.5-4B-Q4_K_M의 문맥을4096으로 설정했습니다. 2048개 출력 토큰 외에 입력을 수용하기 위한 것으로, 위 초기 비교의2048문맥 기록과 구분합니다. 두 경량 모델을 함께 사용하므로 별도 학습은 필요하지 않습니다.

사진 관리 모델: CLIP ViT-B/32 ONNX FP32 + OpenCV YuNet/SFace를 별도 사진 작업자에서 CPU로 실행합니다. 설치 리비전과 SHA256은 `scripts/install-photo-models.py`, 선택 이유·분류 기준·오류 수정·범위는 [photos.md](photos.md)를 참조하세요. 얼굴 사진은 외부로 보내지 않습니다.

## CPU와 Vulkan 비교 환경 (2026-11-03)

Pi 5 8GB, Raspberry Pi OS/Debian 13.7, Linux `6.18.50+rpt-rpi-2712`, Mesa `26.2.2-1~bpo13+0~rpt1`, 실제 장치 V3D 7.1.10.2로 확인했다. 모델은 기존 Qwen3.5-4B-Q4_K_M, llama.cpp는 위의 고정 커밋이다. 커널·디스플레이 드라이버·모델을 비교를 위해 교체하지 않았다.

기존 CPU 빌드와 별도로 공식 Vulkan 백엔드를 빌드했다. `vulkaninfo`에 나오는 llvmpipe는 소프트웨어 CPU 장치이므로 GPU 시험에서 제외한다.

```sh
cd ~/hw-agent/data/build/llama.cpp
cmake --build build --target llama-bench -j1
cmake -S . -B build-vulkan -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=ON -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS \
  -DGGML_VULKAN=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF
cmake --build build-vulkan --target llama-server llama-bench -j2
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/broadcom_icd.json \
  build-vulkan/bin/llama-bench --list-devices
```

속도 시험은 [공식 llama-bench](https://github.com/ggml-org/llama.cpp/tree/704366d76f8748cf9ad3df62a464bfcc8d1ae6ad/tools/llama-bench)를 이용한다. `pp`는 입력 토큰 처리, `tg`는 출력 토큰 생성이며 토큰화·응답 전송·샘플링을 포함하는 실제 채팅 응답 시간과 다르다. 모델 중복 적재를 피하도록 운영 LLM을 잠시 중지하고, 메모리 한도가 있는 일회성 systemd 작업에서 실행한 뒤 운영 서비스를 복구한다. 빌드 중에는 속도를 측정하지 않는다.

CPU 결과: threads=3, OpenBLAS threads=2, batch=128/ubatch=64, GPU layers=0, Flash Attention=auto, 예열 후 3회 반복. 카메라·웹·기존 파일/사진 작업은 실행 중이었으며 순수 전용 벤치마크 환경이 아니다.

| 공식 시험 | 평균 tokens/s | 표준편차 | 회별 tokens/s |
|---|---:|---:|---|
| pp128 입력 처리 | 10.56 | 0.29 | 10.53 / 10.87 / 10.29 |
| tg128 출력 생성 | 1.67 | 0.06 | 1.74 / 1.62 / 1.66 |

시작 CPU 온도 65.3°C, 종료 79.6°C. 시험 중 약80°C와 온도 제한 이력(`get_throttled` 0→0xe0000)을 관측했다. 확인 시점의 현재 제한 비트는 0이고 과거 발생 비트만 설정되어 있었으므로 지속적으로 제한됐다고 단정하지 않는다. 팬은 OS 최대 냉각 단계(약8,393RPM)였다. 이 결과는 현재 장비·냉각·동시 작업 조건의 실측이며 최상의 Pi5 성능을 뜻하지 않는다. systemd 보고 peak 3.1G/swap 30.9M이며 mmap 캐시의 cgroup 귀속에 따라 값이 달라질 수 있다.

```sh
OPENBLAS_NUM_THREADS=2 build/bin/llama-bench \
  -m ~/hw-agent/models/Qwen3.5-4B-Q4_K_M.gguf \
  -p 128 -n 128 -r 3 -t 3 -b 128 -ub 64 -ngl 0 -o json --progress
```

원시 결과는 장비의 비공개 `data/benchmark-cpu-20261103.json`과 같은 이름의 `.log`에 보관한다. 시험 작업에는 운영과 같은 MemoryMax=5800M/MemorySwapMax=128M 한도를 적용했다.

Vulkan 결과:

| 설정 | 관측 | 생성 속도 |
|---|---|---|
| GPU 전체 적재, pp8/tg8, 1회, Flash Attention auto | 240초 제한까지 입력 예열 미완료, 종료124, peak5.3G/swap0B | 산출 불가 |
| GPU 전체 적재, tg8만, 1회, Flash Attention off | 33/33레이어 GPU 적재, 생성 예열 중180초 제한, 종료124, peak4.9G/swap9.7M | 산출 불가 |

두 시험의 실행 중 cgroup `oom`/`oom_kill`은0이었다. 둘째 시험의 GPU 모델 버퍼는2603.50MiB, Host 모델 버퍼는497.32MiB였다. GPU 장치 발견·가중치 적재와 정상 생성 완료는 별개다. 완료된 GPU tokens/s가 없어 CPU 대비 배수를 계산할 수 없으며, 더 오래 예열했을 때의 정상 상태 속도도 이번 시험으로 알 수 없다.

Vulkan 옵션은 `VK_DRIVER_FILES=/usr/share/vulkan/icd.d/broadcom_icd.json`, `-dev Vulkan0 -ngl 99`이며 나머지 threads/batch는 CPU와 같다. 둘째는 `-p 0 -n 8 -r 1 -fa off`를 사용했다. 원시 로그는 비공개 `data/benchmark-vulkan-probe-20261103.log`, `data/benchmark-vulkan-generation-20261103.log`에 보관한다. 미완료 JSON을 성공 결과나0 tokens/s로 취급하지 않는다.

운영 결정: Qwen3.5 4B의 CPU/OpenBLAS 서비스를 유지한다. GPU의 지연·정확성·안정성 개선이 검증되지 않아 사진/음성/동작 인식까지 일괄 전환하지 않았다. 별도 Vulkan 빌드는 재현용으로 남기고 자동 시작 서비스에는 연결하지 않았다. GPU 계측은 추론 백엔드와 독립적으로 적용했다. [Raspberry Pi 공식 LiteRT 자료](https://www.raspberrypi.com/news/mastering-edge-ai-on-raspberry-pi-with-litert-and-gemma/)도 CPU와 GPU 결과를 구분한다. 그 자료의 Gemma 성능을 현재 Qwen의 실측으로 대신하지 않는다.

복구 후 실제 CPU 서버의 한국어 합성 질의1개를 확인했다. 입력46토큰, 출력32토큰, 정상 stop, 전체26.768초였고 서버 보고 생성 속도는1.47tokens/s였다. 원시 결과는 비공개 `data/benchmark-restored-chat-20261103.json`이다. 단일 질의의 실행/복구 확인이며 한국어 종합 품질 평가나 첫 토큰 지연 측정이 아니다.
