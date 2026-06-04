#!/usr/bin/env bash
set -euo pipefail

app_dir="$HOME/.local/share/chrome-dock-profiles"
bin_dir="$HOME/.local/bin"
desktop_file="$HOME/.local/share/applications/chrome-dock-profiles.desktop"

mkdir -p "$app_dir" "$bin_dir" "$HOME/.local/share/applications"
cp "$(dirname "$0")/chrome_dock_profiles.py" "$app_dir/chrome_dock_profiles.py"
chmod +x "$app_dir/chrome_dock_profiles.py"

cat > "$bin_dir/chrome-dock-profiles" <<EOF
#!/usr/bin/env bash
set -e

if command -v python3.10 >/dev/null 2>&1; then
  exec python3.10 "$app_dir/chrome_dock_profiles.py" "\$@"
fi

exec python3 "$app_dir/chrome_dock_profiles.py" "\$@"
EOF
chmod +x "$bin_dir/chrome-dock-profiles"

cat > "$desktop_file" <<EOF
[Desktop Entry]
Version=1.0
Name=Chrome Dock Profiles
Comment=Install separate Ubuntu Dock icons for Chrome profiles
Exec=$bin_dir/chrome-dock-profiles
Terminal=false
Type=Application
Categories=Utility;
Icon=google-chrome
EOF

update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
echo "Installed. Open 'Chrome Dock Profiles' from Applications, or run:"
echo "$bin_dir/chrome-dock-profiles"
