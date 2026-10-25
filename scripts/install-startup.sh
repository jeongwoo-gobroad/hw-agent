#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for unit in alter alter-llm alter-ngrok alter-oauth alter-photos alter-recovery; do
  sudo install -m 644 "deploy/$unit.service" "/etc/systemd/system/$unit.service"
done
bash scripts/install-web-entrypoints.sh
chmod +x start.sh Start-Alter.desktop
sudo systemctl daemon-reload
sudo systemctl enable alter alter-llm alter-ngrok alter-oauth alter-photos alter-recovery smbd
mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/autostart"
install -m 644 deploy/alter-display.service "$HOME/.config/systemd/user/"
install -m 644 deploy/alter-panel.desktop "$HOME/.config/autostart/"
install -m 644 deploy/alter-display.desktop "$HOME/.config/autostart/"
systemctl --user daemon-reload
systemctl --user enable --now alter-display.service
