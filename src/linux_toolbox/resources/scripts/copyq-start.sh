#!/usr/bin/env bash
set -u

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/linux-toolbox"
mkdir -p "$state_dir"
log_file="$state_dir/copyq-start.log"
session_source="${WAYLAND_DISPLAY:-${DISPLAY:-default}}"
session_name="ltb-${session_source//[^A-Za-z0-9_-]/_}"
session_name="${session_name:0:16}"

{
  printf '%s starting CopyQ launcher for %s\n' "$(date -Is)" "$session_name"

  if [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    echo "No graphical display is available yet."
    exit 1
  fi

  copyq --session "$session_name" --start-server config item_popup_interval 0 >/dev/null 2>&1 || true

  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if copyq --session "$session_name" config native_notifications false >/dev/null 2>&1; then
      copyq --session "$session_name" config clipboard_notification_lines 0 >/dev/null 2>&1 || true
      copyq --session "$session_name" config close_on_unfocus true >/dev/null 2>&1 || true
      copyq --session "$session_name" config hide_main_window true >/dev/null 2>&1 || true
      copyq --session "$session_name" config open_windows_on_current_screen true >/dev/null 2>&1 || true
      echo "CopyQ server is ready."
      exit 0
    fi
    sleep 0.3
  done

  echo "CopyQ server did not become ready."
  exit 1
} >>"$log_file" 2>&1
