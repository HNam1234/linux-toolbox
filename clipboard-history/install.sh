#!/usr/bin/env bash
set -euo pipefail

shortcut_path="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipboard-history/"
autostart="$HOME/.config/autostart/copyq.desktop"
shortcut="$HOME/.local/bin/copyq-super-v"

if ! command -v copyq >/dev/null 2>&1; then
  if command -v pkexec >/dev/null 2>&1; then
    pkexec apt-get install -y copyq
  else
    echo "CopyQ is not installed. Run: sudo apt install copyq" >&2
    exit 1
  fi
fi

mkdir -p "$HOME/.config/autostart" "$HOME/.local/bin"
cat > "$autostart" <<EOF
[Desktop Entry]
Type=Application
Name=CopyQ
Comment=Clipboard manager
Exec=copyq
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

cat > "$shortcut" <<'EOF'
#!/usr/bin/env bash
set -e

if ! pgrep -x copyq >/dev/null 2>&1; then
  copyq >/dev/null 2>&1 &
  sleep 0.4
fi

exec copyq toggle
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

copyq >/dev/null 2>&1 &

echo "CopyQ clipboard history installed."
echo "Use Super+V to open history."
echo "CopyQ will start automatically on login."
