#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v nginx >/dev/null || { sudo apt-get update; sudo apt-get install -y nginx; }
sudo install -m 644 deploy/alter-proxy-map.conf /etc/nginx/conf.d/alter-proxy-map.conf
sudo install -m 644 deploy/alter-nginx.conf /etc/nginx/sites-available/alter
sudo ln -sfn /etc/nginx/sites-available/alter /etc/nginx/sites-enabled/alter
if [[ "$(readlink /etc/nginx/sites-enabled/default || true)" == /etc/nginx/sites-available/default ]]; then
  sudo rm /etc/nginx/sites-enabled/default
fi
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx
