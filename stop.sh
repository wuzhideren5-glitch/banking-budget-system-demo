#!/usr/bin/env bash
# Stop the banking budget test environment services started by start.sh.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$ROOT_DIR/var/pids"
BACKEND_SCREEN_SESSION="banking-budget-api"
FRONTEND_SCREEN_SESSION="banking-budget-web"
BACKEND_PORT="8009"
FRONTEND_PORT="8443"

screen_running() {
    local session_name="$1"
    if ! command -v screen >/dev/null 2>&1; then
        return 1
    fi
    local sessions
    sessions="$(screen -ls 2>/dev/null || true)"
    grep -q "[.]${session_name}[[:space:]]" <<< "$sessions"
}

stop_screen() {
    local name="$1"
    local session_name="$2"

    if ! screen_running "$session_name"; then
        return
    fi

    echo "[stop] $name (screen: $session_name)"
    local sessions
    sessions="$(screen -ls 2>/dev/null || true)"
    while read -r screen_id; do
        if [ -n "$screen_id" ]; then
            screen -S "$screen_id" -X quit 2>/dev/null || true
        fi
    done < <(awk -v session_name="$session_name" '$1 ~ "[.]" session_name "$" { print $1 }' <<< "$sessions")

    for _ in $(seq 1 10); do
        if ! screen_running "$session_name"; then
            break
        fi
        sleep 0.5
    done
}

stop_process() {
    local name="$1"
    local pid_file="$PID_DIR/$name.pid"

    if [ ! -f "$pid_file" ]; then
        echo "[skip] $name is not running (no PID file)"
        return
    fi

    local pid
    pid="$(cat "$pid_file")"

    if kill -0 "$pid" 2>/dev/null; then
        echo "[stop] $name (PID $pid)"
        kill "$pid" 2>/dev/null || true
        for _ in $(seq 1 10); do
            if ! kill -0 "$pid" 2>/dev/null; then
                break
            fi
            sleep 0.5
        done
        if kill -0 "$pid" 2>/dev/null; then
            echo "[force] $name"
            kill -9 "$pid" 2>/dev/null || true
        fi
    else
        echo "[skip] $name PID $pid has already exited"
    fi

    rm -f "$pid_file"
}

stop_port_listener() {
    local name="$1"
    local port="$2"
    local pids

    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -z "$pids" ]; then
        return
    fi

    echo "[stop] $name listener(s) on port $port: $pids"
    while read -r pid; do
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null || true
        fi
    done <<< "$pids"

    for _ in $(seq 1 10); do
        if [ -z "$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)" ]; then
            return
        fi
        sleep 0.5
    done

    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    while read -r pid; do
        if [ -n "$pid" ]; then
            echo "[force] $name listener PID $pid"
            kill -9 "$pid" 2>/dev/null || true
        fi
    done <<< "$pids"
}

stop_screen "frontend" "$FRONTEND_SCREEN_SESSION"
stop_screen "backend" "$BACKEND_SCREEN_SESSION"
stop_process "frontend"
stop_process "backend"
stop_port_listener "frontend" "$FRONTEND_PORT"
stop_port_listener "backend" "$BACKEND_PORT"

echo ""
echo "All services stopped."
