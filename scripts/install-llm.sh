#!/usr/bin/env bash
# Pinned upstream runtime and weights; existing matching downloads are reused.
set -euo pipefail
cd "$(dirname "$0")/.."
sudo apt-get install -y git curl cmake g++ libopenblas-dev libcurl4-openssl-dev
mkdir -p data/build models
runtime=data/build/llama.cpp
revision=704366d76f8748cf9ad3df62a464bfcc8d1ae6ad
if [[ ! -d "$runtime/.git" ]]; then
  git clone https://github.com/ggml-org/llama.cpp.git "$runtime"
fi
[[ -z "$(git -C "$runtime" status --porcelain)" ]] || { echo 'Runtime has local changes; preserve them before installation.' >&2; exit 1; }
git -C "$runtime" fetch origin "$revision"
git -C "$runtime" checkout --detach "$revision"
cmake -S "$runtime" -B "$runtime/build" -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS -DLLAMA_BUILD_TESTS=OFF
cmake --build "$runtime/build" --target llama-server -j2
model=models/Qwen3.5-4B-Q4_K_M.gguf
digest=00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4
if ! echo "$digest  $model" | sha256sum --check --status; then
  curl --fail --location --continue-at - --output "$model.part" 'https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf'
  echo "$digest  $model.part" | sha256sum --check
  mv "$model.part" "$model"
fi
.venv/bin/python -c 'from pathlib import Path; import secrets; p=Path("data/llm-api-key"); p.exists() or p.write_text(secrets.token_urlsafe(48)); p.chmod(0o600)'
lan=$(.venv/bin/python -c 'from dotenv import dotenv_values; print(dotenv_values(".env").get("LAN_CIDR", ""))')
.venv/bin/python scripts/render-deployment.py --lan "$lan"
sudo install -m 644 data/deploy/alter-llm.service /etc/systemd/system/alter-llm.service
sudo systemctl daemon-reload
sudo systemctl enable --now alter-llm

# The web process reads the model key on startup.
if systemctl is-active --quiet alter; then sudo systemctl restart alter; fi
