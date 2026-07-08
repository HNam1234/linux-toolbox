#!/usr/bin/env bash
set -euo pipefail

shortcut_path="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipboard-history/"
autostart="$HOME/.config/autostart/copyq.desktop"
shortcut="$HOME/.local/bin/copyq-super-v"
starter="$HOME/.local/bin/copyq-start"
service_dir="$HOME/.config/systemd/user"
service="$service_dir/copyq.service"

if ! command -v copyq >/dev/null 2>&1; then
  if command -v pkexec >/dev/null 2>&1; then
    pkexec apt-get install -y copyq
  else
    echo "CopyQ is not installed. Run: sudo apt install copyq" >&2
    exit 1
  fi
fi

mkdir -p "$HOME/.config/autostart" "$HOME/.local/bin"
cat > "$starter" <<'EOF'
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
EOF
chmod +x "$starter"

cat > "$autostart" <<EOF
[Desktop Entry]
Type=Application
Name=CopyQ
Comment=Clipboard manager
Exec=$starter
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=2
EOF

cat > "$shortcut" <<'EOF'
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
EOF
chmod +x "$shortcut"

current="$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)"
python3 - "$current" "$shortcut_path" <<'PY' | xargs -0 gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings
import ast
import sys

try:
    entries = ast.literal_eval(sys.argv[1])
except Exception:
    entries = []
path = sys.argv[2]
if path not in entries:
    entries.append(path)
print("[" + ", ".join(repr(entry) for entry in entries) + "]", end="\0")
PY

schema="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$shortcut_path"
gsettings set "$schema" name "Clipboard History"
gsettings set "$schema" command "$shortcut"
gsettings set "$schema" binding "<Super>v"

"$starter" >/dev/null 2>&1 || true
if [ -e "$service" ]; then
  systemctl --user disable --now copyq.service >/dev/null 2>&1 || true
  rm -f "$service"
  systemctl --user daemon-reload >/dev/null 2>&1 || true
fi

echo "CopyQ clipboard history installed."
echo "Use Super+V to open history."
echo "CopyQ will start automatically on login."
