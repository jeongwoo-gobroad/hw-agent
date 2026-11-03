#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$EUID" != 0 ]] || { echo "Run as your Pi account, without sudo." >&2; exit 1; }
sudo apt-get update
sudo apt-get install -y git curl libimage-exiftool-perl python3-venv python3-picamera2 ffmpeg samba smbclient wsdd2 ntfs-3g libopenblas-dev cmake g++ libcurl4-openssl-dev libheif-dev
sudo systemctl enable --now wsdd2
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
if [[ ! -f .env ]]; then
  .venv/bin/python scripts/configure.py --lang "${ALTER_LANGUAGE:-en}"
fi
chmod 600 .env
lan=$(.venv/bin/python -c 'from dotenv import dotenv_values; print(dotenv_values(".env").get("LAN_CIDR", ""))')
[[ -n "$lan" ]] || { echo "Set LAN_CIDR in .env first." >&2; exit 1; }
.venv/bin/python scripts/render-deployment.py --lan "$lan"
.venv/bin/python scripts/install-vision.py
.venv/bin/python scripts/install-photo-models.py
test -f .env || { echo "Create .env from .env.example first." >&2; exit 1; }
chmod 600 .env
sudo install -o root -g root -m 755 data/deploy/alter-smb /usr/local/sbin/alter-smb
sudo install -o root -g root -m 755 data/deploy/alter-disk /usr/local/sbin/alter-disk
sudo visudo -cf data/deploy/alter-sudoers
sudo install -o root -g root -m 440 data/deploy/alter-sudoers /etc/sudoers.d/alter-smb
for unit in alter alter-oauth alter-photos; do
  sudo install -m 644 "data/deploy/$unit.service" "/etc/systemd/system/$unit.service"
done
sudo systemctl daemon-reload
bash scripts/install-web-entrypoints.sh
sudo systemctl enable --now alter alter-oauth alter-photos
echo "Dashboard ready. Follow docs/setup.md for the language model, Samba, ngrok and the touch panel."
