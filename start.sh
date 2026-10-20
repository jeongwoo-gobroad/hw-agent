#!/usr/bin/env bash
set -u
cd -- "$(dirname -- "$(readlink -f -- "$0")")"
if [[ ! -x .venv/bin/python || ! -f .env ]]; then
  echo "설치 환경 또는 .env가 없습니다. README의 설치 절차를 확인하세요."
  exit 1
fi
units=(alter.service alter-llm.service alter-ngrok.service alter-oauth.service smbd.service)
missing=()
for unit in "${units[@]}"; do
  state=$(systemctl is-active "$unit" || true)
  [[ "$state" == active || "$state" == activating || "$state" == reloading ]] || missing+=("$unit")
done
if ((${#missing[@]})); then
  echo "중지된 서비스를 시작합니다. 필요한 경우 Pi 계정 암호를 입력하세요."
  sudo systemctl reset-failed "${missing[@]}" || exit 1
  sudo systemctl start "${missing[@]}" || exit 1
fi
systemctl --user start alter-display.service 2>/dev/null || true
PYTHONPATH="$PWD/src" .venv/bin/python scripts/recover.py
result=$?
if [[ "${1:-}" != "--no-browser" ]]; then
  xdg-open http://127.0.0.1:8080/panel >/dev/null 2>&1 || true
  read -r -p "확인이 끝나면 Enter를 누르세요. " || true
fi
exit "$result"
