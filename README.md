# Chrome_Profile_Split_Gnome

Small Ubuntu utility for separate Chrome profile dock icons.

## Install

```bash
cd ~/chrome-dock-profiles
./install.sh
```

Then open **Chrome Dock Profiles** from Applications.

## What It Does

- Detects Chrome/Chromium profiles.
- Creates one `.desktop` launcher per profile.
- Uses each profile picture as the dock icon when available.
- Pins the profile launchers to Ubuntu Dock.
- Lets you choose dock click behavior:
  - Smooth Minimize
  - Minimize + Previews
  - Preview Picker
  - Cycle Windows
- Installs a local GNOME 42 hover-preview extension.

After installing hover previews, restart GNOME Shell:

```text
Alt+F2, type r, press Enter
```

On Wayland, log out and back in instead.
