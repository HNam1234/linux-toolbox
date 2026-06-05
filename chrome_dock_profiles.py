#!/usr/bin/env python3
import json
import os
import platform
import shutil
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # noqa: E402


HOME = Path.home()
APP_DIR = HOME / ".local/share/applications"
BIN_DIR = HOME / ".local/bin"
ICON_DIR = HOME / ".local/share/icons/hicolor/256x256/apps"
EXT_DIR = HOME / ".local/share/gnome-shell/extensions/dock-window-preview@quivio"
AUTOSTART_DIR = HOME / ".config/autostart"
SYSTEMD_USER_DIR = HOME / ".config/systemd/user"
CHROME_CONFIG = HOME / ".config/google-chrome"
CLIPBOARD_SHORTCUT_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipboard-history/"
COPYQ_AUTOSTART = AUTOSTART_DIR / "copyq.desktop"
COPYQ_SHORTCUT = BIN_DIR / "copyq-super-v"
COPYQ_START = BIN_DIR / "copyq-start"
COPYQ_SERVICE = SYSTEMD_USER_DIR / "copyq.service"
CONFIG_DIR = HOME / ".config/chrome-dock-profiles"
CONFIG_PATH = CONFIG_DIR / "config.json"
MOUSE_BACKUP_PATH = CONFIG_DIR / "maccel-previous-state.json"
MOUSE_COMMAND_LOG = CONFIG_DIR / "mouse-movement-commands.log"
MOUSE_INSTALLER = BIN_DIR / "chrome-dock-profiles-install-maccel"
MOUSE_INSTALL_LOG = CONFIG_DIR / "maccel-install.log"

STYLE_ACTIONS = {
    "Smooth Minimize": ("minimize", "Left-click minimizes/restores. Most stable."),
    "Minimize + Previews": ("minimize-or-previews", "Single window toggles; multiple windows show previews."),
    "Preview Picker": ("previews", "Left-click opens window previews."),
    "Cycle Windows": ("cycle-windows", "Left-click cycles through app windows."),
}


WRAPPER = """#!/usr/bin/env bash
set -u

if [ "$#" -lt 2 ]; then
  exit 64
fi

profile_dir=$1
wm_class=$2
shift 2

chrome=$(command -v google-chrome || command -v google-chrome-stable || command -v chromium || command -v chromium-browser)

before_ids=""
if command -v xdotool >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then
  before_ids=$(xdotool search --onlyvisible . 2>/dev/null | sort -u || true)
fi

"$chrome" --profile-directory="$profile_dir" --class="$wm_class" "$@" &

if ! command -v xdotool >/dev/null 2>&1 || [ -z "${DISPLAY:-}" ]; then
  exit 0
fi

is_before_window() {
  case "
$before_ids
" in
    *"
$1
"*) return 0 ;;
    *) return 1 ;;
  esac
}

is_chrome_window() {
  pid=$(xdotool getwindowpid "$1" 2>/dev/null || true)
  [ -n "${pid:-}" ] || return 1

  exe=""
  if [ -e "/proc/$pid/exe" ]; then
    exe=$(readlink "/proc/$pid/exe" 2>/dev/null || true)
  fi

  cmdline=""
  if [ -r "/proc/$pid/cmdline" ]; then
    cmdline=$(tr '\\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)
  fi

  case "$exe $cmdline" in
    *google-chrome*|*chrome*|*chromium*) return 0 ;;
    *) return 1 ;;
  esac
}

i=0
while [ "$i" -lt 150 ]; do
  window_ids=$(xdotool search --onlyvisible . 2>/dev/null | sort -u || true)
  for window_id in $window_ids; do
    if ! is_before_window "$window_id" && is_chrome_window "$window_id"; then
      xdotool set_window --class "$wm_class" --classname "$wm_class" "$window_id" 2>/dev/null || true
      exit 0
    fi
  done

  sleep 0.1
  i=$((i + 1))
done
"""


EXTENSION_JS = r"""const { Clutter, GLib, Pango, St } = imports.gi;
const Main = imports.ui.main;

const HOVER_DELAY_MS = 220;
const HIDE_DELAY_MS = 260;
const POINTER_POLL_MS = 90;
const POPUP_GAP = 12;
const POPUP_MARGIN = 8;
const PREVIEW_WIDTH = 260;
const PREVIEW_HEIGHT = 160;

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function hasStyleClass(actor, className) {
    if (!actor || typeof actor.get_style_class_name !== 'function')
        return false;
    const style = actor.get_style_class_name();
    return typeof style === 'string' && style.split(/\s+/).indexOf(className) !== -1;
}

function getVisibleAppWindows(app) {
    if (!app || typeof app.get_windows !== 'function')
        return [];
    return app.get_windows().filter(window => {
        if (!window)
            return false;
        if (typeof window.is_skip_taskbar === 'function')
            return !window.is_skip_taskbar();
        return !window.skip_taskbar;
    }).sort((left, right) => {
        const leftTime = typeof left.get_user_time === 'function' ? left.get_user_time() : 0;
        const rightTime = typeof right.get_user_time === 'function' ? right.get_user_time() : 0;
        return rightTime - leftTime;
    });
}

class WindowPreviewPopup {
    constructor() {
        this._sourceActor = null;
        this.actor = new St.BoxLayout({
            style_class: 'dock-preview-popup',
            vertical: true,
            reactive: true,
            can_focus: true,
            track_hover: true,
            visible: false,
        });
        Main.layoutManager.addTopChrome(this.actor);
    }

    get visible() {
        return this.actor.visible;
    }

    containsActor(actor) {
        for (let current = actor; current; current = current.get_parent()) {
            if (current === this.actor)
                return true;
        }
        return false;
    }

    show(app, windows, sourceActor) {
        if (!sourceActor || windows.length === 0)
            return;
        this._sourceActor = sourceActor;
        this._clearChildren();
        this.actor.add_child(new St.Label({
            style_class: 'dock-preview-header',
            text: app.get_name(),
            x_align: Clutter.ActorAlign.START,
        }));
        const itemsContainer = new St.BoxLayout({
            style_class: 'dock-preview-items',
            vertical: true,
            x_expand: true,
        });
        this.actor.add_child(itemsContainer);
        for (const window of windows)
            itemsContainer.add_child(this._createWindowButton(window, app));
        this.actor.show();
        this._positionNearSource();
    }

    hide() {
        this._sourceActor = null;
        this.actor.hide();
    }

    destroy() {
        this._clearChildren();
        Main.layoutManager.removeChrome(this.actor);
        this.actor.destroy();
        this.actor = null;
    }

    _clearChildren() {
        for (const child of this.actor.get_children())
            child.destroy();
    }

    _createWindowButton(metaWindow, app) {
        const button = new St.Button({
            style_class: 'dock-preview-item',
            reactive: true,
            can_focus: true,
            track_hover: true,
            x_expand: true,
        });
        const layout = new St.BoxLayout({ vertical: true, x_expand: true });
        layout.add_child(this._createThumbnail(metaWindow, app));
        layout.add_child(this._createTitleLabel(metaWindow, app));
        button.set_child(layout);
        button.connect('clicked', () => {
            this.hide();
            Main.activateWindow(metaWindow);
        });
        return button;
    }

    _createTitleLabel(metaWindow, app) {
        const titleLabel = new St.Label({
            style_class: 'dock-preview-title',
            text: metaWindow.get_title() || app.get_name(),
            x_align: Clutter.ActorAlign.START,
        });
        titleLabel.set_width(PREVIEW_WIDTH);
        if (titleLabel.clutter_text) {
            titleLabel.clutter_text.single_line_mode = true;
            titleLabel.clutter_text.line_wrap = false;
            titleLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        }
        return titleLabel;
    }

    _createThumbnail(metaWindow, app) {
        const thumbnail = new St.Widget({
            style_class: 'dock-preview-thumb',
            layout_manager: new Clutter.BinLayout(),
            x_expand: true,
        });
        thumbnail.set_size(PREVIEW_WIDTH, PREVIEW_HEIGHT);
        const windowActor = metaWindow.get_compositor_private();
        if (windowActor) {
            const [sourceWidth, sourceHeight] = windowActor.get_size();
            const width = Math.max(1, sourceWidth);
            const height = Math.max(1, sourceHeight);
            const scale = Math.min(PREVIEW_WIDTH / width, PREVIEW_HEIGHT / height, 1);
            thumbnail.add_child(new Clutter.Clone({
                source: windowActor,
                reactive: false,
                width: Math.floor(width * scale),
                height: Math.floor(height * scale),
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            }));
        } else {
            let icon = null;
            if (typeof app.create_icon_texture === 'function')
                icon = app.create_icon_texture(72);
            if (!icon)
                icon = new St.Icon({ icon_name: 'application-x-executable-symbolic', icon_size: 72 });
            icon.x_align = Clutter.ActorAlign.CENTER;
            icon.y_align = Clutter.ActorAlign.CENTER;
            thumbnail.add_child(icon);
        }
        return thumbnail;
    }

    _positionNearSource() {
        if (!this._sourceActor)
            return;
        const monitor = Main.layoutManager.findMonitorForActor(this._sourceActor) ||
            Main.layoutManager.primaryMonitor;
        if (!monitor)
            return;
        const [sourceX, sourceY] = this._sourceActor.get_transformed_position();
        const [sourceWidth, sourceHeight] = this._sourceActor.get_transformed_size();
        const [, , popupWidth, popupHeight] = this.actor.get_preferred_size();
        const sourceCenterX = sourceX + sourceWidth / 2;
        const sourceCenterY = sourceY + sourceHeight / 2;
        const side = this._guessDockSide(monitor, sourceCenterX, sourceCenterY);
        let x = sourceX + (sourceWidth - popupWidth) / 2;
        let y = sourceY - popupHeight - POPUP_GAP;
        if (side === St.Side.LEFT) {
            x = sourceX + sourceWidth + POPUP_GAP;
            y = sourceY + (sourceHeight - popupHeight) / 2;
        } else if (side === St.Side.RIGHT) {
            x = sourceX - popupWidth - POPUP_GAP;
            y = sourceY + (sourceHeight - popupHeight) / 2;
        } else if (side === St.Side.TOP) {
            x = sourceX + (sourceWidth - popupWidth) / 2;
            y = sourceY + sourceHeight + POPUP_GAP;
        }
        x = clamp(x, monitor.x + POPUP_MARGIN, monitor.x + monitor.width - popupWidth - POPUP_MARGIN);
        y = clamp(y, monitor.y + POPUP_MARGIN, monitor.y + monitor.height - popupHeight - POPUP_MARGIN);
        this.actor.set_position(Math.round(x), Math.round(y));
    }

    _guessDockSide(monitor, centerX, centerY) {
        const distances = [
            [St.Side.LEFT, Math.abs(centerX - monitor.x)],
            [St.Side.RIGHT, Math.abs(centerX - (monitor.x + monitor.width))],
            [St.Side.TOP, Math.abs(centerY - monitor.y)],
            [St.Side.BOTTOM, Math.abs(centerY - (monitor.y + monitor.height))],
        ];
        distances.sort((left, right) => left[1] - right[1]);
        return distances[0][0];
    }
}

class DockHoverTracker {
    constructor() {
        this._popup = new WindowPreviewPopup();
        this._hoveredIcon = null;
        this._hoveredIconActor = null;
        this._pollId = 0;
        this._showTimeoutId = 0;
        this._hideTimeoutId = 0;
    }

    enable() {
        this._pollId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POINTER_POLL_MS, () => {
            this._pollPointer();
            return GLib.SOURCE_CONTINUE;
        });
    }

    destroy() {
        this._cancelShow();
        this._cancelHide();
        if (this._pollId) {
            GLib.source_remove(this._pollId);
            this._pollId = 0;
        }
        this._popup.destroy();
        this._popup = null;
    }

    _pollPointer() {
        const actor = this._getPointerActor();
        const hoveredIcon = this._findDockIcon(actor);
        const pointerInPopup = this._popup.containsActor(actor);
        if (hoveredIcon) {
            const iconChanged = hoveredIcon.icon !== this._hoveredIcon ||
                hoveredIcon.actor !== this._hoveredIconActor;
            this._hoveredIcon = hoveredIcon.icon;
            this._hoveredIconActor = hoveredIcon.actor;
            this._cancelHide();
            if (iconChanged)
                this._scheduleShow(hoveredIcon.icon, hoveredIcon.actor);
            return;
        }
        this._hoveredIcon = null;
        this._hoveredIconActor = null;
        this._cancelShow();
        if (pointerInPopup)
            this._cancelHide();
        else
            this._scheduleHide();
    }

    _getPointerActor() {
        const [x, y] = global.get_pointer();
        return global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE, x, y);
    }

    _findDockIcon(actor) {
        for (let current = actor; current; current = current.get_parent()) {
            const delegate = current._delegate;
            if (!this._isDockAppIcon(delegate))
                continue;
            if (!delegate.app || !this._isInsideDash(current))
                continue;
            return { icon: delegate, actor: this._getIconActor(delegate, current) };
        }
        return null;
    }

    _isDockAppIcon(delegate) {
        return !!delegate && !!delegate.app &&
            (typeof delegate.getInterestingWindows === 'function' ||
                typeof delegate.app.get_windows === 'function');
    }

    _isInsideDash(actor) {
        for (let current = actor; current; current = current.get_parent()) {
            if (hasStyleClass(current, 'dash-item-container') ||
                hasStyleClass(current, 'dash-item') ||
                hasStyleClass(current, 'dash'))
                return true;
        }
        return false;
    }

    _getIconActor(icon, fallbackActor) {
        if (icon instanceof Clutter.Actor)
            return icon;
        if (icon.actor instanceof Clutter.Actor)
            return icon.actor;
        return fallbackActor;
    }

    _scheduleShow(icon, actor) {
        this._cancelShow();
        this._cancelHide();
        this._showTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, HOVER_DELAY_MS, () => {
            this._showTimeoutId = 0;
            if (this._hoveredIcon !== icon || this._hoveredIconActor !== actor)
                return GLib.SOURCE_REMOVE;
            const windows = this._getAppWindows(icon);
            if (windows.length === 0) {
                this._popup.hide();
                return GLib.SOURCE_REMOVE;
            }
            this._popup.show(icon.app, windows, actor);
            return GLib.SOURCE_REMOVE;
        });
    }

    _scheduleHide() {
        if (this._hideTimeoutId || !this._popup.visible)
            return;
        this._hideTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, HIDE_DELAY_MS, () => {
            this._hideTimeoutId = 0;
            this._popup.hide();
            return GLib.SOURCE_REMOVE;
        });
    }

    _cancelShow() {
        if (this._showTimeoutId) {
            GLib.source_remove(this._showTimeoutId);
            this._showTimeoutId = 0;
        }
    }

    _cancelHide() {
        if (this._hideTimeoutId) {
            GLib.source_remove(this._hideTimeoutId);
            this._hideTimeoutId = 0;
        }
    }

    _getAppWindows(icon) {
        let windows = [];
        if (typeof icon.getInterestingWindows === 'function')
            windows = icon.getInterestingWindows();
        if (windows.length === 0 && icon.app && typeof icon.app.get_windows === 'function')
            windows = icon.app.get_windows();
        return getVisibleAppWindows({ get_windows: () => windows });
    }
}

let tracker = null;

function init() {
}

function enable() {
    if (tracker)
        return;
    tracker = new DockHoverTracker();
    tracker.enable();
}

function disable() {
    if (!tracker)
        return;
    tracker.destroy();
    tracker = null;
}
"""


EXTENSION_CSS = """.dock-preview-popup {
    background-color: rgba(28, 28, 32, 0.96);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 10px;
    padding: 10px;
    spacing: 8px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.38);
}

.dock-preview-header {
    color: #ffffff;
    font-weight: 700;
    font-size: 12px;
    padding: 0 2px 2px;
}

.dock-preview-items {
    spacing: 8px;
}

.dock-preview-item {
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 8px;
    padding: 7px;
}

.dock-preview-item:hover {
    background-color: rgba(74, 144, 226, 0.28);
    border-color: rgba(132, 185, 255, 0.8);
}

.dock-preview-thumb {
    background-color: rgba(0, 0, 0, 0.28);
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.1);
}

.dock-preview-title {
    color: #eeeeee;
    font-size: 12px;
    padding-top: 6px;
}
"""


def run(command, check=True):
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "command failed").strip())
    return completed.stdout.strip()


def parse_gsettings_list(raw):
    if not raw.startswith("["):
        return []
    return [part.strip().strip("'") for part in raw.strip("[]").split(",") if part.strip()]


def format_gsettings_list(items):
    return "[" + ", ".join(f"'{item}'" for item in items) + "]"


def sanitize_id(value):
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-") or "profile"


def profile_slug(directory):
    if directory == "Default":
        return "default"
    if directory.startswith("Profile "):
        suffix = directory.removeprefix("Profile ").strip()
        if suffix.isdigit():
            return suffix
    return sanitize_id(directory)


def profile_window_class(directory, index):
    slug = profile_slug(directory)
    if slug == "default":
        return "ChromeProfileDefault"
    compact = "".join(ch for ch in slug if ch.isalnum())
    return f"ChromeProfile{compact or index}"


def detect_chrome_config():
    if (HOME / ".config/google-chrome/Local State").exists():
        return HOME / ".config/google-chrome", "google-chrome"
    if (HOME / ".config/chromium/Local State").exists():
        return HOME / ".config/chromium", "chromium"
    return CHROME_CONFIG, "google-chrome"


def load_app_config():
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_app_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")


def iso_now():
    return datetime.now(timezone.utc).isoformat()


class MaccelBackend:
    def __init__(self, command_logger=None):
        self.command_logger = command_logger

    def isAvailable(self):
        return shutil.which("maccel") is not None

    def readCurrentConfig(self):
        if not self.isAvailable():
            raise RuntimeError("maccel is not installed.")
        return {
            "mode": self._read_mode(),
            "common": self._read_values(["get", "all", "--oneline", "--quiet", "common"], 4),
            "linear": self._read_values(["get", "all", "--oneline", "--quiet", "linear"], 3),
            "natural": self._read_values(["get", "all", "--oneline", "--quiet", "natural"], 3),
            "synchronous": self._read_values(["get", "all", "--oneline", "--quiet", "synchronous"], 4),
        }

    def writeConfig(self, config):
        if not config:
            raise RuntimeError("No previous maccel backup is available.")
        common = config.get("common")
        if common:
            self._run(["set", "all", "common", *self._string_values(common)])

        mode = config.get("mode", "linear")
        mode_key = self._normalize_mode(mode)
        values = config.get(mode_key)
        if values and mode_key in {"linear", "natural", "synchronous"}:
            self._run(["set", "all", mode_key, *self._string_values(values)])
        self._run(["set", "mode", mode_key])

    def applyWindowsEppPreset(self):
        # Approximation based on RawAccel's Windows Enhanced Pointer Precision
        # emulation points:
        # 1.505035,0.85549892; 4.375,3.30972978;
        # 13.51,15.17478447; 140,354.7026875.
        # maccel's current CLI exposes parametric curves rather than arbitrary
        # velocity points, so this uses a conservative linear curve: low-speed
        # precision, Windows-like mid-speed acceleration, and capped high-speed
        # movement.
        self._run(["set", "all", "common", "1.0", "1.0", "1000.0", "0.0"])
        self._run(["set", "all", "linear", "0.055", "1.5", "2.8"])
        self._run(["set", "mode", "linear"])

    def applyMacOSLikePreset(self):
        # macOS pointer acceleration is proprietary and hardware-dependent; this
        # preset is an approximation. Use maccel's Natural curve with moderate,
        # smooth gain for desktop navigation instead of FPS/raw aiming.
        self._run(["set", "all", "common", "1.0", "1.0", "1000.0", "0.0"])
        self._run(["set", "all", "natural", "0.1", "1.0", "1.65"])
        self._run(["set", "mode", "natural"])

    def backup(self):
        config = self.readCurrentConfig()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        MOUSE_BACKUP_PATH.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        return str(MOUSE_BACKUP_PATH)

    def restore(self):
        if not MOUSE_BACKUP_PATH.exists():
            raise RuntimeError("No previous mouse settings backup was found.")
        config = json.loads(MOUSE_BACKUP_PATH.read_text(encoding="utf-8"))
        self.writeConfig(config)

    def _read_mode(self):
        output = self._run(["get", "mode"])
        first_line = next((line.strip() for line in output.splitlines() if line.strip()), "")
        return self._normalize_mode(first_line)

    def _read_values(self, args, expected_count):
        output = self._run(args)
        values = [float(value) for value in output.split()]
        if len(values) != expected_count:
            raise RuntimeError("Unexpected maccel configuration output.")
        return values

    def _run(self, args):
        command = ["maccel", *args]
        if self.command_logger:
            self.command_logger(command)
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "maccel command failed").strip())
        return completed.stdout.strip()

    def _normalize_mode(self, value):
        normalized = value.strip().lower().replace("_", "-")
        if normalized.startswith("linear"):
            return "linear"
        if normalized.startswith("natural"):
            return "natural"
        if normalized.startswith("synchronous"):
            return "synchronous"
        if normalized.startswith("no"):
            return "no-accel"
        return normalized or "linear"

    def _string_values(self, values):
        return [str(value) for value in values]


class MaccelCompatibilityPatchManager:
    def __init__(self, clone_dir=Path("/opt/maccel")):
        self.clone_dir = Path(clone_dir)
        self.report = {
            "maccelVersion": "unknown",
            "sourceDir": "",
            "patches": [],
        }

    def detectMaccelVersion(self):
        pkgbuild = self.clone_dir / "PKGBUILD"
        if not pkgbuild.exists():
            return "unknown"
        for line in pkgbuild.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("pkgver="):
                version = line.partition("=")[2].strip()
                self.report["maccelVersion"] = version or "unknown"
                return self.report["maccelVersion"]
        return "unknown"

    def findDkmsSourceDir(self, version):
        source_dir = Path(f"/usr/src/maccel-{version}")
        self.report["sourceDir"] = str(source_dir)
        return source_dir

    def findProblematicEnumSyntax(self, sourceDir):
        source_dir = Path(sourceDir)
        if not source_dir.exists():
            return []
        matches = []
        for path in source_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                if "enum accel_mode :" in path.read_text(encoding="utf-8", errors="replace"):
                    matches.append(path)
            except Exception:
                continue
        return matches

    def applyEnumSyntaxPatch(self, sourceDir):
        patched = []
        for path in self.findProblematicEnumSyntax(sourceDir):
            text = path.read_text(encoding="utf-8", errors="replace")
            path.write_text(text.replace("enum accel_mode : unsigned char", "enum accel_mode"), encoding="utf-8")
            patched.append(path)
        return patched

    def verifyEnumSyntaxPatch(self, sourceDir):
        return not self.findProblematicEnumSyntax(sourceDir)

    def applyPatchesIfNeeded(self, sourceDir):
        needed = bool(self.findProblematicEnumSyntax(sourceDir))
        applied = False
        if needed:
            applied = bool(self.applyEnumSyntaxPatch(sourceDir))
        verified = self.verifyEnumSyntaxPatch(sourceDir)
        self.report["patches"].append(
            {
                "name": "enum_accel_mode_c_syntax",
                "needed": needed,
                "applied": applied,
                "verified": verified,
            }
        )
        if needed and not verified:
            raise RuntimeError("enum_accel_mode_c_syntax compatibility patch failed verification.")
        return self.report

    def generatePatchReport(self):
        return self.report


class MouseMovementService:
    def __init__(self):
        self.backend = MaccelBackend(self._log_command)
        self.required_commands = ("curl", "git", "make", "dkms", "gcc", "sudo")

    def isSupportedPlatform(self):
        return platform.system().lower() == "linux"

    def getEnvironment(self):
        session = os.environ.get("XDG_SESSION_TYPE", "unknown").strip().lower() or "unknown"
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown").strip() or "unknown"
        if session not in {"x11", "wayland"}:
            session = "unknown"
        if not desktop:
            desktop = "unknown"
        return {"sessionType": session, "desktop": desktop}

    def isMaccelInstalled(self):
        return self.backend.isAvailable()

    def getInstallStatus(self):
        missing_commands = [command for command in self.required_commands if shutil.which(command) is None]
        kernel_release = run(["uname", "-r"], check=False) or "unknown"
        headers_path = Path("/lib/modules") / kernel_release / "build"
        kernel_compiler = self._detect_kernel_compiler()
        return {
            "maccelInstalled": self.isMaccelInstalled(),
            "pkexecAvailable": shutil.which("pkexec") is not None,
            "missingCommands": missing_commands,
            "kernelCompiler": kernel_compiler,
            "kernelCompilerInstalled": shutil.which(kernel_compiler) is not None if kernel_compiler else True,
            "kernelHeadersInstalled": headers_path.exists(),
            "kernelRelease": kernel_release,
            "installLogPath": str(MOUSE_INSTALL_LOG),
        }

    def getCurrentPresetState(self):
        return load_app_config().get("mouseMovement", {}).get("activePreset", "unknown")

    def applyWindowsPreset(self):
        self._apply_preset("windows", self.backend.applyWindowsEppPreset)

    def applyMacOSPreset(self):
        self._apply_preset("macos", self.backend.applyMacOSLikePreset)

    def backupCurrentMaccelState(self):
        return self.backend.backup()

    def restorePreviousMaccelState(self):
        self.backend.restore()
        self._save_state("previous", str(MOUSE_BACKUP_PATH))

    def runMaccelCommandSafely(self, command):
        return self.backend._run(command)

    def installMaccelBackend(self):
        if not self.isSupportedPlatform():
            raise RuntimeError("maccel install is only supported on Linux.")
        if shutil.which("pkexec") is None:
            raise RuntimeError("pkexec is not installed. Install maccel manually from https://github.com/Gnarus-G/maccel")
        installer = self._write_installer_script()
        self._log_command(["pkexec", str(installer)])
        run(["pkexec", str(installer)])

    def startMaccelBackendInstall(self):
        if not self.isSupportedPlatform():
            raise RuntimeError("maccel install is only supported on Linux.")
        if shutil.which("pkexec") is None:
            raise RuntimeError("pkexec is not installed. Install maccel manually from https://github.com/Gnarus-G/maccel")
        installer = self._write_installer_script()
        command = ["pkexec", str(installer)]
        self._log_command(command)
        return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _apply_preset(self, active_preset, apply_callback):
        backup_path = self.backupCurrentMaccelState()
        try:
            apply_callback()
        except Exception:
            self.backend.restore()
            raise
        self._save_state(active_preset, backup_path)

    def _save_state(self, active_preset, backup_path):
        config = load_app_config()
        env = self.getEnvironment()
        config["mouseMovement"] = {
            "backend": "maccel",
            "activePreset": active_preset,
            "previousStateBackupPath": backup_path,
            "lastAppliedAt": iso_now(),
            "sessionType": env["sessionType"],
            "desktop": env["desktop"],
        }
        save_app_config(config)

    def _log_command(self, command):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with MOUSE_COMMAND_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"{iso_now()} {' '.join(command)}\n")

    def _detect_kernel_compiler(self):
        version = ""
        try:
            version = Path("/proc/version").read_text(encoding="utf-8")
        except Exception:
            return ""
        for part in version.replace(")", " ").replace("(", " ").split():
            if "gcc-" not in part:
                continue
            suffix = part.rsplit("gcc-", 1)[-1]
            digits = "".join(ch for ch in suffix if ch.isdigit())
            if digits:
                return f"gcc-{digits}"
        return ""

    def _write_installer_script(self):
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        MOUSE_INSTALLER.write_text(
            f"""#!/usr/bin/env bash
set -euo pipefail

log_path="{MOUSE_INSTALL_LOG}"
mkdir -p "$(dirname "$log_path")"
: >"$log_path"
exec >>"$log_path" 2>&1

echo "==== maccel install started $(date -Is) ===="
export DEBIAN_FRONTEND=noninteractive

kernel_compiler="$(grep -o 'gcc-[0-9]\\+' /proc/version | head -n 1 || true)"
compiler_package=""
if [ -n "$kernel_compiler" ]; then
  compiler_package="$kernel_compiler"
fi

detectMaccelVersion() {{
  grep "pkgver=" /opt/maccel/PKGBUILD | grep -oP '\\d\\.\\d\\.\\d' | head -n 1
}}

findDkmsSourceDir() {{
  version="$1"
  printf "/usr/src/maccel-%s" "$version"
}}

findProblematicEnumSyntax() {{
  source_dir="$1"
  grep -R "enum accel_mode :" "$source_dir" 2>/dev/null || true
}}

applyEnumSyntaxPatch() {{
  source_dir="$1"
  matches="$(findProblematicEnumSyntax "$source_dir")"
  if [ -z "$matches" ]; then
    echo "Patch enum_accel_mode_c_syntax: not needed"
    return 0
  fi

  echo "Patch enum_accel_mode_c_syntax: needed"
  while IFS= read -r file; do
    file="${{file%%:*}}"
    if [ -n "$file" ] && [ -f "$file" ]; then
      sed -i 's/enum accel_mode : unsigned char/enum accel_mode/g' "$file"
    fi
  done <<EOF_PATCH_MATCHES
$matches
EOF_PATCH_MATCHES
  echo "Patch enum_accel_mode_c_syntax: applied"
}}

verifyEnumSyntaxPatch() {{
  source_dir="$1"
  if findProblematicEnumSyntax "$source_dir" | grep -q "enum accel_mode :"; then
    echo "Patch enum_accel_mode_c_syntax: failed verification"
    return 1
  fi
  echo "Patch enum_accel_mode_c_syntax: verified"
  return 0
}}

applyCompilerPatchIfNeeded() {{
  source_dir="$1"
  version="$2"
  if [ -n "$kernel_compiler" ] && command -v "$kernel_compiler" >/dev/null 2>&1; then
    echo "Patch compiler_path: using $kernel_compiler"
    cat > "$source_dir/dkms.conf" <<EOF_DKMS_CONFIG
PACKAGE_NAME="maccel"
PACKAGE_VERSION="$version"
MAKE[0]="make CC=$kernel_compiler KVER=\\$kernelver DRIVER_CFLAGS=''"
BUILT_MODULE_NAME[0]="maccel"
DEST_MODULE_LOCATION[0]="/kernel/drivers/usb"
AUTOINSTALL="yes"
EOF_DKMS_CONFIG
    patchCompilerHardcodes "$source_dir"
    if [ -d /opt/maccel ]; then
      patchCompilerHardcodes /opt/maccel
    fi
    export CC="$kernel_compiler"
  else
    echo "Patch compiler_path: not needed"
  fi
}}

patchCompilerHardcodes() {{
  patch_dir="$1"
  echo "Searching compiler hardcodes in $patch_dir"
  grep -RIn "make CC=gcc\\|CC=gcc" "$patch_dir" 2>/dev/null || true
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    sed -i "s/^[[:space:]]*CC=gcc$/	CC ?= $kernel_compiler/" "$file"
    sed -i "s/make CC=gcc\\([^0-9-]\\|$\\)/make CC=\\$(CC)\\1/g" "$file"
    sed -i "s/\\$(MAKE) CC=gcc\\([^0-9-]\\|$\\)/\\$(MAKE) CC=\\$(CC)\\1/g" "$file"
    sed -i "s/CC=gcc\\([^0-9-]\\|$\\)/CC=$kernel_compiler\\1/g" "$file"
  done <<EOF_COMPILER_PATCH_FILES
$(grep -RIl "make CC=gcc\\|CC=gcc" "$patch_dir" 2>/dev/null || true)
EOF_COMPILER_PATCH_FILES
}}

verifyCompilerPatch() {{
  source_dir="$1"
  if [ -z "$kernel_compiler" ] || ! command -v "$kernel_compiler" >/dev/null 2>&1; then
    echo "Patch compiler_path: verification skipped"
    return 0
  fi

  echo "Final DKMS config:"
  cat "$source_dir/dkms.conf"
  echo "Final DKMS Makefile compiler lines:"
  grep -n "CC=\\|CC ?=\\|\\$(MAKE).*CC=" "$source_dir/Makefile" || true

  hardcoded_matches="$(grep -RIn "CC=gcc" "$source_dir" 2>/dev/null | grep -v "CC=$kernel_compiler" || true)"
  if [ -n "$hardcoded_matches" ]; then
    echo "Compiler patch verification failed: DKMS source still contains CC=gcc"
    echo "$hardcoded_matches"
    return 1
  fi

  if ! grep -q "CC=$kernel_compiler" "$source_dir/dkms.conf"; then
    echo "Compiler patch verification failed: DKMS config missing CC=$kernel_compiler"
    return 1
  fi
  if grep -q "^[[:space:]]*CC=gcc$" "$source_dir/Makefile"; then
    echo "Compiler patch verification failed: DKMS Makefile still assigns CC=gcc"
    return 1
  fi
  if ! grep -q 'CC=$(CC)' "$source_dir/Makefile"; then
    echo 'Compiler patch verification failed: DKMS Makefile missing CC=$(CC) nested build command'
    return 1
  fi

  echo "Patch compiler_path: verified no hardcoded CC=gcc remains"
}}

applyDkmsConfigPatchIfNeeded() {{
  source_dir="$1"
  if grep -q "@_PKGNAME@\\|@PKGVER@" "$source_dir/dkms.conf"; then
    echo "Patch dkms_config_template: failed"
    return 1
  fi
  if [ -n "$kernel_compiler" ] && command -v "$kernel_compiler" >/dev/null 2>&1; then
    if ! grep -q "CC=$kernel_compiler" "$source_dir/dkms.conf"; then
      echo "Patch dkms_config_template: failed missing CC=$kernel_compiler"
      return 1
    fi
  fi
  echo "Patch dkms_config_template: verified"
}}

applyPatchesIfNeeded() {{
  source_dir="$1"
  version="$2"
  enum_needed=false
  enum_applied=false
  enum_verified=false
  if [ -n "$(findProblematicEnumSyntax "$source_dir")" ]; then
    enum_needed=true
  fi
  applyEnumSyntaxPatch "$source_dir"
  if [ "$enum_needed" = true ]; then
    enum_applied=true
  fi
  verifyEnumSyntaxPatch "$source_dir"
  enum_verified=true

  echo "{{"
  echo "  \\"maccelVersion\\": \\"$version\\","
  echo "  \\"sourceDir\\": \\"$source_dir\\","
  echo "  \\"patches\\": ["
  echo "    {{\\"name\\": \\"enum_accel_mode_c_syntax\\", \\"needed\\": $enum_needed, \\"applied\\": $enum_applied, \\"verified\\": $enum_verified}}"
  echo "  ]"
  echo "}}"

  if [ -d /opt/maccel ]; then
    applyEnumSyntaxPatch /opt/maccel
    verifyEnumSyntaxPatch /opt/maccel
  fi
  applyCompilerPatchIfNeeded "$source_dir" "$version"
  verifyCompilerPatch "$source_dir"
  applyDkmsConfigPatchIfNeeded "$source_dir"
}}

showDkmsMakeLog() {{
  version="$1"
  make_log="/var/lib/dkms/maccel/$version/build/make.log"
  if [ -f "$make_log" ]; then
    echo "==== DKMS make.log: $make_log ===="
    cat "$make_log"
    echo "==== end DKMS make.log ===="
  else
    echo "DKMS make.log was not found at $make_log"
  fi
}}

checkSecureBootWarning() {{
  if command -v mokutil >/dev/null 2>&1; then
    sb_state="$(mokutil --sb-state 2>/dev/null || true)"
    echo "Secure Boot state: $sb_state"
    if printf "%s" "$sb_state" | grep -qi "enabled"; then
      echo "WARNING: Secure Boot is enabled. The maccel kernel module may need signing before modprobe can load it."
    fi
  fi
}}

if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  packages=(curl git make dkms gcc sudo wget ca-certificates "linux-headers-$(uname -r)")
  if [ -n "$compiler_package" ]; then
    packages+=("$compiler_package")
  fi
  apt-get install -y "${{packages[@]}}"
else
  echo "apt-get was not found. Install maccel dependencies manually for this distro."
  exit 1
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
rm -rf /opt/maccel
git clone --depth 1 https://github.com/Gnarus-G/maccel.git /opt/maccel
cd /opt/maccel

dkms_version="$(detectMaccelVersion)"
if [ -z "$dkms_version" ]; then
  echo "Could not detect maccel version from /opt/maccel/PKGBUILD."
  exit 1
fi
echo "Preparing DKMS module maccel/$dkms_version..."
dkms remove -m maccel -v "$dkms_version" --all || true
dkms_source_dir="$(findDkmsSourceDir "$dkms_version")"
rm -rf "$dkms_source_dir"
install -Dm 644 dkms.conf "$dkms_source_dir/dkms.conf"
sed -e "s/@_PKGNAME@/maccel/" \
    -e "s/@PKGVER@/$dkms_version/" \
    -e "s/@DRIVER_CFLAGS@/''/" \
    -i "$dkms_source_dir/dkms.conf"
cp -r driver/. "$dkms_source_dir/"

echo "Installing udev rules..."
make udev_uninstall || true
make udev_install

echo "Applying compatibility patches..."
applyPatchesIfNeeded "$dkms_source_dir" "$dkms_version"

echo "Building and installing DKMS module..."
if ! dkms add -m maccel -v "$dkms_version"; then
  showDkmsMakeLog "$dkms_version"
  exit 1
fi
if ! dkms build -m maccel -v "$dkms_version"; then
  showDkmsMakeLog "$dkms_version"
  exit 1
fi
if ! dkms install --force -m maccel -v "$dkms_version"; then
  showDkmsMakeLog "$dkms_version"
  exit 1
fi

if ! modprobe maccel; then
  echo "modprobe maccel failed."
  checkSecureBootWarning
  exit 1
fi

echo "Installing maccel CLI..."
mkdir -p /opt/maccel/bin
if curl -fsSL "https://github.com/Gnarus-G/maccel/releases/download/v$dkms_version/maccel-cli.tar.gz" -o "$workdir/maccel-cli.tar.gz"; then
  tar -zxvf "$workdir/maccel-cli.tar.gz" -C "$workdir"
  install -m 755 -D "$workdir/maccel_v$dkms_version/maccel" /opt/maccel/bin/maccel
elif command -v cargo >/dev/null 2>&1; then
  cargo build --bin maccel --release
  install -m 755 -D target/release/maccel /opt/maccel/bin/maccel
else
  echo "Could not install maccel CLI from release and cargo is not installed."
  exit 1
fi
ln -sf /opt/maccel/bin/maccel /usr/local/bin/maccel

groupadd -f maccel
if [ -n "${{PKEXEC_UID:-}}" ]; then
  target_user="$(getent passwd "$PKEXEC_UID" | cut -d: -f1 || true)"
  if [ -n "$target_user" ]; then
    usermod -aG maccel "$target_user" || true
  fi
fi

echo "==== maccel install finished $(date -Is) ===="
""",
            encoding="utf-8",
        )
        MOUSE_INSTALLER.chmod(0o755)
        return MOUSE_INSTALLER


class App(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application)
        self.set_title("Chrome Dock Profiles")
        self.set_default_size(880, 680)
        self.set_border_width(0)
        self.profiles = []
        self.syncing_style = False
        self.syncing_features = False
        self.mouse_service = MouseMovementService()
        self.mouse_install_process = None
        self.mouse_install_timer_id = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root)

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "Chrome Dock Profiles"
        header.props.subtitle = "Separate dock icons for each Chrome profile"
        self.set_titlebar(header)

        refresh_header_button = Gtk.Button(label="Refresh")
        refresh_header_button.set_tooltip_text("Scan Chrome profiles again")
        refresh_header_button.connect("clicked", self.on_refresh)
        header.pack_end(refresh_header_button)

        notebook = Gtk.Notebook()
        notebook.set_scrollable(True)
        root.pack_start(notebook, True, True, 0)

        main_scroller, main_tab = self.create_tab_page()
        chrome_scroller, chrome_tab = self.create_tab_page()
        mouse_scroller, mouse_tab = self.create_tab_page()
        clipboard_scroller, clipboard_tab = self.create_tab_page()

        notebook.append_page(main_scroller, Gtk.Label(label="Main"))
        notebook.append_page(chrome_scroller, Gtk.Label(label="Chrome Profile"))
        notebook.append_page(mouse_scroller, Gtk.Label(label="Mouse Movement"))
        notebook.append_page(clipboard_scroller, Gtk.Label(label="Clipboard"))

        intro = Gtk.Label()
        intro.set_markup("<span size='large'><b>Chrome Dock Profiles</b></span>")
        intro.set_xalign(0)
        intro.set_line_wrap(True)
        main_tab.pack_start(intro, False, False, 0)

        description = Gtk.Label(
            label="System overview for Chrome profile dock icons, clipboard history, mouse movement, and dock behavior."
        )
        description.set_xalign(0)
        description.set_line_wrap(True)
        main_tab.pack_start(description, False, False, 0)

        self.compatibility_card = self.create_card("System Check")
        main_tab.pack_start(self.compatibility_card, False, False, 0)
        self.compatibility_label = Gtk.Label()
        self.compatibility_label.set_xalign(0)
        self.compatibility_label.set_line_wrap(True)
        self.compatibility_card.pack_start(self.compatibility_label, False, False, 0)

        status_card = self.create_card("Activity")
        main_tab.pack_start(status_card, False, False, 0)

        self.status_label = Gtk.Label(label="Ready.")
        self.status_label.set_xalign(0)
        self.status_label.set_line_wrap(True)
        status_card.pack_start(self.status_label, False, False, 0)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        log_scroller = Gtk.ScrolledWindow()
        log_scroller.set_min_content_height(180)
        log_scroller.add(self.log_view)
        status_card.pack_start(log_scroller, True, True, 8)

        chrome_intro = Gtk.Label()
        chrome_intro.set_markup("<span size='large'><b>Chrome Profile</b></span>")
        chrome_intro.set_xalign(0)
        chrome_intro.set_line_wrap(True)
        chrome_tab.pack_start(chrome_intro, False, False, 0)

        chrome_description = Gtk.Label(
            label="Install profile-specific launchers, choose how dock clicks behave, and add hover window previews."
        )
        chrome_description.set_xalign(0)
        chrome_description.set_line_wrap(True)
        chrome_tab.pack_start(chrome_description, False, False, 0)

        feature_card = self.create_card("Chrome Features")
        chrome_tab.pack_start(feature_card, False, False, 0)

        self.profile_switch = self.create_feature_switch(
            feature_card,
            "Chrome Profile Dock Icons",
            "Create, pin, and maintain one Ubuntu Dock icon per Chrome profile.",
            self.on_profile_feature_toggled,
        )
        self.hover_switch = self.create_feature_switch(
            feature_card,
            "Hover Window Previews",
            "Install and enable the local GNOME dock hover-preview extension.",
            self.on_hover_feature_toggled,
        )

        mouse_card = self.create_card("Mouse Movement")
        mouse_tab.pack_start(mouse_card, False, False, 0)

        mouse_title = Gtk.Label()
        mouse_title.set_markup("<span size='large'><b>Mouse Movement</b></span>")
        mouse_title.set_xalign(0)
        mouse_card.pack_start(mouse_title, False, False, 0)

        mouse_description = Gtk.Label(label="Make Linux mouse movement feel closer to Windows or macOS.")
        mouse_description.set_xalign(0)
        mouse_description.set_line_wrap(True)
        mouse_card.pack_start(mouse_description, False, False, 0)

        install_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mouse_card.pack_start(install_row, False, False, 0)

        self.mouse_backend_indicator = Gtk.Label()
        self.mouse_backend_indicator.set_xalign(0)
        install_row.pack_start(self.mouse_backend_indicator, True, True, 0)

        self.mouse_install_button = Gtk.Button(label="Install maccel")
        self.mouse_install_button.set_tooltip_text("Install maccel and required Ubuntu packages with authentication.")
        self.mouse_install_button.connect("clicked", self.on_mouse_install_backend)
        install_row.pack_end(self.mouse_install_button, False, False, 0)

        self.mouse_install_progress = Gtk.ProgressBar()
        self.mouse_install_progress.set_no_show_all(True)
        mouse_card.pack_start(self.mouse_install_progress, False, False, 0)

        self.mouse_install_label = Gtk.Label()
        self.mouse_install_label.set_xalign(0)
        self.mouse_install_label.set_line_wrap(True)
        mouse_card.pack_start(self.mouse_install_label, False, False, 0)

        log_label = Gtk.Label()
        log_label.set_markup("<b>Install Log</b>")
        log_label.set_xalign(0)
        mouse_card.pack_start(log_label, False, False, 0)

        self.mouse_install_log_view = Gtk.TextView()
        self.mouse_install_log_view.set_editable(False)
        self.mouse_install_log_view.set_cursor_visible(False)
        self.mouse_install_log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.mouse_install_log_view.set_monospace(True)
        mouse_log_scroller = Gtk.ScrolledWindow()
        mouse_log_scroller.set_min_content_height(180)
        mouse_log_scroller.add(self.mouse_install_log_view)
        mouse_card.pack_start(mouse_log_scroller, True, True, 0)

        mouse_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        mouse_card.pack_start(mouse_grid, False, False, 0)

        self.mouse_windows_button = self.create_primary_button("Windows", "Apply the Windows-like mouse movement preset.")
        self.mouse_windows_button.connect("clicked", self.on_mouse_windows)
        mouse_grid.attach(self.mouse_windows_button, 0, 0, 1, 1)

        self.mouse_macos_button = self.create_primary_button("macOS", "Apply the macOS-like mouse movement preset.")
        self.mouse_macos_button.connect("clicked", self.on_mouse_macos)
        mouse_grid.attach(self.mouse_macos_button, 1, 0, 1, 1)

        self.mouse_restore_button = Gtk.Button(label="Restore Previous")
        self.mouse_restore_button.set_tooltip_text("Restore the mouse settings backed up before the last preset was applied.")
        self.mouse_restore_button.connect("clicked", self.on_mouse_restore)
        mouse_grid.attach(self.mouse_restore_button, 2, 0, 1, 1)

        self.mouse_backend_label = Gtk.Label()
        self.mouse_backend_label.set_xalign(0)
        self.mouse_backend_label.set_line_wrap(True)
        mouse_card.pack_start(self.mouse_backend_label, False, False, 0)

        self.mouse_active_label = Gtk.Label()
        self.mouse_active_label.set_xalign(0)
        self.mouse_active_label.set_line_wrap(True)
        mouse_card.pack_start(self.mouse_active_label, False, False, 0)

        self.mouse_warning_label = Gtk.Label()
        self.mouse_warning_label.set_xalign(0)
        self.mouse_warning_label.set_line_wrap(True)
        mouse_card.pack_start(self.mouse_warning_label, False, False, 0)

        setup_card = self.create_card("Manual Actions")
        chrome_tab.pack_start(setup_card, False, False, 0)

        setup_grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        setup_card.pack_start(setup_grid, False, False, 0)

        install_button = self.create_primary_button("Update Profile Icons", "Regenerate profile launchers without changing feature switches.")
        install_button.connect("clicked", self.on_install_profiles)
        setup_grid.attach(install_button, 0, 0, 1, 1)

        pin_button = self.create_primary_button("Pin To Dock", "Replace the single Chrome dock icon with profile icons.")
        pin_button.connect("clicked", self.on_pin_profiles)
        setup_grid.attach(pin_button, 1, 0, 1, 1)

        hover_button = self.create_primary_button("Install Hover Previews", "Show window thumbnails when hovering dock icons.")
        hover_button.connect("clicked", self.on_install_hover)
        setup_grid.attach(hover_button, 2, 0, 1, 1)

        style_card = self.create_card("Dock Click Style")
        chrome_tab.pack_start(style_card, False, False, 0)

        style_hint = Gtk.Label(label="Choose how a normal left-click on a dock icon behaves.")
        style_hint.set_xalign(0)
        style_hint.set_line_wrap(True)
        style_card.pack_start(style_hint, False, False, 0)

        self.style_buttons = {}
        style_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        style_card.pack_start(style_grid, False, False, 10)

        previous = None
        for index, (name, (action, help_text)) in enumerate(STYLE_ACTIONS.items()):
            button = Gtk.RadioButton.new_with_label_from_widget(previous, name)
            previous = button
            button.set_tooltip_text(help_text)
            button.connect("toggled", self.on_style_toggled, action)
            self.style_buttons[action] = button
            style_grid.attach(button, index % 2, index // 2, 1, 1)

        self.style_description = Gtk.Label()
        self.style_description.set_xalign(0)
        self.style_description.set_line_wrap(True)
        style_card.pack_start(self.style_description, False, False, 0)

        profile_card = self.create_card("Detected Profiles")
        chrome_tab.pack_start(profile_card, True, True, 0)

        self.profile_list = Gtk.ListBox()
        self.profile_list.set_selection_mode(Gtk.SelectionMode.NONE)
        profile_card.pack_start(self.profile_list, True, True, 0)

        clipboard_intro = Gtk.Label()
        clipboard_intro.set_markup("<span size='large'><b>Clipboard</b></span>")
        clipboard_intro.set_xalign(0)
        clipboard_intro.set_line_wrap(True)
        clipboard_tab.pack_start(clipboard_intro, False, False, 0)

        clipboard_description = Gtk.Label(label="Use CopyQ for a smooth community-tested Super+V clipboard history popup.")
        clipboard_description.set_xalign(0)
        clipboard_description.set_line_wrap(True)
        clipboard_tab.pack_start(clipboard_description, False, False, 0)

        clipboard_card = self.create_card("Clipboard History")
        clipboard_tab.pack_start(clipboard_card, False, False, 0)

        self.clipboard_switch = self.create_feature_switch(
            clipboard_card,
            "Clipboard History (CopyQ)",
            "Turn CopyQ autostart and the Super+V clipboard popup on or off.",
            self.on_clipboard_feature_toggled,
        )

        self.refresh_compatibility()
        self.refresh_current_style()
        self.refresh_profiles()
        self.refresh_feature_state()
        self.refresh_mouse_movement_state()

    def create_tab_page(self):
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        page.set_border_width(20)
        scroller.add(page)
        return scroller, page

    def create_card(self, title):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(14)

        label = Gtk.Label()
        label.set_markup(f"<b>{title}</b>")
        label.set_xalign(0)
        box.pack_start(label, False, False, 0)
        return box

    def create_primary_button(self, title, tooltip):
        button = Gtk.Button(label=title)
        button.set_tooltip_text(tooltip)
        button.set_hexpand(True)
        return button

    def create_feature_switch(self, parent, title, detail, callback):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        label = Gtk.Label()
        label.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
        label.set_xalign(0)
        description = Gtk.Label(label=detail)
        description.set_xalign(0)
        description.set_line_wrap(True)
        copy.pack_start(label, False, False, 0)
        copy.pack_start(description, False, False, 0)

        switch = Gtk.Switch()
        switch.set_valign(Gtk.Align.CENTER)
        switch.connect("state-set", callback)

        row.pack_start(copy, True, True, 0)
        row.pack_end(switch, False, False, 0)
        parent.pack_start(row, False, False, 0)
        return switch

    def log(self, message):
        self.status_label.set_text(message)
        buffer = self.log_view.get_buffer()
        end = buffer.get_end_iter()
        buffer.insert(end, f"{message}\n")
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.log_view.scroll_mark_onscreen(mark)

    def refresh_compatibility(self):
        session = os.environ.get("XDG_SESSION_TYPE", "unknown")
        shell = run(["gnome-shell", "--version"], check=False) or "GNOME Shell unknown"
        chrome_available = any(
            shutil.which(binary)
            for binary in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
        )
        xdotool_available = shutil.which("xdotool") is not None
        config_dir, browser_id = detect_chrome_config()
        copyq_available = shutil.which("copyq") is not None

        lines = [
            f"Desktop session: {session}",
            f"Shell: {shell}",
            f"Browser config: {config_dir if config_dir.exists() else 'not found yet'}",
            f"CopyQ: {'installed' if copyq_available else 'not installed'}",
        ]

        if session == "x11" and xdotool_available:
            support = "Full profile window grouping support is available."
        elif session == "wayland":
            support = "Wayland detected: launchers and dock styles work, but profile window grouping may be less reliable."
        else:
            support = "Partial support: xdotool is missing or the display session is unusual."

        if not chrome_available:
            support += " Chrome/Chromium executable was not found in PATH."

        self.compatibility_label.set_text(f"{support}\n\n" + "\n".join(lines))
        return browser_id

    def refresh_feature_state(self):
        self.syncing_features = True
        self.profile_switch.set_active(self.profile_feature_enabled())
        self.hover_switch.set_active(self.hover_feature_enabled())
        self.clipboard_switch.set_active(self.clipboard_feature_enabled())
        self.syncing_features = False

    def refresh_mouse_movement_state(self):
        env = self.mouse_service.getEnvironment()
        supported = self.mouse_service.isSupportedPlatform()
        maccel_available = supported and self.mouse_service.isMaccelInstalled()
        install_status = self.mouse_service.getInstallStatus()
        install_running = self.mouse_install_process is not None and self.mouse_install_process.poll() is None
        self.mouse_windows_button.set_sensitive(maccel_available)
        self.mouse_macos_button.set_sensitive(maccel_available)
        self.mouse_restore_button.set_sensitive(maccel_available and MOUSE_BACKUP_PATH.exists())
        self.mouse_install_button.set_sensitive(
            supported and not maccel_available and install_status["pkexecAvailable"] and not install_running
        )
        self.mouse_install_progress.set_visible(install_running)
        if install_running:
            self.mouse_install_progress.set_text("Installing maccel...")
            self.mouse_install_progress.set_show_text(True)
        else:
            self.mouse_install_progress.set_fraction(0)
            self.mouse_install_progress.set_show_text(False)

        if maccel_available:
            self.mouse_backend_indicator.set_markup("<b>[V] maccel installed</b>")
        else:
            self.mouse_backend_indicator.set_markup("<b>[X] maccel not installed</b>")

        if maccel_available:
            self.mouse_backend_label.set_text("Backend: maccel detected")
        else:
            self.mouse_backend_label.set_text(
                "Backend: maccel not installed\nThis feature requires the open-source maccel backend."
            )

        install_lines = []
        if install_running:
            install_lines.append("Install check: maccel install is running.")
            latest_line = self.latest_mouse_install_log_line()
            if latest_line:
                install_lines.append(f"Progress: {latest_line}")
        elif install_status["maccelInstalled"]:
            install_lines.append("Install check: maccel is installed.")
        elif not install_status["pkexecAvailable"]:
            install_lines.append("Install check: pkexec is missing. Install maccel manually.")
        else:
            install_lines.append("Install check: ready to install maccel with authentication.")

        if install_status["missingCommands"]:
            install_lines.append("Missing tools: " + ", ".join(install_status["missingCommands"]))
        else:
            install_lines.append("Required tools: detected")

        if install_status["kernelHeadersInstalled"]:
            install_lines.append(f"Kernel headers: detected for {install_status['kernelRelease']}")
        else:
            install_lines.append(f"Kernel headers: will install for {install_status['kernelRelease']}")

        if install_status["kernelCompiler"]:
            compiler_state = "detected" if install_status["kernelCompilerInstalled"] else "will install"
            install_lines.append(f"Kernel compiler: {compiler_state} {install_status['kernelCompiler']}")

        install_lines.append(f"Install log: {install_status['installLogPath']}")
        self.mouse_install_label.set_text("\n".join(install_lines))
        self.refresh_mouse_install_log_view()

        active = self.mouse_service.getCurrentPresetState()
        active_label = {
            "windows": "Windows",
            "macos": "macOS",
            "previous": "Previous",
        }.get(active, "Custom / Previous / Unknown")
        self.mouse_active_label.set_text(f"Active preset: {active_label}")

        if env["sessionType"] == "wayland":
            self.mouse_warning_label.set_text("Wayland support may depend on compositor behavior.")
        elif not supported:
            self.mouse_warning_label.set_text("Mouse Movement is only supported on Linux.")
        else:
            self.mouse_warning_label.set_text("")

    def refresh_mouse_install_log_view(self):
        if not hasattr(self, "mouse_install_log_view"):
            return
        text = ""
        if MOUSE_INSTALL_LOG.exists():
            try:
                lines = MOUSE_INSTALL_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
                text = "\n".join(lines[-220:])
            except Exception as error:
                text = f"Could not read install log: {error}"
        buffer = self.mouse_install_log_view.get_buffer()
        current = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        if current == text:
            return
        buffer.set_text(text)
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.mouse_install_log_view.scroll_mark_onscreen(mark)

    def latest_mouse_install_log_line(self):
        if not MOUSE_INSTALL_LOG.exists():
            return ""
        try:
            lines = MOUSE_INSTALL_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return ""
        for line in reversed(lines):
            line = line.strip()
            if line:
                return line[:180]
        return ""

    def pulse_mouse_install_progress(self):
        if self.mouse_install_process is None or self.mouse_install_process.poll() is not None:
            self.mouse_install_timer_id = None
            return False
        self.mouse_install_progress.pulse()
        self.refresh_mouse_movement_state()
        return True

    def refresh_current_style(self):
        current = run(["gsettings", "get", "org.gnome.shell.extensions.dash-to-dock", "click-action"], check=False)
        current = current.strip("'")
        self.syncing_style = True
        if current in self.style_buttons:
            self.style_buttons[current].set_active(True)
            self.style_description.set_text(self.describe_style(current))
        else:
            self.style_description.set_text(f"Current dock click action: {current or 'unknown'}")
        self.syncing_style = False

    def describe_style(self, action):
        for _name, (style_action, help_text) in STYLE_ACTIONS.items():
            if style_action == action:
                return help_text
        return "Custom dock click behavior."

    def refresh_profiles(self):
        self.profiles = self.load_profiles()
        for child in self.profile_list.get_children():
            self.profile_list.remove(child)

        if not self.profiles:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            row.set_border_width(8)
            title = Gtk.Label(label="No Chrome/Chromium profiles found.")
            title.set_xalign(0)
            detail = Gtk.Label(label="Open Chrome once and create at least one profile, then press Refresh.")
            detail.set_xalign(0)
            detail.set_line_wrap(True)
            row.pack_start(title, False, False, 0)
            row.pack_start(detail, False, False, 0)
            self.profile_list.add(row)
        else:
            for profile in self.profiles:
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                row.set_border_width(8)
                name = profile["name"]
                directory = profile["directory"]
                user_name = profile.get("user_name") or ""
                title = Gtk.Label()
                title.set_markup(f"<b>{GLib.markup_escape_text(name)}</b>")
                title.set_xalign(0)
                detail = Gtk.Label(label=f"{directory}" + (f"  -  {user_name}" if user_name else ""))
                detail.set_xalign(0)
                detail.set_line_wrap(True)
                row.pack_start(title, False, False, 0)
                row.pack_start(detail, False, False, 0)
                self.profile_list.add(row)

        self.profile_list.show_all()
        self.log(f"Detected {len(self.profiles)} profile(s).")

    def load_profiles(self):
        config_dir, _ = detect_chrome_config()
        local_state = config_dir / "Local State"
        if not local_state.exists():
            return []

        try:
            data = json.loads(local_state.read_text(encoding="utf-8"))
        except Exception:
            return []

        info_cache = data.get("profile", {}).get("info_cache", {})
        profiles = []
        for directory, info in info_cache.items():
            if not (config_dir / directory / "Preferences").exists():
                continue
            profiles.append(
                {
                    "directory": directory,
                    "name": info.get("name") or directory,
                    "user_name": info.get("user_name") or "",
                    "picture": info.get("gaia_picture_file_name") or "Google Profile Picture.png",
                }
            )
        return profiles

    def on_refresh(self, _button):
        self.refresh_compatibility()
        self.refresh_current_style()
        self.refresh_profiles()
        self.refresh_feature_state()
        self.refresh_mouse_movement_state()

    def on_install_profiles(self, _button):
        try:
            self.install_profile_launchers()
            self.log("Profile dock icons installed. Close Chrome and reopen profiles from the dock icons.")
            self.refresh_feature_state()
        except Exception as error:
            self.log(f"Failed: {error}")

    def on_pin_profiles(self, _button):
        try:
            self.pin_profile_launchers()
            self.log("Pinned profile icons to the dock.")
            self.refresh_feature_state()
        except Exception as error:
            self.log(f"Failed to pin icons: {error}")

    def on_install_hover(self, _button):
        try:
            self.install_hover_extension()
            self.log("Hover preview extension installed and enabled.")
            self.log("Restart GNOME Shell to load it: Alt+F2, type r, press Enter. On Wayland, log out/in.")
            self.refresh_feature_state()
        except Exception as error:
            self.log(f"Failed to install hover previews: {error}")

    def on_profile_feature_toggled(self, _switch, state):
        if self.syncing_features:
            return False
        try:
            if state:
                self.install_profile_launchers()
                self.pin_profile_launchers()
                self.log("Chrome profile dock icons enabled.")
            else:
                self.disable_profile_launchers()
                self.log("Chrome profile dock icons disabled.")
            _switch.set_state(state)
            self.refresh_feature_state()
        except Exception as error:
            self.log(f"Failed to update profile dock icons: {error}")
            _switch.set_state(not state)
            self.refresh_feature_state()
        return True

    def on_hover_feature_toggled(self, _switch, state):
        if self.syncing_features:
            return False
        try:
            if state:
                self.install_hover_extension()
                self.log("Hover previews enabled. Restart GNOME Shell or log out/in to load them.")
            else:
                self.disable_hover_extension()
                self.log("Hover previews disabled. Restart GNOME Shell or log out/in to unload them.")
            _switch.set_state(state)
            self.refresh_feature_state()
        except Exception as error:
            self.log(f"Failed to update hover previews: {error}")
            _switch.set_state(not state)
            self.refresh_feature_state()
        return True

    def on_clipboard_feature_toggled(self, _switch, state):
        if self.syncing_features:
            return False
        try:
            if state:
                self.enable_copyq_clipboard()
                self.log("Clipboard history enabled with CopyQ. Use Super+V.")
            else:
                self.disable_copyq_clipboard()
                self.log("Clipboard history disabled.")
            _switch.set_state(state)
            self.refresh_compatibility()
            self.refresh_feature_state()
        except Exception as error:
            self.log(f"Failed to update clipboard history: {error}")
            _switch.set_state(not state)
            self.refresh_feature_state()
        return True

    def on_mouse_windows(self, _button):
        try:
            self.mouse_service.applyWindowsPreset()
            self.log("Active preset: Windows")
        except Exception as error:
            self.log(f"Failed to apply Windows mouse movement: {error}")
        self.refresh_mouse_movement_state()

    def on_mouse_install_backend(self, _button):
        try:
            self.mouse_install_button.set_sensitive(False)
            self.log("Installing maccel backend. Ubuntu may ask for your password.")
            self.mouse_install_process = self.mouse_service.startMaccelBackendInstall()
            GLib.child_watch_add(self.mouse_install_process.pid, self.on_mouse_install_finished)
            if self.mouse_install_timer_id is None:
                self.mouse_install_timer_id = GLib.timeout_add(700, self.pulse_mouse_install_progress)
        except Exception as error:
            self.log(f"Failed to install maccel backend: {error}")
            self.mouse_install_process = None
        self.refresh_mouse_movement_state()

    def on_mouse_install_finished(self, _pid, status):
        exit_code = status >> 8
        if self.mouse_install_process is not None:
            self.mouse_install_process.wait()
        self.mouse_install_process = None
        self.mouse_install_timer_id = None
        if exit_code == 0 and self.mouse_service.isMaccelInstalled():
            self.log("maccel backend install finished. Log out and back in if group permissions were updated.")
        elif exit_code == 0:
            self.log(f"maccel installer finished, but maccel was not detected. Check {MOUSE_INSTALL_LOG}.")
        else:
            detail = self.latest_mouse_install_log_line()
            message = "maccel install failed."
            if detail:
                message += f" Last log: {detail}"
            message += f" Check {MOUSE_INSTALL_LOG}."
            self.log(message)
        self.refresh_mouse_movement_state()

    def on_mouse_macos(self, _button):
        try:
            self.mouse_service.applyMacOSPreset()
            self.log("Active preset: macOS")
        except Exception as error:
            self.log(f"Failed to apply macOS-like mouse movement: {error}")
        self.refresh_mouse_movement_state()

    def on_mouse_restore(self, _button):
        try:
            self.mouse_service.restorePreviousMaccelState()
            self.log("Previous mouse settings restored")
        except Exception as error:
            self.log(f"Failed to restore previous mouse settings: {error}")
        self.refresh_mouse_movement_state()

    def on_style_toggled(self, button, action):
        if self.syncing_style:
            return
        if not button.get_active():
            return
        try:
            run(["gsettings", "set", "org.gnome.shell.extensions.dash-to-dock", "click-action", action])
            run(["gsettings", "set", "org.gnome.shell.extensions.dash-to-dock", "middle-click-action", "previews"])
            run(["gsettings", "set", "org.gnome.shell.extensions.dash-to-dock", "activate-single-window", "true"])
            self.style_description.set_text(self.describe_style(action))
            self.log(f"Dock click style set to {action}.")
        except Exception as error:
            self.log(f"Failed to set style: {error}")

    def install_profile_launchers(self):
        config_dir, browser_id = detect_chrome_config()
        if not self.profiles:
            self.refresh_profiles()
        if not self.profiles:
            raise RuntimeError("No Chrome/Chromium profiles found.")

        APP_DIR.mkdir(parents=True, exist_ok=True)
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        ICON_DIR.mkdir(parents=True, exist_ok=True)

        wrapper_path = BIN_DIR / "chrome-profile-launch"
        wrapper_path.write_text(WRAPPER, encoding="utf-8")
        wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        for index, profile in enumerate(self.profiles):
            desktop_id = self.desktop_id_for_profile(profile)
            class_name = profile_window_class(profile["directory"], index)
            icon_path = ICON_DIR / desktop_id.replace(".desktop", ".png")
            picture = config_dir / profile["directory"] / profile["picture"]
            fallback = config_dir / profile["directory"] / "Google Profile Picture.png"
            if picture.exists():
                shutil.copyfile(picture, icon_path)
            elif fallback.exists():
                shutil.copyfile(fallback, icon_path)

            desktop_path = APP_DIR / desktop_id
            name = profile["name"].replace("\n", " ").strip()
            directory = profile["directory"]
            desktop = f"""[Desktop Entry]
Version=1.0
Name=Chrome - {name}
GenericName=Web Browser
Comment=Open Chrome with the {name} profile
Exec={wrapper_path} "{directory}" {class_name} --new-window %U
Terminal=false
Icon={icon_path if icon_path.exists() else browser_id}
Type=Application
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;application/xml;application/pdf;x-scheme-handler/http;x-scheme-handler/https;
StartupNotify=true
StartupWMClass={class_name}
Actions=new-window;new-private-window;

[Desktop Action new-window]
Name=New Window
Exec={wrapper_path} "{directory}" {class_name} --new-window

[Desktop Action new-private-window]
Name=New Incognito Window
Exec={wrapper_path} "{directory}" {class_name} --incognito
"""
            desktop_path.write_text(desktop, encoding="utf-8")

        run(["update-desktop-database", str(APP_DIR)], check=False)

    def pin_profile_launchers(self):
        if not self.profiles:
            self.refresh_profiles()
        desktop_ids = [self.desktop_id_for_profile(profile) for profile in self.profiles]
        current = parse_gsettings_list(run(["gsettings", "get", "org.gnome.shell", "favorite-apps"], check=False))
        filtered = [
            item
            for item in current
            if item not in desktop_ids
            and item != "google-chrome.desktop"
            and item != "chromium.desktop"
            and not item.startswith("google-chrome-profile-profile-")
        ]
        run(["gsettings", "set", "org.gnome.shell", "favorite-apps", format_gsettings_list(desktop_ids + filtered)])

    def disable_profile_launchers(self):
        desktop_ids = [self.desktop_id_for_profile(profile) for profile in self.profiles]
        current = parse_gsettings_list(run(["gsettings", "get", "org.gnome.shell", "favorite-apps"], check=False))
        filtered = [item for item in current if item not in desktop_ids and not item.startswith("google-chrome-profile-")]
        if "google-chrome.desktop" not in filtered and shutil.which("google-chrome"):
            filtered.insert(0, "google-chrome.desktop")
        run(["gsettings", "set", "org.gnome.shell", "favorite-apps", format_gsettings_list(filtered)])

        for desktop_file in APP_DIR.glob("google-chrome-profile*.desktop"):
            desktop_file.unlink(missing_ok=True)
        for icon_file in ICON_DIR.glob("google-chrome-profile*.png"):
            icon_file.unlink(missing_ok=True)
        run(["update-desktop-database", str(APP_DIR)], check=False)

    def profile_feature_enabled(self):
        if not self.profiles:
            return False
        current = parse_gsettings_list(run(["gsettings", "get", "org.gnome.shell", "favorite-apps"], check=False))
        return all((APP_DIR / self.desktop_id_for_profile(profile)).exists() for profile in self.profiles) and all(
            self.desktop_id_for_profile(profile) in current for profile in self.profiles
        )

    def desktop_id_for_profile(self, profile):
        return f"google-chrome-profile-{profile_slug(profile['directory'])}.desktop"

    def install_hover_extension(self):
        EXT_DIR.mkdir(parents=True, exist_ok=True)
        metadata = {
            "description": "Preview open windows by hovering a dock icon and activate a window by selecting the preview.",
            "name": "Dock Window Preview",
            "shell-version": ["42"],
            "uuid": "dock-window-preview@quivio",
            "version": 42,
        }
        (EXT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (EXT_DIR / "extension.js").write_text(EXTENSION_JS, encoding="utf-8")
        (EXT_DIR / "stylesheet.css").write_text(EXTENSION_CSS, encoding="utf-8")

        raw = run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], check=False)
        enabled = []
        if raw.startswith("["):
            enabled = [part.strip().strip("'") for part in raw.strip("[]").split(",") if part.strip()]
        if "dock-window-preview@quivio" not in enabled:
            enabled.append("dock-window-preview@quivio")
        value = "[" + ", ".join(f"'{item}'" for item in enabled) + "]"
        run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", value])

    def disable_hover_extension(self):
        enabled = [
            item
            for item in parse_gsettings_list(run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], check=False))
            if item != "dock-window-preview@quivio"
        ]
        run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", format_gsettings_list(enabled)])

    def hover_feature_enabled(self):
        enabled = parse_gsettings_list(run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], check=False))
        return "dock-window-preview@quivio" in enabled

    def enable_copyq_clipboard(self):
        self.ensure_copyq_installed()
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
        COPYQ_START.write_text(
            """#!/usr/bin/env bash
set -e

if ! pgrep -x copyq >/dev/null 2>&1; then
  copyq >/dev/null 2>&1 &
  sleep 0.8
fi

copyq config item_popup_interval 0 >/dev/null 2>&1 || true
copyq config native_notifications false >/dev/null 2>&1 || true
wait
""",
            encoding="utf-8",
        )
        COPYQ_START.chmod(0o755)
        COPYQ_AUTOSTART.write_text(
            f"""[Desktop Entry]
Type=Application
Name=CopyQ
Comment=Clipboard manager
Exec={COPYQ_START}
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=2
""",
            encoding="utf-8",
        )
        COPYQ_SERVICE.write_text(
            f"""[Unit]
Description=CopyQ clipboard manager
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart={COPYQ_START}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
""",
            encoding="utf-8",
        )
        COPYQ_SHORTCUT.write_text(
            """#!/usr/bin/env bash
set -e

if ! pgrep -x copyq >/dev/null 2>&1; then
  copyq >/dev/null 2>&1 &
  sleep 0.5
fi

copyq config item_popup_interval 0 >/dev/null 2>&1 || true
copyq config native_notifications false >/dev/null 2>&1 || true
exec copyq show
""",
            encoding="utf-8",
        )
        COPYQ_SHORTCUT.chmod(0o755)
        self.configure_custom_shortcut(
            CLIPBOARD_SHORTCUT_PATH,
            "Clipboard History",
            str(COPYQ_SHORTCUT),
            "<Super>v",
        )
        subprocess.Popen(["copyq"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        run(["copyq", "config", "item_popup_interval", "0"], check=False)
        run(["copyq", "config", "native_notifications", "false"], check=False)
        run(["systemctl", "--user", "daemon-reload"], check=False)
        run(["systemctl", "--user", "enable", "--now", "copyq.service"], check=False)

    def disable_copyq_clipboard(self):
        COPYQ_AUTOSTART.unlink(missing_ok=True)
        COPYQ_SHORTCUT.unlink(missing_ok=True)
        COPYQ_START.unlink(missing_ok=True)
        run(["systemctl", "--user", "disable", "--now", "copyq.service"], check=False)
        COPYQ_SERVICE.unlink(missing_ok=True)
        run(["systemctl", "--user", "daemon-reload"], check=False)
        self.remove_custom_shortcut(CLIPBOARD_SHORTCUT_PATH)
        if shutil.which("copyq"):
            run(["copyq", "exit"], check=False)

    def ensure_copyq_installed(self):
        if shutil.which("copyq"):
            return
        if not shutil.which("pkexec"):
            raise RuntimeError("CopyQ is not installed and pkexec is unavailable. Install it with: sudo apt install copyq")
        self.log("CopyQ is not installed. Ubuntu will ask for your password to install it.")
        run(["pkexec", "apt-get", "install", "-y", "copyq"])

    def configure_custom_shortcut(self, path, name, command, binding):
        current = parse_gsettings_list(
            run(["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"], check=False)
        )
        if path not in current:
            current.append(path)
        run(["gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", format_gsettings_list(current)])
        schema = f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{path}"
        run(["gsettings", "set", schema, "name", name])
        run(["gsettings", "set", schema, "command", command])
        run(["gsettings", "set", schema, "binding", binding])

    def remove_custom_shortcut(self, path):
        current = [
            item
            for item in parse_gsettings_list(
                run(["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"], check=False)
            )
            if item != path
        ]
        run(["gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", format_gsettings_list(current)])

    def clipboard_feature_enabled(self):
        if not shutil.which("copyq") or not COPYQ_SHORTCUT.exists():
            return False
        current = parse_gsettings_list(
            run(["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"], check=False)
        )
        return CLIPBOARD_SHORTCUT_PATH in current and (COPYQ_AUTOSTART.exists() or COPYQ_SERVICE.exists())


class ChromeDockProfiles(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="local.chrome-dock-profiles")

    def do_activate(self):
        window = App(self)
        window.show_all()


def main():
    app = ChromeDockProfiles()
    return app.run(None)


if __name__ == "__main__":
    raise SystemExit(main())
