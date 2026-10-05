#!/usr/bin/env bash
# Research and Backtest stack lifecycle helpers for the unified launcher.
# Supports host and container modes, nonblocking start, selective down,
# and process validation under Q_RESEARCH_DATA_DIR.

ROOT="${Q_RESEARCH_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BACKEND_DIR="$ROOT/q_backend"
FRONTEND_DIR="$ROOT/q_frontend"

RESEARCH_COMPOSE_PROJECT="${Q_RESEARCH_COMPOSE_PROJECT:-q-research}"
RESEARCH_PG_PORT="${Q_RESEARCH_PG_PORT:-5435}"
RESEARCH_REDIS_PORT="${Q_RESEARCH_REDIS_PORT:-6381}"
RESEARCH_API_PORT="${Q_RESEARCH_API_PORT:-8001}"
RESEARCH_DATA_DIR="${Q_RESEARCH_DATA_DIR:-$BACKEND_DIR/data/research}"
RESEARCH_PID_DIR="${Q_RESEARCH_PID_DIR:-$RESEARCH_DATA_DIR/pids}"
RESEARCH_LOG_DIR="${Q_RESEARCH_LOG_DIR:-$RESEARCH_DATA_DIR/logs}"
RESEARCH_GATEWAY_ENV_FILE="${Q_RESEARCH_GATEWAY_ENV_FILE:-${HOME}/.config/mt5-gateway/mt5-gateway.env}"
RESEARCH_API_BASE_URL="http://127.0.0.1:${RESEARCH_API_PORT}"
RESEARCH_API_HEALTH_URL="${Q_RESEARCH_HEALTH_URL:-${RESEARCH_API_BASE_URL}/api/v1/system/health}"
RESEARCH_BACKEND_IMAGE="${Q_RESEARCH_BACKEND_IMAGE:-q-backend:dev}"
RESEARCH_BUILD_CACHE_MAX="${Q_RESEARCH_BUILD_CACHE_MAX:-4GB}"
RESEARCH_MODE="${Q_RESEARCH_MODE:-host}"

# Scope Compose settings to Research commands. This file is sourced by ./dev,
# whose live Compose project must retain its own exported ports and data root.
RESEARCH_COMPOSE=(
  env
  "Q_COMPOSE_PG_PORT=$RESEARCH_PG_PORT"
  "Q_COMPOSE_REDIS_PORT=$RESEARCH_REDIS_PORT"
  "Q_COMPOSE_API_PORT=$RESEARCH_API_PORT"
  "Q_COMPOSE_DATA_DIR=$RESEARCH_DATA_DIR"
  docker compose --project-directory "$BACKEND_DIR" -f "$BACKEND_DIR/docker-compose.yml" -p "$RESEARCH_COMPOSE_PROJECT"
)

FINGERPRINT_LABEL="dev.q.backend.research-fingerprint"
FORCE_REBUILD=0
STARTED_AT=""

# Defaults for standalone / legacy harness callers
[[ -z "${COMPOSE_PROJECT+x}" ]] && COMPOSE_PROJECT="$RESEARCH_COMPOSE_PROJECT"
[[ -z "${COMPOSE+x}" ]] && COMPOSE=("${RESEARCH_COMPOSE[@]}")
[[ -z "${PG_PORT+x}" ]] && PG_PORT="$RESEARCH_PG_PORT"
[[ -z "${REDIS_PORT+x}" ]] && REDIS_PORT="$RESEARCH_REDIS_PORT"
[[ -z "${API_PORT+x}" ]] && API_PORT="$RESEARCH_API_PORT"
[[ -z "${DATA_DIR+x}" ]] && DATA_DIR="$RESEARCH_DATA_DIR"
[[ -z "${PID_DIR+x}" ]] && PID_DIR="$RESEARCH_PID_DIR"
[[ -z "${LOG_DIR+x}" ]] && LOG_DIR="$RESEARCH_LOG_DIR"
[[ -z "${GATEWAY_ENV_FILE+x}" ]] && GATEWAY_ENV_FILE="$RESEARCH_GATEWAY_ENV_FILE"
[[ -z "${API_BASE_URL+x}" ]] && API_BASE_URL="$RESEARCH_API_BASE_URL"
[[ -z "${API_HEALTH_URL+x}" ]] && API_HEALTH_URL="$RESEARCH_API_HEALTH_URL"
[[ -z "${BACKEND_IMAGE+x}" ]] && BACKEND_IMAGE="$RESEARCH_BACKEND_IMAGE"
[[ -z "${BUILD_CACHE_MAX+x}" ]] && BUILD_CACHE_MAX="$RESEARCH_BUILD_CACHE_MAX"
[[ -z "${MODE+x}" ]] && MODE="$RESEARCH_MODE"

UI_PID=""
API_PID=""
WORKER_PID=""
RELAY_PID=""
CLEANED_UP=0

die() {
  echo "error: $*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' is required but was not found on PATH"
}

# Content hash of image-defining inputs. Paths are sorted; mtimes ignored.
image_fingerprint() {
  local backend="$BACKEND_DIR"
  local -a files=()
  local f

  [[ -f "$backend/Dockerfile" ]] || die "missing $backend/Dockerfile"
  [[ -f "$backend/pyproject.toml" ]] || die "missing $backend/pyproject.toml"
  [[ -f "$backend/uv.lock" ]] || die "missing $backend/uv.lock"
  [[ -f "$backend/docker/entrypoint.sh" ]] || die "missing $backend/docker/entrypoint.sh"

  files+=(
    "$backend/Dockerfile"
    "$backend/pyproject.toml"
    "$backend/uv.lock"
    "$backend/docker/entrypoint.sh"
  )

  while IFS= read -r -d '' f; do
    files+=("$f")
  done < <(find "$backend/docker/metatrader5-stub" -type f -print0 | sort -z)

  (
    cd "$backend"
    for f in "${files[@]}"; do
      rel="${f#"$backend"/}"
      printf '%s\0' "$rel"
      # shellcheck disable=SC2002
      cat "$f"
      printf '\0'
    done
  ) | sha256sum | awk '{print $1}'
}

installed_fingerprint() {
  local tag="${1:-$RESEARCH_BACKEND_IMAGE}"
  docker image inspect \
    --format "{{ index .Config.Labels \"$FINGERPRINT_LABEL\" }}" \
    "$tag" 2>/dev/null || true
}

cap_build_cache() {
  local max="$RESEARCH_BUILD_CACHE_MAX"

  if [[ "$max" == "off" || -z "$max" ]]; then
    echo "cache: build-cache cap disabled (Q_RESEARCH_BUILD_CACHE_MAX=off)"
    return 0
  fi

  echo "cache: capping BuildKit cache at $max ..."
  if docker builder prune --force --max-used-space "$max" >/dev/null 2>&1; then
    return 0
  fi
  if docker builder prune --force --keep-storage "$max" >/dev/null 2>&1; then
    return 0
  fi
  echo "cache: could not cap build cache (non-fatal); check 'docker system df'" >&2
}

ensure_backend_image() {
  local fp installed
  fp="$(image_fingerprint)"
  installed="$(installed_fingerprint "$RESEARCH_BACKEND_IMAGE")"

  if [[ "$FORCE_REBUILD" -eq 1 ]]; then
    echo "image: forcing rebuild of $RESEARCH_BACKEND_IMAGE (fingerprint=$fp)"
  elif [[ -z "$installed" ]]; then
    echo "image: $RESEARCH_BACKEND_IMAGE missing — building (fingerprint=$fp)"
  elif [[ "$installed" != "$fp" ]]; then
    echo "image: $RESEARCH_BACKEND_IMAGE stale (have=$installed want=$fp) — rebuilding"
  else
    echo "image: reusing $RESEARCH_BACKEND_IMAGE (fingerprint=$fp)"
    return 0
  fi

  echo "building $RESEARCH_BACKEND_IMAGE ..."
  docker build \
    --tag "$RESEARCH_BACKEND_IMAGE" \
    --build-arg "Q_RESEARCH_IMAGE_FINGERPRINT=$fp" \
    -f "$BACKEND_DIR/Dockerfile" \
    "$BACKEND_DIR"
  echo "image: built $RESEARCH_BACKEND_IMAGE"
  cap_build_cache
}

check_common_prerequisites() {
  need docker
  need curl
  need pnpm

  docker info >/dev/null 2>&1 || die "Docker daemon is not reachable (verify: docker info)"

  if ! docker compose version >/dev/null 2>&1; then
    die "Docker Compose is required (verify: docker compose version)"
  fi

  if ! command -v nvidia-smi >/dev/null 2>&1; then
    die "nvidia-smi not found — install NVIDIA drivers (verify: nvidia-smi)"
  fi
  if ! nvidia-smi >/dev/null 2>&1; then
    die "nvidia-smi failed — host GPU not usable (verify: nvidia-smi)"
  fi
}

check_container_prerequisites() {
  echo "prerequisites: checking Docker, Compose, and NVIDIA GPU access ..."
  check_common_prerequisites

  if ! command -v nvidia-ctk >/dev/null 2>&1; then
    die "nvidia-ctk not found — install the NVIDIA Container Toolkit (verify: nvidia-ctk --version; see https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)"
  fi
}

check_host_prerequisites() {
  echo "prerequisites: checking Docker, Compose, uv, and host GPU access ..."
  check_common_prerequisites
  need uv
}

check_worker_cuda() {
  echo "CUDA: probing $RESEARCH_BACKEND_IMAGE with --gpus all ..."
  local out
  if ! out="$(
    docker run --rm --gpus all --entrypoint python "$RESEARCH_BACKEND_IMAGE" \
      -c 'import torch; assert torch.cuda.is_available(), "torch.cuda.is_available() is False"; print(torch.cuda.get_device_name(0))'
  )"; then
    die "CUDA probe failed for $RESEARCH_BACKEND_IMAGE — worker cannot see a GPU (verify: docker run --rm --gpus all --entrypoint python $RESEARCH_BACKEND_IMAGE -c \"import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))\")"
  fi
  echo "CUDA: ready ($out)"
}

venv_python() {
  printf '%s' "$BACKEND_DIR/.venv/bin/python"
}

ensure_backend_venv() {
  echo "venv: syncing $BACKEND_DIR/.venv ..."
  (cd "$BACKEND_DIR" && uv sync --frozen --no-dev) \
    || die "uv sync failed in $BACKEND_DIR (verify: cd q_backend && uv sync --frozen)"
  [[ -x "$(venv_python)" ]] || die "missing interpreter $(venv_python) after uv sync"
}

check_host_cuda() {
  echo "CUDA: probing host interpreter $(venv_python) ..."
  local out
  if ! out="$(
    "$(venv_python)" \
      -c 'import torch; assert torch.cuda.is_available(), "torch.cuda.is_available() is False"; print(torch.cuda.get_device_name(0))'
  )"; then
    die "CUDA probe failed for the host venv — torch cannot see a GPU (verify: q_backend/.venv/bin/python -c \"import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))\")"
  fi
  echo "CUDA: ready ($out)"
}

gateway_env_value() {
  local key="$1"
  local envf="${RESEARCH_GATEWAY_ENV_FILE:-$GATEWAY_ENV_FILE}"
  [[ -f "$envf" ]] || return 0
  sed -n "s/^${key}=//p" "$envf" | tail -n1
}

gateway_health() {
  local response
  if [[ -n "${Q_MT5_GATEWAY_TOKEN:-}" ]]; then
    response="$(curl -fsS --max-time 2 -H "X-Gateway-Token: $Q_MT5_GATEWAY_TOKEN" \
      "$Q_MT5_GATEWAY_URL/v1/health" 2>/dev/null)" || return 1
  else
    response="$(curl -fsS --max-time 2 "$Q_MT5_GATEWAY_URL/v1/health" 2>/dev/null)" || return 1
  fi
  [[ "$response" =~ \"mt5_connected\"[[:space:]]*:[[:space:]]*true ]]
}

prepare_mt5_gateway() {
  if [[ "${Q_RESEARCH_MT5:-auto}" == off ]]; then
    unset Q_MT5_GATEWAY_URL Q_MT5_GATEWAY_TOKEN
    return 0
  fi
  [[ "${Q_RESEARCH_MT5:-auto}" == auto ]] || die "Q_RESEARCH_MT5 must be auto or off"

  local start_local_gateway=0
  if [[ -z "${Q_MT5_GATEWAY_URL:-}" ]]; then
    if [[ ! -f "${HOME}/.config/systemd/user/mt5-gateway.service" ]]; then
      echo "warning: MT5 gateway unit is not installed; Research will use local data only" >&2
      echo "hint: run q_backend/gateway/setup_wine.sh and configure mt5-gateway.service" >&2
      return 0
    fi
    need systemctl
    local gateway_host gateway_port
    gateway_host="$(gateway_env_value MT5_GATEWAY_HOST)"
    gateway_port="$(gateway_env_value MT5_GATEWAY_PORT)"
    [[ -n "$gateway_host" ]] || gateway_host=127.0.0.1
    [[ "$gateway_host" == 0.0.0.0 ]] && gateway_host=127.0.0.1
    [[ -n "$gateway_port" ]] || gateway_port=18812
    export Q_MT5_GATEWAY_URL="http://${gateway_host}:${gateway_port}"
    if [[ -z "${Q_MT5_GATEWAY_TOKEN:-}" ]]; then
      Q_MT5_GATEWAY_TOKEN="$(gateway_env_value MT5_GATEWAY_TOKEN)"
      export Q_MT5_GATEWAY_TOKEN
    fi
    start_local_gateway=1
  fi

  if [[ "$MODE" == container && "$Q_MT5_GATEWAY_URL" =~ ^https?://(127\.0\.0\.1|localhost)(:|/|$) ]]; then
    die "the local MT5 gateway is unreachable from a container; use ./research --host or configure a remote gateway URL"
  fi

  if [[ "$start_local_gateway" -eq 1 ]]; then
    echo "starting MT5 data gateway (shared with ./dev) ..."
    systemctl --user start mt5-gateway.service || die "could not start mt5-gateway.service"
  fi

  echo "waiting for MT5 data gateway at $Q_MT5_GATEWAY_URL ..."
  local attempt
  for ((attempt = 0; attempt < 60; attempt++)); do
    if gateway_health; then
      echo "MT5 data gateway connected"
      return 0
    fi
    sleep 1
  done
  die "MT5 data gateway is not connected at $Q_MT5_GATEWAY_URL (check: journalctl --user -u mt5-gateway.service -n 50; broker login)"
}

export_host_backend_env() {
  export Q_DATABASE_URL="postgresql+psycopg://q:q@127.0.0.1:${RESEARCH_PG_PORT}/q"
  export Q_REDIS_URL="redis://127.0.0.1:${RESEARCH_REDIS_PORT}/0"
  export Q_DATA_LAKE_ROOT="$RESEARCH_DATA_DIR/lake"
  export Q_MARKET_DATA_ROOT="$RESEARCH_DATA_DIR/market"
  export Q_TICK_CACHE_DIR="$RESEARCH_DATA_DIR/tick_cache"
  export Q_RUNTIME_CONFIG_PATH="$RESEARCH_DATA_DIR/runtime_config.json"
  export Q_WORKER_PROCESSES="${Q_WORKER_PROCESSES:-14}"
  export Q_TORCH_DEVICE="${Q_TORCH_DEVICE:-cuda}"
  export CUBLAS_WORKSPACE_CONFIG="${CUBLAS_WORKSPACE_CONFIG:-:4096:8}"
}

host_port_open() {
  local port="$1"
  if [[ -n "${Q_TEST_STATE:-}" ]]; then
    if [[ -f "${Q_TEST_STATE}/ports/$port" ]]; then
      return 0
    fi
    local pg="${RESEARCH_PG_PORT:-5435}"
    local rd="${RESEARCH_REDIS_PORT:-6381}"
    if [[ "$port" == "$pg" || "$port" == "$rd" ]]; then
      if [[ -f "${Q_TEST_STATE}/compose_state" ]] && grep -q "up" "${Q_TEST_STATE}/compose_state" 2>/dev/null; then
        return 0
      fi
    fi
    return 1
  fi
  timeout 1 bash -c "</dev/tcp/127.0.0.1/$port" >/dev/null 2>&1
}

docker_research_service_running() {
  local service="$1"
  "${RESEARCH_COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx "$service"
}

check_research_port_conflicts() {
  local port svc
  for svc in postgres redis api; do
    case "$svc" in
      postgres) port="$RESEARCH_PG_PORT" ;;
      redis) port="$RESEARCH_REDIS_PORT" ;;
      api) port="$RESEARCH_API_PORT" ;;
    esac
    if host_port_open "$port"; then
      if [[ "$svc" == "postgres" ]] && docker_research_service_running postgres; then
        continue
      fi
      if [[ "$svc" == "redis" ]] && docker_research_service_running redis; then
        continue
      fi
      if [[ "$svc" == "api" ]] && is_process_running api; then
        continue
      fi
      echo "error: port $port ($svc) is already in use by another process or container." >&2
      return 1
    fi
  done
  return 0
}

ensure_host_compose_ports() {
  local attempt port host_ports_ready=0
  for ((attempt = 0; attempt < 10; attempt++)); do
    if host_port_open "$RESEARCH_PG_PORT" && host_port_open "$RESEARCH_REDIS_PORT"; then
      host_ports_ready=1
      break
    fi
    sleep 0.5
  done
  if [[ "$host_ports_ready" -eq 0 ]]; then
    echo "host ports are not published; recreating $RESEARCH_COMPOSE_PROJECT infrastructure..."
    "${RESEARCH_COMPOSE[@]}" up -d --force-recreate --wait postgres redis \
      || die "could not recreate $RESEARCH_COMPOSE_PROJECT infrastructure (check: ${RESEARCH_COMPOSE[*]} logs postgres redis)"
  fi

  for port in "$RESEARCH_PG_PORT" "$RESEARCH_REDIS_PORT"; do
    for ((attempt = 0; attempt < 90; attempt++)); do
      host_port_open "$port" && break
      sleep 0.5
    done
    host_port_open "$port" \
      || die "Compose reports healthy containers, but host port $port is unreachable (check: ${RESEARCH_COMPOSE[*]} ps and ${RESEARCH_COMPOSE[*]} logs)"
  done
}

run_host_migrations() {
  echo "migrations: alembic upgrade head ..."
  mkdir -p "$RESEARCH_DATA_DIR"
  (cd "$BACKEND_DIR" && "$BACKEND_DIR/.venv/bin/alembic" upgrade head) \
    || die "alembic upgrade head failed (verify: cd q_backend && .venv/bin/alembic upgrade head)"
  date -Iseconds >"$RESEARCH_DATA_DIR/migrate.stamp"
}

validate_pid() {
  local pid="$1" expected="$2"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1

  local cmd=""
  if [[ -f "/proc/$pid/cmdline" ]]; then
    cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
  elif command -v ps >/dev/null 2>&1; then
    cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  fi
  [[ -z "$cmd" ]] && return 0

  case "$expected" in
    api) [[ "$cmd" == *"uvicorn"* || "$cmd" == *"q_backend.api.main"* ]] ;;
    worker) [[ "$cmd" == *"worker"* || "$cmd" == *"-m dramatiq q_backend.tasks"* ]] ;;
    relay) [[ "$cmd" == *"q-outbox-relay"* ]] ;;
    ui) [[ "$cmd" == *"tauri"* || "$cmd" == *"pnpm"* || "$cmd" == *"vite"* || "$cmd" == *"node"* ]] ;;
    pool) [[ "$cmd" == *"pool"* ]] ;;
    *) [[ "$cmd" == *"$expected"* ]] ;;
  esac
}

is_process_running() {
  local name="$1"
  local pdir="${RESEARCH_PID_DIR:-$RESEARCH_DATA_DIR/pids}"
  local ldir="${RESEARCH_LOG_DIR:-$RESEARCH_DATA_DIR/logs}"
  local pidfile=""
  if [[ -f "$pdir/$name.pid" ]]; then
    pidfile="$pdir/$name.pid"
  elif [[ -f "$ldir/$name.pid" ]]; then
    pidfile="$ldir/$name.pid"
  else
    return 1
  fi
  local pid
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  if kill -0 "$pid" 2>/dev/null && validate_pid "$pid" "$name"; then
    return 0
  fi
  # Status must not destroy tracking when called from a restricted PID namespace.
  # Start and stop own stale-file cleanup.
  return 1
}

start_host_process() {
  local name="$1"
  shift
  local pdir="${RESEARCH_PID_DIR:-$RESEARCH_DATA_DIR/pids}"
  local ldir="${RESEARCH_LOG_DIR:-$RESEARCH_DATA_DIR/logs}"
  mkdir -p "$ldir" "$pdir"
  local log="$ldir/$name.log"
  local pidfile="$pdir/$name.pid"
  # Also support LOG_DIR/$name.pid if test overrides LOG_DIR
  if [[ -n "${LOG_DIR:-}" && "$LOG_DIR" != "$RESEARCH_DATA_DIR/logs" ]]; then
    pidfile="$LOG_DIR/$name.pid"
  fi
  local pid="" i

  if is_process_running "$name"; then
    echo "$(cat "$pidfile")"
    return 0
  fi

  rm -f "$pidfile"
  (
    cd "$BACKEND_DIR"
    exec setsid bash -c 'echo "$$" >"$1"; shift; exec "$@"' _ "$pidfile" "$@"
  ) >"$log" 2>&1 &

  for ((i = 0; i < 100; i++)); do
    if [[ -s "$pidfile" ]]; then
      pid="$(cat "$pidfile")"
      break
    fi
    sleep 0.1
  done
  [[ -n "$pid" ]] || die "$name did not start within 10s (check $log)"
  printf '%s' "$pid"
}

stop_host_process() {
  local pid="$1" name="$2" i
  local pdir="${RESEARCH_PID_DIR:-$RESEARCH_DATA_DIR/pids}"
  local ldir="${RESEARCH_LOG_DIR:-$RESEARCH_DATA_DIR/logs}"
  if [[ -z "$pid" ]]; then
    if [[ -f "$pdir/$name.pid" ]]; then
      pid="$(cat "$pdir/$name.pid" 2>/dev/null || true)"
    elif [[ -f "$ldir/$name.pid" ]]; then
      pid="$(cat "$ldir/$name.pid" 2>/dev/null || true)"
    fi
  fi
  [[ -n "$pid" ]] || return 0

  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pdir/$name.pid" "$ldir/$name.pid" 2>/dev/null || true
    return 0
  fi

  if ! validate_pid "$pid" "$name"; then
    echo "warning: $name (PID $pid) does not match expected process; skipping kill" >&2
    rm -f "$pdir/$name.pid" "$ldir/$name.pid" 2>/dev/null || true
    return 0
  fi

  kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  for ((i = 0; i < 100; i++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "stopped $name"
      rm -f "$pdir/$name.pid" "$ldir/$name.pid" 2>/dev/null || true
      return 0
    fi
    sleep 0.1
  done

  kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  echo "stopped $name (forced after 10s)"
  rm -f "$pdir/$name.pid" "$ldir/$name.pid" 2>/dev/null || true
}

wait_for_api() {
  local attempts="${1:-90}"
  local i elapsed
  echo "waiting for API at $RESEARCH_API_HEALTH_URL ..."
  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS "$RESEARCH_API_HEALTH_URL" >/dev/null 2>&1; then
      elapsed=$((SECONDS - STARTED_AT))
      echo "API is healthy (backend ready in ${elapsed}s)"
      return 0
    fi
    sleep 2
  done
  if [[ "$MODE" == "host" ]]; then
    die "API did not become healthy in time (tried ${attempts} times). Check: $RESEARCH_LOG_DIR/api.log"
  fi
  die "API did not become healthy in time (tried ${attempts} times). Check: ${RESEARCH_COMPOSE[*]} logs backend"
}

ensure_frontend_env() {
  local env_file="$FRONTEND_DIR/.env"
  if [[ ! -f "$env_file" ]]; then
    if [[ -f "$FRONTEND_DIR/.env.example" ]]; then
      cp "$FRONTEND_DIR/.env.example" "$env_file"
      echo "created $env_file from .env.example"
    else
      printf 'VITE_API_BASE_URL=%s\nVITE_ENABLE_MSW=false\n' "$RESEARCH_API_BASE_URL" >"$env_file"
      echo "created $env_file"
    fi
  fi

  if grep -q '^VITE_ENABLE_MSW=' "$env_file"; then
    sed -i 's/^VITE_ENABLE_MSW=.*/VITE_ENABLE_MSW=false/' "$env_file"
  else
    printf '\nVITE_ENABLE_MSW=false\n' >>"$env_file"
  fi

  if grep -q '^VITE_API_BASE_URL=' "$env_file"; then
    sed -i "s|^VITE_API_BASE_URL=.*|VITE_API_BASE_URL=$RESEARCH_API_BASE_URL|" "$env_file"
  else
    printf 'VITE_API_BASE_URL=%s\n' "$RESEARCH_API_BASE_URL" >>"$env_file"
  fi
}

launch_ui() {
  local ui_mode="${Q_RESEARCH_UI:-tauri}"
  mkdir -p "$RESEARCH_LOG_DIR" "$RESEARCH_PID_DIR"

  if is_process_running ui; then
    echo "Research UI: already running"
    return 0
  fi

  echo "launching Research UI ($ui_mode) ..."
  echo "  mode:  $MODE"
  echo "  API:   $RESEARCH_API_HEALTH_URL"
  if [[ "$MODE" == "container" ]]; then
    echo "  image: $RESEARCH_BACKEND_IMAGE"
  else
    echo "  venv:  $BACKEND_DIR/.venv"
    echo "  logs:  $RESEARCH_LOG_DIR"
  fi
  echo "  data:  $RESEARCH_DATA_DIR"
  echo

  export __NV_DISABLE_EXPLICIT_SYNC="${__NV_DISABLE_EXPLICIT_SYNC:-1}"
  if [[ -d /sys/module/nvidia ]]; then
    export WEBKIT_DISABLE_DMABUF_RENDERER="${WEBKIT_DISABLE_DMABUF_RENDERER:-0}"
    export WEBKIT_DMABUF_RENDERER_FORCE_SHM="${WEBKIT_DMABUF_RENDERER_FORCE_SHM:-1}"
  fi

  local pid=""
  case "$ui_mode" in
    tauri)
      (
        cd "$FRONTEND_DIR"
        exec pnpm tauri:dev
      ) >"$RESEARCH_LOG_DIR/ui.log" 2>&1 &
      pid=$!
      ;;
    browser)
      need xdg-open
      (
        cd "$FRONTEND_DIR"
        exec pnpm dev
      ) >"$RESEARCH_LOG_DIR/ui.log" 2>&1 &
      pid=$!
      (
        sleep 2
        xdg-open "http://127.0.0.1:1420/" >/dev/null 2>&1 || true
      ) &
      echo "opened http://127.0.0.1:1420/ in the default browser"
      ;;
    *)
      die "invalid Q_RESEARCH_UI=$ui_mode (expected tauri|browser)"
      ;;
  esac

  echo "$pid" >"$RESEARCH_PID_DIR/ui.pid"
  UI_PID="$pid"
}

record_research_gateway_usage() {
  # An idempotent start must not change the gateway used by a running backend.
  if is_process_running api || docker_research_service_running backend; then
    return 0
  fi

  local marker="$RESEARCH_PID_DIR/local-gateway"
  rm -f "$marker"
  if [[ "${Q_RESEARCH_MT5:-auto}" != "off" &&
        "${Q_MT5_GATEWAY_URL:-}" =~ ^https?://(127\.0\.0\.1|localhost)(:|/|$) ]]; then
    : >"$marker"
  fi
}

start_research() {
  local mode="${1:-$MODE}"
  local rebuild="${2:-0}"
  MODE="$mode"
  FORCE_REBUILD="$rebuild"
  STARTED_AT=$SECONDS

  if [[ "$MODE" == "container" ]]; then
    check_container_prerequisites
  else
    check_host_prerequisites
  fi

  [[ -d "$BACKEND_DIR" ]] || die "missing $BACKEND_DIR"
  [[ -d "$FRONTEND_DIR" ]] || die "missing $FRONTEND_DIR"
  [[ -f "$BACKEND_DIR/docker-compose.yml" ]] || die "missing $BACKEND_DIR/docker-compose.yml"

  mkdir -p \
    "$RESEARCH_DATA_DIR/lake" \
    "$RESEARCH_DATA_DIR/market" \
    "$RESEARCH_DATA_DIR/tick_cache" \
    "$RESEARCH_LOG_DIR" \
    "$RESEARCH_PID_DIR"

  check_research_port_conflicts || return 1

  ensure_frontend_env

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo "installing frontend dependencies ..."
    (cd "$FRONTEND_DIR" && pnpm install)
  fi

  echo "$MODE" >"$RESEARCH_PID_DIR/mode"

  if [[ "$MODE" == "container" ]]; then
    ensure_backend_image
    check_worker_cuda
    prepare_mt5_gateway
    record_research_gateway_usage
    local -a compose_cmd=("${RESEARCH_COMPOSE[@]}")
    if [[ -n "${Q_MT5_GATEWAY_URL:-}" ]]; then
      compose_cmd+=(-f "$ROOT/tools/research-gateway-compose.yml")
    fi

    echo "starting Postgres, Redis, API, worker, and outbox relay ..."
    export Q_BACKEND_IMAGE="$RESEARCH_BACKEND_IMAGE"
    export Q_TORCH_DEVICE="${Q_TORCH_DEVICE:-cuda}"
    export CUBLAS_WORKSPACE_CONFIG="${CUBLAS_WORKSPACE_CONFIG:-:4096:8}"
    "${compose_cmd[@]}" --profile containerized up -d
  else
    ensure_backend_venv
    check_host_cuda
    prepare_mt5_gateway
    record_research_gateway_usage
    export_host_backend_env

    LOG_DIR="$RESEARCH_LOG_DIR"
    mkdir -p "$LOG_DIR"

    echo "starting Postgres and Redis ..."
    "${RESEARCH_COMPOSE[@]}" up -d --wait postgres redis
    ensure_host_compose_ports

    run_host_migrations

    echo "starting host API, Dramatiq worker, and outbox relay ..."
    API_PID="$(start_host_process api "$BACKEND_DIR/.venv/bin/uvicorn" \
      q_backend.api.main:app --host 127.0.0.1 --port "$RESEARCH_API_PORT")"
    WORKER_PID="$(start_host_process worker "$BACKEND_DIR/.venv/bin/worker")"
    RELAY_PID="$(start_host_process relay "$BACKEND_DIR/.venv/bin/q-outbox-relay")"
  fi

  wait_for_api 90
  launch_ui
}

research_down() {
  echo "shutting down Research stack ..."
  mkdir -p "$RESEARCH_PID_DIR"

  if [[ -f "$RESEARCH_PID_DIR/ui.pid" ]]; then
    local ui_p
    ui_p="$(cat "$RESEARCH_PID_DIR/ui.pid" 2>/dev/null || true)"
    stop_host_process "$ui_p" "ui"
    rm -f "$RESEARCH_PID_DIR/ui.pid"
  fi

  for proc in worker relay api; do
    if [[ -f "$RESEARCH_PID_DIR/$proc.pid" ]]; then
      local p
      p="$(cat "$RESEARCH_PID_DIR/$proc.pid" 2>/dev/null || true)"
      stop_host_process "$p" "$proc"
      rm -f "$RESEARCH_PID_DIR/$proc.pid"
    fi
  done

  [[ -n "${UI_PID:-}" ]] && stop_host_process "$UI_PID" "ui"
  [[ -n "${WORKER_PID:-}" ]] && stop_host_process "$WORKER_PID" "worker"
  [[ -n "${RELAY_PID:-}" ]] && stop_host_process "$RELAY_PID" "relay"
  [[ -n "${API_PID:-}" ]] && stop_host_process "$API_PID" "api"
  UI_PID="" WORKER_PID="" RELAY_PID="" API_PID=""

  if command -v docker >/dev/null 2>&1; then
    "${RESEARCH_COMPOSE[@]}" --profile containerized down --remove-orphans 2>/dev/null || true
  fi

  rm -f "$RESEARCH_PID_DIR"/*.pid "$RESEARCH_PID_DIR/mode" \
    "$RESEARCH_PID_DIR/local-gateway" 2>/dev/null || true
  echo "Research stack stopped."
}

cleanup() {
  research_down
}

is_research_running() {
  if docker_research_service_running backend || docker_research_service_running worker; then
    return 0
  fi
  if is_process_running api || is_process_running worker || is_process_running relay; then
    return 0
  fi
  if docker_research_service_running postgres || docker_research_service_running redis; then
    return 0
  fi
  return 1
}

is_research_using_gateway() {
  is_research_running || return 1
  [[ -f "$RESEARCH_PID_DIR/local-gateway" ]]
}

research_mode() {
  if [[ -f "$RESEARCH_PID_DIR/mode" ]]; then
    cat "$RESEARCH_PID_DIR/mode"
  else
    echo "${MODE:-host}"
  fi
}

research_service_label() {
  local svc="$1"
  case "$svc" in
    postgres) echo "docker:postgres ($RESEARCH_COMPOSE_PROJECT)" ;;
    redis) echo "docker:redis ($RESEARCH_COMPOSE_PROJECT)" ;;
    migrate) echo "alembic upgrade head" ;;
    api)
      if [[ "$(research_mode)" == "container" ]]; then
        echo "docker:backend ($RESEARCH_COMPOSE_PROJECT)"
      else
        echo "q_backend.api.main:app"
      fi
      ;;
    worker)
      if [[ "$(research_mode)" == "container" ]]; then
        echo "docker:worker ($RESEARCH_COMPOSE_PROJECT)"
      else
        echo "dramatiq worker"
      fi
      ;;
    relay)
      if [[ "$(research_mode)" == "container" ]]; then
        echo "docker:relay ($RESEARCH_COMPOSE_PROJECT)"
      else
        echo "q-outbox-relay"
      fi
      ;;
    ui) echo "Research UI (${Q_RESEARCH_UI:-tauri})" ;;
    *) echo "-" ;;
  esac
}

research_service_state() {
  local svc="$1"
  case "$svc" in
    postgres)
      if docker_research_service_running postgres; then
        echo "running"
      elif host_port_open "$RESEARCH_PG_PORT"; then
        echo "port in use"
      else
        echo "stopped"
      fi
      ;;
    redis)
      if docker_research_service_running redis; then
        echo "running"
      elif host_port_open "$RESEARCH_REDIS_PORT"; then
        echo "port in use"
      else
        echo "stopped"
      fi
      ;;
    migrate)
      if [[ -f "$RESEARCH_DATA_DIR/migrate.stamp" ]]; then
        echo "done"
      elif docker_research_service_running backend || is_process_running api; then
        echo "done"
      else
        echo "pending"
      fi
      ;;
    api)
      if [[ "$(research_mode)" == "container" ]]; then
        if docker_research_service_running backend; then echo "running"; else echo "stopped"; fi
      else
        if is_process_running api; then
          echo "running (PID $(cat "$RESEARCH_PID_DIR/api.pid" 2>/dev/null || echo "?"))"
        else
          echo "stopped"
        fi
      fi
      ;;
    worker)
      if [[ "$(research_mode)" == "container" ]]; then
        if docker_research_service_running worker; then echo "running"; else echo "stopped"; fi
      else
        if is_process_running worker; then
          echo "running (PID $(cat "$RESEARCH_PID_DIR/worker.pid" 2>/dev/null || echo "?"))"
        else
          echo "stopped"
        fi
      fi
      ;;
    relay)
      if [[ "$(research_mode)" == "container" ]]; then
        if docker_research_service_running relay; then echo "running"; else echo "stopped"; fi
      else
        if is_process_running relay; then
          echo "running (PID $(cat "$RESEARCH_PID_DIR/relay.pid" 2>/dev/null || echo "?"))"
        else
          echo "stopped"
        fi
      fi
      ;;
    ui)
      if is_process_running ui; then
        echo "running (PID $(cat "$RESEARCH_PID_DIR/ui.pid" 2>/dev/null || echo "?"))"
      else
        echo "stopped"
      fi
      ;;
    *) echo "-" ;;
  esac
}

research_readiness() {
  local svc="$1"
  case "$svc" in
    postgres)
      if host_port_open "$RESEARCH_PG_PORT"; then echo "ready"; else echo "not ready"; fi
      ;;
    redis)
      if host_port_open "$RESEARCH_REDIS_PORT"; then echo "PONG"; else echo "not ready"; fi
      ;;
    migrate)
      if [[ -f "$RESEARCH_DATA_DIR/migrate.stamp" ]]; then echo "done"; else echo "-"; fi
      ;;
    api)
      if curl -fsS "$RESEARCH_API_HEALTH_URL" >/dev/null 2>&1; then echo "healthy"; else echo "not ready"; fi
      ;;
    worker)
      if [[ "$(research_service_state worker)" == running* ]]; then echo "active"; else echo "offline"; fi
      ;;
    relay)
      if [[ "$(research_service_state relay)" == running* ]]; then echo "active"; else echo "offline"; fi
      ;;
    ui)
      if is_process_running ui; then echo "active"; else echo "inactive"; fi
      ;;
    *) echo "-" ;;
  esac
}

research_logs() {
  local svc="${1:-api}"
  case "$svc" in
    postgres|redis)
      dev_follow "${RESEARCH_COMPOSE[@]}" logs -f "$svc"
      ;;
    api|worker|relay|ui)
      if [[ "$(research_mode)" == "container" && "$svc" != "ui" ]]; then
        local target="$svc"
        [[ "$svc" == "api" ]] && target="backend"
        dev_follow "${RESEARCH_COMPOSE[@]}" logs -f "$target"
      else
        local log="$RESEARCH_LOG_DIR/$svc.log"
        [[ -f "$log" ]] || die "log file not found: $log"
        dev_follow tail -f "$log"
      fi
      ;;
    *)
      die "logs not available for research service: $svc"
      ;;
  esac
}

research_restart() {
  local svc="${1:-}"
  [[ -n "$svc" ]] || die "usage: ./dev restart research:<service>"
  case "$svc" in
    postgres|redis)
      need docker
      "${RESEARCH_COMPOSE[@]}" restart "$svc"
      if [[ "$svc" == postgres ]]; then
        echo "restarted research postgres"
      else
        echo "restarted research redis"
      fi
      ;;
    api|worker|relay)
      if [[ "$(research_mode)" == "container" ]]; then
        local target="$svc"
        [[ "$svc" == "api" ]] && target="backend"
        "${RESEARCH_COMPOSE[@]}" restart "$target"
        echo "restarted research $svc (container)"
      else
        local pid
        pid="$(cat "$RESEARCH_PID_DIR/$svc.pid" 2>/dev/null || true)"
        stop_host_process "$pid" "$svc"
        export_host_backend_env
        case "$svc" in
          api)
            API_PID="$(start_host_process api "$BACKEND_DIR/.venv/bin/uvicorn" \
              q_backend.api.main:app --host 127.0.0.1 --port "$RESEARCH_API_PORT")"
            wait_for_api 30
            ;;
          worker)
            WORKER_PID="$(start_host_process worker "$BACKEND_DIR/.venv/bin/worker")"
            ;;
          relay)
            RELAY_PID="$(start_host_process relay "$BACKEND_DIR/.venv/bin/q-outbox-relay")"
            ;;
        esac
        echo "restarted research $svc (host)"
      fi
      ;;
    *)
      die "cannot restart research service: $svc"
      ;;
  esac
}
