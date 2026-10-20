#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p tools models
if [ ! -d tools/whisper.cpp ]; then
  git clone --depth 1 --branch v1.8.3 https://github.com/ggml-org/whisper.cpp.git tools/whisper.cpp
fi
cmake -S tools/whisper.cpp -B tools/whisper.cpp/build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DWHISPER_BUILD_TESTS=OFF
cmake --build tools/whisper.cpp/build -j2 --target whisper-cli
if [ ! -f models/ggml-tiny.bin ]; then
  curl -fL --retry 3 https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin -o models/ggml-tiny.bin.partial
  mv models/ggml-tiny.bin.partial models/ggml-tiny.bin
fi
