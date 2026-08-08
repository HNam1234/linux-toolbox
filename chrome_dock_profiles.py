#!/usr/bin/env python3
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import gi

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, GLib, Gdk, Gio  # noqa: E402

from linux_toolbox.resources import load_template, load_text  # noqa: E402


HOME = Path.home()
APP_DIR = HOME / ".local/share/applications"
BIN_DIR = HOME / ".local/bin"
ICON_DIR = HOME / ".local/share/icons/hicolor/256x256/apps"
HOVER_EXTENSION_UUID = "dock-window-preview@quivio"
EXT_DIR = HOME / ".local/share/gnome-shell/extensions" / HOVER_EXTENSION_UUID
AUTOSTART_DIR = HOME / ".config/autostart"
SYSTEMD_USER_DIR = HOME / ".config/systemd/user"
CHROME_CONFIG = HOME / ".config/google-chrome"
CLIPBOARD_SHORTCUT_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipboard-history/"
COPYQ_AUTOSTART = AUTOSTART_DIR / "copyq.desktop"
COPYQ_SHORTCUT = BIN_DIR / "copyq-super-v"
COPYQ_START = BIN_DIR / "copyq-start"
COPYQ_CLEAR = BIN_DIR / "copyq-clear"
COPYQ_SERVICE = SYSTEMD_USER_DIR / "copyq.service"
CLIPBOARD_SHORTCUT_BINDING = "<Super>v"
CONFIG_DIR = HOME / ".config/chrome-dock-profiles"
CONFIG_PATH = CONFIG_DIR / "config.json"
# GNOME binds <Super>v to the notification tray by default, which steals the key
# from CopyQ. We remove it from this binding (keeping the rest) so Super+V is
# reliable, and restore it when the feature is turned off.
GNOME_TRAY_SCHEMA = "org.gnome.shell.keybindings"
GNOME_TRAY_KEY = "toggle-message-tray"
MOUSE_APPLY_ON_LOGIN = BIN_DIR / "chrome-dock-profiles-apply-mouse"
MOUSE_AUTOSTART = AUTOSTART_DIR / "chrome-dock-profiles-mouse.desktop"
MOUSE_BACKUP_PATH = CONFIG_DIR / "maccel-previous-state.json"
MOUSE_ORIGINAL_BACKUP_PATH = CONFIG_DIR / "maccel-original-state.json"
MOUSE_COMMAND_LOG = CONFIG_DIR / "mouse-movement-commands.log"
MOUSE_INSTALLER = BIN_DIR / "chrome-dock-profiles-install-maccel"
MOUSE_INSTALL_LOG = CONFIG_DIR / "maccel-install.log"
MOUSE_PERMISSION_FIXER = BIN_DIR / "chrome-dock-profiles-fix-maccel-permission"
SENS_MULT_PATH = Path("/sys/module/maccel/parameters/SENS_MULT")
MACCEL_GROUP = "maccel"
GNOME_EXTENSION_ROOTS = (
    HOME / ".local/share/gnome-shell/extensions",
    Path("/usr/local/share/gnome-shell/extensions"),
    Path("/usr/share/gnome-shell/extensions"),
)
DASH_TO_DOCK_SCHEMA = "org.gnome.shell.extensions.dash-to-dock"
DOCK_LAYOUT_KEYS = (
    "dock-position",
    "extend-height",
    "dock-fixed",
    "autohide",
    "intellihide",
    "show-favorites",
    "show-running",
    "show-show-apps-button",
    "show-apps-at-top",
)
WINDOWS_DOCK_PRESET = {
    "dock-position": "BOTTOM",
    "extend-height": "true",
    "dock-fixed": "true",
    "autohide": "false",
    "intellihide": "false",
    "show-favorites": "true",
    "show-running": "true",
    "show-show-apps-button": "true",
    "show-apps-at-top": "true",
}
DEFAULT_DOCK_PRESET = {
    "dock-position": "LEFT",
    "extend-height": "true",
    "dock-fixed": "true",
    "autohide": "false",
    "intellihide": "false",
    "show-favorites": "true",
    "show-running": "true",
    "show-show-apps-button": "true",
    "show-apps-at-top": "false",
}


STYLE_ACTIONS = {
    "Smooth Minimize": ("minimize", "Left-click minimizes/restores. Most stable."),
    "Minimize + Previews": ("minimize-or-previews", "Single window toggles; multiple windows show previews."),
    "Preview Picker": ("previews", "Left-click opens window previews."),
    "Cycle Windows": ("cycle-windows", "Left-click cycles through app windows."),
}


# These are the extensions that make the desktop workflow useful for a
# Windows-like setup. They are intentionally described as modules rather than
# as a download list: each module has a lifecycle (installed/enabled) and a
# small set of high-value settings that Linux Toolbox can edit directly.
# The extension's complete preferences remain available through the fallback
# "Open full preferences" action.
EXTENSION_MODULES = (
    {
        "name": "ArcMenu",
        "uuid": "arcmenu@arcmenu.com",
        "description": "A familiar application menu with layouts, button, and panel placement controls.",
        "schema": "org.gnome.shell.extensions.arcmenu",
        "settings": (
            "menu-layout",
            "position-in-panel",
            "menu-button-appearance",
            "menu-button-text",
            "menu-button-icon-size",
            "default-menu-view",
            "menu-position-alignment",
            "show-user-avatar",
            "show-bookmarks",
            "multi-monitor",
        ),
    },
    {
        "name": "Bluetooth Battery Meter",
        "uuid": "Bluetooth-Battery-Meter@maniacx.github.com",
        "description": "Show battery levels for Bluetooth devices in the panel and quick settings.",
        "schema": "org.gnome.shell.extensions.Bluetooth-Battery-Meter",
        "settings": (
            "modify-quick-settings",
            "popup-in-quick-settings",
            "enable-battery-level-icon",
            "enable-battery-level-text",
            "swap-icon-text",
            "sort-devices-by-history",
            "indicator-type",
            "enable-on-hover-mode",
            "on-hover-delay",
            "enable-tooltip",
            "indicator-size",
            "disable-level-in-icon",
        ),
    },
    {
        "name": "Dash to Panel",
        "uuid": "dash-to-panel@jderose9.github.com",
        "description": "Turn GNOME's top bar and dock into a configurable taskbar.",
        "schema": "org.gnome.shell.extensions.dash-to-panel",
        "settings": (
            "panel-position",
            "panel-size",
            "taskbar-locked",
            "intellihide",
            "show-window-previews",
            "show-tooltip",
            "show-running-apps",
            "show-favorites",
            "group-apps",
            "multi-monitors",
            "click-action",
            "scroll-panel-action",
            "scroll-icon-action",
        ),
    },
)


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


def normalize_gsettings_value(value):
    value = str(value).strip()
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1]
    return value


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


def current_username():
    for value in (os.environ.get("USER"), os.environ.get("LOGNAME")):
        if value and value.strip():
            return value.strip()
    try:
        import pwd

        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        return ""


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

    def detectCurrentPreset(self):
        if not self.isAvailable():
            return "default_ubuntu"
        config = self.readCurrentConfig()
        mode = self._normalize_mode(config.get("mode", ""))
        common = config.get("common", [])
        linear = config.get("linear", [])
        natural = config.get("natural", [])
        if self._close_values(common, [1.0, 1.0, 1000.0, 0.0]):
            if mode == "linear" and self._close_values(linear, [0.055, 1.5, 2.8]):
                return "windows"
            if mode == "natural" and self._close_values(natural, [0.1, 1.0, 1.65]):
                return "macos"
        if mode == "linear" and self._close_values(linear, [0.0, 0.0, 0.0]):
            return "default_ubuntu"
        if mode in {"no-accel", "none"}:
            return "default_ubuntu"
        return "custom"

    def setSensMultiplier(self, multiplier):
        value = float(multiplier)
        if value <= 0:
            raise RuntimeError("Sensitivity multiplier must be greater than 0.")
        self._run(["set", "param", "sens-mult", self._format_value(value)])
        return value

    def _format_value(self, value):
        text = f"{float(value):.4f}".rstrip("0").rstrip(".")
        return text or "0"

    def backup(self):
        config = self.readCurrentConfig()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        MOUSE_BACKUP_PATH.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        return str(MOUSE_BACKUP_PATH)

    def backupOriginal(self):
        if MOUSE_ORIGINAL_BACKUP_PATH.exists():
            return str(MOUSE_ORIGINAL_BACKUP_PATH)
        config = self.readCurrentConfig()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        MOUSE_ORIGINAL_BACKUP_PATH.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        return str(MOUSE_ORIGINAL_BACKUP_PATH)

    def restore(self):
        if not MOUSE_BACKUP_PATH.exists():
            raise RuntimeError("No previous mouse settings backup was found.")
        config = json.loads(MOUSE_BACKUP_PATH.read_text(encoding="utf-8"))
        self.writeConfig(config)

    def restoreOriginal(self):
        if not MOUSE_ORIGINAL_BACKUP_PATH.exists():
            raise RuntimeError("No original mouse settings backup was found.")
        config = json.loads(MOUSE_ORIGINAL_BACKUP_PATH.read_text(encoding="utf-8"))
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

    def _close_values(self, actual, expected, tolerance=0.0005):
        if len(actual) != len(expected):
            return False
        return all(abs(float(left) - float(right)) <= tolerance for left, right in zip(actual, expected))


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


class PermissionStatus:
    def __init__(
        self,
        maccelLoaded,
        sensMultExists,
        sensMultWritable,
        userInMaccelGroup,
        currentSessionInWriteGroup,
        parameterGroup,
        sysfsReadOnly,
        needsLogout,
        message,
    ):
        self.maccelLoaded = maccelLoaded
        self.sensMultExists = sensMultExists
        self.sensMultWritable = sensMultWritable
        self.userInMaccelGroup = userInMaccelGroup
        self.currentSessionInWriteGroup = currentSessionInWriteGroup
        self.parameterGroup = parameterGroup
        self.sysfsReadOnly = sysfsReadOnly
        self.needsLogout = needsLogout
        self.message = message

    def to_dict(self):
        return {
            "maccelLoaded": self.maccelLoaded,
            "sensMultExists": self.sensMultExists,
            "sensMultWritable": self.sensMultWritable,
            "userInMaccelGroup": self.userInMaccelGroup,
            "currentSessionInWriteGroup": self.currentSessionInWriteGroup,
            "parameterGroup": self.parameterGroup,
            "sysfsReadOnly": self.sysfsReadOnly,
            "needsLogout": self.needsLogout,
            "message": self.message,
        }


class MaccelPermissionService:
    """Checks and repairs the ability of the current process to write maccel
    kernel parameters such as /sys/module/maccel/parameters/SENS_MULT.

    The repair flow prefers the supported approach (maccel group ownership via
    udev rules) and never chmods sysfs files as a permanent fix. All privileged
    steps are bundled into a single pkexec invocation so the user is asked to
    authenticate at most once per fix.
    """

    def __init__(self, username=None):
        self.username = username or current_username()

    def isMaccelLoaded(self):
        if Path("/sys/module/maccel").exists():
            return True
        output = run(["lsmod"], check=False)
        return any(line.split()[:1] == ["maccel"] for line in output.splitlines() if line.strip())

    def doesSensMultExist(self):
        return SENS_MULT_PATH.exists()

    def canWriteSensMult(self):
        # Mirrors `test -w`: reflects whether THIS process (with its current
        # session group membership) may write the file.
        try:
            return self.doesSensMultExist() and os.access(SENS_MULT_PATH, os.W_OK)
        except Exception:
            return False

    def listUserGroups(self):
        user = self.username
        if not user:
            return []
        output = run(["id", "-nG", user], check=False)
        return [name for name in output.split() if name]

    def listCurrentProcessGroups(self):
        output = run(["id", "-nG"], check=False)
        return [name for name in output.split() if name]

    def parameterGroupName(self):
        if not self.doesSensMultExist():
            return ""
        try:
            import grp

            return grp.getgrgid(SENS_MULT_PATH.stat().st_gid).gr_name
        except Exception:
            return ""

    def isSysfsReadOnly(self):
        try:
            for line in Path("/proc/mounts").read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[1] == "/sys":
                    return "ro" in parts[3].split(",")
        except Exception:
            return False
        return False

    def isUserInMaccelGroup(self):
        # Reflects the configured group membership (what `usermod -aG` changes),
        # which updates immediately even if the live session has not picked it up.
        if MACCEL_GROUP in self.listUserGroups():
            return True
        try:
            import grp

            return self.username in grp.getgrnam(MACCEL_GROUP).gr_mem
        except Exception:
            return False

    def doesMaccelGroupExist(self):
        return bool(run(["getent", "group", MACCEL_GROUP], check=False).strip())

    # --- Privileged step builders (composed into one pkexec script) ---------

    def ensureMaccelGroupExists(self):
        return ['getent group maccel >/dev/null 2>&1 || groupadd maccel']

    def addCurrentUserToMaccelGroup(self):
        user = self.username
        if not user:
            return []
        return [f'usermod -aG maccel "{user}"']

    def reloadUdevRules(self):
        return [
            'udevadm control --reload-rules',
            'udevadm trigger',
        ]

    def reloadMaccelModule(self):
        return [
            'modprobe -r maccel || true',
            'modprobe maccel',
        ]

    def getPermissionStatus(self):
        maccel_loaded = self.isMaccelLoaded()
        sens_exists = self.doesSensMultExist()
        sens_writable = self.canWriteSensMult()
        in_group = self.isUserInMaccelGroup()
        parameter_group = self.parameterGroupName()
        current_groups = self.listCurrentProcessGroups()
        configured_groups = self.listUserGroups()
        current_session_in_write_group = bool(parameter_group and parameter_group in current_groups)
        configured_in_write_group = bool(parameter_group and parameter_group in configured_groups)
        sysfs_read_only = self.isSysfsReadOnly()

        needs_logout = False
        if sens_writable:
            message = "maccel parameters are writable."
        elif not maccel_loaded:
            message = "maccel kernel module is not loaded."
        elif not sens_exists:
            message = "maccel SENS_MULT parameter was not found."
        elif sysfs_read_only:
            message = "/sys is mounted read-only, so maccel parameters cannot be changed in this session."
        elif configured_in_write_group and not current_session_in_write_group:
            needs_logout = True
            message = f"Log out and back in so this session joins the {parameter_group} group."
        elif in_group:
            message = "maccel group is configured, but driver parameters are still not writable."
        else:
            message = "User is not in the maccel write group yet."

        return PermissionStatus(
            maccelLoaded=maccel_loaded,
            sensMultExists=sens_exists,
            sensMultWritable=sens_writable,
            userInMaccelGroup=in_group,
            currentSessionInWriteGroup=current_session_in_write_group,
            parameterGroup=parameter_group,
            sysfsReadOnly=sysfs_read_only,
            needsLogout=needs_logout,
            message=message,
        )

    def _write_fixer_script(self):
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        steps = []
        steps += self.ensureMaccelGroupExists()
        steps += self.addCurrentUserToMaccelGroup()
        steps += self.reloadUdevRules()
        steps += self.reloadMaccelModule()
        user = self.username or "$SUDO_USER"
        MOUSE_PERMISSION_FIXER.write_text(
            load_template(
                "scripts/fix-maccel-permission.sh.tmpl",
                MOUSE_INSTALL_LOG=MOUSE_INSTALL_LOG,
                CREATE_GROUP_STEP=steps[0],
                ADD_USER_STEP=steps[1] if len(self.addCurrentUserToMaccelGroup()) else "true",
                SENS_MULT_PATH=SENS_MULT_PATH,
                USER=user,
            ),
            encoding="utf-8",
        )
        MOUSE_PERMISSION_FIXER.chmod(
            MOUSE_PERMISSION_FIXER.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )
        return MOUSE_PERMISSION_FIXER

    def startFixPermissions(self):
        if shutil.which("pkexec") is None:
            raise RuntimeError("pkexec is not installed. Cannot run the maccel permission fix.")
        fixer = self._write_fixer_script()
        command = ["pkexec", str(fixer)]
        return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def fixPermissions(self):
        # Blocking variant: runs the privileged fix once, then returns fresh status.
        if shutil.which("pkexec") is None:
            raise RuntimeError("pkexec is not installed. Cannot run the maccel permission fix.")
        fixer = self._write_fixer_script()
        run(["pkexec", str(fixer)], check=False)
        return self.getPermissionStatus()


class MouseMovementService:
    def __init__(self):
        self.backend = MaccelBackend(self._log_command)
        self.permission_service = MaccelPermissionService()
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

    def getDetectedPresetState(self):
        if not self.isMaccelInstalled():
            return "default_ubuntu"
        try:
            return self.backend.detectCurrentPreset()
        except Exception:
            return "unknown"

    def applyWindowsPreset(self):
        self._apply_preset("windows", self.backend.applyWindowsEppPreset)

    def applyMacOSPreset(self):
        self._apply_preset("macos", self.backend.applyMacOSLikePreset)

    def getPermissionStatus(self):
        return self.permission_service.getPermissionStatus()

    def startFixPermissions(self):
        return self.permission_service.startFixPermissions()

    def getLastCustomSensitivity(self):
        value = load_app_config().get("mouseMovement", {}).get("customSensMult")
        try:
            return float(value)
        except (TypeError, ValueError):
            return 1.0

    def applyCustomSensitivity(self, multiplier):
        # Caller (UI) is responsible for running the permission preflight before
        # invoking this. We still re-check here so the maccel CLI is never asked
        # to write SENS_MULT when the current process cannot.
        if not self.permission_service.canWriteSensMult():
            raise PermissionError("maccel SENS_MULT is not writable yet.")
        backup_path = self.backupCurrentMaccelState()
        try:
            applied = self.backend.setSensMultiplier(multiplier)
        except Exception:
            self.backend.restore()
            raise
        self._save_state("custom", backup_path, custom_sens=applied)
        self.ensureMouseAutostart()
        return applied

    def backupCurrentMaccelState(self):
        self.backend.backupOriginal()
        return self.backend.backup()

    def restorePreviousMaccelState(self):
        self.backend.restore()
        self._save_state("previous", str(MOUSE_BACKUP_PATH))
        self.ensureMouseAutostart()

    def restoreOriginalMaccelState(self):
        self.backend.restoreOriginal()
        self._save_state("original", str(MOUSE_ORIGINAL_BACKUP_PATH))
        self.ensureMouseAutostart()

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
        self.ensureMouseAutostart()

    def _save_state(self, active_preset, backup_path, custom_sens=None):
        config = load_app_config()
        env = self.getEnvironment()
        mouse_state = {
            "backend": "maccel",
            "activePreset": active_preset,
            "previousStateBackupPath": backup_path,
            "lastAppliedAt": iso_now(),
            "sessionType": env["sessionType"],
            "desktop": env["desktop"],
        }
        previous_custom = config.get("mouseMovement", {}).get("customSensMult")
        if custom_sens is not None:
            mouse_state["customSensMult"] = custom_sens
        elif previous_custom is not None:
            mouse_state["customSensMult"] = previous_custom
        config["mouseMovement"] = mouse_state
        save_app_config(config)

    def ensureMouseAutostart(self):
        config = load_app_config()
        mouse_state = config.get("mouseMovement", {})
        active = mouse_state.get("activePreset", "unknown")
        if active not in {"windows", "macos", "custom"}:
            MOUSE_AUTOSTART.unlink(missing_ok=True)
            MOUSE_APPLY_ON_LOGIN.unlink(missing_ok=True)
            return

        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        MOUSE_APPLY_ON_LOGIN.write_text(
            load_template(
                "scripts/apply-mouse.sh.tmpl",
                MOUSE_COMMAND_LOG=MOUSE_COMMAND_LOG,
                CONFIG_PATH=CONFIG_PATH,
            ),
            encoding="utf-8",
        )
        MOUSE_APPLY_ON_LOGIN.chmod(0o755)
        MOUSE_AUTOSTART.write_text(
            load_template("desktop/mouse-autostart.desktop.tmpl", MOUSE_APPLY_ON_LOGIN=MOUSE_APPLY_ON_LOGIN),
            encoding="utf-8",
        )

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
            load_template("scripts/install-maccel.sh.tmpl", MOUSE_INSTALL_LOG=MOUSE_INSTALL_LOG),
            encoding="utf-8",
        )
        MOUSE_INSTALLER.chmod(0o755)
        return MOUSE_INSTALLER


class App(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application)
        self.load_css()
        self.set_title("Linux Toolbox")
        self.set_default_size(1120, 720)
        self.set_border_width(0)
        self.profiles = []
        self.syncing_style = False
        self.syncing_features = False
        self.syncing_dock_layout = False
        self.syncing_sidebar = False
        self.syncing_extensions = False
        self.extension_modules = {}
        self.mouse_service = MouseMovementService()
        self.mouse_install_process = None
        self.mouse_install_timer_id = None
        self.mouse_permission_fix_process = None
        self.mouse_permission_pending = None

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.get_style_context().add_class("app-shell")
        self.add(root)

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "Linux Toolbox"
        header.props.subtitle = "Set-and-forget tools for Ubuntu"
        header.get_style_context().add_class("app-header")
        self.set_titlebar(header)

        refresh_header_button = Gtk.Button(label="Refresh")
        refresh_header_button.set_tooltip_text("Scan Chrome profiles again")
        refresh_header_button.get_style_context().add_class("header-button")
        refresh_header_button.connect("clicked", self.on_refresh)
        header.pack_end(refresh_header_button)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(180)
        self.stack.connect("notify::visible-child-name", self.on_stack_visible_child_changed)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.set_size_request(232, -1)
        sidebar.get_style_context().add_class("sidebar")
        root.pack_start(sidebar, False, False, 0)

        self.nav_list = Gtk.ListBox()
        self.nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_list.connect("row-selected", self.on_nav_row_selected)
        sidebar.pack_start(self.nav_list, True, True, 10)

        root.pack_start(self.stack, True, True, 0)

        main_scroller, main_tab = self.create_tab_page()
        chrome_scroller, chrome_tab = self.create_tab_page()
        mouse_scroller, mouse_tab = self.create_tab_page()
        clipboard_scroller, clipboard_tab = self.create_tab_page()
        extensions_scroller, extensions_tab = self.create_tab_page()

        self.stack.add_titled(main_scroller, "overview", "Overview")
        self.stack.add_titled(chrome_scroller, "chrome", "Chrome Profiles")
        self.stack.add_titled(mouse_scroller, "mouse", "Mouse")
        self.stack.add_titled(clipboard_scroller, "clipboard", "Clipboard")
        self.stack.add_titled(extensions_scroller, "extensions", "Modules")

        for name, title, icon in (
            ("overview", "Overview", "view-dashboard-symbolic"),
            ("chrome", "Chrome Profiles", "web-browser-symbolic"),
            ("mouse", "Mouse", "input-mouse-symbolic"),
            ("clipboard", "Clipboard", "edit-paste-symbolic"),
            ("extensions", "Modules", "preferences-system-symbolic"),
        ):
            self.nav_list.add(self.create_nav_row(name, title, icon))

        intro = Gtk.Label()
        intro.set_markup("<span size='large'><b>Overview</b></span>")
        intro.set_xalign(0)
        intro.set_line_wrap(True)
        intro.get_style_context().add_class("page-title")
        main_tab.pack_start(intro, False, False, 0)

        description = Gtk.Label(
            label="System overview for profile dock icons, clipboard history, mouse movement, and dock behavior."
        )
        description.set_xalign(0)
        description.set_line_wrap(True)
        description.get_style_context().add_class("page-description")
        main_tab.pack_start(description, False, False, 0)

        summary_card = self.create_card("At a Glance", "Current setup status for the main tools.")
        main_tab.pack_start(summary_card, False, False, 0)
        self.overview_summary_box = Gtk.FlowBox()
        self.overview_summary_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.overview_summary_box.set_max_children_per_line(5)
        self.overview_summary_box.set_column_spacing(8)
        self.overview_summary_box.set_row_spacing(8)
        summary_card.pack_start(self.overview_summary_box, False, False, 0)

        self.overview_restore_card = self.create_card("Restore Original", "Undo Linux Toolbox changes from one place.")
        main_tab.pack_start(self.overview_restore_card, False, False, 0)
        self.overview_restore_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.overview_restore_card.pack_start(self.overview_restore_grid, False, False, 0)
        self.overview_restore_buttons = {}
        for index, (key, title, tooltip, handler) in enumerate(
            (
                ("chrome", "Chrome", "Remove profile launchers and hover previews.", self.on_chrome_restore_original),
                ("mouse", "Mouse", "Restore original maccel mouse settings.", self.on_mouse_restore),
                ("clipboard", "Clipboard", "Restore original clipboard startup and shortcuts.", self.on_clipboard_restore_original),
            )
        ):
            button = Gtk.Button(label=title)
            button.set_tooltip_text(tooltip)
            button.connect("clicked", handler)
            self.overview_restore_grid.attach(button, index % 3, index // 3, 1, 1)
            self.overview_restore_buttons[key] = button

        self.compatibility_card = self.create_card("System Check", "Linux, GNOME, Chrome, and helper availability.")
        main_tab.pack_start(self.compatibility_card, False, False, 0)
        self.compatibility_label = Gtk.Label()
        self.compatibility_label.set_xalign(0)
        self.compatibility_label.set_line_wrap(True)
        self.compatibility_card.pack_start(self.compatibility_label, False, False, 0)

        status_card = self.create_card("Activity", "Recent app actions and status messages.")
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
        log_scroller.set_min_content_height(80)
        log_scroller.set_no_show_all(True)
        log_scroller.hide()
        log_scroller.add(self.log_view)
        status_card.pack_start(log_scroller, True, True, 8)

        chrome_intro = Gtk.Label()
        chrome_intro.set_markup("<span size='large'><b>Chrome Profiles</b></span>")
        chrome_intro.set_xalign(0)
        chrome_intro.set_line_wrap(True)
        chrome_intro.get_style_context().add_class("page-title")
        chrome_tab.pack_start(chrome_intro, False, False, 0)

        chrome_description = Gtk.Label(
            label="Install profile-specific launchers and add hover window previews."
        )
        chrome_description.set_xalign(0)
        chrome_description.set_line_wrap(True)
        chrome_description.get_style_context().add_class("page-description")
        chrome_tab.pack_start(chrome_description, False, False, 0)

        chrome_status_card = self.create_card("Status Check", "Browser profile dependencies and current dock state.")
        chrome_tab.pack_start(chrome_status_card, False, False, 0)
        self.chrome_status_pills = self.create_status_table(
            chrome_status_card,
            (
                ("browser", "Chrome/Chromium"),
                ("profiles", "Profiles found"),
                ("icons", "Profile dock icons"),
                ("hover", "Hover previews"),
            ),
        )

        feature_card = self.create_card("Setup Flow", "Turn on the behavior you want. Turning it off restores the default path.")
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
        self.chrome_restore_button = Gtk.Button(label="Restore Original")
        self.chrome_restore_button.set_no_show_all(True)
        self.chrome_restore_button.set_tooltip_text("Remove Linux Toolbox Chrome profile launchers and disable hover previews.")
        self.chrome_restore_button.connect("clicked", self.on_chrome_restore_original)
        feature_card.pack_start(self.chrome_restore_button, False, False, 0)

        setup_card = self.create_card("Manual Actions", "Regenerate or pin profile launchers when Chrome profiles change.")
        chrome_tab.pack_start(setup_card, False, False, 0)
        self.chrome_manual_actions_card = setup_card
        setup_card.set_no_show_all(True)
        setup_card.hide()

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

        chrome_restore_button = Gtk.Button(label="Restore Original")
        chrome_restore_button.set_tooltip_text("Remove Linux Toolbox Chrome profile launchers and disable hover previews.")
        chrome_restore_button.connect("clicked", self.on_chrome_restore_original)
        setup_grid.attach(chrome_restore_button, 0, 1, 3, 1)

        profile_card = self.create_card("Detected Profiles", "Chrome profiles found on this machine.")
        chrome_tab.pack_start(profile_card, True, True, 0)
        profile_card.set_no_show_all(True)
        profile_card.hide()

        self.profile_list = Gtk.ListBox()
        self.profile_list.set_selection_mode(Gtk.SelectionMode.NONE)
        profile_card.pack_start(self.profile_list, True, True, 0)

        mouse_intro = Gtk.Label()
        mouse_intro.set_markup("<span size='large'><b>Mouse</b></span>")
        mouse_intro.set_xalign(0)
        mouse_intro.set_line_wrap(True)
        mouse_intro.get_style_context().add_class("page-title")
        mouse_tab.pack_start(mouse_intro, False, False, 0)

        mouse_description = Gtk.Label(
            label="Tune pointer movement and acceleration presets for daily desktop use."
        )
        mouse_description.set_xalign(0)
        mouse_description.set_line_wrap(True)
        mouse_description.get_style_context().add_class("page-description")
        mouse_tab.pack_start(mouse_description, False, False, 0)

        mouse_card = self.create_card("Mouse Movement", "Make Linux mouse movement feel closer to Windows or macOS.")
        mouse_tab.pack_start(mouse_card, False, False, 0)

        self.mouse_status_pills = self.create_status_table(
            mouse_card,
            (
                ("platform", "Linux desktop"),
                ("pkexec", "Authentication helper"),
                ("maccel", "maccel backend"),
                ("permission", "Driver write permission"),
            ),
        )

        install_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mouse_card.pack_start(install_row, False, False, 0)

        self.mouse_backend_indicator = Gtk.Label()
        self.mouse_backend_indicator.set_xalign(0)
        self.mouse_backend_indicator.get_style_context().add_class("pill")
        install_row.pack_start(self.mouse_backend_indicator, True, True, 0)

        self.mouse_install_button = Gtk.Button(label="Install maccel")
        self.mouse_install_button.set_no_show_all(True)
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
        log_label.set_markup("<b>Install / Permission Log</b>")
        log_label.set_xalign(0)
        log_label.set_no_show_all(True)
        log_label.hide()
        self.mouse_log_label = log_label
        mouse_card.pack_start(log_label, False, False, 0)

        self.mouse_install_log_view = Gtk.TextView()
        self.mouse_install_log_view.set_editable(False)
        self.mouse_install_log_view.set_cursor_visible(False)
        self.mouse_install_log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.mouse_install_log_view.set_monospace(True)
        mouse_log_scroller = Gtk.ScrolledWindow()
        mouse_log_scroller.set_min_content_height(72)
        mouse_log_scroller.set_no_show_all(True)
        mouse_log_scroller.hide()
        mouse_log_scroller.add(self.mouse_install_log_view)
        self.mouse_log_scroller = mouse_log_scroller
        mouse_card.pack_start(mouse_log_scroller, True, True, 0)

        mouse_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.mouse_preset_grid = mouse_grid
        mouse_card.pack_start(mouse_grid, False, False, 0)

        self.mouse_windows_button = self.create_primary_button("Windows", "Apply the Windows-like mouse movement preset.")
        self.mouse_windows_button.connect("clicked", self.on_mouse_windows)
        mouse_grid.attach(self.mouse_windows_button, 0, 0, 1, 1)

        self.mouse_macos_button = self.create_primary_button("macOS", "Apply the macOS-like mouse movement preset.")
        self.mouse_macos_button.connect("clicked", self.on_mouse_macos)
        mouse_grid.attach(self.mouse_macos_button, 1, 0, 1, 1)

        self.mouse_restore_button = Gtk.Button(label="Restore Original")
        self.mouse_restore_button.set_no_show_all(True)
        self.mouse_restore_button.set_tooltip_text("Restore the mouse settings saved before Linux Toolbox changed them.")
        self.mouse_restore_button.connect("clicked", self.on_mouse_restore)
        mouse_grid.attach(self.mouse_restore_button, 2, 0, 1, 1)

        custom_label = Gtk.Label()
        custom_label.set_markup("<b>Custom maccel SensMouse</b>")
        custom_label.set_xalign(0)
        self.mouse_custom_label = custom_label
        mouse_card.pack_start(custom_label, False, False, 0)

        custom_hint = Gtk.Label(
            label="Set a custom mouse sensitivity multiplier (Sens-Mult). 1.0 is the maccel default."
        )
        custom_hint.set_xalign(0)
        custom_hint.set_line_wrap(True)
        custom_hint.set_no_show_all(True)
        custom_hint.hide()
        mouse_card.pack_start(custom_hint, False, False, 0)

        custom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.mouse_custom_row = custom_row
        mouse_card.pack_start(custom_row, False, False, 0)

        sens_caption = Gtk.Label(label="Sensitivity multiplier")
        sens_caption.set_xalign(0)
        custom_row.pack_start(sens_caption, False, False, 0)

        # value, lower, upper, step, page, page_size
        sens_adjustment = Gtk.Adjustment(1.0, 0.01, 10.0, 0.05, 0.5, 0)
        self.mouse_custom_sens_spin = Gtk.SpinButton()
        self.mouse_custom_sens_spin.set_adjustment(sens_adjustment)
        self.mouse_custom_sens_spin.set_digits(2)
        self.mouse_custom_sens_spin.set_value(self.mouse_service.getLastCustomSensitivity())
        self.mouse_custom_sens_spin.set_tooltip_text("maccel Sens-Mult value to apply.")
        custom_row.pack_start(self.mouse_custom_sens_spin, False, False, 0)

        self.mouse_custom_sens_button = self.create_primary_button(
            "Custom maccel SensMouse", "Apply your custom maccel sensitivity multiplier."
        )
        self.mouse_custom_sens_button.connect("clicked", self.on_mouse_custom_sens)
        custom_row.pack_end(self.mouse_custom_sens_button, False, False, 0)

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

        extensions_intro = Gtk.Label()
        extensions_intro.set_markup("<span size='large'><b>Modules</b></span>")
        extensions_intro.set_xalign(0)
        extensions_intro.set_line_wrap(True)
        extensions_intro.get_style_context().add_class("page-title")
        extensions_tab.pack_start(extensions_intro, False, False, 0)

        extensions_description = Gtk.Label(
            label="Manage essential GNOME extensions as first-class Linux Toolbox modules. Install once, then configure each feature here."
        )
        extensions_description.set_xalign(0)
        extensions_description.set_line_wrap(True)
        extensions_description.get_style_context().add_class("page-description")
        extensions_tab.pack_start(extensions_description, False, False, 0)

        extensions_status_card = self.create_card(
            "Module status",
            "A module can be installed, enabled, and configured independently.",
        )
        extensions_tab.pack_start(extensions_status_card, False, False, 0)
        self.extension_status_pills = self.create_status_table(
            extensions_status_card,
            (
                ("installed", "Installed modules"),
                ("enabled", "Enabled modules"),
                ("configurable", "Configurable modules"),
            ),
        )

        self.extension_modules_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        extensions_tab.pack_start(self.extension_modules_box, False, False, 0)
        for module in EXTENSION_MODULES:
            module_state = self.create_extension_module_card(module)
            self.extension_modules[module["uuid"]] = module_state
            self.extension_modules_box.pack_start(module_state["card"], False, False, 0)

        clipboard_intro = Gtk.Label()
        clipboard_intro.set_markup("<span size='large'><b>Clipboard</b></span>")
        clipboard_intro.set_xalign(0)
        clipboard_intro.set_line_wrap(True)
        clipboard_intro.get_style_context().add_class("page-title")
        clipboard_tab.pack_start(clipboard_intro, False, False, 0)

        clipboard_description = Gtk.Label(label="Use CopyQ for a smooth community-tested Super+V clipboard history popup.")
        clipboard_description.set_xalign(0)
        clipboard_description.set_line_wrap(True)
        clipboard_description.get_style_context().add_class("page-description")
        clipboard_tab.pack_start(clipboard_description, False, False, 0)

        clipboard_card = self.create_card("Status Check", "CopyQ dependency and current shortcut state.")
        clipboard_tab.pack_start(clipboard_card, False, False, 0)
        self.clipboard_status_pills = self.create_status_table(
            clipboard_card,
            (
                ("copyq", "CopyQ"),
                ("running", "CopyQ running"),
                ("autostart", "Start at login"),
                ("shortcut", "Super+V shortcut"),
            ),
        )

        clipboard_setup_card = self.create_card("Setup Flow", "One switch installs and enables the complete clipboard history setup.")
        clipboard_tab.pack_start(clipboard_setup_card, False, False, 0)
        self.clipboard_master_switch = self.create_feature_switch(
            clipboard_setup_card,
            "Clipboard History",
            "Start CopyQ at login and bind Super+V to the history popup.",
            self.on_clipboard_master_toggled,
        )

        self.clipboard_autostart_check, self.clipboard_autostart_pill = self.create_feature_check(
            clipboard_setup_card,
            "Start CopyQ at login",
            "Launch CopyQ automatically when you log in, so clipboard history is always running.",
            self.on_clipboard_autostart_toggled,
        )
        self.clipboard_shortcut_check, self.clipboard_shortcut_pill = self.create_feature_check(
            clipboard_setup_card,
            "Super+V opens clipboard history",
            "Bind Super+V to the CopyQ history popup. Frees Super+V from GNOME's notification tray so it works every time.",
            self.on_clipboard_shortcut_toggled,
        )
        for widget in (self.clipboard_autostart_check, self.clipboard_shortcut_check):
            row = getattr(widget, "ltb_row", None)
            if row is not None:
                row.set_no_show_all(True)
                row.hide()

        clipboard_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        clipboard_actions.set_margin_top(6)
        clipboard_setup_card.pack_start(clipboard_actions, False, False, 0)

        self.clipboard_clear_button = Gtk.Button(label="Clear Clipboard")
        self.clipboard_clear_button.set_no_show_all(True)
        self.clipboard_clear_button.set_tooltip_text("Erase CopyQ history and the current system clipboard.")
        self.clipboard_clear_button.connect("clicked", self.on_clipboard_clear)
        clipboard_actions.pack_start(self.clipboard_clear_button, False, False, 0)

        self.clipboard_repair_button = Gtk.Button(label="Repair Clipboard")
        self.clipboard_repair_button.set_no_show_all(True)
        self.clipboard_repair_button.set_tooltip_text("Recreate the CopyQ startup file, scripts, and Super+V shortcut.")
        self.clipboard_repair_button.connect("clicked", self.on_clipboard_repair_startup)
        clipboard_actions.pack_start(self.clipboard_repair_button, False, False, 0)

        self.clipboard_restore_button = Gtk.Button(label="Restore Original")
        self.clipboard_restore_button.set_no_show_all(True)
        self.clipboard_restore_button.set_tooltip_text("Turn off Linux Toolbox clipboard startup and restore GNOME's Super+V binding.")
        self.clipboard_restore_button.connect("clicked", self.on_clipboard_restore_original)
        clipboard_actions.pack_start(self.clipboard_restore_button, False, False, 0)

        self.clipboard_status_label = Gtk.Label()
        self.clipboard_status_label.set_xalign(0)
        self.clipboard_status_label.set_line_wrap(True)
        self.clipboard_status_label.get_style_context().add_class("section-subtitle")
        clipboard_setup_card.pack_start(self.clipboard_status_label, False, False, 0)

        self.refresh_compatibility()
        self.refresh_profiles()
        self.refresh_feature_state()
        self.refresh_mouse_movement_state()
        self.refresh_extension_modules()
        self.refresh_overview_summary()
        self.stack.set_visible_child_name("overview")
        self.nav_list.select_row(self.nav_list.get_row_at_index(0))
        GLib.idle_add(self.ensure_startup_features_once)

    def load_css(self):
        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(load_text("app.css").encode("utf-8"))
            screen = Gdk.Screen.get_default()
            if screen is not None:
                Gtk.StyleContext.add_provider_for_screen(
                    screen,
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_USER,
                )
        except Exception:
            pass

    def create_tab_page(self):
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.get_style_context().add_class("content-page")
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(16)
        page.set_size_request(720, -1)
        scroller.add(page)
        return scroller, page

    def create_card(self, title, subtitle=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(10)
        box.get_style_context().add_class("card")

        label = Gtk.Label()
        label.set_text(title)
        label.set_xalign(0)
        label.get_style_context().add_class("section-title")
        box.pack_start(label, False, False, 0)
        if subtitle:
            subtitle_label = Gtk.Label(label=subtitle)
            subtitle_label.set_xalign(0)
            subtitle_label.set_line_wrap(True)
            subtitle_label.get_style_context().add_class("section-subtitle")
            box.pack_start(subtitle_label, False, False, 0)
        return box

    def create_status_table(self, parent, rows):
        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        grid.get_style_context().add_class("data-grid")
        values = {}
        for row_index, (key, label_text) in enumerate(rows):
            label = Gtk.Label(label=label_text)
            label.set_xalign(0)
            label.set_halign(Gtk.Align.START)
            grid.attach(label, 0, row_index, 1, 1)
            pill = self.make_pill("Unknown", "warn")
            grid.attach(pill, 1, row_index, 1, 1)
            values[key] = pill
        parent.pack_start(grid, False, False, 0)
        return values

    def make_pill(self, text, level):
        label = Gtk.Label(label=text)
        label.set_xalign(0.5)
        label.set_halign(Gtk.Align.START)
        label.set_valign(Gtk.Align.CENTER)
        context = label.get_style_context()
        context.add_class("pill")
        context.add_class(f"pill-{level}")
        return label

    def create_nav_row(self, stack_name, title, icon_name):
        row = Gtk.ListBoxRow()
        row.stack_name = stack_name
        row.get_style_context().add_class("nav-row")
        container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        container.get_style_context().add_class("nav-row-box")
        accent = Gtk.Box()
        accent.set_size_request(4, 1)
        accent.get_style_context().add_class("nav-accent")
        container.pack_start(accent, False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        content.set_margin_left(12)
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
        content.pack_start(icon, False, False, 0)
        label = Gtk.Label(label=title)
        label.set_xalign(0)
        label.get_style_context().add_class("nav-label")
        content.pack_start(label, True, True, 0)
        container.pack_start(content, True, True, 0)
        row.add(container)
        return row

    def on_nav_row_selected(self, _listbox, row):
        if row is None or self.syncing_sidebar:
            return
        self.stack.set_visible_child_name(row.stack_name)

    def on_stack_visible_child_changed(self, stack, _param):
        if not hasattr(self, "nav_list"):
            return
        visible = stack.get_visible_child_name()
        self.syncing_sidebar = True
        try:
            for row in self.nav_list.get_children():
                if getattr(row, "stack_name", None) == visible:
                    self.nav_list.select_row(row)
                    break
        finally:
            self.syncing_sidebar = False

    def create_primary_button(self, title, tooltip):
        button = Gtk.Button(label=title)
        button.set_no_show_all(True)
        button.set_tooltip_text(tooltip)
        button.set_hexpand(True)
        button.get_style_context().add_class("suggested-action")
        return button


    def create_feature_switch(self, parent, title, detail, callback):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_margin_top(0)
        row.set_margin_bottom(0)

        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
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
        switch.ltb_row = row

        row.pack_start(copy, True, True, 0)
        row.pack_end(switch, False, False, 0)
        parent.pack_start(row, False, False, 0)
        return switch

    def create_feature_check(self, parent, title, detail, callback):
        """A labeled checkbox row with a trailing status pill.

        Returns (check_button, pill_label). The check emits `toggled`; handlers
        should guard against programmatic updates using self.syncing_features.
        """
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_margin_top(0)
        row.set_margin_bottom(0)

        check = Gtk.CheckButton()
        check.set_valign(Gtk.Align.START)

        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        label = Gtk.Label()
        label.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
        label.set_xalign(0)
        description = Gtk.Label(label=detail)
        description.set_xalign(0)
        description.set_line_wrap(True)
        description.get_style_context().add_class("section-subtitle")
        copy.pack_start(label, False, False, 0)
        copy.pack_start(description, False, False, 0)

        pill = self.make_pill("Off", "warn")
        pill.set_valign(Gtk.Align.CENTER)

        check.connect("toggled", callback)
        check.ltb_row = row
        pill.ltb_row = row
        row.pack_start(check, False, False, 0)
        row.pack_start(copy, True, True, 0)
        row.pack_end(pill, False, False, 0)
        parent.pack_start(row, False, False, 0)
        return check, pill

    def create_extension_module_card(self, module):
        """Create one self-contained extension module.

        The card deliberately keeps installation, enablement, and settings in
        the same place. This makes an extension behave like Clipboard or Mouse
        instead of leaving the user with an install-only action.
        """
        uuid = module["uuid"]
        card = self.create_card(module["name"], module["description"])
        card.get_style_context().add_class("module-card")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.set_margin_top(4)
        status_pill = self.make_pill("Not installed", "warn")
        header.pack_start(status_pill, False, False, 0)

        enabled_switch = Gtk.Switch()
        enabled_switch.set_valign(Gtk.Align.CENTER)
        enabled_switch.set_tooltip_text("Enable or disable this module without uninstalling it.")
        enabled_switch.connect("state-set", self.on_extension_toggled, uuid)
        header.pack_end(enabled_switch, False, False, 0)
        card.pack_start(header, False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        install_button = self.create_primary_button(
            "Install module",
            "Download this GNOME extension and make its settings available here.",
        )
        install_button.set_hexpand(False)
        install_button.connect("clicked", self.on_install_extension_clicked, uuid, module["name"])
        actions.pack_start(install_button, False, False, 0)

        preferences_button = Gtk.Button(label="Open full preferences")
        preferences_button.set_no_show_all(True)
        preferences_button.set_tooltip_text("Open the extension's complete GNOME preferences window.")
        preferences_button.get_style_context().add_class("secondary-action")
        preferences_button.connect("clicked", self.on_extension_open_preferences, uuid)
        actions.pack_start(preferences_button, False, False, 0)

        reset_button = Gtk.Button(label="Reset featured settings")
        reset_button.set_no_show_all(True)
        reset_button.set_tooltip_text("Restore the featured settings in this module to their defaults.")
        reset_button.get_style_context().add_class("secondary-action")
        reset_button.connect("clicked", self.on_extension_reset_settings, uuid)
        actions.pack_start(reset_button, False, False, 0)
        card.pack_start(actions, False, False, 0)

        configuration = Gtk.Expander(label="Configure in Linux Toolbox")
        configuration.set_expanded(True)
        configuration.set_no_show_all(True)
        configuration_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        configuration_box.set_margin_top(8)
        configuration.add(configuration_box)
        card.pack_start(configuration, False, False, 0)

        return {
            "definition": module,
            "uuid": uuid,
            "card": card,
            "status": status_pill,
            "enabled_switch": enabled_switch,
            "install_button": install_button,
            "preferences_button": preferences_button,
            "reset_button": reset_button,
            "configuration": configuration,
            "configuration_box": configuration_box,
            "settings": None,
            "schema": None,
            "setting_widgets": {},
        }

    def create_extension_setting_row(self, state, settings, key_name, schema_key):
        """Create a compact editor for a supported GSettings key."""
        type_string = schema_key.get_value_type().dup_string()
        current = settings.get_value(key_name).unpack()
        summary = schema_key.get_summary() or self.extension_setting_label(key_name)
        description = schema_key.get_description() or ""

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title = Gtk.Label(label=summary)
        title.set_xalign(0)
        title.set_line_wrap(True)
        copy.pack_start(title, False, False, 0)
        if description and description != summary:
            detail = Gtk.Label(label=description)
            detail.set_xalign(0)
            detail.set_line_wrap(True)
            detail.get_style_context().add_class("section-subtitle")
            copy.pack_start(detail, False, False, 0)
        row.pack_start(copy, True, True, 0)

        editor = self.create_extension_setting_editor(
            state,
            settings,
            key_name,
            schema_key,
            type_string,
            current,
        )
        if editor is None:
            return None
        row.pack_end(editor, False, False, 0)
        return row

    def create_extension_setting_editor(self, state, settings, key_name, schema_key, type_string, current):
        uuid = state["uuid"]
        if type_string == "b":
            switch = Gtk.Switch()
            switch.set_valign(Gtk.Align.CENTER)
            switch.set_active(bool(current))
            switch.connect("state-set", self.on_extension_boolean_setting_changed, uuid, key_name)
            state["setting_widgets"][key_name] = switch
            return switch

        choices = self.extension_setting_choices(schema_key)
        if type_string == "s" and choices:
            combo = Gtk.ComboBoxText()
            for choice in choices:
                combo.append(choice, self.extension_setting_label(choice))
            combo.set_active_id(str(current))
            combo.set_valign(Gtk.Align.CENTER)
            combo.connect("changed", self.on_extension_combo_setting_changed, uuid, key_name)
            state["setting_widgets"][key_name] = combo
            return combo

        if type_string in {"i", "u", "x", "t", "d"}:
            lower, upper, digits = self.extension_numeric_bounds(key_name, type_string)
            adjustment = Gtk.Adjustment(float(current), lower, upper, 1 if digits == 0 else 0.05, 10, 0)
            spin = Gtk.SpinButton.new(adjustment, 1 if digits == 0 else 0.05, digits)
            spin.set_numeric(True)
            spin.set_valign(Gtk.Align.CENTER)
            spin.connect("value-changed", self.on_extension_numeric_setting_changed, uuid, key_name, type_string)
            state["setting_widgets"][key_name] = spin
            return spin

        if type_string in {"s", "as"}:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            entry = Gtk.Entry()
            entry.set_width_chars(16)
            entry.set_text(self.extension_setting_text(current))
            entry.set_tooltip_text("Press Enter or Apply to save this value.")
            entry.connect("activate", self.on_extension_entry_setting_changed, uuid, key_name, type_string)
            apply_button = Gtk.Button(label="Apply")
            apply_button.connect("clicked", self.on_extension_entry_setting_changed, uuid, key_name, type_string, entry)
            row.pack_start(entry, True, True, 0)
            row.pack_start(apply_button, False, False, 0)
            state["setting_widgets"][key_name] = entry
            return row

        return None

    def extension_setting_label(self, value):
        text = str(value).replace("_", " ").replace("-", " ")
        return " ".join(part.capitalize() for part in text.split())

    def extension_setting_text(self, value):
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)
        return str(value)

    def extension_setting_choices(self, schema_key):
        try:
            setting_range = schema_key.get_range()
            if isinstance(setting_range, tuple) and len(setting_range) == 2 and setting_range[0] == "enum":
                return [str(value) for value in setting_range[1].unpack()]
        except Exception:
            pass
        return []

    def extension_setting_type_supported(self, type_string):
        return type_string in {"b", "i", "u", "x", "t", "d", "s", "as"}

    def extension_numeric_bounds(self, key_name, type_string):
        if type_string == "d":
            if "opacity" in key_name:
                return 0.0, 1.0, 2
            return -10000.0, 10000.0, 2
        if type_string in {"u", "t"}:
            lower = 0.0
        else:
            lower = 0.0 if any(word in key_name for word in ("size", "width", "height", "padding", "margin", "delay", "time", "radius")) else -100000.0
        upper = 10000.0
        if "opacity" in key_name:
            upper = 100.0
        return lower, upper, 0

    def set_extension_setting_value(self, uuid, key_name, type_string, value):
        state = self.extension_modules.get(uuid)
        if not state or state.get("settings") is None:
            raise RuntimeError("The module settings are not available.")
        settings = state["settings"]
        if type_string == "b":
            value = bool(value)
        elif type_string in {"i", "u", "x", "t"}:
            value = int(value)
        elif type_string == "d":
            value = float(value)
        elif type_string == "s":
            value = str(value)
        elif type_string == "as":
            value = [item.strip() for item in str(value).split(",") if item.strip()]
        else:
            raise RuntimeError(f"Unsupported setting type: {type_string}")
        settings.set_value(key_name, GLib.Variant(type_string, value))
        self.log(f"{state['definition']['name']}: {self.extension_setting_label(key_name)} updated.")

    def on_extension_boolean_setting_changed(self, _switch, state, uuid, key_name):
        if self.syncing_extensions:
            return False
        try:
            self.set_extension_setting_value(uuid, key_name, "b", state)
        except Exception as error:
            self.log(f"Could not update extension setting: {error}")
            self.refresh_extension_modules()
        return True

    def on_extension_combo_setting_changed(self, combo, uuid, key_name):
        if self.syncing_extensions:
            return
        value = combo.get_active_id()
        if value is None:
            return
        try:
            self.set_extension_setting_value(uuid, key_name, "s", value)
        except Exception as error:
            self.log(f"Could not update extension setting: {error}")
            self.refresh_extension_modules()

    def on_extension_numeric_setting_changed(self, spin, uuid, key_name, type_string):
        if self.syncing_extensions:
            return
        try:
            value = spin.get_value() if type_string == "d" else spin.get_value_as_int()
            self.set_extension_setting_value(uuid, key_name, type_string, value)
        except Exception as error:
            self.log(f"Could not update extension setting: {error}")
            self.refresh_extension_modules()

    def on_extension_entry_setting_changed(self, widget, uuid, key_name, type_string, entry=None):
        if self.syncing_extensions:
            return
        actual_entry = entry if entry is not None else widget
        try:
            self.set_extension_setting_value(uuid, key_name, type_string, actual_entry.get_text())
        except Exception as error:
            self.log(f"Could not update extension setting: {error}")

    def on_extension_toggled(self, switch, enabled, uuid):
        if self.syncing_extensions:
            return False
        state = self.extension_modules.get(uuid)
        if not state or not self.extension_installed(uuid):
            switch.set_state(False)
            self.log("Install this module before enabling it.")
            return True
        try:
            self.set_gnome_extension_enabled(uuid, enabled)
            self.log(f"{state['definition']['name']} {'enabled' if enabled else 'disabled'}.")
            switch.set_state(enabled)
        except Exception as error:
            self.log(f"Failed to update {state['definition']['name']}: {error}")
            switch.set_state(not enabled)
        self.refresh_extension_modules()
        return True

    def on_extension_reset_settings(self, _button, uuid):
        state = self.extension_modules.get(uuid)
        if not state or state.get("settings") is None:
            return
        try:
            for key_name in state["definition"]["settings"]:
                if state["schema"].get_key(key_name) is not None:
                    state["settings"].reset(key_name)
            self.log(f"{state['definition']['name']} module settings restored to defaults.")
        except Exception as error:
            self.log(f"Could not reset module settings: {error}")
        self.refresh_extension_modules()

    def on_extension_open_preferences(self, _button, uuid):
        if shutil.which("gnome-extensions") is None:
            self.log("gnome-extensions is not available on this system.")
            return
        try:
            subprocess.Popen(
                ["gnome-extensions", "prefs", uuid],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self.log("Opened the full GNOME preferences window.")
        except Exception as error:
            self.log(f"Could not open extension preferences: {error}")

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
        self.refresh_overview_summary()
        return browser_id

    def refresh_feature_state(self):
        self.syncing_features = True
        profile_enabled = self.profile_feature_enabled()
        hover_enabled = self.hover_feature_enabled()
        self.profile_switch.set_active(profile_enabled)
        self.hover_switch.set_active(hover_enabled)
        if hasattr(self, "clipboard_autostart_check"):
            self.clipboard_autostart_check.set_active(self.clipboard_autostart_active())
            self.clipboard_shortcut_check.set_active(self.clipboard_shortcut_active())
        if hasattr(self, "clipboard_master_switch"):
            self.clipboard_master_switch.set_active(self.clipboard_feature_enabled())
        self.syncing_features = False
        if hasattr(self, "chrome_status_pills"):
            config_dir, _browser_id = detect_chrome_config()
            browser_available = any(
                shutil.which(binary)
                for binary in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
            )
            profiles_found = len(self.profiles)
            self.profile_switch.set_sensitive(bool(profiles_found and browser_available))
            self.set_pill(
                self.chrome_status_pills["browser"],
                "installed" if browser_available else "missing",
                "ok" if browser_available else "err",
            )
            self.set_pill(
                self.chrome_status_pills["profiles"],
                str(profiles_found) if profiles_found else ("not found" if config_dir.exists() else "no config"),
                "ok" if profiles_found else "warn",
            )
            self.set_pill(
                self.chrome_status_pills["icons"],
                "on" if profile_enabled else "off",
                "ok" if profile_enabled else "warn",
            )
            self.set_pill(
                self.chrome_status_pills["hover"],
                "on" if hover_enabled else "off",
                "ok" if hover_enabled else "warn",
            )
        if hasattr(self, "chrome_restore_button"):
            self.chrome_restore_button.set_visible(False)
        self.refresh_clipboard_state()
        self.refresh_overview_summary()

    def refresh_clipboard_state(self):
        if not hasattr(self, "clipboard_status_label"):
            return
        copyq_available = shutil.which("copyq") is not None
        autostart_active = self.clipboard_autostart_active()
        shortcut_active = self.clipboard_shortcut_active()
        running = self._copyq_running()

        if hasattr(self, "clipboard_autostart_pill"):
            self.set_pill(self.clipboard_autostart_pill, "On" if autostart_active else "Off", "ok" if autostart_active else "warn")
            self.set_pill(self.clipboard_shortcut_pill, "On" if shortcut_active else "Off", "ok" if shortcut_active else "warn")
        if hasattr(self, "clipboard_status_pills"):
            self.set_pill(self.clipboard_status_pills["copyq"], "installed" if copyq_available else "missing", "ok" if copyq_available else "err")
            self.set_pill(self.clipboard_status_pills["running"], "running" if running else "stopped", "ok" if running else "warn")
            self.set_pill(self.clipboard_status_pills["autostart"], "on" if autostart_active else "off", "ok" if autostart_active else "warn")
            self.set_pill(self.clipboard_status_pills["shortcut"], "on" if shortcut_active else "off", "ok" if shortcut_active else "warn")

        # Controls depend on CopyQ being installed.
        for widget in ("clipboard_autostart_check", "clipboard_shortcut_check", "clipboard_clear_button", "clipboard_repair_button", "clipboard_restore_button"):
            if hasattr(self, widget):
                getattr(self, widget).set_sensitive(copyq_available)
        if hasattr(self, "clipboard_clear_button"):
            self.clipboard_clear_button.set_sensitive(copyq_available and running)
            self.clipboard_clear_button.set_visible(False)
        if hasattr(self, "clipboard_repair_button"):
            self.clipboard_repair_button.set_visible(False)
        if hasattr(self, "clipboard_restore_button"):
            restore_needed = (
                autostart_active
                or shortcut_active
                or self.clipboard_autostart_saved()
                or self.clipboard_shortcut_saved()
                or COPYQ_START.exists()
                or COPYQ_SHORTCUT.exists()
                or COPYQ_CLEAR.exists()
            )
            self.clipboard_restore_button.set_sensitive(restore_needed)
            self.clipboard_restore_button.set_visible(False)

        lines = [
            f"CopyQ: {'installed' if copyq_available else 'not installed — toggle a setting to install'}",
            f"Running now: {'yes' if running else 'no'}",
            f"Start at login: {'on' if autostart_active else 'off'}",
            f"Super+V popup: {'on' if shortcut_active else 'off'}",
        ]
        self.clipboard_status_label.set_text("\n".join(lines))
        self.refresh_overview_summary()

    def refresh_overview_summary(self):
        if not hasattr(self, "overview_summary_box"):
            return
        for child in self.overview_summary_box.get_children():
            child.destroy()

        try:
            chrome_ready = self.profile_feature_enabled()
        except Exception:
            chrome_ready = False
        try:
            hover_ready = self.hover_feature_enabled()
        except Exception:
            hover_ready = False
        try:
            mouse_installed = self.mouse_service.isMaccelInstalled()
            mouse_detected = self.mouse_service.getDetectedPresetState()
        except Exception:
            mouse_installed = False
            mouse_detected = "unknown"
        try:
            clipboard_ready = self.clipboard_feature_enabled()
        except Exception:
            clipboard_ready = False
        try:
            style_action = run(["gsettings", "get", DASH_TO_DOCK_SCHEMA, "click-action"], check=False).strip("'")
        except Exception:
            style_action = "unknown"
        try:
            dock_layout = self.dock_layout_label()
        except Exception:
            dock_layout = "Unavailable"
        try:
            module_summary = self.extension_module_summary()
            module_level = "ok" if module_summary.startswith(str(len(self.extension_modules)) + "/") else "warn"
        except Exception:
            module_summary = "Unavailable"
            module_level = "warn"

        pills = [
            ("Chrome Profiles: On" if chrome_ready else "Chrome Profiles: Setup", "ok" if chrome_ready else "warn"),
            ("Hover Previews: On" if hover_ready else "Hover Previews: Off", "ok" if hover_ready else "warn"),
            (
                f"Mouse: {self.mouse_preset_label(mouse_detected)}" if mouse_installed else "Mouse: maccel missing",
                "ok" if mouse_installed and mouse_detected not in {"unknown", "default_ubuntu"} else ("warn" if mouse_installed else "err"),
            ),
            ("Clipboard: On" if clipboard_ready else "Clipboard: Off", "ok" if clipboard_ready else "warn"),
            (f"Modules: {module_summary}", module_level),
        ]
        for text, level in pills:
            self.overview_summary_box.add(self.make_pill(text, level))
        self.overview_summary_box.show_all()
        self.refresh_overview_restore_actions()

    def refresh_overview_restore_actions(self):
        if not hasattr(self, "overview_restore_buttons"):
            return

        try:
            chrome_needed = self.profile_feature_enabled() or self.hover_feature_enabled()
        except Exception:
            chrome_needed = False

        mouse_needed = MOUSE_ORIGINAL_BACKUP_PATH.exists()
        mouse_ready = mouse_needed and self.mouse_service.isMaccelInstalled()

        try:
            clipboard_needed = (
                self.clipboard_autostart_active()
                or self.clipboard_shortcut_active()
                or self.clipboard_autostart_saved()
                or self.clipboard_shortcut_saved()
                or COPYQ_START.exists()
                or COPYQ_SHORTCUT.exists()
                or COPYQ_CLEAR.exists()
            )
        except Exception:
            clipboard_needed = False

        states = {
            "chrome": (chrome_needed, chrome_needed),
            "mouse": (mouse_needed, mouse_ready),
            "clipboard": (clipboard_needed, clipboard_needed),
        }
        for key, (visible, sensitive) in states.items():
            button = self.overview_restore_buttons[key]
            button.set_visible(True)
            button.set_sensitive(sensitive)
        self.overview_restore_card.set_visible(True)


    def refresh_mouse_movement_state(self):
        env = self.mouse_service.getEnvironment()
        supported = self.mouse_service.isSupportedPlatform()
        maccel_available = supported and self.mouse_service.isMaccelInstalled()
        install_status = self.mouse_service.getInstallStatus()
        install_running = self.mouse_install_process is not None and self.mouse_install_process.poll() is None
        fix_running = (
            self.mouse_permission_fix_process is not None
            and self.mouse_permission_fix_process.poll() is None
        )
        if hasattr(self, "mouse_log_label"):
            self.mouse_log_label.set_visible(install_running or fix_running)
        if hasattr(self, "mouse_log_scroller"):
            self.mouse_log_scroller.set_visible(install_running or fix_running)
        if hasattr(self, "mouse_status_pills"):
            self.set_pill(
                self.mouse_status_pills["platform"],
                env["sessionType"],
                "ok" if supported else "err",
            )
            self.set_pill(
                self.mouse_status_pills["pkexec"],
                "available" if install_status["pkexecAvailable"] else "missing",
                "ok" if install_status["pkexecAvailable"] else "err",
            )
            self.set_pill(
                self.mouse_status_pills["maccel"],
                "installed" if maccel_available else "missing",
                "ok" if maccel_available else "err",
            )
            permission_ready = False
            permission_label = "not checked"
            if maccel_available:
                try:
                    permission_status = self.mouse_service.getPermissionStatus()
                    permission_ready = permission_status.sensMultWritable
                    permission_label = "ready" if permission_ready else "needs fix"
                except Exception:
                    permission_label = "unknown"
            self.set_pill(
                self.mouse_status_pills["permission"],
                permission_label,
                "ok" if permission_ready else ("warn" if maccel_available else "err"),
            )
        self.mouse_windows_button.set_sensitive(maccel_available and not fix_running)
        self.mouse_macos_button.set_sensitive(maccel_available and not fix_running)
        self.mouse_restore_button.set_sensitive(
            maccel_available and MOUSE_ORIGINAL_BACKUP_PATH.exists() and not fix_running
        )
        self.mouse_windows_button.set_visible(maccel_available)
        self.mouse_macos_button.set_visible(maccel_available)
        self.mouse_restore_button.set_visible(False)
        if hasattr(self, "mouse_custom_sens_button"):
            self.mouse_custom_sens_button.set_sensitive(maccel_available and not fix_running)
            self.mouse_custom_sens_spin.set_sensitive(maccel_available and not fix_running)
            self.mouse_custom_sens_button.set_visible(maccel_available)
            self.mouse_custom_label.set_visible(maccel_available)
            self.mouse_custom_row.set_visible(maccel_available)
        self.mouse_install_button.set_sensitive(
            supported and not maccel_available and install_status["pkexecAvailable"] and not install_running
        )
        self.mouse_install_button.set_visible(supported and not maccel_available)
        self.mouse_install_progress.set_visible(install_running)
        if install_running:
            self.mouse_install_progress.set_text("Installing maccel...")
            self.mouse_install_progress.set_show_text(True)
        else:
            self.mouse_install_progress.set_fraction(0)
            self.mouse_install_progress.set_show_text(False)

        if maccel_available:
            self.mouse_backend_indicator.set_markup("<b>[V] maccel installed</b>")
            self.set_widget_level(self.mouse_backend_indicator, "ok")
        else:
            self.mouse_backend_indicator.set_markup("<b>[X] maccel not installed</b>")
            self.set_widget_level(self.mouse_backend_indicator, "err")

        if maccel_available:
            self.mouse_backend_label.set_text("Backend: maccel detected")
        else:
            self.mouse_backend_label.set_text(
                "Backend: maccel not installed\nThis feature requires the open-source maccel backend."
            )

        install_lines = []
        if install_running:
            install_lines.append("maccel install is running.")
            latest_line = self.latest_mouse_install_log_line()
            if latest_line:
                install_lines.append(f"Progress: {latest_line}")
        elif install_status["maccelInstalled"]:
            install_lines.append("maccel is installed.")
        elif not install_status["pkexecAvailable"]:
            install_lines.append("pkexec is missing. Install maccel manually.")
        else:
            install_lines.append("Ready to install maccel.")

        if install_status["missingCommands"]:
            install_lines.append("Missing tools: " + ", ".join(install_status["missingCommands"]))

        if not install_status["kernelHeadersInstalled"]:
            install_lines.append(f"Kernel headers will install for {install_status['kernelRelease']}.")
        self.mouse_install_label.set_text("\n".join(install_lines))
        self.refresh_mouse_install_log_view()

        active = self.mouse_service.getCurrentPresetState()
        detected = self.mouse_service.getDetectedPresetState()
        active_label = self.mouse_preset_label(active, saved=True)
        detected_label = self.mouse_preset_label(detected, saved=False)
        if active == "custom":
            try:
                active_label = f"Custom SensMouse ({self.mouse_service.getLastCustomSensitivity():g})"
            except Exception:
                pass
        self.mouse_active_label.set_text(f"Saved preset: {active_label}\nDetected now: {detected_label}")

        warning_lines = []
        if env["sessionType"] == "wayland":
            warning_lines.append("Wayland support may depend on compositor behavior.")
        elif not supported:
            warning_lines.append("Mouse Movement is only supported on Linux.")
        if maccel_available:
            try:
                permission_status = self.mouse_service.getPermissionStatus()
                if not permission_status.sensMultWritable:
                    warning_lines.append(permission_status.message)
            except Exception:
                pass
        self.mouse_warning_label.set_text("\n".join(warning_lines))
        self.refresh_overview_summary()

    def set_widget_level(self, widget, level):
        context = widget.get_style_context()
        for class_name in ("pill-ok", "pill-warn", "pill-err"):
            context.remove_class(class_name)
        context.add_class(f"pill-{level}")

    def set_pill(self, pill, text, level):
        pill.set_text(text)
        self.set_widget_level(pill, level)

    def mouse_preset_label(self, preset, saved=False):
        labels = {
            "windows": "Windows",
            "macos": "macOS-like",
            "custom": "Custom SensMouse",
            "previous": "Previous",
            "original": "Original restored",
            "default_ubuntu": "Default Ubuntu",
            "unknown": "Unknown",
        }
        fallback = "Not set yet" if saved else "Unknown"
        return labels.get(preset, fallback)

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

    def dash_to_dock_available(self):
        schemas = run(["gsettings", "list-schemas"], check=False).splitlines()
        return DASH_TO_DOCK_SCHEMA in schemas

    def read_dock_layout_settings(self):
        if not self.dash_to_dock_available():
            raise RuntimeError("Dash-to-Dock settings are not available on this system.")
        settings = {}
        for key in DOCK_LAYOUT_KEYS:
            value = run(["gsettings", "get", DASH_TO_DOCK_SCHEMA, key], check=False).strip()
            if not value:
                raise RuntimeError(f"Could not read Dash-to-Dock setting: {key}")
            settings[key] = value
        return settings

    def set_dock_layout_setting(self, key, value):
        run(["gsettings", "set", DASH_TO_DOCK_SCHEMA, key, normalize_gsettings_value(value)])

    def apply_dock_layout_settings(self, settings):
        if not self.dash_to_dock_available():
            raise RuntimeError("Dash-to-Dock settings are not available on this system.")
        for key, value in settings.items():
            self.set_dock_layout_setting(key, value)

    def dock_layout_is_windows_taskbar(self, settings):
        return all(
            normalize_gsettings_value(settings.get(key, "")) == normalize_gsettings_value(value)
            for key, value in WINDOWS_DOCK_PRESET.items()
        )

    def dock_layout_is_default(self, settings):
        return all(
            normalize_gsettings_value(settings.get(key, "")) == normalize_gsettings_value(value)
            for key, value in DEFAULT_DOCK_PRESET.items()
        )

    def dock_layout_label(self):
        try:
            settings = self.read_dock_layout_settings()
        except Exception:
            return "Unavailable"
        if self.dock_layout_is_windows_taskbar(settings):
            return "Windows taskbar"
        if self.dock_layout_is_default(settings):
            return "Ubuntu default"
        return "Custom"

    def dock_layout_restore_available(self):
        state = load_app_config().get("dockLayout")
        return isinstance(state, dict) and (
            isinstance(state.get("originalSettings"), dict) or isinstance(state.get("previousSettings"), dict)
        )

    def save_dock_layout_restore_point(self, previous_settings, active_preset):
        config = load_app_config()
        existing = config.get("dockLayout")
        original_settings = (
            existing.get("originalSettings")
            if isinstance(existing, dict) and isinstance(existing.get("originalSettings"), dict)
            else previous_settings
        )
        config["dockLayout"] = {
            "activePreset": active_preset,
            "originalSettings": original_settings,
            "previousSettings": previous_settings,
            "savedAt": datetime.now(timezone.utc).isoformat(),
        }
        save_app_config(config)

    def clear_dock_layout_active_preset(self):
        config = load_app_config()
        state = config.get("dockLayout")
        if not isinstance(state, dict):
            return
        state["activePreset"] = "restored"
        config["dockLayout"] = state
        save_app_config(config)

    def read_dock_style_settings(self):
        if not self.dash_to_dock_available():
            raise RuntimeError("Dash-to-Dock settings are not available on this system.")
        keys = ("click-action", "middle-click-action", "activate-single-window")
        settings = {}
        for key in keys:
            value = run(["gsettings", "get", DASH_TO_DOCK_SCHEMA, key], check=False).strip()
            if value:
                settings[key] = value
        if "click-action" not in settings:
            raise RuntimeError("Could not read current dock click style.")
        return settings

    def apply_dock_style_settings(self, settings):
        if not self.dash_to_dock_available():
            raise RuntimeError("Dash-to-Dock settings are not available on this system.")
        for key, value in settings.items():
            run(["gsettings", "set", DASH_TO_DOCK_SCHEMA, key, normalize_gsettings_value(value)])

    def save_dock_style_restore_point(self, previous_settings, active_action):
        config = load_app_config()
        existing = config.get("dockStyle")
        original_settings = (
            existing.get("originalSettings")
            if isinstance(existing, dict) and isinstance(existing.get("originalSettings"), dict)
            else previous_settings
        )
        config["dockStyle"] = {
            "activeAction": active_action,
            "originalSettings": original_settings,
            "previousSettings": previous_settings,
            "savedAt": datetime.now(timezone.utc).isoformat(),
        }
        save_app_config(config)

    def dock_style_restore_available(self):
        state = load_app_config().get("dockStyle")
        return isinstance(state, dict) and (
            isinstance(state.get("originalSettings"), dict) or isinstance(state.get("previousSettings"), dict)
        )

    def clear_dock_style_active_action(self):
        config = load_app_config()
        state = config.get("dockStyle")
        if not isinstance(state, dict):
            return
        state["activeAction"] = "restored"
        config["dockStyle"] = state
        save_app_config(config)

    def refresh_dock_layout_state(self):
        if not hasattr(self, "dock_layout_status_label"):
            return
        layout = self.dock_layout_label()
        restore_available = self.dock_layout_restore_available()
        if hasattr(self, "dock_status_pills"):
            schema_available = self.dash_to_dock_available()
            self.set_pill(
                self.dock_status_pills["schema"],
                "available" if schema_available else "missing",
                "ok" if schema_available else "err",
            )
            self.set_pill(
                self.dock_status_pills["layout"],
                layout,
                "ok" if layout == "Windows taskbar" else ("err" if layout == "Unavailable" else "warn"),
            )
            self.set_pill(
                self.dock_status_pills["restore"],
                "saved" if restore_available else "none",
                "ok" if restore_available else "warn",
            )
        if layout == "Unavailable":
            self.dock_layout_status_label.set_text("Dock layout: unavailable. Dash-to-Dock settings were not found.")
            self.syncing_dock_layout = True
            self.dock_layout_switch.set_active(False)
            self.syncing_dock_layout = False
            self.dock_layout_switch.set_sensitive(False)
            self.dock_windows_button.set_sensitive(False)
            self.dock_restore_button.set_sensitive(False)
            self.dock_restore_button.set_visible(False)
        else:
            self.dock_layout_status_label.set_text(
                f"Dock layout: {layout}. Restore point: {'saved' if restore_available else 'none yet'}."
            )
            self.syncing_dock_layout = True
            self.dock_layout_switch.set_active(layout == "Windows taskbar")
            self.syncing_dock_layout = False
            self.dock_layout_switch.set_sensitive(True)
            self.dock_windows_button.set_sensitive(True)
            self.dock_restore_button.set_sensitive(restore_available)
            self.dock_restore_button.set_visible(False)
        self.refresh_overview_summary()

    def refresh_current_style(self):
        current = run(["gsettings", "get", DASH_TO_DOCK_SCHEMA, "click-action"], check=False)
        current = current.strip("'")
        self.syncing_style = True
        if current in self.style_buttons:
            self.style_buttons[current].set_active(True)
            self.style_description.set_text(self.describe_style(current))
        else:
            self.style_description.set_text(f"Current dock click action: {current or 'unknown'}")
        self.syncing_style = False
        if hasattr(self, "dock_status_pills"):
            self.set_pill(
                self.dock_status_pills["click"],
                current or "unknown",
                "ok" if current else "warn",
            )
        if hasattr(self, "style_restore_button"):
            restore_available = self.dock_style_restore_available()
            self.style_restore_button.set_sensitive(restore_available)
            self.style_restore_button.set_visible(False)
        self.refresh_overview_summary()

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
        self.refresh_profiles()
        self.refresh_feature_state()
        self.refresh_mouse_movement_state()
        self.refresh_extension_modules()
        self.refresh_overview_summary()


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
            self.log("If previews do not appear immediately, restart GNOME Shell: Alt+F2, type r, press Enter. On Wayland, log out/in.")
            self.refresh_feature_state()
        except Exception as error:
            self.log(f"Failed to install hover previews: {error}")

    def on_chrome_restore_original(self, _button):
        errors = []
        try:
            self.disable_profile_launchers()
        except Exception as error:
            errors.append(f"profile launchers: {error}")
        try:
            self.disable_hover_extension()
        except Exception as error:
            errors.append(f"hover previews: {error}")
        if errors:
            self.log("Chrome restore finished with issues: " + "; ".join(errors))
        else:
            self.log("Original Chrome dock setup restored.")
        self.refresh_feature_state()

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
                self.log("Hover previews enabled. If they do not appear immediately, restart GNOME Shell or log out/in.")
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

    def on_clipboard_autostart_toggled(self, check):
        if self.syncing_features:
            return
        state = check.get_active()
        try:
            if state:
                self.enable_copyq_autostart()
                self.log("CopyQ will now start automatically at login.")
            else:
                self.disable_copyq_autostart()
                self.log("CopyQ login autostart turned off.")
            self.refresh_compatibility()
            self.refresh_feature_state()
        except Exception as error:
            self.log(f"Failed to update CopyQ autostart: {error}")
            self.refresh_feature_state()

    def on_clipboard_shortcut_toggled(self, check):
        if self.syncing_features:
            return
        state = check.get_active()
        try:
            if state:
                self.enable_copyq_shortcut()
                self.log("Super+V now opens clipboard history. (Notification tray moved to Super+M.)")
            else:
                self.disable_copyq_shortcut()
                self.log("Super+V clipboard shortcut turned off. GNOME's Super+V was restored.")
            self.refresh_compatibility()
            self.refresh_feature_state()
        except Exception as error:
            self.log(f"Failed to update Super+V shortcut: {error}")
            self.refresh_feature_state()

    def on_clipboard_master_toggled(self, switch, state):
        if self.syncing_features:
            return False
        try:
            if state:
                self.enable_copyq_clipboard()
                self.log("Clipboard history enabled.")
            else:
                self.disable_copyq_clipboard()
                self.log("Clipboard history restored to original setup.")
            switch.set_state(state)
            self.refresh_feature_state()
        except Exception as error:
            self.log(f"Failed to update clipboard history: {error}")
            switch.set_state(not state)
            self.refresh_feature_state()
        return True

    def on_clipboard_clear(self, _button):
        try:
            self.clear_clipboard()
            self.log("Clipboard history and current clipboard cleared.")
        except Exception as error:
            self.log(f"Failed to clear clipboard: {error}")
        self.refresh_clipboard_state()

    def on_clipboard_repair_startup(self, _button):
        try:
            want_autostart = self.clipboard_autostart_check.get_active() if hasattr(self, "clipboard_autostart_check") else True
            want_shortcut = self.clipboard_shortcut_check.get_active() if hasattr(self, "clipboard_shortcut_check") else True
            if not want_autostart and not want_shortcut:
                # Nothing ticked: repair both so the user gets a working setup.
                want_autostart = want_shortcut = True
            if want_autostart:
                self.enable_copyq_autostart(quiet=True)
            if want_shortcut:
                self.enable_copyq_shortcut(quiet=True)
            self.log("Clipboard repaired. CopyQ scripts, autostart, and Super+V were recreated.")
        except Exception as error:
            self.log(f"Failed to repair clipboard: {error}")
        self.refresh_feature_state()

    def on_clipboard_restore_original(self, _button):
        try:
            self.disable_copyq_clipboard(quiet=True)
            self.log("Original clipboard shortcuts and startup restored.")
        except Exception as error:
            self.log(f"Failed to restore original clipboard setup: {error}")
        self.refresh_feature_state()

    def ensure_startup_features_once(self):
        want_autostart = self.clipboard_autostart_saved()
        want_shortcut = self.clipboard_shortcut_saved()
        if want_autostart or want_shortcut:
            if shutil.which("copyq"):
                try:
                    if want_autostart:
                        self.enable_copyq_autostart(allow_install=False, quiet=True)
                    if want_shortcut:
                        self.enable_copyq_shortcut(allow_install=False, quiet=True)
                    self.log("Clipboard startup checked.")
                except Exception as error:
                    self.log(f"Clipboard startup check failed: {error}")
            else:
                self.log("Clipboard is enabled, but CopyQ is not installed.")
        try:
            self.mouse_service.ensureMouseAutostart()
        except Exception as error:
            self.log(f"Mouse Movement startup check failed: {error}")
        self.refresh_feature_state()
        self.refresh_mouse_movement_state()
        return False

    def on_mouse_windows(self, _button):
        self.preflight_and_apply(
            "windows",
            lambda: self.mouse_service.applyWindowsPreset(),
            "Active preset: Windows",
            "Failed to apply Windows mouse movement",
        )

    def on_mouse_macos(self, _button):
        self.preflight_and_apply(
            "macos",
            lambda: self.mouse_service.applyMacOSPreset(),
            "Active preset: macOS",
            "Failed to apply macOS-like mouse movement",
        )

    def on_mouse_custom_sens(self, _button):
        multiplier = round(self.mouse_custom_sens_spin.get_value(), 4)
        self.preflight_and_apply(
            "custom",
            lambda: self.mouse_service.applyCustomSensitivity(multiplier),
            f"Custom maccel sensitivity applied (Sens-Mult = {multiplier:g})",
            "Failed to apply custom maccel sensitivity",
        )

    # --- maccel permission preflight + apply orchestration ------------------

    FRIENDLY_PERMISSION_ERROR = (
        "Linux Toolbox cannot write to maccel driver parameters yet. "
        "Fix permission or log out and back in."
    )

    def preflight_and_apply(self, preset, apply_callback, success_message, failure_prefix):
        """Run the maccel permission preflight, then apply the requested setting
        only if SENS_MULT is writable in this process. Otherwise show a friendly
        permission dialog and remember the pending action for after a fix."""
        if not self.mouse_service.isMaccelInstalled():
            self.log("maccel is not installed. Install it first.")
            return

        self.log("Checking maccel module...")
        status = self.mouse_service.getPermissionStatus()
        self.log("Checking SENS_MULT...")
        self.log("Checking write permission...")
        self.log("Checking maccel group...")

        if status.sensMultWritable:
            self.apply_mouse_action(apply_callback, success_message, failure_prefix)
            return

        self.mouse_permission_pending = {
            "preset": preset,
            "apply_callback": apply_callback,
            "success_message": success_message,
            "failure_prefix": failure_prefix,
        }

        if status.needsLogout:
            self.log(status.message)
            self.show_logout_required_dialog()
            return

        self.log(f"Driver write preflight: {status.message}")
        self.apply_mouse_action(apply_callback, success_message, failure_prefix)

    def apply_mouse_action(self, apply_callback, success_message, failure_prefix):
        try:
            apply_callback()
            self.mouse_permission_pending = None
            self.log(success_message)
        except PermissionError:
            self.log(self.FRIENDLY_PERMISSION_ERROR)
        except Exception as error:
            if self.is_permission_denied_error(error):
                self.log(self.FRIENDLY_PERMISSION_ERROR)
                self.show_permission_required_dialog()
            else:
                self.mouse_permission_pending = None
                self.log(f"{failure_prefix}: {error}")
        self.refresh_mouse_movement_state()

    def is_permission_denied_error(self, error):
        text = str(error).lower()
        return (
            "permission denied" in text
            or "os error 13" in text
            or "errno 13" in text
            or "operation not permitted" in text
        )

    def show_permission_required_dialog(self):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Permission required for maccel",
        )
        dialog.format_secondary_text(
            "Linux Toolbox needs permission to write maccel driver parameters.\n"
            "This is required to apply custom mouse sensitivity."
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        fix_button = dialog.add_button("Fix Permission", Gtk.ResponseType.OK)
        fix_button.get_style_context().add_class("suggested-action")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.start_permission_fix()
        else:
            self.mouse_permission_pending = None
            self.log("Permission fix cancelled. No mouse settings were changed.")

    def show_logout_required_dialog(self):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,
            text="Permission required for maccel",
        )
        dialog.format_secondary_text(
            "Permission was updated, but you need to log out and log back in "
            "before applying maccel settings."
        )
        dialog.add_button("I will log out later", Gtk.ResponseType.CANCEL)
        recheck_button = dialog.add_button("Recheck", Gtk.ResponseType.OK)
        recheck_button.get_style_context().add_class("suggested-action")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.recheck_permission_and_continue()
        else:
            self.log("Permission updated. Logout/login required.")

    def recheck_permission_and_continue(self):
        self.log("Rechecking write permission...")
        status = self.mouse_service.getPermissionStatus()
        if status.sensMultWritable:
            self.log("Permission ready")
            self.resume_pending_action()
        elif status.needsLogout:
            self.log("Permission updated. Logout/login required.")
            self.show_logout_required_dialog()
        else:
            self.log(self.FRIENDLY_PERMISSION_ERROR)
            self.show_permission_required_dialog()

    def start_permission_fix(self):
        if shutil.which("pkexec") is None:
            self.log("pkexec is missing, cannot run the maccel permission fix.")
            self.mouse_permission_pending = None
            return
        try:
            self.log("Creating maccel group if needed...")
            self.log("Adding user to maccel group...")
            self.log("Reloading udev rules...")
            self.log("Reloading maccel module...")
            self.log("Ubuntu may ask for your password to fix maccel permissions.")
            self.mouse_permission_fix_process = self.mouse_service.startFixPermissions()
            GLib.child_watch_add(
                self.mouse_permission_fix_process.pid, self.on_permission_fix_finished
            )
        except Exception as error:
            self.log(f"Failed to start maccel permission fix: {error}")
            self.mouse_permission_fix_process = None
            self.mouse_permission_pending = None
        self.refresh_mouse_movement_state()

    def on_permission_fix_finished(self, _pid, status):
        exit_code = status >> 8
        if self.mouse_permission_fix_process is not None:
            self.mouse_permission_fix_process.wait()
        self.mouse_permission_fix_process = None
        self.refresh_mouse_install_log_view()

        if exit_code != 0:
            self.log("maccel permission fix did not complete. No settings were changed.")
            self.refresh_mouse_movement_state()
            return

        self.log("Rechecking write permission...")
        new_status = self.mouse_service.getPermissionStatus()
        if new_status.sensMultWritable:
            self.log("Permission ready")
            self.resume_pending_action()
        elif new_status.needsLogout:
            self.log("Permission updated. Logout/login required.")
            self.show_logout_required_dialog()
        else:
            self.log(self.FRIENDLY_PERMISSION_ERROR)
        self.refresh_mouse_movement_state()

    def resume_pending_action(self):
        pending = self.mouse_permission_pending
        self.mouse_permission_pending = None
        if not pending:
            return
        self.apply_mouse_action(
            pending["apply_callback"],
            pending["success_message"],
            pending["failure_prefix"],
        )

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

    def on_mouse_restore(self, _button):
        try:
            self.mouse_service.restoreOriginalMaccelState()
            self.log("Original mouse settings restored")
        except Exception as error:
            self.log(f"Failed to restore original mouse settings: {error}")
        self.refresh_mouse_movement_state()

    def on_dock_windows_taskbar(self, _button):
        try:
            previous_settings = self.read_dock_layout_settings()
            self.save_dock_layout_restore_point(previous_settings, "windowsTaskbar")
            self.apply_dock_layout_settings(WINDOWS_DOCK_PRESET)
            self.log("Dock layout set to Windows taskbar.")
        except Exception as error:
            self.log(f"Failed to set Windows taskbar dock layout: {error}")
        self.refresh_dock_layout_state()

    def on_dock_layout_switch_toggled(self, switch, state):
        if self.syncing_dock_layout:
            return False
        try:
            if state:
                previous_settings = self.read_dock_layout_settings()
                self.save_dock_layout_restore_point(previous_settings, "windowsTaskbar")
                self.apply_dock_layout_settings(WINDOWS_DOCK_PRESET)
                self.log("Dock layout set to Windows taskbar.")
            else:
                self.apply_dock_layout_settings(DEFAULT_DOCK_PRESET)
                self.clear_dock_layout_active_preset()
                self.log("Dock layout restored to Ubuntu default.")
            switch.set_state(state)
        except Exception as error:
            self.log(f"Failed to update dock layout: {error}")
            switch.set_state(not state)
        self.refresh_dock_layout_state()
        return True

    def on_dock_restore_layout(self, _button):
        try:
            state = load_app_config().get("dockLayout")
            if not isinstance(state, dict):
                raise RuntimeError("No original dock layout restore point was found.")
            settings = state.get("originalSettings") if isinstance(state.get("originalSettings"), dict) else state.get("previousSettings")
            if not isinstance(settings, dict):
                raise RuntimeError("No original dock layout restore point was found.")
            self.apply_dock_layout_settings(settings)
            self.clear_dock_layout_active_preset()
            self.log("Original dock layout restored.")
        except Exception as error:
            self.log(f"Failed to restore original dock layout: {error}")
        self.refresh_dock_layout_state()

    def on_style_toggled(self, button, action):
        if self.syncing_style:
            return
        if not button.get_active():
            return
        try:
            self.save_dock_style_restore_point(self.read_dock_style_settings(), action)
            run(["gsettings", "set", DASH_TO_DOCK_SCHEMA, "click-action", action])
            run(["gsettings", "set", DASH_TO_DOCK_SCHEMA, "middle-click-action", "previews"])
            run(["gsettings", "set", DASH_TO_DOCK_SCHEMA, "activate-single-window", "true"])
            self.style_description.set_text(self.describe_style(action))
            self.log(f"Dock click style set to {action}.")
        except Exception as error:
            self.log(f"Failed to set style: {error}")
        self.refresh_current_style()

    def on_dock_restore_style(self, _button):
        try:
            state = load_app_config().get("dockStyle")
            if not isinstance(state, dict):
                raise RuntimeError("No original dock click style restore point was found.")
            settings = state.get("originalSettings") if isinstance(state.get("originalSettings"), dict) else state.get("previousSettings")
            if not isinstance(settings, dict):
                raise RuntimeError("No original dock click style restore point was found.")
            self.apply_dock_style_settings(settings)
            self.clear_dock_style_active_action()
            self.log("Original dock click style restored.")
        except Exception as error:
            self.log(f"Failed to restore original dock click style: {error}")
        self.refresh_current_style()

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
        wrapper_path.write_text(load_text("scripts/chrome-profile-launch.sh"), encoding="utf-8")
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
            desktop = load_template(
                "desktop/chrome-profile.desktop.tmpl",
                NAME=name,
                WRAPPER_PATH=wrapper_path,
                DIRECTORY=directory,
                CLASS_NAME=class_name,
                ICON=icon_path if icon_path.exists() else browser_id,
            )
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

    def gnome_shell_major_version(self):
        output = run(["gnome-shell", "--version"], check=False)
        for token in output.replace("-", " ").split():
            major = token.split(".", 1)[0]
            if major.isdigit():
                return int(major)
        return 0

    def hover_extension_bundle(self):
        major = self.gnome_shell_major_version()
        if major >= 45:
            return "hover-extension/extension-45.js", [str(major)]
        return "hover-extension/extension-legacy.js", ["42", "43", "44"]

    def hover_extension_metadata(self, shell_versions):
        version = 1
        for item in shell_versions:
            try:
                version = max(version, int(item))
            except ValueError:
                pass
        return json.dumps(
            {
                "uuid": HOVER_EXTENSION_UUID,
                "name": "Dock Window Preview",
                "description": "Preview open windows by hovering a dock icon and activate a window by selecting the preview.",
                "shell-version": shell_versions,
                "version": version,
            },
            indent=2,
        ) + "\n"

    def set_hover_extension_enabled(self, enabled):
        current = parse_gsettings_list(run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], check=False))
        filtered = [item for item in current if item != HOVER_EXTENSION_UUID]
        if enabled:
            filtered.append(HOVER_EXTENSION_UUID)
        run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", format_gsettings_list(filtered)])

    def reload_hover_extension(self):
        if shutil.which("gnome-extensions") is None:
            return
        run(["gnome-extensions", "disable", HOVER_EXTENSION_UUID], check=False)
        run(["gnome-extensions", "enable", HOVER_EXTENSION_UUID], check=False)

    def extension_directory(self, uuid):
        existing_directories = []
        for root in GNOME_EXTENSION_ROOTS:
            candidate = root / uuid
            if (candidate / "metadata.json").exists():
                return candidate
            if candidate.exists():
                existing_directories.append(candidate)
        if existing_directories:
            return existing_directories[0]
        return GNOME_EXTENSION_ROOTS[0] / uuid

    def extension_installed(self, uuid):
        directory = self.extension_directory(uuid)
        return (directory / "metadata.json").exists()

    def extension_enabled(self, uuid):
        enabled = parse_gsettings_list(
            run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], check=False)
        )
        return uuid in enabled

    def set_gnome_extension_enabled(self, uuid, enabled):
        current = parse_gsettings_list(
            run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], check=False)
        )
        filtered = [item for item in current if item != uuid]
        if enabled:
            run(["gsettings", "set", "org.gnome.shell", "disable-user-extensions", "false"], check=False)
            filtered.append(uuid)
        run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", format_gsettings_list(filtered)])
        if shutil.which("gnome-extensions"):
            action = "enable" if enabled else "disable"
            run(["gnome-extensions", action, uuid], check=False)

    def extension_settings(self, module):
        """Load an extension's local compiled schema without using global schemas."""
        directory = self.extension_directory(module["uuid"])
        schema_dir = directory / "schemas"
        if not schema_dir.exists():
            return None, None

        try:
            # Some extension packages ship XML only. Compile it locally so the
            # module still works with both distro and extensions.gnome.org
            # packages.
            if not (schema_dir / "gschemas.compiled").exists() and shutil.which("glib-compile-schemas"):
                run(["glib-compile-schemas", str(schema_dir)], check=False)
            source = Gio.SettingsSchemaSource.new_from_directory(str(schema_dir), None, False)
            local_schemas, _relocatable = source.list_schemas(False)
            schema_id = module.get("schema")
            if schema_id not in local_schemas:
                metadata_path = directory / "metadata.json"
                if metadata_path.exists():
                    try:
                        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                        candidate = metadata.get("settings-schema")
                        if candidate in local_schemas:
                            schema_id = candidate
                    except Exception:
                        pass
            if schema_id not in local_schemas:
                schema_id = next(
                    (item for item in local_schemas if item.startswith("org.gnome.shell.extensions.")),
                    None,
                )
            if not schema_id:
                return None, None
            schema = source.lookup(schema_id, False)
            if schema is None:
                return None, None
            return Gio.Settings.new_full(schema, None, None), schema
        except Exception as error:
            self.log(f"Could not load {module['name']} settings: {error}")
            return None, None

    def refresh_extension_module(self, state):
        module = state["definition"]
        uuid = state["uuid"]
        installed = self.extension_installed(uuid)
        enabled = installed and self.extension_enabled(uuid)
        settings, schema = self.extension_settings(module) if installed else (None, None)

        if not installed:
            self.set_pill(state["status"], "Not installed", "warn")
        elif enabled:
            self.set_pill(state["status"], "Enabled", "ok")
        else:
            self.set_pill(state["status"], "Installed · Off", "warn")

        self.syncing_extensions = True
        state["enabled_switch"].set_active(enabled)
        self.syncing_extensions = False
        state["enabled_switch"].set_sensitive(installed)
        state["install_button"].set_visible(not installed)
        state["install_button"].set_sensitive(not installed)
        state["preferences_button"].set_visible(installed)
        state["reset_button"].set_visible(settings is not None)
        state["configuration"].set_visible(True)
        state["settings"] = settings
        state["schema"] = schema

        configuration_box = state["configuration_box"]
        for child in configuration_box.get_children():
            child.destroy()
        state["setting_widgets"] = {}

        if not installed:
            hint = Gtk.Label(
                label="Install this module to unlock its settings. Installation is the only step that needs a download."
            )
            hint.set_xalign(0)
            hint.set_line_wrap(True)
            hint.get_style_context().add_class("section-subtitle")
            configuration_box.pack_start(hint, False, False, 0)
        elif settings is None or schema is None:
            hint = Gtk.Label(
                label="This module is installed, but it did not expose a local settings schema. Use Open full preferences to configure it."
            )
            hint.set_xalign(0)
            hint.set_line_wrap(True)
            hint.get_style_context().add_class("section-subtitle")
            configuration_box.pack_start(hint, False, False, 0)
        else:
            grid = Gtk.Grid(column_spacing=12, row_spacing=7)
            rendered = 0
            for key_name in module["settings"]:
                schema_key = schema.get_key(key_name)
                if schema_key is None:
                    continue
                row = self.create_extension_setting_row(state, settings, key_name, schema_key)
                if row is None:
                    continue
                grid.attach(row, 0, rendered, 1, 1)
                rendered += 1
            if rendered:
                configuration_box.pack_start(grid, False, False, 0)
                note = Gtk.Label(
                    label="Changes are saved immediately. Use Open full preferences for advanced options not shown here."
                )
                note.set_xalign(0)
                note.set_line_wrap(True)
                note.get_style_context().add_class("section-subtitle")
                configuration_box.pack_start(note, False, False, 0)
            else:
                hint = Gtk.Label(label="No supported settings were found for this module.")
                hint.set_xalign(0)
                hint.set_line_wrap(True)
                configuration_box.pack_start(hint, False, False, 0)

            advanced_keys = []
            for key_name in schema.list_keys():
                schema_key = schema.get_key(key_name)
                if schema_key is None:
                    continue
                type_string = schema_key.get_value_type().dup_string()
                if key_name not in module["settings"] and self.extension_setting_type_supported(type_string):
                    advanced_keys.append(key_name)
            if advanced_keys:
                advanced = Gtk.Expander(label=f"Advanced settings ({len(advanced_keys)})")
                advanced_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                advanced_box.set_margin_top(8)
                advanced_hint = Gtk.Label(
                    label="All other simple GSettings keys are available here. Complex keys stay in the full GNOME preferences window."
                )
                advanced_hint.set_xalign(0)
                advanced_hint.set_line_wrap(True)
                advanced_hint.get_style_context().add_class("section-subtitle")
                advanced_box.pack_start(advanced_hint, False, False, 0)
                advanced_combo = Gtk.ComboBoxText()
                for key_name in sorted(advanced_keys):
                    schema_key = schema.get_key(key_name)
                    label = schema_key.get_summary() or self.extension_setting_label(key_name)
                    advanced_combo.append(key_name, label)
                advanced_box.pack_start(advanced_combo, False, False, 0)
                advanced_editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                advanced_box.pack_start(advanced_editor, False, False, 0)
                advanced.add(advanced_box)
                advanced_combo.connect(
                    "changed",
                    self.on_extension_advanced_key_changed,
                    state,
                    advanced_editor,
                )
                advanced_combo.set_active(0)
                configuration_box.pack_start(advanced, False, False, 0)
        configuration_box.show_all()

    def on_extension_advanced_key_changed(self, combo, state, editor_box):
        if self.syncing_extensions:
            return
        key_name = combo.get_active_id()
        if not key_name or state.get("schema") is None or state.get("settings") is None:
            return
        for child in editor_box.get_children():
            child.destroy()
        row = self.create_extension_setting_row(
            state,
            state["settings"],
            key_name,
            state["schema"].get_key(key_name),
        )
        if row is None:
            row = Gtk.Label(label="This setting uses a complex value. Open full preferences to edit it.")
            row.set_xalign(0)
            row.set_line_wrap(True)
        editor_box.pack_start(row, False, False, 0)
        editor_box.show_all()

    def refresh_extension_modules(self):
        if not hasattr(self, "extension_modules") or not self.extension_modules:
            return
        for state in self.extension_modules.values():
            self.refresh_extension_module(state)

        installed_count = 0
        enabled_count = 0
        configurable_count = 0
        for state in self.extension_modules.values():
            if self.extension_installed(state["uuid"]):
                installed_count += 1
                if self.extension_enabled(state["uuid"]):
                    enabled_count += 1
                if state.get("settings") is not None:
                    configurable_count += 1
        if hasattr(self, "extension_status_pills"):
            total = len(self.extension_modules)
            self.set_pill(
                self.extension_status_pills["installed"],
                f"{installed_count}/{total}",
                "ok" if installed_count else "warn",
            )
            self.set_pill(
                self.extension_status_pills["enabled"],
                f"{enabled_count}/{total}",
                "ok" if enabled_count else "warn",
            )
            self.set_pill(
                self.extension_status_pills["configurable"],
                f"{configurable_count}/{total}",
                "ok" if configurable_count else "warn",
            )

    def extension_module_summary(self):
        if not self.extension_modules:
            return "No modules installed"
        enabled = sum(1 for state in self.extension_modules.values() if self.extension_enabled(state["uuid"]))
        return f"{enabled}/{len(self.extension_modules)} enabled"

    def on_install_extension_clicked(self, button, uuid, name):
        button.set_sensitive(False)
        button.set_label("Installing…")

        def do_install():
            success = self.install_gnome_extension(uuid)
            GLib.idle_add(self.finish_install_extension, button, uuid, name, success)

        import threading
        threading.Thread(target=do_install, daemon=True).start()

    def finish_install_extension(self, button, uuid, name, success):
        if success:
            try:
                self.set_gnome_extension_enabled(uuid, True)
                self.log(f"{name} installed and enabled. Configure it in this module card.")
            except Exception as error:
                self.log(f"{name} installed, but could not enable it automatically: {error}")
        else:
            self.log(f"Could not install {name}. Check your network connection and GNOME Shell version.")
            button.set_label("Install module")
            button.set_sensitive(True)
        self.refresh_extension_modules()

    def install_gnome_extension(self, uuid):
        import urllib.request
        import zipfile
        import io

        try:
            major_version = self.gnome_shell_major_version()
            api_url = f"https://extensions.gnome.org/extension-info/?uuid={uuid}&shell_version={major_version}"

            with urllib.request.urlopen(api_url) as response:
                data = json.loads(response.read().decode('utf-8'))
                download_url = "https://extensions.gnome.org" + data["download_url"]

            with urllib.request.urlopen(download_url) as response:
                zip_data = response.read()

            ext_dir = GNOME_EXTENSION_ROOTS[0] / uuid
            ext_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                z.extractall(ext_dir)

            schema_dir = ext_dir / "schemas"
            if (
                schema_dir.exists()
                and not (schema_dir / "gschemas.compiled").exists()
                and shutil.which("glib-compile-schemas")
            ):
                run(["glib-compile-schemas", str(schema_dir)], check=False)
            return True
        except Exception as e:
            print(f"Failed to install extension {uuid}: {e}")
            return False

    def install_hover_extension(self):
        extension_resource, shell_versions = self.hover_extension_bundle()
        EXT_DIR.mkdir(parents=True, exist_ok=True)
        (EXT_DIR / "metadata.json").write_text(self.hover_extension_metadata(shell_versions), encoding="utf-8")
        (EXT_DIR / "extension.js").write_text(load_text(extension_resource), encoding="utf-8")
        (EXT_DIR / "extension-legacy.js").write_text(load_text("hover-extension/extension-legacy.js"), encoding="utf-8")
        (EXT_DIR / "extension-45.js").write_text(load_text("hover-extension/extension-45.js"), encoding="utf-8")
        (EXT_DIR / "stylesheet.css").write_text(load_text("hover-extension/stylesheet.css"), encoding="utf-8")

        run(["gsettings", "set", "org.gnome.shell", "disable-user-extensions", "false"], check=False)
        self.set_hover_extension_enabled(True)
        self.reload_hover_extension()

    def disable_hover_extension(self):
        self.set_hover_extension_enabled(False)
        if shutil.which("gnome-extensions"):
            run(["gnome-extensions", "disable", HOVER_EXTENSION_UUID], check=False)

    def hover_feature_enabled(self):
        enabled = parse_gsettings_list(run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], check=False))
        return HOVER_EXTENSION_UUID in enabled

    def _write_copyq_scripts(self):
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        # Launcher used by autostart. CopyQ is single-instance, so this is safe
        # to run even if a server is already up. Runs the server in foreground so
        # the session tracks it as a live process (no broken `wait`).
        COPYQ_START.write_text(load_text("scripts/copyq-start.sh"), encoding="utf-8")
        COPYQ_START.chmod(0o755)
        # Super+V popup. Ensures the server is up, then toggles the history window.
        COPYQ_SHORTCUT.write_text(load_text("scripts/copyq-super-v.sh"), encoding="utf-8")
        COPYQ_SHORTCUT.chmod(0o755)
        # Clear history + the current system clipboard/selection.
        COPYQ_CLEAR.write_text(load_text("scripts/copyq-clear.sh"), encoding="utf-8")
        COPYQ_CLEAR.chmod(0o755)

    def reassign_gnome_super_v(self):
        # Remove <Super>v from GNOME's notification-tray binding so CopyQ owns it.
        current = parse_gsettings_list(
            run(["gsettings", "get", GNOME_TRAY_SCHEMA, GNOME_TRAY_KEY], check=False)
        )
        kept = [item for item in current if item not in ("<Super>v", "<Super>V")]
        if kept != current:
            run(["gsettings", "set", GNOME_TRAY_SCHEMA, GNOME_TRAY_KEY, format_gsettings_list(kept)])

    def restore_gnome_super_v(self):
        current = parse_gsettings_list(
            run(["gsettings", "get", GNOME_TRAY_SCHEMA, GNOME_TRAY_KEY], check=False)
        )
        if "<Super>v" not in current and "<Super>V" not in current:
            current.append("<Super>v")
            run(["gsettings", "set", GNOME_TRAY_SCHEMA, GNOME_TRAY_KEY, format_gsettings_list(current)])

    def enable_copyq_autostart(self, allow_install=True, quiet=False):
        self.ensure_copyq_installed(allow_install=allow_install)
        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        self._write_copyq_scripts()
        COPYQ_AUTOSTART.write_text(
            load_template("desktop/copyq.desktop.tmpl", COPYQ_START=COPYQ_START),
            encoding="utf-8",
        )
        COPYQ_AUTOSTART.chmod(0o644)
        if not self._copyq_running():
            self._start_copyq()
        self._configure_copyq()
        self.save_clipboard_config(autostart=True)
        if not quiet:
            self.refresh_clipboard_state()

    def disable_copyq_autostart(self, quiet=False):
        COPYQ_AUTOSTART.unlink(missing_ok=True)
        # Clean up the legacy systemd user service if a previous version made one.
        if COPYQ_SERVICE.exists():
            run(["systemctl", "--user", "disable", "--now", "copyq.service"], check=False)
            COPYQ_SERVICE.unlink(missing_ok=True)
            run(["systemctl", "--user", "daemon-reload"], check=False)
        self.save_clipboard_config(autostart=False)
        if not quiet:
            self.refresh_clipboard_state()

    def enable_copyq_shortcut(self, allow_install=True, quiet=False):
        self.ensure_copyq_installed(allow_install=allow_install)
        self._write_copyq_scripts()
        self.reassign_gnome_super_v()
        self.configure_custom_shortcut(
            CLIPBOARD_SHORTCUT_PATH,
            "Clipboard History",
            str(COPYQ_SHORTCUT),
            CLIPBOARD_SHORTCUT_BINDING,
        )
        if not self._copyq_running():
            self._start_copyq()
        self._configure_copyq()
        self.save_clipboard_config(shortcut=True)
        if not quiet:
            self.refresh_clipboard_state()

    def disable_copyq_shortcut(self, quiet=False):
        self.remove_custom_shortcut(CLIPBOARD_SHORTCUT_PATH)
        self.restore_gnome_super_v()
        self.save_clipboard_config(shortcut=False)
        if not quiet:
            self.refresh_clipboard_state()

    def clear_clipboard(self):
        if not shutil.which("copyq"):
            raise RuntimeError("CopyQ is not installed.")
        self._write_copyq_scripts()
        if not self._copyq_running():
            self._start_copyq()
        run([str(COPYQ_CLEAR)], check=False)

    def _copyq_session_name(self):
        source = os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY") or "default"
        safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in source)
        return f"ltb-{safe}"[:16]

    def _copyq_command(self, *args):
        return ["copyq", "--session", self._copyq_session_name(), *args]

    def _start_copyq(self):
        subprocess.Popen(self._copyq_command(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def _configure_copyq(self):
        settings = {
            "item_popup_interval": "0",
            "native_notifications": "false",
            "clipboard_notification_lines": "0",
            "close_on_unfocus": "true",
            "hide_main_window": "true",
            "open_windows_on_current_screen": "true",
        }
        for key, value in settings.items():
            run(self._copyq_command("config", key, value), check=False)

    def _copyq_running(self):
        if not shutil.which("copyq"):
            return False
        return run(self._copyq_command("count"), check=False).strip() != ""

    def enable_copyq_clipboard(self, allow_install=True, quiet=False):
        # Composite: turn on both parts (used by Repair and startup self-heal).
        self.enable_copyq_autostart(allow_install=allow_install, quiet=True)
        self.enable_copyq_shortcut(allow_install=allow_install, quiet=True)
        if not quiet:
            self.refresh_clipboard_state()

    def disable_copyq_clipboard(self, quiet=False):
        self.disable_copyq_autostart(quiet=True)
        self.disable_copyq_shortcut(quiet=True)
        COPYQ_START.unlink(missing_ok=True)
        COPYQ_SHORTCUT.unlink(missing_ok=True)
        COPYQ_CLEAR.unlink(missing_ok=True)
        if shutil.which("copyq"):
            run(self._copyq_command("exit"), check=False)
        if not quiet:
            self.refresh_clipboard_state()

    def ensure_copyq_installed(self, allow_install=True):
        if shutil.which("copyq"):
            return
        if not allow_install:
            raise RuntimeError("CopyQ is not installed.")
        if not shutil.which("pkexec"):
            raise RuntimeError("CopyQ is not installed and pkexec is unavailable. Install it with: sudo apt install copyq")
        self.log("CopyQ is not installed. Ubuntu will ask for your password to install it.")
        run(["pkexec", "apt-get", "install", "-y", "copyq"])

    def save_clipboard_config(self, autostart=None, shortcut=None):
        config = load_app_config()
        existing = config.get("clipboard") if isinstance(config.get("clipboard"), dict) else {}
        new_autostart = existing.get("autoStart", False) if autostart is None else bool(autostart)
        new_shortcut = existing.get("shortcut", False) if shortcut is None else bool(shortcut)
        config["clipboard"] = {
            "enabled": bool(new_autostart or new_shortcut),
            "autoStart": new_autostart,
            "shortcut": new_shortcut,
            "backend": "copyq",
            "shortcutBinding": CLIPBOARD_SHORTCUT_BINDING,
            "lastUpdatedAt": iso_now(),
        }
        save_app_config(config)


    def clipboard_config_enabled(self):
        clipboard_state = load_app_config().get("clipboard")
        if isinstance(clipboard_state, dict) and "enabled" in clipboard_state:
            return bool(clipboard_state.get("enabled"))
        return bool(COPYQ_SHORTCUT.exists() and (COPYQ_AUTOSTART.exists() or COPYQ_SERVICE.exists()))

    def clipboard_autostart_saved(self):
        state = load_app_config().get("clipboard")
        if isinstance(state, dict) and "autoStart" in state:
            return bool(state.get("autoStart"))
        return COPYQ_AUTOSTART.exists()

    def clipboard_shortcut_saved(self):
        state = load_app_config().get("clipboard")
        if isinstance(state, dict) and "shortcut" in state:
            return bool(state.get("shortcut"))
        return COPYQ_SHORTCUT.exists()

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

    def clipboard_autostart_active(self):
        return shutil.which("copyq") is not None and COPYQ_AUTOSTART.exists()

    def clipboard_shortcut_active(self):
        if not shutil.which("copyq") or not COPYQ_SHORTCUT.exists():
            return False
        current = parse_gsettings_list(
            run(["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"], check=False)
        )
        return CLIPBOARD_SHORTCUT_PATH in current

    def clipboard_feature_enabled(self):
        # Composite used by the Overview summary: on when either part is active.
        return self.clipboard_autostart_active() or self.clipboard_shortcut_active()


class ChromeDockProfiles(Gtk.Application):
    def __init__(self):
        application_id = os.environ.get("LINUX_TOOLBOX_APP_ID", "local.linux_toolbox")
        super().__init__(application_id=application_id)
        self.window = None

    def do_activate(self):
        if self.window is None:
            self.window = App(self)
        self.window.show_all()
        self.window.present()


def main():
    app = ChromeDockProfiles()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
