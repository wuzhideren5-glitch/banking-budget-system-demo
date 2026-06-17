#!/usr/bin/env bash
# Start the banking budget test environment services.
# Backend: FastAPI on 8009. Frontend: Vite on 8443 for the test server.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$ROOT_DIR/apps/api"
WEB_DIR="$ROOT_DIR/apps/web"
PID_DIR="$ROOT_DIR/var/pids"
LOG_DIR="$ROOT_DIR/var/logs"
BACKEND_PORT="8009"
FRONTEND_PORT="8443"
BACKEND_RELOAD="${BACKEND_RELOAD:-0}"
BACKEND_SCREEN_SESSION="banking-budget-api"
FRONTEND_SCREEN_SESSION="banking-budget-web"

mkdir -p "$PID_DIR" "$LOG_DIR" "$ROOT_DIR/var/data" "$ROOT_DIR/var/output"

is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid
        pid="$(cat "$pid_file")"
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        rm -f "$pid_file"
    fi
    return 1
}

screen_running() {
    local session_name="$1"
    if ! command -v screen >/dev/null 2>&1; then
        return 1
    fi
    local sessions
    sessions="$(screen -ls 2>/dev/null || true)"
    grep -q "[.]${session_name}[[:space:]]" <<< "$sessions"
}

port_listening() {
    local port="$1"
    lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

start_screen() {
    local session_name="$1"
    local command_text="$2"

    screen -dmS "$session_name" bash -lc "$command_text"
}

run_frontend_install() {
    cd "$ROOT_DIR"
    npm install --include=optional
}

run_frontend_dev() {
    cd "$WEB_DIR"
    npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
}

api_python() {
    if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
        echo "$ROOT_DIR/.venv/bin/python"
    elif [ -x "$API_DIR/.venv/bin/python" ]; then
        echo "$API_DIR/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        echo "python3"
    else
        echo "python"
    fi
}

prepare_deploy_generated_paths() {
    local python_bin
    python_bin="$(api_python)"

    "$python_bin" "$API_DIR/scripts/prepare_deploy_generated_paths.py" --data-dir "$ROOT_DIR/var/data"
}

start_detached() {
    local pid_file="$1"
    local log_file="$2"
    shift 2

    nohup "$@" > "$log_file" 2>&1 &
    echo $! > "$pid_file"
}

frontend_deps_need_install() {
    if [ ! -d "$ROOT_DIR/node_modules" ] && [ ! -d "$WEB_DIR/node_modules" ]; then
        return 0
    fi

    # Rollup/Vite rely on platform-specific optional native packages.
    # A copied or --omit=optional install can leave Linux servers without this module.
    if [ "$(uname -s)" = "Linux" ] && [ "$(uname -m)" = "x86_64" ]; then
        if [ ! -d "$ROOT_DIR/node_modules/@rollup/rollup-linux-x64-gnu" ] &&
           [ ! -d "$WEB_DIR/node_modules/@rollup/rollup-linux-x64-gnu" ]; then
            echo "[setup] missing Rollup Linux optional package, reinstalling frontend dependencies"
            return 0
        fi
    fi

    return 1
}

if screen_running "$BACKEND_SCREEN_SESSION"; then
    echo "[skip] backend is already running (screen: $BACKEND_SCREEN_SESSION)"
elif is_running "$PID_DIR/backend.pid"; then
    echo "[skip] backend is already running (PID $(cat "$PID_DIR/backend.pid"))"
elif port_listening "$BACKEND_PORT"; then
    echo "[skip] backend port $BACKEND_PORT is already in use"
else
    echo "[setup] preparing Smart Report/PPT generated-file paths"
    prepare_deploy_generated_paths
    echo "[start] backend FastAPI service on 0.0.0.0:$BACKEND_PORT"
    cd "$API_DIR"
    backend_args=(run_server.py --host 0.0.0.0 --port "$BACKEND_PORT")
    if [ "$BACKEND_RELOAD" = "1" ]; then
        backend_args=(run_server.py --reload --host 0.0.0.0 --port "$BACKEND_PORT")
    fi
    if command -v screen >/dev/null 2>&1 && [ "$BACKEND_RELOAD" != "1" ]; then
        rm -f "$PID_DIR/backend.pid"
        python_bin="$(api_python)"
        if [ "$python_bin" != "python3" ] && [ "$python_bin" != "python" ]; then
            start_screen "$BACKEND_SCREEN_SESSION" "cd '$API_DIR' && exec '$python_bin' run_server.py --host 0.0.0.0 --port '$BACKEND_PORT' >> '$LOG_DIR/backend.log' 2>&1"
        elif command -v uv >/dev/null 2>&1; then
            start_screen "$BACKEND_SCREEN_SESSION" "cd '$API_DIR' && exec uv run uvicorn app.main:app --host 0.0.0.0 --port '$BACKEND_PORT' >> '$LOG_DIR/backend.log' 2>&1"
        else
            start_screen "$BACKEND_SCREEN_SESSION" "cd '$API_DIR' && exec python3 run_server.py --host 0.0.0.0 --port '$BACKEND_PORT' >> '$LOG_DIR/backend.log' 2>&1"
        fi
        echo "       screen: $BACKEND_SCREEN_SESSION"
        echo "       log: $LOG_DIR/backend.log"
    elif python_bin="$(api_python)" && [ "$python_bin" != "python3" ] && [ "$python_bin" != "python" ]; then
        start_detached "$PID_DIR/backend.pid" "$LOG_DIR/backend.log" "$python_bin" "${backend_args[@]}"
        echo "       pid: $(cat "$PID_DIR/backend.pid")"
        echo "       log: $LOG_DIR/backend.log"
    elif command -v uv >/dev/null 2>&1; then
        uv_args=(run uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT")
        if [ "$BACKEND_RELOAD" = "1" ]; then
            uv_args=(run uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT")
        fi
        start_detached "$PID_DIR/backend.pid" "$LOG_DIR/backend.log" uv "${uv_args[@]}"
        echo "       pid: $(cat "$PID_DIR/backend.pid")"
        echo "       log: $LOG_DIR/backend.log"
    else
        start_detached "$PID_DIR/backend.pid" "$LOG_DIR/backend.log" python3 "${backend_args[@]}"
        echo "       pid: $(cat "$PID_DIR/backend.pid")"
        echo "       log: $LOG_DIR/backend.log"
    fi
    cd "$ROOT_DIR"
fi

if screen_running "$FRONTEND_SCREEN_SESSION"; then
    echo "[skip] frontend is already running (screen: $FRONTEND_SCREEN_SESSION)"
elif is_running "$PID_DIR/frontend.pid"; then
    echo "[skip] frontend is already running (PID $(cat "$PID_DIR/frontend.pid"))"
elif port_listening "$FRONTEND_PORT"; then
    echo "[skip] frontend port $FRONTEND_PORT is already in use"
else
    if frontend_deps_need_install; then
        echo "[setup] installing frontend dependencies"
        run_frontend_install
    fi
    echo "[start] frontend Vite service on 0.0.0.0:$FRONTEND_PORT"
    if command -v screen >/dev/null 2>&1; then
        rm -f "$PID_DIR/frontend.pid"
        start_screen "$FRONTEND_SCREEN_SESSION" "cd '$WEB_DIR' && exec npm run dev -- --host 0.0.0.0 --port '$FRONTEND_PORT' >> '$LOG_DIR/frontend.log' 2>&1"
        echo "       screen: $FRONTEND_SCREEN_SESSION"
    else
        start_detached "$PID_DIR/frontend.pid" "$LOG_DIR/frontend.log" bash -lc "cd '$WEB_DIR' && npm run dev -- --host 0.0.0.0 --port '$FRONTEND_PORT'"
        echo "       pid: $(cat "$PID_DIR/frontend.pid")"
    fi
    echo "       log: $LOG_DIR/frontend.log"
fi

echo ""
echo "Services started:"
echo "  backend:  http://127.0.0.1:$BACKEND_PORT"
echo "  frontend: http://127.0.0.1:$FRONTEND_PORT"
echo "  docs:     http://127.0.0.1:$BACKEND_PORT/docs"
echo ""
echo "Stop services with: bash stop.sh"
