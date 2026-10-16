#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
STATE_DIR="${PRIVLEDGER_DEV_STATE_DIR:-${ROOT_DIR}/.privledger/dev}"

API_DIR="${ROOT_DIR}/apps/api"
WEB_DIR="${ROOT_DIR}/apps/web"
API_PORT="${PRIVLEDGER_API_PORT:-4577}"
WEB_PORT="${PRIVLEDGER_WEB_PORT:-5173}"
API_URL="http://127.0.0.1:${API_PORT}"
WEB_URL="http://127.0.0.1:${WEB_PORT}"

API_PID_FILE="${STATE_DIR}/api.pid"
WEB_PID_FILE="${STATE_DIR}/web.pid"
API_LOG_FILE="${STATE_DIR}/api.log"
WEB_LOG_FILE="${STATE_DIR}/web.log"

usage() {
  cat <<EOF
Usage: $(basename "$0") <start|stop|restart|status>

Environment overrides:
  PRIVLEDGER_API_PORT  API port (default: 4577)
  PRIVLEDGER_WEB_PORT  web port (default: 5173)
  PRIVLEDGER_DEV_STATE_DIR  PID/log directory (default: .privledger/dev)
EOF
}

pid_alive() {
  kill -0 "$1" 2>/dev/null
}

pid_command() {
  ps -ww -p "$1" -o command= 2>/dev/null || true
}

managed_pid() {
  local pid="$1"
  local command
  command="$(pid_command "$pid")"
  [[ "$command" == *"npm run dev"* ]]
}

wait_for_exit() {
  local pid="$1"
  local attempt
  for ((attempt = 0; attempt < 50; attempt += 1)); do
    if ! pid_alive "$pid"; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

wait_for_service() {
  local pid_file="$1"
  local url="$2"
  local pid
  local attempt

  pid="$(<"$pid_file")"
  for ((attempt = 0; attempt < 100; attempt += 1)); do
    if ! pid_alive "$pid"; then
      return 1
    fi
    if curl -fsS --max-time 1 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

start_service() {
  local name="$1"
  local directory="$2"
  local pid_file="$3"
  local log_file="$4"
  shift 4

  mkdir -p "$STATE_DIR"

  if [[ -f "$pid_file" ]]; then
    local existing_pid
    existing_pid="$(<"$pid_file")"
    if pid_alive "$existing_pid" && managed_pid "$existing_pid"; then
      echo "$name is already running (pid ${existing_pid})"
      return 0
    fi
    if pid_alive "$existing_pid"; then
      echo "$name PID file points to an unmanaged process (pid ${existing_pid}); refusing to stop it" >&2
      return 1
    fi
    rm -f "$pid_file"
  fi

  : > "$log_file"
  (
    cd "$directory"
    exec nohup env "$@" npm run dev < /dev/null
  ) >>"$log_file" 2>&1 &
  local pid=$!
  printf '%s\n' "$pid" > "$pid_file"
  echo "started $name (pid ${pid}); log: ${log_file}"
}

stop_service() {
  local name="$1"
  local pid_file="$2"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name is not running"
    return 0
  fi

  local pid
  pid="$(<"$pid_file")"
  if ! pid_alive "$pid"; then
    rm -f "$pid_file"
    echo "$name is not running (removed stale PID file)"
    return 0
  fi

  if ! managed_pid "$pid"; then
    echo "$name PID file points to an unmanaged process (pid ${pid}); refusing to stop it" >&2
    return 1
  fi

  kill -TERM "$pid" 2>/dev/null || true
  if ! wait_for_exit "$pid"; then
    echo "$name did not stop gracefully; sending SIGKILL" >&2
    kill -KILL "$pid" 2>/dev/null || true
    wait_for_exit "$pid" || true
  fi
  rm -f "$pid_file"
  echo "stopped $name"
}

start_all() {
  start_service \
    "api" \
    "$API_DIR" \
    "$API_PID_FILE" \
    "$API_LOG_FILE" \
    "PRIVLEDGER_API_PORT=${API_PORT}"

  if ! wait_for_service "$API_PID_FILE" "${API_URL}/api/health"; then
    echo "API did not become healthy; see ${API_LOG_FILE}" >&2
    stop_service "api" "$API_PID_FILE" || true
    return 1
  fi

  start_service \
    "web" \
    "$WEB_DIR" \
    "$WEB_PID_FILE" \
    "$WEB_LOG_FILE" \
    "PRIVLEDGER_WEB_PORT=${WEB_PORT}" \
    "PRIVLEDGER_API_URL=${API_URL}"

  if ! wait_for_service "$WEB_PID_FILE" "$WEB_URL/"; then
    echo "web app did not become ready; see ${WEB_LOG_FILE}" >&2
    stop_service "web" "$WEB_PID_FILE" || true
    stop_service "api" "$API_PID_FILE" || true
    return 1
  fi

  echo "Privledger is running:"
  echo "  API: ${API_URL}"
  echo "  Web: ${WEB_URL}"
}

stop_all() {
  local result=0
  stop_service "web" "$WEB_PID_FILE" || result=1
  stop_service "api" "$API_PID_FILE" || result=1
  return "$result"
}

status_service() {
  local name="$1"
  local pid_file="$2"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name: stopped"
    return 0
  fi

  local pid
  pid="$(<"$pid_file")"
  if pid_alive "$pid" && managed_pid "$pid"; then
    echo "$name: running (pid ${pid})"
  elif pid_alive "$pid"; then
    echo "$name: unmanaged process at recorded pid ${pid}"
  else
    echo "$name: stopped (stale PID file)"
  fi
}

status_all() {
  status_service "api" "$API_PID_FILE"
  status_service "web" "$WEB_PID_FILE"
}

command="${1:-}"
case "$command" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    start_all
    ;;
  status)
    status_all
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
