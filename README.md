# Linux Toolbox

Set-and-forget Ubuntu GNOME utilities for a more Windows-like desktop workflow. Linux Toolbox is built for one-time setup: choose the desktop behavior you want, then use your machine without thinking about those tweaks again.

- Separate dock icons and window grouping for each Chrome/Chromium profile.
- A Windows-style horizontal dock preset for Ubuntu Dock, with restore back to the original layout.
- `Super+V` clipboard history popup powered by CopyQ.
- Simple Windows/macOS-like mouse movement presets powered by maccel.
- Managed installer for the Cockpit Tools Codex fork.

## Install

Install once, then open **Linux Toolbox** whenever you want to check or change a setup:

```bash
git clone https://github.com/HNam1234/linux-toolbox.git
cd linux-toolbox
./install.sh
```

Then open **Linux Toolbox** from Applications, or run:

```bash
linux-toolbox
```

The app gives you a guided tabbed GUI with:

- A Main tab with system overview and activity.
- Detected Chrome/Chromium profile cards.
- One-click install/update for profile dock icons.
- One-click pinning to Ubuntu Dock.
- A Windows taskbar-style dock layout toggle with original-layout restore.
- Dock click style choices.
- Dedicated ArcMenu, Bluetooth Battery Meter, and Dash to Panel tabs with independent install, enable/disable, reset, and inline GSettings controls.
- A Clipboard tab with CopyQ clipboard history toggle and `Super+V` binding.
- A Mouse Movement tab with install status, maccel installer progress, Windows, macOS, and Restore Original buttons.
- A Cockpit Fork tab that builds and installs `HNam1234/cockpit-tools-linux-codex`, replacing an official `cockpit-tools` package only after the fork `.deb` has been built and validated.

The old `chrome-dock-profiles` command is still installed as a compatibility alias for existing users.

## What It Does

- Detects Chrome/Chromium profiles.
- Creates one `.desktop` launcher per profile.
- Uses a profile-specific `StartupWMClass` plus launcher-side window-class assignment so GNOME can keep profile windows grouped under their own dock icons.
- Uses each profile picture as the dock icon when available.
- Pins the profile launchers to Ubuntu Dock.
- Moves Ubuntu Dock to a bottom, full-width, always-visible Windows-style taskbar layout with Show Applications on the left.
- Lets you toggle back to the Ubuntu default dock layout or restore the original saved dock layout.
- Lets you choose dock click behavior:
  - Smooth Minimize
  - Minimize + Previews
  - Preview Picker
  - Cycle Windows

## GNOME Extensions

Each essential GNOME extension has its own top-level tab rather than being grouped into an install-only list. Every tab shows whether the extension is installed and enabled, lets you turn it on or off independently, and exposes common settings directly in Linux Toolbox. Additional simple settings are available under **Advanced settings**; complex preferences remain available through the extension's full GNOME preferences window.

The initial extensions are:

- **ArcMenu** — menu layout, panel position, button appearance, icon size, default view, and display options.
- **Bluetooth Battery Meter** — quick settings display, panel indicator style, hover behavior, tooltip, and sizing.
- **Dash to Panel** — panel position/size, intellihide, previews, app grouping, multi-monitor behavior, and click/scroll actions.

## Clipboard History

Clipboard history is handled by **CopyQ**, a mature clipboard manager packaged by Ubuntu.

### Install

```bash
cd linux-toolbox/clipboard-history
./install.sh
```

### Use

- Press `Super+V` to open clipboard history.
- Type to search copied text.
- Select an item in CopyQ to reuse it.

CopyQ starts automatically on login. The main **Linux Toolbox** GUI also has a Clipboard History switch that turns CopyQ autostart and the `Super+V` shortcut on or off.

If CopyQ is not installed yet, the GUI/installer asks Ubuntu to install the `copyq` package.

## Mouse Movement

Mouse Movement uses the open-source `maccel` Linux mouse acceleration backend:

https://github.com/Gnarus-G/maccel

The GUI shows a simple `[V]` or `[X]` backend indicator and an install button. It does not install anything silently. If you click **Install maccel**, Ubuntu will ask for authentication and the app will install maccel plus required packages such as `curl`, `git`, `make`, `dkms`, `gcc`, and matching Linux headers.

While installation runs, the Mouse Movement tab shows an active progress bar and the latest install log line.

If `maccel` is available in `PATH`, open **Linux Toolbox** and use:

- **Windows** for a Windows Enhanced Pointer Precision-like approximation.
- **macOS** for a smooth macOS-like approximation.
- **Restore Original** to restore the maccel settings backed up before Linux Toolbox changed them.

On Wayland, support may depend on compositor behavior.

Install logs are written to:

```text
~/.config/chrome-dock-profiles/maccel-install.log
```

## Cockpit Tools Codex Fork

Linux Toolbox includes a managed installer for the Cockpit Tools Codex patch:

<https://github.com/HNam1234/cockpit-tools-linux-codex>

The fork currently does not publish Linux release assets, so the installer
fetches the upstream source and applies a local patch before building the
Debian package. It checks the package name and architecture, then removes an
existing official/unknown `cockpit-tools` package and installs the validated
patched build. A failed build leaves the existing installation untouched.

The package is removed with `dpkg --remove`, never `purge`; Cockpit account,
session, and configuration data are kept. Linux Toolbox records a small marker
and binary hash under `~/.local/share/linux-toolbox/` so it can distinguish its
managed fork from an official or manually installed package.

The same installer is available from the command line after running the main
installer:

```bash
linux-toolbox-install-cockpit-tools status
linux-toolbox-install-cockpit-tools install --stop-running
linux-toolbox-install-cockpit-tools repair --stop-running
linux-toolbox-install-cockpit-tools uninstall --stop-running
```

If a later official update overwrites the patched package, use the **Reapply
Fork Patch** button in the Cockpit tab or run the `repair` command. This does
not require maintaining another fork: it reapplies the patch to the latest
upstream source. If upstream moves or removes a patch target, the build fails
before the installed package is changed.

Building requires Node.js 18+, npm 9+, Rust/Cargo, Go, Git, and the Tauri Linux
build libraries. Missing Ubuntu/Debian build packages are installed through
`pkexec` during the build. The patched build is pointed at the fork's updater
and remote-config URLs so it does not automatically replace itself with the
official release channel.

## Compatibility

- Best support: Ubuntu GNOME on X11.
- Wayland: dock settings and clipboard history should work. Chrome profile window grouping is forced through Chrome's X11 backend when launched from generated profile icons for better GNOME dock separation.
- Hover previews install a legacy extension on GNOME 42-44 and a module-based extension on GNOME 45+.
