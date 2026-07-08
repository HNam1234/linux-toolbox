---
name: verify
description: Runtime verification recipe for Linux Toolbox GUI changes
---

# Linux Toolbox runtime verification

Use this skill when verifying Linux Toolbox GUI/launcher behavior.

## GUI handle

Linux Toolbox is a GTK 3 app launched by:

```bash
python3 chrome_dock_profiles.py
```

For isolated GUI verification, run it under Xvfb with a temporary HOME, memory-backed gsettings, and fake Chrome profiles:

```bash
verify_dir=$(mktemp -d /tmp/linux-toolbox-verify.XXXXXX)
fake_home="$verify_dir/home"
mkdir -p "$fake_home/.config/google-chrome/Default" "$fake_home/.config/google-chrome/Profile 1" "$verify_dir/bin" "$verify_dir/out"
printf '{"profile":{"info_cache":{"Default":{"name":"Personal"},"Profile 1":{"name":"Work"}}}}' > "$fake_home/.config/google-chrome/Local State"
printf '{}' > "$fake_home/.config/google-chrome/Default/Preferences"
printf '{}' > "$fake_home/.config/google-chrome/Profile 1/Preferences"
```

Put a fake Chrome binary in `$verify_dir/bin/google-chrome` to capture launcher args without opening real Chrome:

```bash
cat > "$verify_dir/bin/google-chrome" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$@" >>"$HOME/chrome-args.log"
exit 0
SH
chmod +x "$verify_dir/bin/google-chrome"
```

Launch with:

```bash
xvfb-run -a --server-args='-screen 0 1280x900x24' bash -c '
  cd /path/to/linux-toolbox
  export HOME="'$fake_home'"
  export XDG_CONFIG_HOME="$HOME/.config"
  export XDG_DATA_HOME="$HOME/.local/share"
  export XDG_STATE_HOME="$HOME/.local/state"
  export GSETTINGS_BACKEND=memory
  export LINUX_TOOLBOX_APP_ID=local.linux_toolbox.verify
  export PATH="'$verify_dir'/bin:$PATH"
  python3 chrome_dock_profiles.py
'
```

## Driving the UI

- The app starts on Overview.
- Set `LINUX_TOOLBOX_APP_ID` to a unique value if a real Linux Toolbox instance is already running; otherwise GTK single-instance activation can make the Xvfb app exit immediately.
- Use `xdotool key Down` after the first click/focus to move from Overview to Chrome Profiles. Direct coordinate clicks can be unreliable under Xvfb without a window manager.
- To enable Chrome Profile Dock Icons on the Chrome Profiles page, a click near absolute/window-relative `(1050, 435)` toggled the first switch in a 1280x900 Xvfb screen.
- To enable Hover Window Previews on the Chrome Profiles page, a click near absolute/window-relative `(1040, 465)` toggled the second switch in a 1280x900 Xvfb screen.
- Capture screenshots from inside the X session with GDK if normal screenshot tools capture the host display.

## Evidence to capture

For Chrome profile launcher changes, capture:

1. Screenshot of the Overview/sidebar proving removed tabs are not exposed.
2. Screenshot of Chrome Profiles before/after enabling the switch.
3. Generated files under `$HOME/.local/share/applications/google-chrome-profile*.desktop` showing `StartupWMClass=<profile class>` and `Exec=... chrome-profile-launch "<profile>" <profile class> ...`.
4. Captured fake Chrome args after running the generated wrapper, expecting `--ozone-platform=x11`, `--profile-directory=<profile>`, and `--class=<profile class>`.

Keep generated files under the temp HOME so verification does not change the user's real desktop settings.
