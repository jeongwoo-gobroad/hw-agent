#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(id -un)" != jeongwoo || "$PWD" != /home/jeongwoo/hw-agent ]]; then
  echo "This deployment targets /home/jeongwoo/hw-agent as jeongwoo." >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y libimage-exiftool-perl python3-venv python3-picamera2 ffmpeg samba smbclient wsdd2 libopenblas-dev cmake g++ libcurl4-openssl-dev libheif-dev
sudo systemctl enable --now wsdd2
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/install-vision.py
.venv/bin/python scripts/install-photo-models.py
test -f .env || { echo "Create .env from .env.example first." >&2; exit 1; }
chmod 600 .env
sudo install -o root -g root -m 755 deploy/alter-smb /usr/local/sbin/alter-smb
sudo install -o root -g root -m 755 deploy/alter-disk /usr/local/sbin/alter-disk
printf 'jeongwoo ALL=(root) NOPASSWD: /usr/local/sbin/alter-smb, /usr/local/sbin/alter-disk\n' | sudo tee /etc/sudoers.d/alter-smb >/dev/null
sudo chmod 440 /etc/sudoers.d/alter-smb
sudo visudo -cf /etc/sudoers.d/alter-smb
sudo install -m 644 deploy/alter.service /etc/systemd/system/alter.service
sudo install -m 644 deploy/alter-oauth.service /etc/systemd/system/alter-oauth.service
sudo install -m 644 deploy/alter-photos.service /etc/systemd/system/alter-photos.service
sudo systemctl daemon-reload
bash scripts/install-web-entrypoints.sh
sudo systemctl enable --now alter alter-oauth alter-photos
echo "Configure Samba using docs/operations.md before enabling shares."
