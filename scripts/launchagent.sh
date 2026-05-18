#!/usr/bin/env bash
# Manage the brickset-tracker LaunchAgent.
# Usage: ./scripts/launchagent.sh {install|uninstall|status}
set -euo pipefail

LABEL="de.hhalfpap.brickset-tracker"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="${PROJECT_ROOT}/scripts/${LABEL}.plist.template"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG="${HOME}/Library/Logs/brickset-tracker.log"

read_port_from_env() {
  local p
  p="$(grep -E '^PORT=' "${PROJECT_ROOT}/.env" 2>/dev/null | cut -d= -f2 | tr -d ' "' || true)"
  echo "${p:-8000}"
}

find_free_port() {
  # Scan from $1 upward for up to 100 ports; echo first free, return 1 if none.
  local start="$1"
  local max=$((start + 99))
  local p
  for ((p=start; p<=max; p++)); do
    if ! nc -z -G 1 127.0.0.1 "${p}" >/dev/null 2>&1; then
      echo "${p}"
      return 0
    fi
  done
  return 1
}

write_port_to_env() {
  local port="$1"
  local env="${PROJECT_ROOT}/.env"
  if grep -qE '^PORT=' "${env}" 2>/dev/null; then
    # BSD sed: -i needs '' for in-place with no backup
    sed -i '' -E "s|^PORT=.*|PORT=${port}|" "${env}"
  else
    printf '\nPORT=%s\n' "${port}" >> "${env}"
  fi
}

cmd_install() {
  # Pre-flight: venv must exist
  if [[ ! -x "${PROJECT_ROOT}/.venv/bin/uvicorn" ]]; then
    echo "ERROR: ${PROJECT_ROOT}/.venv/bin/uvicorn not found."
    echo "Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
  fi

  # If already loaded, unload first so the new plist takes effect
  if launchctl list "${LABEL}" >/dev/null 2>&1; then
    launchctl unload "${PLIST}" 2>/dev/null || true
  fi

  local start_port
  start_port="$(read_port_from_env)"

  local port
  if ! port="$(find_free_port "${start_port}")"; then
    echo "ERROR: no free port in ${start_port}..$((start_port + 99))."
    echo "Check what's bound: lsof -nP -iTCP -sTCP:LISTEN | grep 80"
    exit 1
  fi

  if [[ "${port}" != "${start_port}" ]]; then
    echo "Port ${start_port} busy — using ${port} instead."
  fi
  write_port_to_env "${port}"

  # Render template
  sed -e "s|__PROJECT_ROOT__|${PROJECT_ROOT}|g" \
      -e "s|__HOME__|${HOME}|g" \
      -e "s|__PORT__|${port}|g" \
      "${TEMPLATE}" > "${PLIST}"

  # Validate the rendered plist
  if ! plutil -lint "${PLIST}" >/dev/null; then
    echo "ERROR: rendered plist failed plutil -lint. Aborting."
    rm -f "${PLIST}"
    exit 1
  fi

  # Ensure log directory exists (LaunchAgents won't create parent dirs)
  mkdir -p "$(dirname "${LOG}")"

  # Load
  launchctl load -w "${PLIST}"

  # Smoke check: poll for up to 15s (one probe per second). FastAPI cold-start
  # with the brickset-tracker import graph can take ~8–12s on a slow disk.
  local i
  for i in $(seq 1 15); do
    if curl -fsS "http://localhost:${port}/" >/dev/null 2>&1; then
      echo "✓ LaunchAgent installed and responding on http://localhost:${port}/"
      echo "  Logs:  ${LOG}"
      echo "  Plist: ${PLIST}"
      return 0
    fi
    sleep 1
  done
  echo "ERROR: LaunchAgent loaded but server did not respond on port ${port} within 15s."
  echo "The agent is likely loaded — check 'launchctl list ${LABEL}' and tail -50 ${LOG}"
  exit 1
}

case "${1:-}" in
  install) cmd_install ;;
  *) echo "Usage: $0 {install|uninstall|status}"; exit 2 ;;
esac
