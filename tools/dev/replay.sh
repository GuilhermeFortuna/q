# shellcheck shell=bash
# Replay simulator lifecycle (Q-145). Sourced by ./dev; relies on its helpers (die, need,
# check_port, wait_for, systemd_available, ensure_systemd_user, BACKEND_DIR, STATE_DIR).
#
# The simulator is an isolated process group: its own run-scoped state, ports and systemd unit.
# It never touches the live or research stacks, and nothing here starts Wine, MT5, Docker or GPU
# services. A new run needs the previous simulator stopped, so run state is never reused.

REPLAY_STATE_DIR="${Q_REPLAY_STATE_DIR:-${STATE_DIR}/replay}"
REPLAY_ADMIN_PORT="${Q_REPLAY_ADMIN_PORT:-18914}"
REPLAY_MARKET_PORT="${Q_REPLAY_MARKET_PORT:-18912}"
REPLAY_EDGE_PORT="${Q_REPLAY_EDGE_PORT:-18913}"
REPLAY_UNIT="q-replay.service"
REPLAY_BIN="${Q_REPLAY_BIN:-$BACKEND_DIR/.venv/bin/q-replay}"
REPLAY_ADMIN_URL="http://127.0.0.1:${REPLAY_ADMIN_PORT}"
REPLAY_TEMPLATE="$BACKEND_DIR/deploy/systemd/replay/q-replay.service.in"
REPLAY_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
REPLAY_ENV_FILE="$REPLAY_STATE_DIR/replay.env"

replay_unit_active() {
  systemd_available && systemctl --user is-active --quiet "$REPLAY_UNIT" 2>/dev/null
}

replay_ready() {
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "$REPLAY_ADMIN_URL/replay/v1/runs/current" 2>/dev/null || true)"
  [[ "$code" == "200" || "$code" == "404" ]]
}

replay_write_env() {
  local run_dir="$1" root="$2"
  mkdir -p "$REPLAY_STATE_DIR"
  cat >"$REPLAY_ENV_FILE" <<ENV
Q_REPLAY_STORE=$run_dir/replay.sqlite3
Q_REPLAY_ROOT=$root
Q_REPLAY_MARKET_PORT=$REPLAY_MARKET_PORT
Q_REPLAY_EDGE_PORT=$REPLAY_EDGE_PORT
Q_REPLAY_ADMIN_PORT=$REPLAY_ADMIN_PORT
ENV
  chmod 600 "$REPLAY_ENV_FILE"
}

replay_install_unit() {
  [[ -f "$REPLAY_TEMPLATE" ]] || die "missing replay unit template: $REPLAY_TEMPLATE"
  mkdir -p "$REPLAY_UNIT_DIR"
  sed \
    -e "s|__REPLAY_ENV_FILE__|$REPLAY_ENV_FILE|g" \
    -e "s|__REPLAY_BIN__|$REPLAY_BIN|g" \
    "$REPLAY_TEMPLATE" >"$REPLAY_UNIT_DIR/$REPLAY_UNIT"
}

cmd_replay() {
  local config="" root=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --config) config="${2:-}"; shift 2 ;;
      --root) root="${2:-}"; shift 2 ;;
      *) die "unknown replay option: $1 (expected --config <path> [--root <dir>])" ;;
    esac
  done
  [[ -n "$config" ]] || die "./dev replay requires --config <path>"
  [[ -f "$config" ]] || die "replay config not found: $config"
  root="${root:-$(dirname "$(readlink -f "$config")")}"
  need curl
  [[ -x "$REPLAY_BIN" ]] || die "q-replay is not installed; run uv sync in q_backend (or set Q_REPLAY_BIN)"
  ensure_systemd_user

  if replay_unit_active; then
    die "the replay simulator is already running; stop it with ./dev down replay before a new run"
  fi
  local port
  for port in "$REPLAY_MARKET_PORT" "$REPLAY_EDGE_PORT" "$REPLAY_ADMIN_PORT"; do
    if check_port "$port"; then
      die "replay port $port is already in use; set Q_REPLAY_MARKET_PORT, Q_REPLAY_EDGE_PORT or Q_REPLAY_ADMIN_PORT"
    fi
  done

  # Offline verification first: a bad config, a mutated input or an uncovered interval stops here.
  "$REPLAY_BIN" prepare --config "$config" --root "$root" >/dev/null \
    || die "replay config or dataset failed verification (run q-replay prepare for details)"

  local stamp run_dir
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  run_dir="$REPLAY_STATE_DIR/runs/$stamp"
  mkdir -p "$run_dir"
  replay_write_env "$run_dir" "$root"
  replay_install_unit
  systemctl --user daemon-reload
  systemctl --user start "$REPLAY_UNIT"
  wait_for "replay simulator" "journalctl --user -u $REPLAY_UNIT -n 30 --no-pager" replay_ready
  "$REPLAY_BIN" --url "$REPLAY_ADMIN_URL" create --config "$config" >/dev/null \
    || die "replay run creation failed (see journalctl --user -u $REPLAY_UNIT)"
  echo "==> Replay prepared and paused (run state: $run_dir)."
  echo "    Resume after deployment setup: $REPLAY_BIN --url $REPLAY_ADMIN_URL resume"
  echo "    Stop: ./dev down replay. Live and research stacks are not affected."
}

cmd_down_replay() {
  if systemd_available; then
    systemctl --user stop "$REPLAY_UNIT" 2>/dev/null || true
  fi
  echo "==> Replay simulator stopped (run state kept for inspection)."
}

cmd_restart_replay() {
  ensure_systemd_user
  [[ -f "$REPLAY_UNIT_DIR/$REPLAY_UNIT" ]] || die "$REPLAY_UNIT is not installed; start with ./dev replay --config <path>"
  systemctl --user restart "$REPLAY_UNIT"
  wait_for "replay simulator" "journalctl --user -u $REPLAY_UNIT -n 30 --no-pager" replay_ready
  echo "restarted $REPLAY_UNIT"
}

replay_status_lines() {
  local state="stopped" readiness="-"
  if replay_unit_active; then
    state="active"
    readiness="$(replay_ready && echo ready || echo not-ready)"
  fi
  printf "%-20s %-28s %-18s %s\n" "replay" "q-replay simulator" "$state" "$readiness"
}
