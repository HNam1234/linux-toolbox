#!/usr/bin/env bash
set -u

session_source="${WAYLAND_DISPLAY:-${DISPLAY:-default}}"
session_name="ltb-${session_source//[^A-Za-z0-9_-]/_}"
session_name="${session_name:0:16}"

if ! copyq --session "$session_name" config item_popup_interval 0 >/dev/null 2>&1; then
  copyq --session "$session_name" --start-server config item_popup_interval 0 >/dev/null 2>&1 || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    copyq --session "$session_name" config item_popup_interval 0 >/dev/null 2>&1 && break
    sleep 0.2
  done
fi

copyq --session "$session_name" config item_popup_interval 0 >/dev/null 2>&1 || true
copyq --session "$session_name" config native_notifications false >/dev/null 2>&1 || true
copyq --session "$session_name" config clipboard_notification_lines 0 >/dev/null 2>&1 || true
copyq --session "$session_name" config close_on_unfocus true >/dev/null 2>&1 || true
copyq --session "$session_name" config hide_main_window true >/dev/null 2>&1 || true
copyq --session "$session_name" config open_windows_on_current_screen true >/dev/null 2>&1 || true
exec copyq --session "$session_name" show >/dev/null 2>&1
