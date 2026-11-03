#!/usr/bin/env bash
# Official ngrok apt repository, with a repository-scoped signing key.
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -c 'from dotenv import dotenv_values; import sys; sys.exit(0 if dotenv_values(".env").get("NGROK_AUTHTOKEN") else "Run scripts/configure.py --smartthings first.")'
if ! command -v ngrok >/dev/null; then
  key=$(mktemp)
  trap 'rm -f "$key"' EXIT
  curl -fsSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc -o "$key"
  sudo install -m 644 "$key" /usr/share/keyrings/alter-ngrok.asc
  echo 'deb [signed-by=/usr/share/keyrings/alter-ngrok.asc] https://ngrok-agent.s3.amazonaws.com bookworm main' | sudo tee /etc/apt/sources.list.d/ngrok.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y ngrok
fi
lan=$(.venv/bin/python -c 'from dotenv import dotenv_values; print(dotenv_values(".env").get("LAN_CIDR", ""))')
.venv/bin/python scripts/render-deployment.py --lan "$lan"
sudo install -m 644 data/deploy/alter-ngrok.service /etc/systemd/system/alter-ngrok.service
sudo systemctl daemon-reload
sudo systemctl enable --now alter-ngrok
