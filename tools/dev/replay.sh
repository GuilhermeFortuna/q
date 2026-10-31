# shellcheck shell=bash
# Dedicated replay composition. Normal live/research units and environments are never modified.
REPLAY_STATE_DIR="${Q_REPLAY_STATE_DIR:-${STATE_DIR}/replay}"
REPLAY_ADMIN_PORT="${Q_REPLAY_ADMIN_PORT:-18914}"
REPLAY_MARKET_PORT="${Q_REPLAY_MARKET_PORT:-18912}"
REPLAY_EDGE_PORT="${Q_REPLAY_EDGE_PORT:-18913}"
REPLAY_PG_PORT="${Q_REPLAY_PG_PORT:-5436}"
REPLAY_REDIS_PORT="${Q_REPLAY_REDIS_PORT:-6382}"
REPLAY_API_PORT="${Q_REPLAY_API_PORT:-8002}"
REPLAY_UNIT="q-replay.service"
REPLAY_BIN="${Q_REPLAY_BIN:-$BACKEND_DIR/.venv/bin/q-replay}"
REPLAY_ADMIN_URL="http://127.0.0.1:${REPLAY_ADMIN_PORT}"
REPLAY_TEMPLATES="$BACKEND_DIR/deploy/systemd/replay"
REPLAY_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
REPLAY_ENV_FILE="$REPLAY_STATE_DIR/replay.env"
REPLAY_STATE_FILE="$REPLAY_STATE_DIR/current.json"
REPLAY_PHASE_OPEN=0
REPLAY_TOKEN=""
REPLAY_BACKEND_ENV="$REPLAY_STATE_DIR/backend.env"
REPLAY_COMPOSE=(docker compose --project-directory "$BACKEND_DIR" -f "$REPLAY_TEMPLATES/compose.yml" -p q-replay)

replay_unit() {
  case "$1" in
    simulator|replay) echo "$REPLAY_UNIT" ;;
    api|terminal) echo "q-replay-$1.service" ;;
    execution|worker) echo q-replay-execution-worker.service ;;
    publisher|market) echo q-replay-market-publisher.service ;;
    outbox|relay) echo q-replay-outbox-relay.service ;;
    *) die "unknown replay service: $1" ;;
  esac
}

replay_lock() {
  need flock
  mkdir -p "$REPLAY_STATE_DIR"
  exec 9>"$REPLAY_STATE_DIR/lifecycle.lock"
  flock -n 9 || die "another replay lifecycle operation is running"
}

replay_unit_active() { systemd_available && systemctl --user is-active --quiet "${1:-$REPLAY_UNIT}" 2>/dev/null; }
replay_ready() {
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "X-Replay-Token: $REPLAY_TOKEN" \
    "$REPLAY_ADMIN_URL/replay/v1/runs/current" 2>/dev/null || true)"
  [[ "$code" == 200 || "$code" == 404 ]]
}

# The state file is what the Research API reads (phase, run directory, generation, admin URL and
# the per-run admin token). It is written atomically with mode 0600; values travel as argv, not code.
replay_publish_state() {
  local phase="$1" run_dir="${2:-}" generation="${3:-}" token="${4:-}"
  mkdir -p "$REPLAY_STATE_DIR"
  python3 - "$REPLAY_STATE_FILE" "$phase" "$run_dir" "$generation" "$token" "$REPLAY_ADMIN_URL" <<'REPLAY_PY_Q146'
import json, os, pathlib, sys
target, phase, run_dir, generation, token, admin_url = sys.argv[1:]
payload = {"phase": phase}
if run_dir:
    payload["run_dir"] = run_dir
if generation:
    payload["generation"] = generation
if token:
    payload.update({"admin_url": admin_url, "admin_token": token})
tmp = pathlib.Path(target + ".tmp")
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
os.replace(tmp, target)
REPLAY_PY_Q146
}

# Token of the run whose state file is current; empty when none is published.
replay_current_token() {
  [[ -f "$REPLAY_STATE_FILE" ]] || return 0
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("admin_token", ""))' "$REPLAY_STATE_FILE" 2>/dev/null || true
}

replay_new_token() {
  python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
}

# Runs on exit: a launch that failed after it began leaves the stack reported as failed, not starting.
replay_exit_trap() {
  local status="$1"
  if [[ "$REPLAY_PHASE_OPEN" == 1 && "$status" != 0 ]]; then
    replay_publish_state failed || true
  fi
  REPLAY_PHASE_OPEN=0
}
replay_api_ready() {
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$REPLAY_API_PORT/api/v1/system/health" 2>/dev/null || true)" == 200 ]]
}

replay_compose_settings() {
  [[ -f "$REPLAY_STATE_DIR/compose.env" ]] || die "replay infrastructure is not configured; start ./dev replay first"
  REPLAY_COMPOSE_ENV=()
  local key value
  while IFS='=' read -r key value; do
    case "$key" in
      Q_REPLAY_PG_PORT|Q_REPLAY_REDIS_PORT|Q_REPLAY_VOLUME_PREFIX) REPLAY_COMPOSE_ENV+=("$key=$value") ;;
      *) die "invalid replay Compose environment key: $key" ;;
    esac
  done <"$REPLAY_STATE_DIR/compose.env"
}

replay_compose() {
  replay_compose_settings
  env "${REPLAY_COMPOSE_ENV[@]}" "${REPLAY_COMPOSE[@]}" --env-file "$REPLAY_STATE_DIR/compose.env" "$@"
}

# Values use systemd EnvironmentFile syntax. Refuse control characters and escape quoted
# metacharacters; migration subprocesses parse this data without shell evaluation.
replay_env() {
  local key="$1" value="$2"
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || die "newline in replay setting: $key"
  if [[ "$value" =~ ^[a-zA-Z0-9_./:=,@+-]+$ ]]; then
    printf '%s=%s\n' "$key" "$value"
  else
    value="${value//\\/\\\\}"; value="${value//\"/\\\"}"
    # systemd does not expand dollars; avoid sourcing these values in a shell.
    printf '%s="%s"\n' "$key" "$value"
  fi
}

replay_render() {
  # Replace literal placeholders without sed replacement expansion (paths may contain '&').
  python3 - "$@" <<'PY'
import pathlib, sys
source, target, *pairs = sys.argv[1:]
text = pathlib.Path(source).read_text()
for key, value in zip(pairs[::2], pairs[1::2]):
    if any(c in value for c in '\n\r%'):
        raise SystemExit('unsupported newline or systemd specifier in replay path')
    if key not in ("__COMMAND__", "__DESCRIPTION__", "__TYPE__"):
        value = value.replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace(key, value)
pathlib.Path(target).write_text(text)
PY
}

replay_install_units() {
  local run_dir="$1" service command type
  mkdir -p "$REPLAY_UNIT_DIR"
  replay_render "$REPLAY_TEMPLATES/q-replay.service.in" "$REPLAY_UNIT_DIR/$REPLAY_UNIT" \
    __REPLAY_ENV_FILE__ "$REPLAY_ENV_FILE" __REPLAY_BIN__ "$REPLAY_BIN"
  for service in api execution publisher outbox terminal; do
    type=notify
    case "$service" in
      api) command="\"$BACKEND_DIR/.venv/bin/q-api\" --host 127.0.0.1 --port $REPLAY_API_PORT" ;;
      execution) command="\"$BACKEND_DIR/.venv/bin/q-execution\" run" ;;
      publisher) command="\"$BACKEND_DIR/.venv/bin/q-market-publisher\"" ;;
      outbox) command="\"$BACKEND_DIR/.venv/bin/q-outbox-relay\"" ;;
      terminal) type=simple; command="/usr/bin/make -C \"$TERMINAL_DIR\" run" ;;
    esac
    replay_render "$REPLAY_TEMPLATES/q-replay-backend.service.in" "$REPLAY_UNIT_DIR/$(replay_unit "$service")" \
      __DESCRIPTION__ "$service" __TYPE__ "$type" __ENV_FILE__ "$REPLAY_BACKEND_ENV" \
      __RUN_DIR__ "$run_dir" __COMMAND__ "$command"
  done
}

replay_write_env() {
  local run_dir="$1" root="$2"
  {
    replay_env Q_REPLAY_STORE "$run_dir/replay.sqlite3"
    replay_env Q_REPLAY_ROOT "$root"
    replay_env Q_REPLAY_MARKET_PORT "$REPLAY_MARKET_PORT"
    replay_env Q_REPLAY_EDGE_PORT "$REPLAY_EDGE_PORT"
    replay_env Q_REPLAY_ADMIN_PORT "$REPLAY_ADMIN_PORT"
    replay_env Q_REPLAY_TOKEN "$REPLAY_TOKEN"
  } >"$REPLAY_ENV_FILE"
  chmod 600 "$REPLAY_ENV_FILE"
}

replay_write_backend_env() {
  local run_dir="$1" generation="$2" config="$3"
  local symbols account
  symbols="$(python3 -c 'import json,sys; print(",".join(json.load(open(sys.argv[1]))["symbols"]))' "$config")"
  account="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["account"]["login"])' "$config")"
  mkdir -p "$run_dir"/{lake,market,tick_cache,trade_cache,tick_store,strategy_bundles,strategies,config,cache,data}
  printf '{"data_source":"remote"}\n' >"$run_dir/runtime_config.json"
  {
    replay_env Q_DATABASE_URL "postgresql+psycopg://q:q@127.0.0.1:$REPLAY_PG_PORT/q"
    replay_env Q_REDIS_URL "redis://127.0.0.1:$REPLAY_REDIS_PORT/0"
    replay_env Q_PORT "$REPLAY_API_PORT"
    replay_env Q_MT5_GATEWAY_URL "http://127.0.0.1:$REPLAY_MARKET_PORT"
    replay_env Q_MT5_EDGE_URL "http://127.0.0.1:$REPLAY_EDGE_PORT"
    replay_env Q_MT5_GATEWAY_TOKEN ""
    replay_env Q_MARKET_CLOCK_URL "http://127.0.0.1:$REPLAY_MARKET_PORT"
    replay_env Q_MARKET_CLOCK_GENERATION "$generation"
    replay_env Q_MARKET_DATA_CACHE_NAMESPACE "$generation"
    replay_env Q_DATA_LAKE_ROOT "$run_dir/lake"
    replay_env Q_MARKET_DATA_ROOT "$run_dir/market"
    replay_env Q_TICK_CACHE_DIR "$run_dir/tick_cache"
    replay_env Q_TRADE_CACHE_DIR "$run_dir/trade_cache"
    replay_env Q_RESEARCH_TICK_STORE "$run_dir/tick_store"
    replay_env Q_RUNTIME_CONFIG_PATH "$run_dir/runtime_config.json"
    replay_env Q_STRATEGY_BUNDLE_ROOT "$run_dir/strategy_bundles"
    replay_env Q_STRATEGY_DIR "$run_dir/strategies"
    replay_env Q_TORCH_DEVICE cpu
    replay_env Q_STREAM_SYMBOLS "$symbols"
    replay_env Q_EXECUTION_SINGLE_OWNER_PER_SYMBOL true
    replay_env Q_LIVE_EXECUTION_ENABLED true
    replay_env Q_LIVE_EXECUTION_ACCOUNT_ALLOWLIST "$account"
    replay_env Q_EXECUTION_LIVE_CAPABILITY_LOCKED false
    replay_env Q_TERMINAL_API_BASE "http://127.0.0.1:$REPLAY_API_PORT"
    replay_env Q_TERMINAL_SYMBOL "${symbols%%,*}"
    replay_env Q_TERMINAL_TIMEFRAME 1m
    replay_env XDG_CONFIG_HOME "$run_dir/config"
    replay_env XDG_CACHE_HOME "$run_dir/cache"
    replay_env XDG_DATA_HOME "$run_dir/data"
  } >"$REPLAY_BACKEND_ENV"
  chmod 600 "$REPLAY_BACKEND_ENV"
  cp "$REPLAY_BACKEND_ENV" "$run_dir/backend.env"
}

replay_start_consumers() {
  local no_terminal="${1:-0}"
  systemctl --user start "$(replay_unit api)" "$(replay_unit outbox)" "$(replay_unit publisher)" "$(replay_unit execution)"
  wait_for "replay API" "journalctl --user -u $(replay_unit api) -n 30 --no-pager" replay_api_ready
  if [[ "$no_terminal" != 1 ]]; then
    systemctl --user start "$(replay_unit terminal)"
  fi
}

replay_open_terminal() {
  ensure_systemd_user
  replay_lock
  replay_unit_active && [[ -f "$REPLAY_STATE_FILE" ]] \
    || die "the replay stack is not running; start it with ./dev replay --config <path> first"
  systemctl --user start "$(replay_unit terminal)"
  echo "==> Replay terminal started (q-replay-terminal.service)."
}

cmd_replay() {
  local config="" root="" no_terminal=0
  if [[ "${1:-}" == terminal ]]; then
    [[ $# -eq 1 ]] || die "replay terminal takes no options"
    replay_open_terminal
    return
  fi
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --config|--root)
        [[ $# -ge 2 && -n "$2" ]] || die "$1 requires a value"
        if [[ "$1" == --config ]]; then config="$2"; else root="$2"; fi
        shift 2 ;;
      --no-terminal) no_terminal=1; shift ;;
      *) die "unknown replay option: $1 (expected --config <path> [--root <dir>] [--no-terminal] or terminal)" ;;
    esac
  done
  [[ -n "$config" ]] || die "./dev replay requires --config <path>"
  [[ -f "$config" ]] || die "replay config not found: $config"
  config="$(readlink -f "$config")"
  root="$(readlink -f "${root:-$(dirname "$config")}")"
  [[ -d "$root" ]] || die "replay dataset root not found: $root"
  need curl; need python3; need flock
  [[ -x "$REPLAY_BIN" ]] || die "q-replay is not installed; run uv sync in q_backend (or set Q_REPLAY_BIN)"
  ensure_systemd_user
  replay_lock
  local expected_gateway="http://127.0.0.1:$REPLAY_MARKET_PORT" expected_edge="http://127.0.0.1:$REPLAY_EDGE_PORT"
  [[ "${Q_MT5_GATEWAY_URL:-$expected_gateway}" == "$expected_gateway" && "${Q_MT5_EDGE_URL:-$expected_edge}" == "$expected_edge" ]] \
    || die "mixed replay/live endpoints refused; unset Q_MT5_GATEWAY_URL and Q_MT5_EDGE_URL"
  local fingerprint
  fingerprint="$(sha256sum "$config" | cut -d' ' -f1):$root:$REPLAY_MARKET_PORT:$REPLAY_EDGE_PORT:$REPLAY_ADMIN_PORT:$REPLAY_PG_PORT:$REPLAY_REDIS_PORT:$REPLAY_API_PORT:$BACKEND_DIR:$TERMINAL_DIR:$REPLAY_BIN"
  if replay_unit_active; then
    [[ -f "$REPLAY_STATE_DIR/fingerprint" && "$(cat "$REPLAY_STATE_DIR/fingerprint")" == "$fingerprint" ]] \
      || die "a different replay generation is already running; stop it with ./dev down replay first"
    local generation
    REPLAY_TOKEN="$(replay_current_token)"
    generation="$(Q_REPLAY_TOKEN="$REPLAY_TOKEN" "$REPLAY_BIN" --url "$REPLAY_ADMIN_URL" status \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["generation"])')"
    [[ -f "$REPLAY_STATE_DIR/generation" && "$generation" == "$(cat "$REPLAY_STATE_DIR/generation")" ]] \
      || die "replay generation replaced; stop all replay services before starting again"
    replay_publish_state ready "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("run_dir",""))' "$REPLAY_STATE_FILE" 2>/dev/null || true)" "$generation" "$REPLAY_TOKEN"
    replay_start_consumers "$no_terminal"
    echo "==> Replay already running; reused generation $generation."
    return
  fi
  local service port
  for service in api execution publisher outbox terminal; do
    replay_unit_active "$(replay_unit "$service")" && die "replay consumers are already running; use ./dev down replay first"
  done
  local seen=" "
  for port in "$REPLAY_MARKET_PORT" "$REPLAY_EDGE_PORT" "$REPLAY_ADMIN_PORT" "$REPLAY_PG_PORT" "$REPLAY_REDIS_PORT" "$REPLAY_API_PORT"; do
    [[ "$port" =~ ^[0-9]+$ && "$port" -gt 0 && "$port" -le 65535 ]] || die "invalid replay port: $port"
    [[ "$seen" != *" $port "* ]] || die "duplicate replay port: $port"
    seen+="$port "
    if check_port "$port"; then die "replay port $port is already in use; stop replay or configure Q_REPLAY_*_PORT"; fi
  done
  "$REPLAY_BIN" prepare --config "$config" --root "$root" >/dev/null \
    || die "replay config or dataset failed verification (run q-replay prepare for details)"
  for service in python alembic q-api q-execution q-market-publisher q-outbox-relay; do
    [[ -x "$BACKEND_DIR/.venv/bin/$service" ]] || die "missing $service; run uv sync in q_backend"
  done
  "$BACKEND_DIR/.venv/bin/python" -c 'from q_core import execution; assert all(callable(getattr(execution, name, None)) for name in ("match_quote", "price_to_ticks", "fill_cost")), "released q_core quote execution API required"' \
    || die "released q_core replay execution capability unavailable; sync the documented backend dependencies"
  ensure_docker
  local run_dir generation
  replay_publish_state starting
  REPLAY_PHASE_OPEN=1
  trap 'replay_exit_trap $?' EXIT
  run_dir="$(mktemp -d "$REPLAY_STATE_DIR/run-XXXXXXXX")"
  cp "$config" "$run_dir/config.json"
  REPLAY_TOKEN="$(replay_new_token)"
  replay_write_env "$run_dir" "$root"
  replay_install_units "$run_dir"
  systemctl --user daemon-reload
  # A simulator that crashed earlier can sit in start-limit-hit; clear that so this start is attempted.
  systemctl --user reset-failed "$REPLAY_UNIT" 2>/dev/null || true
  systemctl --user start "$REPLAY_UNIT"
  wait_for "replay simulator" "journalctl --user -u $REPLAY_UNIT -n 30 --no-pager" replay_ready
  Q_REPLAY_TOKEN="$REPLAY_TOKEN" "$REPLAY_BIN" --url "$REPLAY_ADMIN_URL" create --config "$run_dir/config.json" \
    >"$run_dir/created.json" \
    || die "replay run creation failed (see journalctl --user -u $REPLAY_UNIT)"
  generation="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["generation"])' "$run_dir/created.json")"
  [[ "$generation" =~ ^[a-zA-Z0-9_-]+$ ]] || die "invalid replay generation"
  replay_write_backend_env "$run_dir" "$generation" "$run_dir/config.json"
  printf 'Q_REPLAY_PG_PORT=%s\nQ_REPLAY_REDIS_PORT=%s\nQ_REPLAY_VOLUME_PREFIX=q-replay-%s\n' \
    "$REPLAY_PG_PORT" "$REPLAY_REDIS_PORT" "${run_dir##*/}" >"$REPLAY_STATE_DIR/compose.env"
  cp "$REPLAY_STATE_DIR/compose.env" "$run_dir/compose.env"
  replay_compose up -d --wait postgres redis
  # Read EnvironmentFile syntax with Python; never source config/path values as shell code.
  python3 - "$REPLAY_BACKEND_ENV" "$run_dir" "$BACKEND_DIR/.venv/bin/alembic" "$BACKEND_DIR/alembic.ini" <<'PY'
import os, pathlib, shlex, subprocess, sys
file, run_dir, alembic, ini = sys.argv[1:]
env = {key: value for key, value in os.environ.items() if not key.startswith('Q_')}
for line in pathlib.Path(file).read_text().splitlines():
    key, value = line.split('=', 1)
    env[key] = shlex.split(value)[0] if value else ''
subprocess.run([alembic, '-c', ini, 'upgrade', 'head'], env=env, cwd=run_dir, check=True)
PY
  printf '%s\n' "$fingerprint" >"$REPLAY_STATE_DIR/fingerprint"
  printf '%s\n' "$generation" >"$REPLAY_STATE_DIR/generation"
  replay_start_consumers "$no_terminal"
  replay_publish_state ready "$run_dir" "$generation" "$REPLAY_TOKEN"
  REPLAY_PHASE_OPEN=0
  echo "==> Replay stack prepared and paused (run state: $run_dir)."
  echo "    Resume after deployment setup: Q_REPLAY_TOKEN from $REPLAY_STATE_FILE; $REPLAY_BIN --url $REPLAY_ADMIN_URL resume"
  echo "    Stop: ./dev down replay. Live and research stacks are not affected."
}

cmd_down_replay() {
  replay_lock
  if systemd_available; then
    systemctl --user stop "$(replay_unit terminal)" "$(replay_unit execution)" "$(replay_unit publisher)" \
      "$(replay_unit outbox)" "$(replay_unit api)" "$REPLAY_UNIT" 2>/dev/null || true
  fi
  if [[ -f "$REPLAY_STATE_DIR/compose.env" ]] && command -v docker >/dev/null 2>&1; then replay_compose down; fi
  replay_publish_state idle
  echo "==> Replay stack stopped (run state and database volumes kept for inspection)."
}

cmd_restart_replay() {
  replay_lock
  local service="${1:-simulator}"
  case "$service" in
    postgres|redis) replay_compose restart "$service" ;;
    *)
      ensure_systemd_user
      local unit
      unit="$(replay_unit "$service")"
      [[ -f "$REPLAY_UNIT_DIR/$unit" ]] || die "$unit is not installed; start with ./dev replay --config <path>"
      systemctl --user restart "$unit"
      if [[ "$service" == simulator ]]; then
        wait_for "replay simulator" "journalctl --user -u $unit -n 30 --no-pager" replay_ready
      fi ;;
  esac
}

replay_logs() {
  local service="${1:-simulator}"
  case "$service" in
    postgres|redis)
      replay_compose_settings
      dev_follow env "${REPLAY_COMPOSE_ENV[@]}" "${REPLAY_COMPOSE[@]}" --env-file "$REPLAY_STATE_DIR/compose.env" logs -f "$service" ;;
    *) dev_follow journalctl --user -u "$(replay_unit "$service")" -f ;;
  esac
}

replay_status_lines() {
  local service unit state
  for service in simulator api execution publisher outbox terminal; do
    unit="$(replay_unit "$service")"; state=stopped
    if replay_unit_active "$unit"; then state=active; fi
    printf "%-20s %-28s %-18s %s\n" "replay:$service" "$unit" "$state" -
  done
  for service in postgres redis; do
    state=stopped
    if [[ -f "$REPLAY_STATE_DIR/compose.env" ]] && replay_compose ps --status running --services 2>/dev/null | grep -qx "$service"; then state=running; fi
    printf "%-20s %-28s %-18s %s\n" "replay:$service" "docker:q-replay/$service" "$state" -
  done
}
