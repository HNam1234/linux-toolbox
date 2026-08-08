#!/usr/bin/env bash
set -euo pipefail

app_dir="$HOME/.local/share/chrome-dock-profiles"
bin_dir="$HOME/.local/bin"
desktop_file="$HOME/.local/share/applications/chrome-dock-profiles.desktop"
new_desktop_file="$HOME/.local/share/applications/linux-toolbox.desktop"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$app_dir" "$bin_dir" "$HOME/.local/share/applications"
cp "$script_dir/chrome_dock_profiles.py" "$app_dir/chrome_dock_profiles.py"
rm -rf "$app_dir/src"
cp -a "$script_dir/src" "$app_dir/src"
chmod +x "$app_dir/chrome_dock_profiles.py"

cockpit_installer="$bin_dir/linux-toolbox-install-cockpit-tools"
cp "$script_dir/src/linux_toolbox/resources/scripts/install-cockpit-tools-fork.sh" "$cockpit_installer"
chmod +x "$cockpit_installer"

write_launcher() {
  local target="$1"
  cat > "$target" <<EOF
#!/usr/bin/env bash
set -e

if command -v python3.10 >/dev/null 2>&1; then
  exec python3.10 "$app_dir/chrome_dock_profiles.py" "\$@"
fi

exec python3 "$app_dir/chrome_dock_profiles.py" "\$@"
EOF
  chmod +x "$target"
}

write_launcher "$bin_dir/chrome-dock-profiles"
write_launcher "$bin_dir/linux-toolbox"

cat > "$new_desktop_file" <<EOF
[Desktop Entry]
Version=1.0
Name=Linux Toolbox
Comment=Set-and-forget Ubuntu tools for Chrome profiles, dock, clipboard, mouse movement, and the Cockpit fork
Exec=$bin_dir/linux-toolbox
Terminal=false
Type=Application
Categories=Utility;
Icon=applications-utilities
EOF
rm -f "$desktop_file"

remove_managed_ai_wrapper() {
  local target="$1"
  if [ -f "$target" ] && grep -q "Managed by Linux Toolbox AI Tools" "$target" 2>/dev/null; then
    rm -f "$target"
  fi
}

# Clean up obsolete generated files from older Linux Toolbox AI Tools and
# Vietnamese Input features. Personal Claude/Codex/IBus configs are left alone.
rm -f \
  "$HOME/.local/share/applications/aitools.desktop" \
  "$bin_dir/linux-toolbox-aitools" \
  "$bin_dir/chrome-dock-profiles-install-vietnamese-input"
remove_managed_ai_wrapper "$bin_dir/bicodex"
remove_managed_ai_wrapper "$bin_dir/biclaude"
if command -v gsettings >/dev/null 2>&1; then
  current_favorites="$(gsettings get org.gnome.shell favorite-apps 2>/dev/null || true)"
  if [ -n "$current_favorites" ]; then
    python3 - "$current_favorites" <<'PY' | xargs -0 -r gsettings set org.gnome.shell favorite-apps
import ast
import sys

try:
    favorites = ast.literal_eval(sys.argv[1])
except Exception:
    sys.exit(0)
if not isinstance(favorites, list):
    sys.exit(0)
filtered = [item for item in favorites if item != "aitools.desktop"]
if filtered == favorites:
    sys.exit(0)
print("[" + ", ".join(repr(item) for item in filtered) + "]", end="\0")
PY
  fi
fi

update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
echo "Installed. Open 'Linux Toolbox' from Applications, or run:"
echo "$bin_dir/linux-toolbox"
echo "Compatibility command kept: $bin_dir/chrome-dock-profiles"
echo "Cockpit fork installer: $cockpit_installer"
