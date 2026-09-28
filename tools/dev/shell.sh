# Interactive ./dev shell — sourced from dev after dispatch_dev is defined.

shell_help() {
  cat <<'EOF'
Interactive dev shell commands:
  up live|research|all     Start stacks (research: --host | --container [--rebuild])
  down live|research|all   Stop stacks (default target: all)
  status                   Stack overview
  logs <service>           Follow logs until Ctrl+C (returns to prompt)
  restart <service>        Restart a service by alias
  help                     Show this message
  exit, quit               Leave the shell (running stacks are not stopped)

Use ./dev down to stop stacks; exit only closes this prompt.
EOF
}

shell_run_command() {
  set +e
  Q_DEV_SHELL_ACTIVE=1
  local status=0
  (
    set -euo pipefail
    dispatch_dev "$@"
  )
  status=$?
  unset Q_DEV_SHELL_ACTIVE
  set -e
  if [[ $status -ne 0 ]]; then
    echo "command exited with status $status" >&2
  fi
}

shell_handle_line() {
  local line="$1"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "$line" ]] && return 0

  local -a words=()
  read -r -a words <<<"$line"
  local verb="${words[0]}"

  case "$verb" in
    exit|quit)
      return 2
      ;;
    help|-h|--help)
      shell_help
      return 0
      ;;
    status)
      shell_run_command status
      ;;
    up)
      if [[ ${#words[@]} -lt 2 ]]; then
        echo "usage: up live|research|all" >&2
        return 0
      fi
      case "${words[1]}" in
        live)
          shell_run_command live
          ;;
        all)
          shell_run_command all
          ;;
        research)
          shell_run_command research "${words[@]:2}"
          ;;
        *)
          echo "unknown up target: ${words[1]} (expected live|research|all)" >&2
          ;;
      esac
      ;;
    down)
      local target="${words[1]:-all}"
      shell_run_command down "$target"
      ;;
    logs)
      if [[ ${#words[@]} -lt 2 ]]; then
        echo "usage: logs <service>" >&2
        return 0
      fi
      shell_run_command logs "${words[1]}"
      ;;
    restart)
      if [[ ${#words[@]} -lt 2 ]]; then
        echo "usage: restart <service>" >&2
        return 0
      fi
      shell_run_command restart "${words[1]}"
      ;;
    *)
      echo "unknown command: $verb (type 'help' for commands)" >&2
      ;;
  esac
  return 0
}

cmd_shell() {
  echo "Q dev shell (type 'help' for commands, 'exit' to leave stacks running)"
  while true; do
    local line rc=0
    set +e
    IFS= read -r -p "dev> " line
    rc=$?
    set -e
    if [[ $rc -ne 0 ]]; then
      if [[ $rc -eq 130 ]]; then
        echo
        continue
      fi
      echo
      break
    fi
    if shell_handle_line "$line"; then
      rc=0
    else
      rc=$?
    fi
    if [[ $rc -eq 2 ]]; then
      break
    fi
  done
}
