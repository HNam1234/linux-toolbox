# Chrome Profile Split GNOME

Small Ubuntu GNOME utilities for a more Windows-like desktop workflow:

- Separate dock icons for each Chrome/Chromium profile.
- `Super+V` clipboard history popup powered by CopyQ.
- Simple Windows/macOS-like mouse movement presets powered by maccel.

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
- CopyQ clipboard history toggle with `Super+V` binding.
- Mouse Movement presets with Windows, macOS, and Restore Previous buttons.

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

Clipboard history is handled by **CopyQ**, a mature clipboard manager packaged by Ubuntu.

### Install

```bash
cd Chrome_Profile_Split_Gnome/clipboard-history
./install.sh
```

### Use

- Press `Super+V` to open clipboard history.
- Type to search copied text.
- Select an item in CopyQ to reuse it.

CopyQ starts automatically on login. The main **Chrome Dock Profiles** GUI also has a Clipboard History switch that turns CopyQ autostart and the `Super+V` shortcut on or off.

If CopyQ is not installed yet, the GUI/installer asks Ubuntu to install the `copyq` package.

## Mouse Movement

Mouse Movement uses the open-source `maccel` Linux mouse acceleration backend:

https://github.com/Gnarus-G/maccel

The GUI does not install maccel, does not run sudo, and does not expose curve editing. If `maccel` is available in `PATH`, open **Chrome Dock Profiles** and use:

- **Windows** for a Windows Enhanced Pointer Precision-like approximation.
- **macOS** for a smooth macOS-like approximation.
- **Restore Previous** to restore the maccel settings backed up before the last preset.

On Wayland, support may depend on compositor behavior.

## Compatibility

- Best support: Ubuntu GNOME on X11.
- Wayland: dock settings and clipboard history should work, but Chrome profile window grouping and maccel behavior may be less reliable.
- Hover previews currently target GNOME 42.
