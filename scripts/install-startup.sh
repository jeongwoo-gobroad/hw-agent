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
desktop_dir="$(xdg-user-dir DESKTOP)"
mkdir -p "$desktop_dir"
# 시스템에 설치한 앱을 링크하면 PCManFM의 스크립트 실행 확인창을 피할 수 있습니다.
sudo install -D -m 644 deploy/alter-dashboard.desktop /usr/local/share/applications/alter-dashboard.desktop
install -m 644 deploy/alter-dashboard-link.desktop "$desktop_dir/Alter-Dashboard.desktop"
systemctl --user daemon-reload
systemctl --user enable --now alter-display.service
