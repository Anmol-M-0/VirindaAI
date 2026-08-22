#!/usr/bin/env bash
# ==============================================================================
# VirindaAI OpenVoiceOS (OVOS) Runtime Supervisor
# ==============================================================================
# Starts, stops, supervises, and health-checks the complete voice loop:
# 1. ovos-messagebus (WebSocket bus on 127.0.0.1:8181)
# 2. ovos-core (Skills & Persona engine)
# 3. ovos-audio (TTS speech playback service)
# 4. ovos-dinkum-listener (Microphone, wake-word, VAD, whispercpp STT)
# 5. virinda ovos bridge (AssistantService & memory synchronization)
# ==============================================================================

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# Activate virtualenv if present
if [[ -f "${PROJECT_ROOT}/.venv/bin/activate" ]]; then
    export PATH="${PROJECT_ROOT}/.venv/bin:${PATH}"
fi

RUNTIME_DIR="${OVOS_RUNTIME_DIR:-${PROJECT_ROOT}/.runtime/ovos}"
PID_DIR="${RUNTIME_DIR}/pids"
LOG_DIR="${RUNTIME_DIR}/logs"
STATE_FILE="${RUNTIME_DIR}/state"

BUS_HOST="${OVOS_BUS_HOST:-127.0.0.1}"
BUS_PORT="${OVOS_BUS_PORT:-8181}"

STARTUP_TIMEOUT="${OVOS_STARTUP_TIMEOUT:-30}"
SHUTDOWN_TIMEOUT="${OVOS_SHUTDOWN_TIMEOUT:-10}"

VIRINDA_BRIDGE_CMD="${VIRINDA_BRIDGE_CMD:-${PROJECT_ROOT}/virinda ovos bridge --host ${BUS_HOST} --port ${BUS_PORT}}"

mkdir -p "${PID_DIR}" "${LOG_DIR}"

declare -A PIDS=()
declare -A COMMANDS=()

PIDS[messagebus]="${PID_DIR}/messagebus.pid"
PIDS[core]="${PID_DIR}/core.pid"
PIDS[audio]="${PID_DIR}/audio.pid"
PIDS[listener]="${PID_DIR}/listener.pid"
PIDS[bridge]="${PID_DIR}/bridge.pid"

COMMANDS[messagebus]="ovos-messagebus"
COMMANDS[core]="ovos-core"
COMMANDS[audio]="ovos-audio"
COMMANDS[listener]="ovos-dinkum-listener"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

warn() {
    printf '[%s] WARNING: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

die() {
    printf '[%s] ERROR: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
    exit 1
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

require_command() {
    command_exists "$1" || die "Required command not found: $1 (Install with: ./scripts/install-ovos.sh)"
}

pid_from_file() {
    local service="$1"
    local pid_file="${PIDS[$service]}"

    [[ -f "$pid_file" ]] || return 1

    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"

    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    printf '%s\n' "$pid"
}

is_pid_alive() {
    local pid="$1"
    kill -0 "$pid" 2>/dev/null
}

is_running() {
    local service="$1"
    local pid

    pid="$(pid_from_file "$service")" || return 1
    is_pid_alive "$pid"
}

write_pid() {
    local service="$1"
    local pid="$2"

    printf '%s\n' "$pid" > "${PIDS[$service]}"
}

remove_pid() {
    local service="$1"
    rm -f "${PIDS[$service]}"
}

clear_runtime_state() {
    rm -f "${STATE_FILE}"
}

set_runtime_state() {
    printf '%s\n' "$1" > "${STATE_FILE}"
}

runtime_state() {
    [[ -f "$STATE_FILE" ]] && cat "$STATE_FILE" || printf 'STOPPED\n'
}

port_ready() {
    local host="$1"
    local port="$2"

    (echo >/dev/tcp/"${host}"/"${port}") >/dev/null 2>&1
}

wait_for_port() {
    local host="$1"
    local port="$2"
    local timeout="$3"

    local start
    start="$(date +%s)"

    while true; do
        if port_ready "$host" "$port"; then
            return 0
        fi

        if (( "$(date +%s)" - start >= timeout )); then
            return 1
        fi

        sleep 0.2
    done
}

wait_for_process() {
    local service="$1"
    local timeout="$2"

    local start
    start="$(date +%s)"

    while true; do
        if is_running "$service"; then
            return 0
        fi

        if (( "$(date +%s)" - start >= timeout )); then
            return 1
        fi

        sleep 0.2
    done
}

cleanup_stale_pid() {
    local service="$1"

    if [[ -f "${PIDS[$service]}" ]] && ! is_running "$service"; then
        remove_pid "$service"
    fi
}

preflight() {
    require_command bash
    require_command setsid

    require_command ovos-messagebus
    require_command ovos-core
    require_command ovos-audio
    require_command ovos-dinkum-listener

    if [[ -z "${VIRINDA_BRIDGE_CMD}" ]]; then
        die "VIRINDA_BRIDGE_CMD is not configured"
    fi

    if port_ready "$BUS_HOST" "$BUS_PORT"; then
        die "OVOS messagebus port ${BUS_HOST}:${BUS_PORT} is already occupied"
    fi

    for service in messagebus core audio listener bridge; do
        cleanup_stale_pid "$service"
    done
}

start_service() {
    local service="$1"
    local command="$2"

    if is_running "$service"; then
        die "${service} is already running"
    fi

    log "Starting ${service}: ${command}"

    local log_file="${LOG_DIR}/${service}.log"

    setsid bash -c 'exec "$@"' _ bash -lc "$command" \
        >>"${log_file}" 2>&1 &

    local pid=$!

    write_pid "$service" "$pid"

    sleep 0.3

    if ! is_pid_alive "$pid"; then
        remove_pid "$service"
        die "${service} exited immediately; see ${log_file}"
    fi
}

start_bridge() {
    start_service bridge "${VIRINDA_BRIDGE_CMD}"
}

start_stack() {
    preflight

    if [[ "$(runtime_state)" == "RUNNING" ]]; then
        die "Virinda OVOS runtime is already RUNNING"
    fi

    log "Starting VirindaAI OVOS runtime"
    set_runtime_state "STARTING"

    # 1. Message bus
    start_service messagebus "${COMMANDS[messagebus]}"
    log "Waiting for OVOS messagebus ${BUS_HOST}:${BUS_PORT}..."
    if ! wait_for_port "$BUS_HOST" "$BUS_PORT" "$STARTUP_TIMEOUT"; then
        stop_stack
        die "OVOS messagebus did not become ready"
    fi
    log "✔ Messagebus is ready."

    # 2. Core (skills & persona)
    start_service core "${COMMANDS[core]}"
    if ! wait_for_process core "$STARTUP_TIMEOUT"; then
        stop_stack
        die "ovos-core failed to remain running"
    fi
    log "✔ ovos-core is ready."

    # 3. Audio (TTS)
    start_service audio "${COMMANDS[audio]}"
    if ! wait_for_process audio "$STARTUP_TIMEOUT"; then
        stop_stack
        die "ovos-audio failed to remain running"
    fi
    log "✔ ovos-audio is ready."

    # 4. Listener (Mic, VAD, STT)
    start_service listener "${COMMANDS[listener]}"
    if ! wait_for_process listener "$STARTUP_TIMEOUT"; then
        stop_stack
        die "ovos-dinkum-listener failed to remain running"
    fi
    log "✔ ovos-dinkum-listener is ready."

    # 5. Virinda bridge
    start_bridge
    if ! wait_for_process bridge "$STARTUP_TIMEOUT"; then
        stop_stack
        die "Virinda bridge failed to remain running"
    fi
    log "✔ Virinda bridge is ready."

    set_runtime_state "RUNNING"
    log "================================================================="
    log "  VirindaAI OpenVoiceOS Voice Loop is ACTIVE and RUNNING!        "
    log "================================================================="
}

terminate_service() {
    local service="$1"
    local pid

    pid="$(pid_from_file "$service")" || return 0

    if ! is_pid_alive "$pid"; then
        remove_pid "$service"
        return 0
    fi

    log "Stopping ${service} (pid=${pid})"
    kill -TERM -- "-${pid}" 2>/dev/null || true

    local start
    start="$(date +%s)"

    while is_pid_alive "$pid"; do
        if (( "$(date +%s)" - start >= SHUTDOWN_TIMEOUT )); then
            warn "${service} did not stop gracefully; sending SIGKILL"
            kill -KILL -- "-${pid}" 2>/dev/null || true
            break
        fi
        sleep 0.2
    done

    remove_pid "$service"
}

stop_stack() {
    log "Stopping VirindaAI OVOS runtime..."
    set_runtime_state "STOPPING"

    # Strict reverse dependency order
    terminate_service bridge
    terminate_service listener
    terminate_service audio
    terminate_service core
    terminate_service messagebus

    set_runtime_state "STOPPED"
    log "✔ All Virinda OVOS services cleanly terminated."
}

status_stack() {
    local state
    state="$(runtime_state)"

    printf 'Runtime State : %s\n' "$state"
    printf 'Bus Endpoint  : ws://%s:%s/core\n' "$BUS_HOST" "$BUS_PORT"
    printf 'Log Directory : %s\n' "$LOG_DIR"
    printf '%s\n' "-----------------------------------------------------------------"

    for service in messagebus core audio listener bridge; do
        if is_running "$service"; then
            local pid
            pid="$(pid_from_file "$service")"
            printf '%-15s : [RUNNING] (pid=%s)\n' "$service" "$pid"
        else
            printf '%-15s : [STOPPED]\n' "$service"
        fi
    done
}

supervise_foreground() {
    trap 'log "Received interrupt signal. Initiating clean teardown..."; stop_stack; exit 0' INT TERM EXIT

    start_stack

    log "Supervising services in foreground. Press [Ctrl+C] to stop."

    while true; do
        for service in messagebus core audio listener bridge; do
            if ! is_running "$service"; then
                die "${service} crashed or stopped unexpectedly! Aborting stack."
            fi
        done
        sleep 1
    done
}

usage() {
    cat <<EOF
VirindaAI OVOS Runtime Supervisor

Usage:
  $(basename "$0") start [--foreground | --daemon]
  $(basename "$0") stop
  $(basename "$0") restart
  $(basename "$0") status
  $(basename "$0") logs [service]

Services Managed:
  • messagebus : ovos-messagebus (ws://127.0.0.1:8181/core)
  • core       : ovos-core (intent & persona engine)
  • audio      : ovos-audio (TTS playback engine)
  • listener   : ovos-dinkum-listener (mic, wake-word, VAD, STT)
  • bridge     : virinda ovos bridge (Virinda state coordinator)
EOF
    exit 1
}

# Entrypoint
ACTION="${1:-}"
MODE="${2:---foreground}"

case "$ACTION" in
    start)
        if [[ "$MODE" == "--daemon" ]]; then
            start_stack
        else
            supervise_foreground
        fi
        ;;
    stop)
        stop_stack
        ;;
    restart)
        stop_stack
        sleep 1
        start_stack
        ;;
    status)
        status_stack
        ;;
    logs)
        SVC="${2:-}"
        if [[ -n "$SVC" && -f "${LOG_DIR}/${SVC}.log" ]]; then
            tail -f "${LOG_DIR}/${SVC}.log"
        else
            tail -f "${LOG_DIR}"/*.log
        fi
        ;;
    *)
        usage
        ;;
esac
