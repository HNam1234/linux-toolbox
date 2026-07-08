#!/usr/bin/env bash
set -u

session_source="${WAYLAND_DISPLAY:-${DISPLAY:-default}}"
session_name="ltb-${session_source//[^A-Za-z0-9_-]/_}"
session_name="${session_name:0:16}"

if ! copyq --session "$session_name" count >/dev/null 2>&1; then
  exit 0
fi

copyq --session "$session_name" eval -- '
  var n = count();
  if (n > 0) {
    var rows = [];
    for (var i = 0; i < n; ++i) rows.push(i);
    remove.apply(this, rows);
  }
  copy("");
  copySelection("");
' >/dev/null 2>&1 || true
