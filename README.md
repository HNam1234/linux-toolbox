# Linux Toolbox

Set-and-forget Ubuntu GNOME utilities for a more Windows-like desktop workflow. Linux Toolbox is built for one-time setup: choose the desktop behavior you want, then use your machine without thinking about those tweaks again.

- Separate dock icons for each Chrome/Chromium profile.
- Simple AI login and terminal command setup.
- A Windows-style horizontal dock preset for Ubuntu Dock, with restore back to the original layout.
- `Super+V` clipboard history popup powered by CopyQ.
- Simple Windows/macOS-like mouse movement presets powered by maccel.

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
- An AI Tools tab with separate Codex CLI, Claude CLI, Codex VS Code, and Claude VS Code configs.
- Detected Chrome/Chromium profile cards.
- One-click install/update for profile dock icons.
- One-click pinning to Ubuntu Dock.
- A Windows taskbar-style dock layout toggle with original-layout restore.
- Dock click style choices.
- Hover preview extension installation.
- A Clipboard tab with CopyQ clipboard history toggle and `Super+V` binding.
- A Mouse Movement tab with install status, maccel installer progress, Windows, macOS, and Restore Original buttons.

The old `chrome-dock-profiles` command is still installed as a compatibility alias for existing users.

## AI Tools

Set it up once:

1. Use the overview table to see which mode each real config is using and whether it is configured.
2. Click **Edit** on a row to open that target's config popup.
3. In the popup, choose **Bifrost** or **Web login**. If a target uses Bifrost, paste its URL/key/model. If it uses Web login, set an account label.
4. Click **Install / Update bicodex** or **Install / Update biclaude** to refresh terminal wrappers.
5. Use **Bifrost Token Usage** to open `https://bifrost.sotatek.works/portal` and check API-key token usage.

Then use these from any terminal:

```bash
codex
claude
bicodex
biclaude
```

## What It Does

- Detects Chrome/Chromium profiles.
- Stores split AI config in Linux Toolbox config: `codexCli`, `claudeCli`, `codexVscode`, and `claudeVscode`.
- Reads the current wrapper/config files back from disk so the overview reflects actual state, not only saved UI values.
- Lets each AI target choose Bifrost or web login independently.
- Keeps the main AI Tools page as an overview table; detailed config opens in per-target popups.
- Installs `bicodex` with either a dedicated Bifrost `CODEX_HOME` at `~/.config/linux-toolbox/codex-bifrost` or a clean web-login wrapper.
- Installs `biclaude` with either its own Bifrost environment wrapper or a clean web-login wrapper.
- Can write Bifrost config for Codex VS Code in `~/.codex/config.toml`, or open `codex login` for web auth.
- Can write Bifrost env settings for Claude in `~/.claude/settings.json`, or open `claude auth login` for web auth.
- Creates one `.desktop` launcher per profile.
- Uses each profile picture as the dock icon when available.
- Pins the profile launchers to Ubuntu Dock.
- Moves Ubuntu Dock to a bottom, full-width, always-visible Windows-style taskbar layout with Show Applications on the left.
- Lets you toggle back to the Ubuntu default dock layout or restore the original saved dock layout.
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

## Compatibility

- Best support: Ubuntu GNOME on X11.
- Wayland: dock settings and clipboard history should work, but Chrome profile window grouping and maccel behavior may be less reliable.
- Hover previews currently target GNOME 42.
