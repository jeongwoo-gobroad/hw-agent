# Validation scope / 검증 범위

The reference system runs on Raspberry Pi 5 8GB. Tests use disposable fixtures unless explicitly identified as device checks. Historical benchmark details remain in [models.md](models.md); they are not a claim of universal performance.

기준 장비는 Pi 5 8GB입니다. 합성 시험과 실제 장비 확인을 구분하며 모델 성능 조건은 별도 문서를 따릅니다.

| Area | Evidence and limits |
|---|---|
| Translation and install templates | EN/KO request isolation, catalog interpolation, English photo/date queries, two Linux account/subnet renderings and invalid-account rejection |
| Access and OAuth | Login blocking, scoped sessions, CSRF/root boundaries, one-time state, token encryption/refresh and allowed-action checks using fixtures |
| Files and photos | Synthetic folder/preview/search, independent roots, metadata filters, stored person labels and checkpoint reuse; not a comprehensive recognition-accuracy benchmark |
| UI | Real browser checks on the running app. Public screenshots use a separate sample dataset; their files, devices and labels are examples |
| Hardware | A working assembled device is pictured. CAD mesh/collision checks do not certify printer fit, cable strength, stability or cooling |
| SmartThings | OAuth and selected device control were exercised on the reference installation. Another account requires its own registration/plan and authorization |
| Voice | Engine and synthetic Korean speech tested; microphone/environment-specific recognition and wake false-positive rates are not established |
| LLM/GPU | CPU completed the recorded throughput test; Vulkan warmup timed out. GPU metrics and successful GPU model loading do not prove faster inference |

Fresh-OS installation, every printer/material, all storage hardware and all SmartThings regions/plans have not been exhaustively tested. Do not substitute a health endpoint, mock response or screenshot for the corresponding hardware/API verification.

## Release verification — 2026-11-04

- 55 focused tests passed on the Pi across translation, OAuth, login policy, generation, explorer/camera, photos, recovery and access boundaries. Translation tests were rerun after the final catalog changes.
- Chrome checked all ten English navigation pages, file/code preview, photo preview, both themes and both 1280 × 720 touch keyboards. A 390 px dashboard check found no document-width overflow. Native browser controls can retain the OS language.
- The production CPU model answered a synthetic greeting in each language through the streaming endpoint. English: 2 answer chunks, first chunk 26.02 s, total 43.34 s. Korean: 4 chunks, first chunk 23.81 s, total 42.51 s. These are single-request checks under concurrent indexing, not a throughput benchmark. Test conversations were removed.
- All 14 published STL files match the original design exports, have watertight meshes and positive volume, and fit within 220 mm in X/Y. These checks do not replace print-fit tests.

영문 10개 메뉴·파일/사진 미리보기·한영 터치 키보드와 두 테마를 Chrome에서 확인했습니다. 운영 Pi의 한영 스트리밍 응답은 각각 합성 인사 요청 1건으로 확인했으며, 속도 벤치마크나 대화 품질 종합 평가가 아닙니다. 기존 사진 작업자와 모델 서비스를 유지하고 웹 서비스를 갱신했습니다. 재시작 직후 기존 색인 작업의 DB 쓰기 잠금으로 로그인 1회가 실패했으며, 잠금 해제 후 로그인과 응답 시험은 성공했습니다.
