# Chrome Profile Split GNOME

Small Ubuntu GNOME utilities for a more Windows-like desktop workflow:

- Separate dock icons for each Chrome/Chromium profile.
- `Super+V` clipboard history popup.

## Chrome Profile Dock Icons

### Install

```bash
git clone git@github.com:HNam1234/Chrome_Profile_Split_Gnome.git
cd Chrome_Profile_Split_Gnome
./install.sh
```

Then open **Chrome Dock Profiles** from Applications.

The app gives you a guided GUI with:

- A system compatibility check.
- Detected Chrome/Chromium profile cards.
- One-click install/update for profile dock icons.
- One-click pinning to Ubuntu Dock.
- Dock click style choices.
- Hover preview extension installation.

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

## Clipboard History

### Install

```bash
cd Chrome_Profile_Split_Gnome/clipboard-history
./install.sh
```

### Use

- Press `Super+V` to open clipboard history.
- Type to search copied text.
- Press `Enter` or double-click an item to copy it back.
- Click **Clear History** to remove saved entries.

The clipboard daemon starts automatically on login. Pressing `Super+V` also starts it if it is not running yet.

Clipboard entries are stored locally at:

```text
~/.local/share/clipboard-history/history.json
```

## Compatibility

- Best support: Ubuntu GNOME on X11.
- Wayland: dock settings and clipboard history should work, but Chrome profile window grouping may be less reliable.
- Hover previews currently target GNOME 42.
