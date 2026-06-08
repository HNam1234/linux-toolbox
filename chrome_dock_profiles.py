#!/usr/bin/env python3
import ast
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import gi

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk, Pango  # noqa: E402

from linux_toolbox.resources import load_template, load_text  # noqa: E402


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
COPYQ_CLEAR = BIN_DIR / "copyq-clear"
COPYQ_SERVICE = SYSTEMD_USER_DIR / "copyq.service"
CLIPBOARD_SHORTCUT_BINDING = "<Super>v"
AITOOLS_DESKTOP_ID = "aitools.desktop"
AITOOLS_DESKTOP = APP_DIR / AITOOLS_DESKTOP_ID
AITOOLS_WRAPPER = BIN_DIR / "linux-toolbox-aitools"
CONFIG_DIR = HOME / ".config/chrome-dock-profiles"
CONFIG_PATH = CONFIG_DIR / "config.json"
VSCODE_AI_TOOLS_INIT = CONFIG_DIR / "vscode-ai-tools.sh"
BICLAUDE_COMMAND = BIN_DIR / "biclaude"
BICODEX_COMMAND = BIN_DIR / "bicodex"
# Codex reads ~/.codex/config.toml globally, which both the VS Code extension
# and the plain `codex` command share. To keep personal (web login) Codex
# separate from Bifrost, bicodex points CODEX_HOME at this dedicated home so
# the Bifrost/Sotatek provider lives only here and never leaks into VS Code.
CODEX_BIFROST_HOME = HOME / ".config/linux-toolbox/codex-bifrost"
CODEX_VSCODE_HOME = HOME / ".codex"
CODEX_VSCODE_CONFIG = CODEX_VSCODE_HOME / "config.toml"
CLAUDE_HOME = HOME / ".claude"
CLAUDE_SETTINGS = CLAUDE_HOME / "settings.json"
AITOOLS_MANAGED_MARKER = "Managed by Linux Toolbox AI Tools"
BIFROST_PORTAL_URL = "https://bifrost.sotatek.works/portal"
AITOOLS_TARGETS = (
    ("codexCli", "Codex CLI", "codex", BICODEX_COMMAND),
    ("claudeCli", "Claude CLI", "claude", BICLAUDE_COMMAND),
    ("codexVscode", "Codex Plugin VS Code", "codex", CODEX_VSCODE_CONFIG),
    ("claudeVscode", "Claude Plugin VS Code", "claude", CLAUDE_SETTINGS),
)
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
VIETNAMESE_INSTALLER = BIN_DIR / "chrome-dock-profiles-install-vietnamese-input"
VIETNAMESE_INPUT_LOG = CONFIG_DIR / "vietnamese-input.log"
BAMBOO_CONFIG_DIR = HOME / ".config/ibus-bamboo"
BAMBOO_CONFIG_PATH = BAMBOO_CONFIG_DIR / "ibus-bamboo.config.json"
BAMBOO_CONFIG_BACKUP_PATH = CONFIG_DIR / "ibus-bamboo.config.json.backup"
BAMBOO_ORIGINAL_CONFIG_BACKUP_PATH = CONFIG_DIR / "ibus-bamboo.config.json.original"
GNOME_INPUT_SOURCES_SCHEMA = "org.gnome.desktop.input-sources"
GNOME_INPUT_SOURCES_KEY = "sources"
BAMBOO_INPUT_SOURCE = ("ibus", "Bamboo")
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


class VietnameseInputService:
    def __init__(self, logger=None):
        self.logger = logger or (lambda _message: None)

    def _log(self, message):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with VIETNAMESE_INPUT_LOG.open("a", encoding="utf-8") as handle:
                handle.write(f"{iso_now()} {message}\n")
        except Exception:
            pass
        self.logger(message)

    def diagnostics(self):
        raw_sources = self.current_input_sources_raw()
        parsed_sources = self.parse_input_sources(raw_sources)
        return {
            "os": self.detect_os(),
            "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "unknown").strip() or "unknown",
            "session": os.environ.get("XDG_SESSION_TYPE", "unknown").strip().lower() or "unknown",
            "ibusInstalled": self.is_ibus_installed(),
            "bambooInstalled": self.is_bamboo_installed(),
            "ibusDaemonRunning": self.ibus_daemon_running(),
            "framework": self.current_framework(),
            "inputSourcesRaw": raw_sources,
            "inputSources": parsed_sources,
            "bambooSourceActive": self.has_bamboo_source(parsed_sources),
            "bambooConfigPath": str(BAMBOO_CONFIG_PATH),
            "bambooConfigExists": BAMBOO_CONFIG_PATH.exists(),
            "bambooConfigDirExists": BAMBOO_CONFIG_DIR.exists(),
            "pkexecAvailable": shutil.which("pkexec") is not None,
            "aptBambooAvailable": self.apt_bamboo_available(),
        }

    def classify_status(self, diagnostics):
        if not diagnostics["ibusInstalled"] or not diagnostics["bambooInstalled"]:
            return "Needs install"
        if not diagnostics["ibusDaemonRunning"]:
            return "Needs restart"
        if diagnostics["framework"] != "IBus" or not diagnostics["bambooSourceActive"]:
            return "Misconfigured"
        if self._saved_needs_logout():
            self.clear_needs_logout()
        return "Ready"

    def detect_os(self):
        output = run(["lsb_release", "-ds"], check=False).strip()
        if output:
            return output.strip('"')
        if Path("/etc/os-release").exists():
            try:
                for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
            except Exception:
                pass
        return "Unknown"

    def is_ibus_installed(self):
        return shutil.which("ibus") is not None

    def is_bamboo_installed(self):
        output = run(["dpkg-query", "-W", "-f=${Status}", "ibus-bamboo"], check=False)
        return "install ok installed" in output

    def ibus_daemon_running(self):
        return run(["pgrep", "-x", "ibus-daemon"], check=False).strip() != ""

    def current_framework(self):
        if shutil.which("im-config") is None:
            return "Unknown"
        output = run(["im-config", "-m"], check=False).lower()
        if "ibus" in output:
            return "IBus"
        if "fcitx" in output:
            return "Fcitx"
        if output.strip():
            return output.splitlines()[0].strip() or "Unknown"
        return "Unknown"

    def current_framework_id(self):
        framework = self.current_framework()
        if framework == "IBus":
            return "ibus"
        if framework == "Fcitx":
            return "fcitx"
        return ""

    def apt_bamboo_available(self):
        if shutil.which("apt-cache") is None:
            return False
        output = run(["apt-cache", "policy", "ibus-bamboo"], check=False)
        for line in output.splitlines():
            if line.strip().startswith("Candidate:"):
                candidate = line.split(":", 1)[1].strip()
                return bool(candidate and candidate != "(none)")
        return False

    def current_input_sources_raw(self):
        return run(["gsettings", "get", GNOME_INPUT_SOURCES_SCHEMA, GNOME_INPUT_SOURCES_KEY], check=False)

    @staticmethod
    def parse_input_sources(raw):
        try:
            value = ast.literal_eval(raw)
        except Exception:
            return []
        if not isinstance(value, list):
            return []
        sources = []
        for item in value:
            if (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], str)
            ):
                sources.append(item)
        return sources

    @staticmethod
    def has_bamboo_source(sources):
        return BAMBOO_INPUT_SOURCE in sources

    @classmethod
    def append_bamboo_source_value(cls, raw):
        if not raw.strip():
            raise RuntimeError("Could not read current GNOME input sources. No changes were made.")
        sources = cls.parse_input_sources(raw)
        if not sources and raw.strip() != "[]":
            raise RuntimeError("Could not parse current GNOME input sources. No changes were made.")
        if BAMBOO_INPUT_SOURCE not in sources:
            sources.append(BAMBOO_INPUT_SOURCE)
        return repr(sources)

    def _write_installer_script(self, add_ppa=False):
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        VIETNAMESE_INSTALLER.write_text(
            load_template(
                "scripts/install-vietnamese-input.sh.tmpl",
                VIETNAMESE_INPUT_LOG=VIETNAMESE_INPUT_LOG,
                ADD_PPA="1" if add_ppa else "0",
            ),
            encoding="utf-8",
        )
        VIETNAMESE_INSTALLER.chmod(0o755)
        return VIETNAMESE_INSTALLER

    def start_install(self, add_ppa=False):
        if shutil.which("pkexec") is None:
            raise RuntimeError("pkexec is not installed. Cannot install Vietnamese input packages.")
        installer = self._write_installer_script(add_ppa=add_ppa)
        self._log("Installing packages...")
        return subprocess.Popen(["pkexec", str(installer)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def apply_unikey_like_fixes(self):
        self._log("Applying UniKey-like fixes...")
        if not self.is_ibus_installed():
            raise RuntimeError("IBus is not installed.")
        if not self.is_bamboo_installed():
            raise RuntimeError("ibus-bamboo is not installed.")

        self._log("Backup saved...")
        previous_sources = self.current_input_sources_raw()
        previous_framework = self.current_framework_id()
        bamboo_backup = self.backup_bamboo_config()

        self._log("Checking input sources...")
        new_sources = self.append_bamboo_source_value(previous_sources)

        self._log("Setting IBus as input framework...")
        if shutil.which("im-config"):
            run(["im-config", "-n", "ibus"], check=False)

        if new_sources != previous_sources:
            run(["gsettings", "set", GNOME_INPUT_SOURCES_SCHEMA, GNOME_INPUT_SOURCES_KEY, new_sources])

        self.save_previous_settings(previous_sources, previous_framework, bamboo_backup)
        self.restart_input_method()
        self._log("Open ibus-bamboo preferences and choose Telex + Unicode.")
        self._log("Done / Needs logout")

    def backup_bamboo_config(self):
        if not BAMBOO_CONFIG_PATH.exists():
            return ""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BAMBOO_CONFIG_PATH, BAMBOO_CONFIG_BACKUP_PATH)
        if not BAMBOO_ORIGINAL_CONFIG_BACKUP_PATH.exists():
            shutil.copy2(BAMBOO_CONFIG_PATH, BAMBOO_ORIGINAL_CONFIG_BACKUP_PATH)
        return str(BAMBOO_CONFIG_BACKUP_PATH)

    def save_previous_settings(self, previous_sources, previous_framework, bamboo_backup):
        config = load_app_config()
        existing = config.get("vietnameseInput")
        if not isinstance(existing, dict):
            existing = {}
        config["vietnameseInput"] = {
            "originalInputSources": existing.get("originalInputSources") or previous_sources,
            "originalInputMethod": existing.get("originalInputMethod") or previous_framework,
            "originalBambooConfigBackupPath": existing.get("originalBambooConfigBackupPath")
            or (str(BAMBOO_ORIGINAL_CONFIG_BACKUP_PATH) if BAMBOO_ORIGINAL_CONFIG_BACKUP_PATH.exists() else ""),
            "previousInputSources": previous_sources,
            "previousInputMethod": previous_framework,
            "previousBambooConfigBackupPath": bamboo_backup,
            "lastAppliedAt": iso_now(),
            "needsLogout": True,
        }
        save_app_config(config)

    def restart_input_method(self):
        self._log("Restarting IBus...")
        if shutil.which("ibus") is None:
            raise RuntimeError("IBus command was not found.")
        completed = subprocess.run(["ibus", "restart"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode == 0:
            return
        run(["killall", "ibus-daemon"], check=False)
        subprocess.Popen(["ibus-daemon", "-drx"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def restore_previous_settings(self):
        state = load_app_config().get("vietnameseInput")
        if not isinstance(state, dict):
            raise RuntimeError("No Vietnamese input backup was found.")

        previous_sources = state.get("originalInputSources") or state.get("previousInputSources")
        if previous_sources:
            run(["gsettings", "set", GNOME_INPUT_SOURCES_SCHEMA, GNOME_INPUT_SOURCES_KEY, previous_sources])

        previous_method = state.get("originalInputMethod") or state.get("previousInputMethod")
        if previous_method and shutil.which("im-config"):
            run(["im-config", "-n", previous_method], check=False)

        backup_path = state.get("originalBambooConfigBackupPath") or state.get("previousBambooConfigBackupPath")
        if backup_path and Path(backup_path).exists():
            BAMBOO_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, BAMBOO_CONFIG_PATH)

        config = load_app_config()
        current = config.get("vietnameseInput", {})
        if isinstance(current, dict):
            current["needsLogout"] = False
            current["lastRestoredAt"] = iso_now()
            config["vietnameseInput"] = current
            save_app_config(config)
        self.restart_input_method()

    def _saved_needs_logout(self):
        state = load_app_config().get("vietnameseInput")
        return isinstance(state, dict) and bool(state.get("needsLogout"))

    def clear_needs_logout(self):
        config = load_app_config()
        state = config.get("vietnameseInput")
        if not isinstance(state, dict) or not state.get("needsLogout"):
            return
        state["needsLogout"] = False
        state["logoutSatisfiedAt"] = iso_now()
        config["vietnameseInput"] = state
        save_app_config(config)

    def latest_log_text(self, limit=220):
        if not VIETNAMESE_INPUT_LOG.exists():
            return ""
        try:
            lines = VIETNAMESE_INPUT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as error:
            return f"Could not read Vietnamese input log: {error}"
        return "\n".join(lines[-limit:])


class AIToolsService:
    def defaultMode(self, target):
        return "web" if target in {"codexVscode", "claudeVscode"} else "bifrost"

    def targetConfig(self, config=None, target="codexCli"):
        config = config or {}
        raw = config.get(target, {})
        if not isinstance(raw, dict):
            raw = {}

        legacy_model = str(config.get("selectedModel", "")).strip()
        legacy_mode = config.get("connectionMode") if target in {"codexCli", "claudeCli"} else None
        mode = str(raw.get("connectionMode") or legacy_mode or self.defaultMode(target)).strip()
        if mode not in {"bifrost", "web"}:
            mode = self.defaultMode(target)
        defaults = {
            "connectionMode": mode,
            "bifrostBaseUrl": raw.get("bifrostBaseUrl") or config.get("bifrostBaseUrl", ""),
            "bifrostToken": raw.get("bifrostToken") or config.get("bifrostToken", ""),
            "selectedModel": raw.get("selectedModel") or legacy_model,
            "accountLabel": raw.get("accountLabel") or "",
        }
        return {key: str(value).strip() for key, value in defaults.items() if value is not None}

    def vscodeTargetConfig(self, config=None, target="codexVscode"):
        return self.targetConfig(config, target)

    def actualTargetConfig(self, config=None, target="codexCli"):
        saved = self.targetConfig(config, target)
        actual = dict(saved)
        actual["source"] = "saved"

        if target == "codexCli":
            wrapper = self.readShellWrapper(BICODEX_COMMAND)
            if wrapper.get("exists"):
                actual["source"] = str(BICODEX_COMMAND)
                codex_home = wrapper.get("CODEX_HOME")
                if codex_home:
                    codex = self.readCodexConfig(Path(codex_home))
                    actual.update({key: value for key, value in codex.items() if value})
                    actual["connectionMode"] = "bifrost" if codex.get("bifrost") else "web"
                elif wrapper.get("unset_CODEX_HOME"):
                    actual["connectionMode"] = "web"
                    global_codex = self.readCodexConfig(CODEX_VSCODE_HOME)
                    if global_codex.get("bifrost"):
                        actual.update({key: value for key, value in global_codex.items() if value})
                        actual["connectionMode"] = "bifrost"
            elif (CODEX_BIFROST_HOME / "config.toml").exists():
                codex = self.readCodexConfig(CODEX_BIFROST_HOME)
                actual.update({key: value for key, value in codex.items() if value})
                actual["connectionMode"] = "bifrost" if codex.get("bifrost") else saved.get("connectionMode", "bifrost")
                actual["source"] = str(CODEX_BIFROST_HOME / "config.toml")

        elif target == "claudeCli":
            wrapper = self.readShellWrapper(BICLAUDE_COMMAND)
            if wrapper.get("exists"):
                actual["source"] = str(BICLAUDE_COMMAND)
                if wrapper.get("ANTHROPIC_BASE_URL") or wrapper.get("ANTHROPIC_AUTH_TOKEN") or wrapper.get("ANTHROPIC_API_KEY"):
                    actual["connectionMode"] = "bifrost"
                    actual["bifrostBaseUrl"] = wrapper.get("ANTHROPIC_BASE_URL", "")
                    actual["bifrostToken"] = wrapper.get("ANTHROPIC_AUTH_TOKEN") or wrapper.get("ANTHROPIC_API_KEY") or ""
                    actual["selectedModel"] = wrapper.get("ANTHROPIC_MODEL", "")
                elif wrapper.get("unset_ANTHROPIC_BASE_URL") or wrapper.get("unset_ANTHROPIC_AUTH_TOKEN"):
                    actual["connectionMode"] = "web"
            else:
                claude = self.readClaudeSettings()
                if claude.get("bifrost"):
                    actual.update({key: value for key, value in claude.items() if value})
                    actual["connectionMode"] = "bifrost"
                    actual["source"] = str(CLAUDE_SETTINGS)

        elif target == "codexVscode":
            codex = self.readCodexConfig(CODEX_VSCODE_HOME)
            if codex.get("exists"):
                actual.update({key: value for key, value in codex.items() if value})
                actual["connectionMode"] = "bifrost" if codex.get("bifrost") else "web"
                actual["source"] = str(CODEX_VSCODE_CONFIG)
            elif self.pathHasFiles(CODEX_VSCODE_HOME):
                actual["connectionMode"] = "web"
                actual["source"] = str(CODEX_VSCODE_HOME)

        elif target == "claudeVscode":
            claude = self.readClaudeSettings()
            if claude.get("exists"):
                actual.update({key: value for key, value in claude.items() if value})
                actual["connectionMode"] = "bifrost" if claude.get("bifrost") else "web"
                actual["source"] = str(CLAUDE_SETTINGS)
            elif self.pathHasFiles(CLAUDE_HOME):
                actual["connectionMode"] = "web"
                actual["source"] = str(CLAUDE_HOME)

        if actual.get("connectionMode") not in {"bifrost", "web"}:
            actual["connectionMode"] = self.defaultMode(target)
        return {key: str(value).strip() if isinstance(value, str) else value for key, value in actual.items()}

    def readShellWrapper(self, path):
        result = {"exists": path.exists()}
        if not path.exists():
            return result
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return result
        for key in (
            "CODEX_HOME",
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_MODEL",
            "AITOOLS_BASE_URL",
            "AITOOLS_AUTH_TOKEN",
            "AITOOLS_MODEL",
        ):
            value = self.shellValue(text, key)
            if value:
                result[key] = value
            if re.search(rf"^\s*unset\s+{re.escape(key)}\b", text, re.MULTILINE):
                result[f"unset_{key}"] = True
        return result

    def pathHasFiles(self, path):
        try:
            return path.exists() and any(path.iterdir())
        except Exception:
            return False

    def shellValue(self, text, key):
        pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}=(.+?)\s*$", re.MULTILINE)
        match = pattern.search(text)
        if not match:
            return ""
        raw = match.group(1).strip()
        try:
            parts = shlex.split(raw)
            if parts:
                return parts[0]
        except Exception:
            pass
        return raw.strip("\"'")

    def readCodexConfig(self, codex_home):
        config_path = codex_home / "config.toml"
        result = {"exists": config_path.exists(), "configPath": str(config_path)}
        if not config_path.exists():
            return result
        try:
            text = config_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return result
        base_url = self.tomlValue(text, "base_url")
        token = self.tomlValue(text, "experimental_bearer_token")
        model = self.tomlValue(text, "model")
        provider = self.tomlValue(text, "model_provider")
        result.update(
            {
                "bifrostBaseUrl": base_url,
                "bifrostToken": token,
                "selectedModel": model,
                "provider": provider,
                "managed": AITOOLS_MANAGED_MARKER in text,
            }
        )
        result["bifrost"] = bool(
            token
            or "sotatek" in provider.lower()
            or "bifrost" in base_url.lower()
            or AITOOLS_MANAGED_MARKER in text
        )
        result["accountLabel"] = "Bifrost/Sotatek" if result["bifrost"] else "Codex web login"
        return result

    def tomlValue(self, text, key):
        match = re.search(rf"^\s*{re.escape(key)}\s*=\s*\"((?:\\.|[^\"])*)\"", text, re.MULTILINE)
        if match:
            return match.group(1).replace('\\"', '"').replace("\\\\", "\\")
        match = re.search(rf"^\s*{re.escape(key)}\s*=\s*([^\n#]+)", text, re.MULTILINE)
        if match:
            return match.group(1).strip().strip("\"'")
        return ""

    def readClaudeSettings(self):
        result = {"exists": CLAUDE_SETTINGS.exists(), "configPath": str(CLAUDE_SETTINGS)}
        if not CLAUDE_SETTINGS.exists():
            return result
        try:
            data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
        except Exception:
            return result
        env = data.get("env", {}) if isinstance(data, dict) else {}
        if not isinstance(env, dict):
            env = {}
        base_url = str(env.get("ANTHROPIC_BASE_URL", "")).strip()
        token = str(env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY") or "").strip()
        model = str(env.get("ANTHROPIC_MODEL", "")).strip()
        managed = bool(data.get("linuxToolboxAiTools", {}).get("managedEnv")) if isinstance(data.get("linuxToolboxAiTools"), dict) else False
        result.update(
            {
                "bifrostBaseUrl": base_url,
                "bifrostToken": token,
                "selectedModel": model,
                "managed": managed,
                "bifrost": bool(base_url or token or managed),
                "accountLabel": "Bifrost/Sotatek" if (base_url or token or managed) else "Claude web login",
            }
        )
        return result

    def tool_path(self, tool):
        path = shutil.which(tool)
        if path:
            return Path(path)

        candidates = [
            BIN_DIR / tool,
        ]
        nvm_dir = HOME / ".nvm/versions/node"
        if nvm_dir.exists():
            candidates.extend(sorted(nvm_dir.glob(f"*/bin/{tool}"), reverse=True))
        local_share = HOME / f".local/share/{tool}"
        if local_share.exists():
            candidates.extend(sorted(local_share.glob(f"versions/{tool}"), reverse=True))
            candidates.extend(sorted(local_share.glob("versions/*"), reverse=True))

        for candidate in candidates:
            try:
                if candidate.exists() and os.access(candidate, os.X_OK):
                    return candidate
            except OSError:
                continue
        return None

    def npm_path(self):
        path = shutil.which("npm")
        if path:
            return Path(path)
        nvm_dir = HOME / ".nvm/versions/node"
        if nvm_dir.exists():
            for candidate in sorted(nvm_dir.glob("*/bin/npm"), reverse=True):
                if candidate.exists() and os.access(candidate, os.X_OK):
                    return candidate
        return None

    def commandEnv(self, config=None, mode="bifrost"):
        if mode.startswith("personal_"):
            return self.personalEnv(config)

        env = dict(os.environ)
        env.update(self.loadClaudeEnv())
        config = config or {}
        base_url = str(config.get("bifrostBaseUrl", "")).strip()
        token = str(config.get("bifrostToken", "")).strip()
        model = str(config.get("selectedModel", "")).strip()
        if base_url:
            env["AITOOLS_BASE_URL"] = base_url
            env["ANTHROPIC_BASE_URL"] = base_url
        if token:
            env["AITOOLS_AUTH_TOKEN"] = token
            env["ANTHROPIC_AUTH_TOKEN"] = token
            env["ANTHROPIC_API_KEY"] = token
        if model:
            env["AITOOLS_MODEL"] = model
            env["ANTHROPIC_MODEL"] = model
        return env

    def personalEnv(self, config=None):
        env = dict(os.environ)
        config = config or {}
        saved_bases = {
            str(config.get("bifrostBaseUrl", "")).strip().rstrip("/"),
            str(self.targetConfig(config, "codexCli").get("bifrostBaseUrl", "")).strip().rstrip("/"),
            str(self.targetConfig(config, "claudeCli").get("bifrostBaseUrl", "")).strip().rstrip("/"),
            str(self.targetConfig(config, "codexVscode").get("bifrostBaseUrl", "")).strip().rstrip("/"),
            str(self.targetConfig(config, "claudeVscode").get("bifrostBaseUrl", "")).strip().rstrip("/"),
        }
        saved_tokens = {
            str(config.get("bifrostToken", "")).strip(),
            str(self.targetConfig(config, "codexCli").get("bifrostToken", "")).strip(),
            str(self.targetConfig(config, "claudeCli").get("bifrostToken", "")).strip(),
            str(self.targetConfig(config, "codexVscode").get("bifrostToken", "")).strip(),
            str(self.targetConfig(config, "claudeVscode").get("bifrostToken", "")).strip(),
        }
        saved_bases.discard("")
        saved_tokens.discard("")
        for key in ("AITOOLS_BASE_URL", "AITOOLS_AUTH_TOKEN", "AITOOLS_MODEL"):
            env.pop(key, None)
        current_base = env.get("ANTHROPIC_BASE_URL", "").strip().rstrip("/")
        if current_base and (current_base in saved_bases or "bifrost" in current_base.lower()):
            env.pop("ANTHROPIC_BASE_URL", None)
        for key in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
            if env.get(key) in saved_tokens:
                env.pop(key, None)
        return env

    def executable_path(self):
        path = shutil.which("aitools")
        if path:
            return Path(path)
        fallback = BIN_DIR / "aitools"
        return fallback if fallback.exists() else None

    def isInstalled(self):
        path = self.executable_path()
        return bool(path and path.exists())

    def desktopLauncherInstalled(self):
        return AITOOLS_DESKTOP.exists()

    def isPinned(self):
        current = parse_gsettings_list(run(["gsettings", "get", "org.gnome.shell", "favorite-apps"], check=False))
        return AITOOLS_DESKTOP_ID in current

    def installDesktopLauncher(self):
        path = self.executable_path()
        if not path:
            raise RuntimeError("aitools was not found in PATH.")
        APP_DIR.mkdir(parents=True, exist_ok=True)
        launcher_path = self.writeWrapper(path)
        AITOOLS_DESKTOP.write_text(
            load_template("desktop/aitools.desktop.tmpl", AITOOLS_PATH=launcher_path),
            encoding="utf-8",
        )
        AITOOLS_DESKTOP.chmod(0o644)
        run(["update-desktop-database", str(APP_DIR)], check=False)

    def writeWrapper(self, aitools_path):
        config = load_app_config().get("aiTools", {})
        if not isinstance(config, dict):
            config = {}
        target = self.targetConfig(config, "claudeCli")
        if target.get("connectionMode") != "bifrost":
            return aitools_path
        base_url = str(target.get("bifrostBaseUrl", "")).strip()
        token = str(target.get("bifrostToken", "")).strip()
        model = str(target.get("selectedModel", "")).strip()
        if not base_url and not token and not model:
            return aitools_path

        BIN_DIR.mkdir(parents=True, exist_ok=True)
        lines = [
            "#!/usr/bin/env bash",
            "set -e",
        ]
        if base_url:
            lines.append(f"export AITOOLS_BASE_URL={shlex.quote(base_url)}")
        if token:
            lines.append(f"export AITOOLS_AUTH_TOKEN={shlex.quote(token)}")
        if model:
            lines.append(f"export AITOOLS_MODEL={shlex.quote(model)}")
        lines.append(f"exec {shlex.quote(str(aitools_path))} \"$@\"")
        AITOOLS_WRAPPER.write_text("\n".join(lines) + "\n", encoding="utf-8")
        AITOOLS_WRAPPER.chmod(0o700)
        return AITOOLS_WRAPPER

    def installTerminalCommands(self, config=None):
        installed = []
        errors = []
        for installer in (self.installCodexCliCommand, self.installClaudeCliCommand):
            try:
                installed.append(installer(config))
            except Exception as error:
                errors.append(str(error))
        if errors and not installed:
            raise RuntimeError("; ".join(errors))
        if errors:
            raise RuntimeError(f"Partial install: {', '.join(installed)}. {'; '.join(errors)}")
        return installed

    def installClaudeCliCommand(self, config=None):
        config = config or {}
        target = self.targetConfig(config, "claudeCli")
        mode = target.get("connectionMode", "bifrost")
        base_url = str(target.get("bifrostBaseUrl", "")).strip()
        token = str(target.get("bifrostToken", "")).strip()
        model = str(target.get("selectedModel", "")).strip()
        if mode == "bifrost" and not base_url:
            raise RuntimeError("Claude CLI Bifrost URL is required.")
        if mode == "bifrost" and not token:
            raise RuntimeError("Claude CLI Bifrost key is required.")

        claude_path = self.tool_path("claude")
        if not claude_path:
            raise RuntimeError("claude CLI was not found in PATH.")

        BIN_DIR.mkdir(parents=True, exist_ok=True)
        if mode == "bifrost":
            env_lines = [
                f"export ANTHROPIC_BASE_URL={shlex.quote(base_url)}",
                f"export ANTHROPIC_AUTH_TOKEN={shlex.quote(token)}",
                f"export ANTHROPIC_API_KEY={shlex.quote(token)}",
            ]
            if model:
                env_lines.append(f"export ANTHROPIC_MODEL={shlex.quote(model)}")
        else:
            env_lines = [
                "unset ANTHROPIC_BASE_URL",
                "unset ANTHROPIC_AUTH_TOKEN",
                "unset ANTHROPIC_API_KEY",
                "unset ANTHROPIC_MODEL",
                "unset AITOOLS_BASE_URL",
                "unset AITOOLS_AUTH_TOKEN",
                "unset AITOOLS_MODEL",
            ]

        biclaude = [
            "#!/usr/bin/env bash",
            "set -e",
            *env_lines,
            f"exec {shlex.quote(str(claude_path))} \"$@\"",
        ]
        BICLAUDE_COMMAND.write_text("\n".join(biclaude) + "\n", encoding="utf-8")
        BICLAUDE_COMMAND.chmod(0o700)
        return "biclaude"

    def installCodexCliCommand(self, config=None):
        config = config or {}
        target = self.targetConfig(config, "codexCli")
        mode = target.get("connectionMode", "bifrost")
        base_url = str(target.get("bifrostBaseUrl", "")).strip()
        token = str(target.get("bifrostToken", "")).strip()
        if mode == "bifrost" and not base_url:
            raise RuntimeError("Codex CLI Bifrost URL is required.")
        if mode == "bifrost" and not token:
            raise RuntimeError("Codex CLI Bifrost key is required.")

        codex_path = self.tool_path("codex")
        if not codex_path:
            raise RuntimeError("codex CLI was not found in PATH.")

        BIN_DIR.mkdir(parents=True, exist_ok=True)
        if mode == "bifrost":
            self.writeCodexBifrostHome(base_url, token, target)

        bicodex = [
            "#!/usr/bin/env bash",
            "set -e",
        ]
        if mode == "bifrost":
            bicodex.append(f"export CODEX_HOME={shlex.quote(str(CODEX_BIFROST_HOME))}")
        else:
            bicodex.append("unset CODEX_HOME")
        bicodex.append(f"exec {shlex.quote(str(codex_path))} \"$@\"")
        BICODEX_COMMAND.write_text("\n".join(bicodex) + "\n", encoding="utf-8")
        BICODEX_COMMAND.chmod(0o700)
        return "bicodex"

    def applyRealtimeConfig(self, config=None):
        config = config or {}
        codex = self.targetConfig(config, "codexCli")
        codex_base = str(codex.get("bifrostBaseUrl", "")).strip()
        codex_token = str(codex.get("bifrostToken", "")).strip()
        if codex.get("connectionMode") == "bifrost" and codex_base and codex_token:
            self.writeCodexBifrostHome(codex_base, codex_token, codex)
        if BICODEX_COMMAND.exists() and (
            codex.get("connectionMode") == "web" or (codex_base and codex_token)
        ):
            self.installCodexCliCommand(config)
        if BICLAUDE_COMMAND.exists():
            claude = self.targetConfig(config, "claudeCli")
            if claude.get("connectionMode") == "web" or (
                str(claude.get("bifrostBaseUrl", "")).strip() and str(claude.get("bifrostToken", "")).strip()
            ):
                self.installClaudeCliCommand(config)
        codex_vscode = self.targetConfig(config, "codexVscode")
        codex_vscode_base = str(codex_vscode.get("bifrostBaseUrl", "")).strip()
        codex_vscode_token = str(codex_vscode.get("bifrostToken", "")).strip()
        if codex_vscode.get("connectionMode") == "bifrost" and codex_vscode_base and codex_vscode_token:
            self.writeCodexBifrostHome(codex_vscode_base, codex_vscode_token, codex_vscode, CODEX_VSCODE_HOME)
        elif codex_vscode.get("connectionMode") == "web":
            self.clearManagedCodexConfig(CODEX_VSCODE_CONFIG)

        claude_vscode = self.targetConfig(config, "claudeVscode")
        if claude_vscode.get("connectionMode") == "bifrost":
            self.writeClaudeSettingsEnv(claude_vscode)
        else:
            self.clearManagedClaudeEnv(claude_vscode)

    def writeCodexBifrostHome(self, base_url, token, config=None, codex_home=None):
        """Write a dedicated CODEX_HOME for Bifrost so the personal ~/.codex
        used by VS Code keeps its web login untouched."""
        config = config or {}
        codex_home = codex_home or CODEX_BIFROST_HOME
        model = str(config.get("selectedModel", "")).strip()
        # Codex's OpenAI-compatible endpoint lives under /openai/v1; the stored
        # Bifrost base URL points at the Anthropic path, so swap the suffix.
        trimmed = base_url.rstrip("/")
        for suffix in ("/anthropic", "/openai/v1", "/openai", "/v1"):
            if trimmed.endswith(suffix):
                trimmed = trimmed[: -len(suffix)]
                break
        codex_base = f"{trimmed}/openai/v1"
        codex_model = model if model.startswith("fridaycodex/") else "fridaycodex/gpt-5.5"

        codex_home.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# {AITOOLS_MANAGED_MARKER}",
            "approvals_reviewer = \"user\"",
            "service_tier = \"default\"",
            f"model = {self._toml_str(codex_model)}",
            "model_provider = \"sotatek\"",
            "model_reasoning_effort = \"high\"",
            "",
            "[model_providers.sotatek]",
            "name = \"Sotatek Proxy\"",
            f"base_url = {self._toml_str(codex_base)}",
            f"experimental_bearer_token = {self._toml_str(token)}",
            "wire_api = \"responses\"",
            "",
            f"[projects.{self._toml_str(str(HOME))}]",
            "trust_level = \"trusted\"",
            "",
            "[notice]",
            "hide_rate_limit_model_nudge = true",
        ]
        config_path = codex_home / "config.toml"
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        config_path.chmod(0o600)

    def clearManagedCodexConfig(self, config_path):
        try:
            text = config_path.read_text(encoding="utf-8")
        except Exception:
            return
        if AITOOLS_MANAGED_MARKER in text:
            config_path.unlink(missing_ok=True)

    def writeClaudeSettingsEnv(self, target):
        base_url = str(target.get("bifrostBaseUrl", "")).strip()
        token = str(target.get("bifrostToken", "")).strip()
        model = str(target.get("selectedModel", "")).strip()
        if not base_url or not token:
            return
        try:
            data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        env = data.get("env")
        if not isinstance(env, dict):
            env = {}
        env["ANTHROPIC_BASE_URL"] = base_url
        env["ANTHROPIC_AUTH_TOKEN"] = token
        env["ANTHROPIC_API_KEY"] = token
        if model:
            env["ANTHROPIC_MODEL"] = model
        data["env"] = env
        data["linuxToolboxAiTools"] = {"managedEnv": True}
        CLAUDE_HOME.mkdir(parents=True, exist_ok=True)
        CLAUDE_SETTINGS.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        CLAUDE_SETTINGS.chmod(0o600)

    def clearManagedClaudeEnv(self, target=None):
        try:
            data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        env = data.get("env")
        if not isinstance(env, dict):
            return
        target = target or {}
        saved_values = {
            str(target.get("bifrostBaseUrl", "")).strip(),
            str(target.get("bifrostToken", "")).strip(),
            str(target.get("selectedModel", "")).strip(),
        }
        managed = data.get("linuxToolboxAiTools", {}).get("managedEnv") if isinstance(data.get("linuxToolboxAiTools"), dict) else False
        for key in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
            value = str(env.get(key, "")).strip()
            if managed or value in saved_values or (key == "ANTHROPIC_BASE_URL" and "bifrost" in value.lower()):
                env.pop(key, None)
        if env:
            data["env"] = env
        else:
            data.pop("env", None)
        if managed:
            data.pop("linuxToolboxAiTools", None)
        CLAUDE_SETTINGS.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        CLAUDE_SETTINGS.chmod(0o600)

    def restoreOriginal(self, config=None):
        config = config or {}
        BICODEX_COMMAND.unlink(missing_ok=True)
        BICLAUDE_COMMAND.unlink(missing_ok=True)
        try:
            self.removeDesktopLauncher()
        except Exception:
            AITOOLS_DESKTOP.unlink(missing_ok=True)
            AITOOLS_WRAPPER.unlink(missing_ok=True)
        self.clearManagedCodexConfig(CODEX_BIFROST_HOME / "config.toml")
        self.clearManagedCodexConfig(CODEX_VSCODE_CONFIG)
        for target in ("claudeCli", "claudeVscode"):
            self.clearManagedClaudeEnv(self.targetConfig(config, target))

    @staticmethod
    def _toml_str(value):
        escaped = str(value).replace("\\", "\\\\").replace("\"", "\\\"")
        return f"\"{escaped}\""

    def terminalCommandsInstalled(self):
        return BICLAUDE_COMMAND.exists() and BICODEX_COMMAND.exists()

    def removeDesktopLauncher(self):
        self.unpinFromDock()
        AITOOLS_DESKTOP.unlink(missing_ok=True)
        AITOOLS_WRAPPER.unlink(missing_ok=True)
        run(["update-desktop-database", str(APP_DIR)], check=False)

    def pinToDock(self):
        self.installDesktopLauncher()
        current = parse_gsettings_list(run(["gsettings", "get", "org.gnome.shell", "favorite-apps"], check=False))
        filtered = [item for item in current if item != AITOOLS_DESKTOP_ID]
        run(["gsettings", "set", "org.gnome.shell", "favorite-apps", format_gsettings_list([AITOOLS_DESKTOP_ID] + filtered)])

    def unpinFromDock(self):
        current = parse_gsettings_list(run(["gsettings", "get", "org.gnome.shell", "favorite-apps"], check=False))
        filtered = [item for item in current if item != AITOOLS_DESKTOP_ID]
        if filtered != current:
            run(["gsettings", "set", "org.gnome.shell", "favorite-apps", format_gsettings_list(filtered)])

    def terminalCommand(self, extra_args=None, raw=False):
        if raw:
            args = list(extra_args or [])
        else:
            path = self.executable_path()
            if not path:
                raise RuntimeError("aitools was not found in PATH.")
            args = [str(path), *(extra_args or [])]
        if not args:
            raise RuntimeError("No command was provided.")
        candidates = (
            ("x-terminal-emulator", ["x-terminal-emulator", "-e", *args]),
            ("gnome-terminal", ["gnome-terminal", "--", *args]),
            ("kgx", ["kgx", "--", *args]),
            ("konsole", ["konsole", "-e", *args]),
            ("xfce4-terminal", ["xfce4-terminal", "-e", *args]),
            ("xterm", ["xterm", "-e", *args]),
        )
        for binary, command in candidates:
            if shutil.which(binary):
                return command
        raise RuntimeError("No terminal emulator was found.")

    def setupCodexCli(self):
        npm = self.npm_path()
        if not npm:
            raise RuntimeError("npm was not found. Install Node.js/npm or nvm first.")
        command = (
            "set -e; "
            'export NVM_DIR="$HOME/.nvm"; '
            '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; '
            "npm install -g @openai/codex; "
            "codex --version; "
            'printf "\\nCodex CLI setup finished. Press Enter to close..."; '
            "read _"
        )
        subprocess.Popen(
            self.terminalCommand(["bash", "-lc", command], raw=True),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def launchInteractive(self, model=None, chat=False, config=None):
        extra_args = []
        if chat:
            extra_args.append("--chat")
        if model:
            extra_args.extend(["-m", model])
        subprocess.Popen(
            self.terminalCommand(extra_args),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=self.commandEnv(config, "bifrost"),
        )

    def runPrompt(self, prompt, model=None, system_prompt=None, max_tokens=None, temperature=None, config=None):
        path = self.executable_path()
        if not path:
            raise RuntimeError("aitools was not found in PATH.")
        command = [str(path), "-p", prompt, "--no-stream"]
        if model:
            command.extend(["-m", model])
        if system_prompt:
            command.extend(["--system", system_prompt])
        if max_tokens:
            command.extend(["--max-tokens", str(max_tokens)])
        if temperature is not None:
            command.extend(["--temperature", str(temperature)])
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600,
            env=self.commandEnv(config, "bifrost"),
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "aitools command failed").strip())
        return completed.stdout.strip()

    def supportedModels(self, config=None):
        path = self.executable_path()
        if not path:
            raise RuntimeError("aitools was not found in PATH.")
        completed = subprocess.run(
            [str(path), "--list"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            env=self.commandEnv(config, "bifrost"),
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "aitools model list failed").strip())
        return self.parseModels(completed.stdout)

    def launchPersonal(self, tool, model=None):
        binary = self.tool_path(tool)
        if not binary:
            raise RuntimeError(f"{tool} CLI was not found in PATH.")
        if tool == "claude":
            args = [str(binary)]
            if model:
                args.extend(["--model", model])
        elif tool == "codex":
            args = [str(binary)]
            if model:
                args.extend(["--model", model])
        else:
            raise RuntimeError(f"Unsupported personal AI tool: {tool}")
        subprocess.Popen(
            self.terminalCommand(args, raw=True),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=self.personalEnv(load_app_config().get("aiTools", {})),
        )

    def launchLogin(self, tool):
        if tool == "codex":
            binary = self.tool_path("codex")
            args = [str(binary), "login"] if binary else []
        elif tool == "claude":
            binary = self.tool_path("claude")
            args = [str(binary), "auth", "login"] if binary else []
        else:
            raise RuntimeError(f"Unsupported login tool: {tool}")
        if not args:
            raise RuntimeError(f"{tool} CLI was not found in PATH.")
        subprocess.Popen(
            self.terminalCommand(args, raw=True),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=self.personalEnv(load_app_config().get("aiTools", {})),
        )

    def runPersonalPrompt(self, tool, prompt, model=None, system_prompt=None):
        binary = self.tool_path(tool)
        if not binary:
            raise RuntimeError(f"{tool} CLI was not found in PATH.")
        if tool == "claude":
            command = [str(binary), "-p"]
            if model:
                command.extend(["--model", model])
            if system_prompt:
                command.extend(["--system-prompt", system_prompt])
            command.append(prompt)
        elif tool == "codex":
            command = [str(binary), "exec"]
            if model:
                command.extend(["--model", model])
            if system_prompt:
                prompt = f"System instructions:\n{system_prompt}\n\nUser prompt:\n{prompt}"
            command.append(prompt)
        else:
            raise RuntimeError(f"Unsupported personal AI tool: {tool}")

        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600,
            env=self.personalEnv(load_app_config().get("aiTools", {})),
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or f"{tool} command failed").strip())
        return completed.stdout.strip()

    def parseModels(self, output):
        models = []
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line or line.lower().startswith(("supported models", "pick a model")):
                continue
            if ")" in line:
                number, candidate = line.split(")", 1)
                if number.strip().isdigit():
                    line = candidate.strip()
            if line.startswith("- "):
                line = line[2:].strip()
            if line and line not in models:
                models.append(line)
        return models

    def loadClaudeEnv(self):
        path = CLAUDE_SETTINGS
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        env = data.get("env", {})
        if not isinstance(env, dict):
            return {}
        return {str(key): str(value) for key, value in env.items() if value is not None}

    def configStatus(self, config=None):
        config = config or {}
        targets = {target: self.actualTargetConfig(config, target) for target, _label, _tool, _path in AITOOLS_TARGETS}
        codex_cli = targets["codexCli"]
        claude_cli = targets["claudeCli"]
        env = self.commandEnv(claude_cli, "bifrost")
        saved_base = any(str(item.get("bifrostBaseUrl", "")).strip() for item in targets.values())
        saved_token = any(str(item.get("bifrostToken", "")).strip() for item in targets.values())
        target_status = {}
        for target, _label, tool, path in AITOOLS_TARGETS:
            target_config = targets[target]
            mode = target_config.get("connectionMode", self.defaultMode(target))
            bifrost_ready = bool(target_config.get("bifrostBaseUrl") and target_config.get("bifrostToken"))
            binary_ready = self.tool_path(tool) is not None
            if target == "codexCli":
                runtime_ready = BICODEX_COMMAND.exists()
                config_ready = bool(target_config.get("configPath") and Path(str(target_config.get("configPath"))).exists())
                if mode == "web":
                    config_ready = self.pathHasFiles(CODEX_VSCODE_HOME)
            elif target == "claudeCli":
                runtime_ready = BICLAUDE_COMMAND.exists()
                config_ready = bifrost_ready if mode == "bifrost" else self.pathHasFiles(CLAUDE_HOME)
            elif target == "codexVscode":
                runtime_ready = CODEX_VSCODE_CONFIG.exists() if mode == "bifrost" else self.pathHasFiles(CODEX_VSCODE_HOME)
                config_ready = runtime_ready
            else:
                runtime_ready = CLAUDE_SETTINGS.exists() if mode == "bifrost" else self.pathHasFiles(CLAUDE_HOME)
                config_ready = runtime_ready
            target_status[target] = {
                "mode": mode,
                "bifrost": bifrost_ready,
                "binary": binary_ready,
                "runtime": runtime_ready,
                "config": config_ready,
                "accountLabel": target_config.get("accountLabel", ""),
                "source": target_config.get("source", ""),
                "model": target_config.get("selectedModel", ""),
                "baseUrl": target_config.get("bifrostBaseUrl", ""),
                "path": str(path),
            }
        return {
            "mode": config.get("connectionMode", "bifrost"),
            "baseUrl": bool(env.get("ANTHROPIC_BASE_URL") or env.get("AITOOLS_BASE_URL")),
            "token": bool(
                env.get("ANTHROPIC_AUTH_TOKEN")
                or env.get("ANTHROPIC_API_KEY")
                or env.get("AITOOLS_AUTH_TOKEN")
            ),
            "savedBaseUrl": saved_base,
            "savedToken": saved_token,
            "defaultModel": env.get("ANTHROPIC_MODEL") or env.get("AITOOLS_MODEL") or "",
            "personalClaude": self.tool_path("claude") is not None,
            "personalCodex": self.tool_path("codex") is not None,
            "targets": target_status,
            "codexCli": target_status["codexCli"]["runtime"]
            and (
                (target_status["codexCli"]["mode"] == "web" and target_status["codexCli"]["config"])
                or (target_status["codexCli"]["mode"] == "bifrost" and target_status["codexCli"]["bifrost"])
            ),
            "claudeCli": target_status["claudeCli"]["runtime"]
            and (
                (target_status["claudeCli"]["mode"] == "web" and target_status["claudeCli"]["config"])
                or (target_status["claudeCli"]["mode"] == "bifrost" and target_status["claudeCli"]["bifrost"])
            ),
            "codexCliCommand": BICODEX_COMMAND.exists(),
            "claudeCliCommand": BICLAUDE_COMMAND.exists(),
            "codexCliHome": (CODEX_BIFROST_HOME / "config.toml").exists(),
            "codexVscodeConfig": CODEX_VSCODE_CONFIG.exists(),
            "claudeVscodeConfig": CLAUDE_SETTINGS.exists(),
            "codexVscodeAccount": targets["codexVscode"].get("accountLabel", ""),
            "claudeVscodeAccount": targets["claudeVscode"].get("accountLabel", ""),
        }


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
        self.syncing_aitools_fields = False
        self.aitools_service = AIToolsService()
        self.mouse_service = MouseMovementService()
        self.vietnamese_service = VietnameseInputService(lambda message: self.log(message))
        self.mouse_install_process = None
        self.mouse_install_timer_id = None
        self.mouse_permission_fix_process = None
        self.mouse_permission_pending = None
        self.vietnamese_install_process = None
        self.vietnamese_install_timer_id = None

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
        aitools_scroller, aitools_tab = self.create_tab_page()
        chrome_scroller, chrome_tab = self.create_tab_page()
        mouse_scroller, mouse_tab = self.create_tab_page()
        clipboard_scroller, clipboard_tab = self.create_tab_page()
        vietnamese_scroller, vietnamese_tab = self.create_tab_page()
        dock_scroller, dock_tab = self.create_tab_page()

        self.stack.add_titled(main_scroller, "overview", "Overview")
        self.stack.add_titled(aitools_scroller, "aitools", "AI Tools")
        self.stack.add_titled(chrome_scroller, "chrome", "Chrome Profiles")
        self.stack.add_titled(mouse_scroller, "mouse", "Mouse")
        self.stack.add_titled(clipboard_scroller, "clipboard", "Clipboard")
        self.stack.add_titled(vietnamese_scroller, "vietnamese", "Vietnamese Input")
        self.stack.add_titled(dock_scroller, "dock", "Dock Style")

        for name, title, icon in (
            ("overview", "Overview", "view-dashboard-symbolic"),
            ("aitools", "AI Tools", "applications-science-symbolic"),
            ("chrome", "Chrome Profiles", "web-browser-symbolic"),
            ("mouse", "Mouse", "input-mouse-symbolic"),
            ("clipboard", "Clipboard", "edit-paste-symbolic"),
            ("vietnamese", "Vietnamese Input", "input-keyboard-symbolic"),
            ("dock", "Dock Style", "preferences-desktop-symbolic"),
        ):
            self.nav_list.add(self.create_nav_row(name, title, icon))

        intro = Gtk.Label()
        intro.set_markup("<span size='large'><b>Overview</b></span>")
        intro.set_xalign(0)
        intro.set_line_wrap(True)
        intro.get_style_context().add_class("page-title")
        main_tab.pack_start(intro, False, False, 0)

        description = Gtk.Label(
            label="System overview for AI tools, profile dock icons, clipboard history, mouse movement, and dock behavior."
        )
        description.set_xalign(0)
        description.set_line_wrap(True)
        description.get_style_context().add_class("page-description")
        main_tab.pack_start(description, False, False, 0)

        summary_card = self.create_card("At a Glance", "Current setup status for the main tools.")
        main_tab.pack_start(summary_card, False, False, 0)
        self.overview_summary_box = Gtk.FlowBox()
        self.overview_summary_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.overview_summary_box.set_max_children_per_line(4)
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
                ("aitools", "AI Tools", "Remove managed AI wrappers/config only.", self.on_aitools_restore_original),
                ("chrome", "Chrome", "Remove profile launchers and hover previews.", self.on_chrome_restore_original),
                ("mouse", "Mouse", "Restore original maccel mouse settings.", self.on_mouse_restore),
                ("clipboard", "Clipboard", "Restore original clipboard startup and shortcuts.", self.on_clipboard_restore_original),
                ("vietnamese", "Vietnamese Input", "Restore original input method settings.", self.on_vietnamese_restore),
                ("dock_layout", "Dock Layout", "Restore original dock layout.", self.on_dock_restore_layout),
                ("dock_style", "Dock Click", "Restore original dock click behavior.", self.on_dock_restore_style),
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

        aitools_intro = Gtk.Label()
        aitools_intro.set_markup("<span size='large'><b>AI Tools</b></span>")
        aitools_intro.set_xalign(0)
        aitools_intro.set_line_wrap(True)
        aitools_intro.get_style_context().add_class("page-title")
        aitools_tab.pack_start(aitools_intro, False, False, 0)

        aitools_description = Gtk.Label(
            label="Manage separate configs for Codex CLI, Claude CLI, Codex VS Code, and Claude VS Code without mixing Bifrost keys with web-login accounts."
        )
        aitools_description.set_xalign(0)
        aitools_description.set_line_wrap(True)
        aitools_description.get_style_context().add_class("page-description")
        aitools_tab.pack_start(aitools_description, False, False, 0)

        aitools_dependency_card = self.create_card("Status Check", "Required commands and generated wrappers.")
        aitools_tab.pack_start(aitools_dependency_card, False, False, 0)
        self.aitools_dependency_pills = self.create_status_table(
            aitools_dependency_card,
            (
                ("codex", "Codex CLI"),
                ("claude", "Claude CLI"),
                ("bicodex", "bicodex wrapper"),
                ("biclaude", "biclaude wrapper"),
                ("bifrost", "Bifrost config"),
            ),
        )

        aitools_guide_card = self.create_card("Config Split", "Use the overview table first; open details only when you need to edit.")
        aitools_tab.pack_start(aitools_guide_card, False, False, 0)
        aitools_guide_card.set_no_show_all(True)
        aitools_guide_card.hide()

        self.aitools_guide_label = Gtk.Label(
            label=(
                "Each row shows whether that target is configured and which mode it uses.\n"
                "Click Edit to switch Bifrost/Web login or change keys and account labels.\n"
                "Use Bifrost Token Usage to check API-key token usage in the portal."
            )
        )
        self.aitools_guide_label.set_xalign(0)
        self.aitools_guide_label.set_line_wrap(True)
        aitools_guide_card.pack_start(self.aitools_guide_label, False, False, 0)

        aitools_summary_card = self.create_card("Configuration", "Edit only the target that needs setup.")
        aitools_tab.pack_start(aitools_summary_card, False, False, 0)
        self.create_aitools_summary_table(aitools_summary_card)

        aitools_actions_card = self.create_card("Next Step", "Only actions needed for the current state are shown.")
        aitools_tab.pack_start(aitools_actions_card, False, False, 0)
        self.aitools_actions_card = aitools_actions_card
        aitools_actions_card.set_no_show_all(True)
        aitools_actions_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        aitools_actions_card.pack_start(aitools_actions_grid, False, False, 0)

        self.aitools_install_codex_command_button = self.create_primary_button(
            "Install bicodex",
            "Create or refresh ~/.local/bin/bicodex using the current Codex CLI mode.",
        )
        self.aitools_install_codex_command_button.connect("clicked", self.on_aitools_install_codex_command)
        aitools_actions_grid.attach(self.aitools_install_codex_command_button, 0, 0, 1, 1)

        self.aitools_install_claude_command_button = self.create_primary_button(
            "Install biclaude",
            "Create or refresh ~/.local/bin/biclaude using the current Claude CLI mode.",
        )
        self.aitools_install_claude_command_button.connect("clicked", self.on_aitools_install_claude_command)
        aitools_actions_grid.attach(self.aitools_install_claude_command_button, 1, 0, 1, 1)

        self.aitools_install_codex_button = self.create_primary_button(
            "Install Codex CLI",
            "Run npm install -g @openai/codex in a terminal.",
        )
        self.aitools_install_codex_button.connect("clicked", self.on_aitools_install_codex)
        aitools_actions_grid.attach(self.aitools_install_codex_button, 0, 1, 1, 1)

        self.aitools_bifrost_portal_button = self.create_primary_button(
            "Bifrost Token Usage",
            f"Open {BIFROST_PORTAL_URL} to check token usage for your Bifrost API key.",
        )
        self.aitools_bifrost_portal_button.connect("clicked", self.on_aitools_open_bifrost_portal)
        aitools_actions_grid.attach(self.aitools_bifrost_portal_button, 1, 1, 1, 1)

        self.aitools_restore_button = Gtk.Button(label="Restore Original")
        self.aitools_restore_button.set_no_show_all(True)
        self.aitools_restore_button.set_tooltip_text("Remove Linux Toolbox AI wrappers and managed Bifrost config without deleting personal web logins.")
        self.aitools_restore_button.connect("clicked", self.on_aitools_restore_original)
        aitools_actions_grid.attach(self.aitools_restore_button, 0, 2, 2, 1)

        aitools_status_card = self.create_card("Current Status", "Live status for the split CLI and VS Code configs.")
        aitools_tab.pack_start(aitools_status_card, False, False, 0)
        aitools_status_card.set_no_show_all(True)
        aitools_status_card.hide()

        self.aitools_status_pill = self.make_pill("Unknown", "warn")
        aitools_status_card.pack_start(self.aitools_status_pill, False, False, 0)

        self.aitools_status_label = Gtk.Label()
        self.aitools_status_label.set_xalign(0)
        self.aitools_status_label.set_line_wrap(True)
        aitools_status_card.pack_start(self.aitools_status_label, False, False, 0)

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

        dock_intro = Gtk.Label()
        dock_intro.set_markup("<span size='large'><b>Dock Style</b></span>")
        dock_intro.set_xalign(0)
        dock_intro.set_line_wrap(True)
        dock_intro.get_style_context().add_class("page-title")
        dock_tab.pack_start(dock_intro, False, False, 0)

        dock_description = Gtk.Label(
            label="Set the Ubuntu Dock layout and click behavior to match your workflow."
        )
        dock_description.set_xalign(0)
        dock_description.set_line_wrap(True)
        dock_description.get_style_context().add_class("page-description")
        dock_tab.pack_start(dock_description, False, False, 0)

        dock_status_card = self.create_card("Status Check", "Dash-to-Dock dependency and current behavior.")
        dock_tab.pack_start(dock_status_card, False, False, 0)
        self.dock_status_pills = self.create_status_table(
            dock_status_card,
            (
                ("schema", "Dash-to-Dock schema"),
                ("layout", "Dock layout"),
                ("click", "Click style"),
                ("restore", "Restore point"),
            ),
        )

        layout_card = self.create_card("Dock Layout", "Set the Ubuntu Dock once to a Windows-style horizontal taskbar.")
        dock_tab.pack_start(layout_card, False, False, 0)

        self.dock_layout_switch = self.create_feature_switch(
            layout_card,
            "Windows Taskbar Layout",
            "Turn on the bottom Windows-style dock. Turn off to restore the Ubuntu default dock layout.",
            self.on_dock_layout_switch_toggled,
        )

        layout_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        layout_card.pack_start(layout_grid, False, False, 0)

        self.dock_windows_button = self.create_primary_button(
            "Apply Windows Taskbar",
            "Move the dock to the bottom, stretch it across the screen, and keep it visible.",
        )
        self.dock_windows_button.connect("clicked", self.on_dock_windows_taskbar)
        layout_grid.attach(self.dock_windows_button, 0, 0, 1, 1)
        self.dock_windows_button.set_no_show_all(True)
        self.dock_windows_button.hide()

        self.dock_restore_button = Gtk.Button(label="Restore Original")
        self.dock_restore_button.set_no_show_all(True)
        self.dock_restore_button.set_tooltip_text("Restore the dock layout saved before Linux Toolbox changed it.")
        self.dock_restore_button.connect("clicked", self.on_dock_restore_layout)
        layout_grid.attach(self.dock_restore_button, 1, 0, 1, 1)

        self.dock_layout_status_label = Gtk.Label()
        self.dock_layout_status_label.set_xalign(0)
        self.dock_layout_status_label.set_line_wrap(True)
        layout_card.pack_start(self.dock_layout_status_label, False, False, 0)

        style_card = self.create_card("Dock Click Style", "Choose how a normal left-click on a dock icon behaves.")
        dock_tab.pack_start(style_card, False, False, 0)

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

        self.style_restore_button = Gtk.Button(label="Restore Original")
        self.style_restore_button.set_no_show_all(True)
        self.style_restore_button.set_tooltip_text("Restore the dock click behavior saved before Linux Toolbox changed it.")
        self.style_restore_button.connect("clicked", self.on_dock_restore_style)
        style_grid.attach(self.style_restore_button, 0, 2, 2, 1)

        self.style_description = Gtk.Label()
        self.style_description.set_xalign(0)
        self.style_description.set_line_wrap(True)
        style_card.pack_start(self.style_description, False, False, 0)

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

        vietnamese_intro = Gtk.Label()
        vietnamese_intro.set_markup("<span size='large'><b>Vietnamese Input</b></span>")
        vietnamese_intro.set_xalign(0)
        vietnamese_intro.set_line_wrap(True)
        vietnamese_intro.get_style_context().add_class("page-title")
        vietnamese_tab.pack_start(vietnamese_intro, False, False, 0)

        vietnamese_description = Gtk.Label(
            label="Set up Vietnamese typing to feel closer to Windows UniKey."
        )
        vietnamese_description.set_xalign(0)
        vietnamese_description.set_line_wrap(True)
        vietnamese_description.get_style_context().add_class("page-description")
        vietnamese_tab.pack_start(vietnamese_description, False, False, 0)

        vietnamese_powered = Gtk.Label(label="UniKey-like Vietnamese Input - Powered by ibus-bamboo")
        vietnamese_powered.set_xalign(0)
        vietnamese_powered.get_style_context().add_class("section-subtitle")
        vietnamese_tab.pack_start(vietnamese_powered, False, False, 0)

        vietnamese_status_card = self.create_card("Status", "Current Vietnamese input setup.")
        vietnamese_tab.pack_start(vietnamese_status_card, False, False, 0)

        vietnamese_grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        vietnamese_status_card.pack_start(vietnamese_grid, False, False, 0)
        self.vietnamese_status_pill = self.make_pill("Unknown", "warn")
        self.vietnamese_ibus_pill = self.make_pill("Unknown", "warn")
        self.vietnamese_bamboo_pill = self.make_pill("Unknown", "warn")
        self.vietnamese_framework_pill = self.make_pill("Unknown", "warn")
        self.vietnamese_session_pill = self.make_pill("Unknown", "warn")
        self.vietnamese_source_pill = self.make_pill("Unknown", "warn")
        self.vietnamese_mode_pill = self.make_pill("Telex", "ok")
        for row_index, (label_text, pill) in enumerate(
            (
                ("Overall", self.vietnamese_status_pill),
                ("IBus", self.vietnamese_ibus_pill),
                ("ibus-bamboo", self.vietnamese_bamboo_pill),
                ("Framework", self.vietnamese_framework_pill),
                ("Session", self.vietnamese_session_pill),
                ("Input source", self.vietnamese_source_pill),
            )
        ):
            label = Gtk.Label(label=label_text)
            label.set_xalign(0)
            vietnamese_grid.attach(label, 0, row_index, 1, 1)
            vietnamese_grid.attach(pill, 1, row_index, 1, 1)

        self.vietnamese_status_label = Gtk.Label()
        self.vietnamese_status_label.set_xalign(0)
        self.vietnamese_status_label.set_line_wrap(True)
        vietnamese_status_card.pack_start(self.vietnamese_status_label, False, False, 0)

        vietnamese_actions_card = self.create_card("Actions", "Install, fix, restart, or restore Vietnamese input.")
        vietnamese_tab.pack_start(vietnamese_actions_card, False, False, 0)
        self.vietnamese_actions_card = vietnamese_actions_card
        vietnamese_actions_card.set_no_show_all(True)
        vietnamese_actions = Gtk.Grid(column_spacing=10, row_spacing=10)
        vietnamese_actions_card.pack_start(vietnamese_actions, False, False, 0)

        self.vietnamese_check_button = self.create_primary_button("Check", "Run Vietnamese input diagnostics.")
        self.vietnamese_check_button.connect("clicked", self.on_vietnamese_check)
        vietnamese_actions.attach(self.vietnamese_check_button, 0, 0, 1, 1)

        self.vietnamese_install_button = self.create_primary_button(
            "Install UniKey-like Vietnamese Input",
            "Install IBus and ibus-bamboo with authentication.",
        )
        self.vietnamese_install_button.connect("clicked", self.on_vietnamese_install)
        vietnamese_actions.attach(self.vietnamese_install_button, 1, 0, 1, 1)

        self.vietnamese_apply_button = self.create_primary_button(
            "Apply UniKey-like Fixes",
            "Set IBus, add Bamboo input source, back up settings, and restart IBus.",
        )
        self.vietnamese_apply_button.connect("clicked", self.on_vietnamese_apply_fixes)
        vietnamese_actions.attach(self.vietnamese_apply_button, 0, 1, 1, 1)

        self.vietnamese_restart_button = self.create_primary_button(
            "Restart Input Method",
            "Restart IBus, with a daemon fallback if needed.",
        )
        self.vietnamese_restart_button.connect("clicked", self.on_vietnamese_restart)
        vietnamese_actions.attach(self.vietnamese_restart_button, 1, 1, 1, 1)

        self.vietnamese_restore_button = Gtk.Button(label="Restore Original")
        self.vietnamese_restore_button.set_no_show_all(True)
        self.vietnamese_restore_button.set_tooltip_text("Restore Vietnamese input settings saved before Linux Toolbox changed them.")
        self.vietnamese_restore_button.connect("clicked", self.on_vietnamese_restore)
        vietnamese_actions.attach(self.vietnamese_restore_button, 0, 2, 2, 1)

        self.vietnamese_install_progress = Gtk.ProgressBar()
        self.vietnamese_install_progress.set_no_show_all(True)
        vietnamese_actions_card.pack_start(self.vietnamese_install_progress, False, False, 0)

        compatibility_card = self.create_card("Compatibility Fixes", "Safe recommendations for common app input issues.")
        vietnamese_tab.pack_start(compatibility_card, False, False, 0)
        compatibility_card.set_no_show_all(True)
        compatibility_card.hide()
        self.vietnamese_compatibility_card = compatibility_card
        self.vietnamese_compatibility_label = Gtk.Label()
        self.vietnamese_compatibility_label.set_xalign(0)
        self.vietnamese_compatibility_label.set_line_wrap(True)
        compatibility_card.pack_start(self.vietnamese_compatibility_label, False, False, 0)

        vietnamese_log_card = self.create_card("Live Log", "Vietnamese input check, install, and fix output.")
        vietnamese_tab.pack_start(vietnamese_log_card, True, True, 0)
        vietnamese_log_card.set_no_show_all(True)
        vietnamese_log_card.hide()
        self.vietnamese_log_card = vietnamese_log_card
        self.vietnamese_log_view = Gtk.TextView()
        self.vietnamese_log_view.set_editable(False)
        self.vietnamese_log_view.set_cursor_visible(False)
        self.vietnamese_log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.vietnamese_log_view.set_monospace(True)
        vietnamese_log_scroller = Gtk.ScrolledWindow()
        vietnamese_log_scroller.set_min_content_height(72)
        vietnamese_log_scroller.add(self.vietnamese_log_view)
        vietnamese_log_card.pack_start(vietnamese_log_scroller, True, True, 0)

        self.load_aitools_account_fields()
        self.refresh_compatibility()
        self.refresh_current_style()
        self.refresh_dock_layout_state()
        self.refresh_aitools_state()
        self.refresh_profiles()
        self.refresh_feature_state()
        self.refresh_mouse_movement_state()
        self.refresh_vietnamese_input_state()
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

    def create_aitools_entry_row(self, grid, row, label_text, placeholder="", secret=False):
        label = Gtk.Label(label=label_text)
        label.set_xalign(0)
        grid.attach(label, 0, row, 1, 1)

        entry = Gtk.Entry()
        entry.set_placeholder_text(placeholder)
        entry.set_hexpand(True)
        if secret:
            entry.set_visibility(False)
        entry.connect("changed", self.on_aitools_field_changed)
        grid.attach(entry, 1, row, 3, 1)
        return entry

    def create_aitools_mode_row(self, grid, row, label_text="Mode"):
        label = Gtk.Label(label=label_text)
        label.set_xalign(0)
        grid.attach(label, 0, row, 1, 1)

        combo = Gtk.ComboBoxText()
        combo.append("bifrost", "Bifrost")
        combo.append("web", "Web login")
        combo.set_active_id("bifrost")
        combo.set_hexpand(True)
        combo.connect("changed", self.on_aitools_field_changed)
        grid.attach(combo, 1, row, 3, 1)
        return combo

    def create_aitools_path_row(self, grid, row, label_text, path):
        label = Gtk.Label(label=label_text)
        label.set_xalign(0)
        grid.attach(label, 0, row, 1, 1)

        value = Gtk.Label(label=str(path))
        value.set_xalign(0)
        value.set_selectable(True)
        value.set_line_wrap(True)
        value.get_style_context().add_class("section-subtitle")
        grid.attach(value, 1, row, 3, 1)
        return value

    def create_aitools_summary_table(self, parent):
        grid = Gtk.Grid(column_spacing=18, row_spacing=10)
        grid.set_column_homogeneous(False)
        grid.get_style_context().add_class("data-grid")
        headers = ("Status", "Target", "Mode", "Config", "Runtime", "")
        for column, text in enumerate(headers):
            label = Gtk.Label()
            label.set_markup(f"<b>{GLib.markup_escape_text(text)}</b>")
            label.set_xalign(0)
            label.set_halign(Gtk.Align.START)
            label.set_valign(Gtk.Align.CENTER)
            label.get_style_context().add_class("table-header")
            grid.attach(label, column, 0, 1, 1)

        self.aitools_summary_labels = {}
        for row, (target, title, _tool, _path) in enumerate(AITOOLS_TARGETS, start=1):
            status = self.make_pill("Setup", "warn")
            status.set_size_request(96, -1)
            grid.attach(status, 0, row, 1, 1)

            title_label = Gtk.Label(label=title)
            title_label.set_xalign(0)
            title_label.set_halign(Gtk.Align.START)
            title_label.set_valign(Gtk.Align.CENTER)
            title_label.set_width_chars(20)
            title_label.set_max_width_chars(22)
            title_label.set_ellipsize(Pango.EllipsizeMode.END)
            title_label.get_style_context().add_class("table-cell")
            grid.attach(title_label, 1, row, 1, 1)
            self.aitools_summary_labels[target] = {"status": status}
            for column, key, width in (
                (2, "mode", 10),
                (3, "config", 38),
                (4, "runtime", 22),
            ):
                value = Gtk.Label(label="Unknown")
                value.set_xalign(0)
                value.set_halign(Gtk.Align.START)
                value.set_valign(Gtk.Align.CENTER)
                value.set_width_chars(width)
                value.set_max_width_chars(width)
                if key == "mode":
                    value.set_ellipsize(Pango.EllipsizeMode.END)
                else:
                    value.set_line_wrap(True)
                    value.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                value.get_style_context().add_class("section-subtitle")
                value.get_style_context().add_class("table-cell")
                grid.attach(value, column, row, 1, 1)
                self.aitools_summary_labels[target][key] = value

            edit_button = Gtk.Button(label="Edit")
            edit_button.set_tooltip_text(f"Edit {title} config.")
            edit_button.set_halign(Gtk.Align.END)
            edit_button.set_valign(Gtk.Align.CENTER)
            edit_button.get_style_context().add_class("secondary-action")
            edit_button.connect("clicked", self.on_aitools_edit_target, target)
            grid.attach(edit_button, 5, row, 1, 1)
            self.aitools_summary_labels[target]["edit"] = edit_button
        parent.pack_start(grid, False, False, 0)

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
        aitools_available = self.aitools_service.isInstalled()
        aitools_status = self.aitools_service.configStatus(self.aitools_config())

        lines = [
            f"Desktop session: {session}",
            f"Shell: {shell}",
            f"Browser config: {config_dir if config_dir.exists() else 'not found yet'}",
            f"AI Tools: {'installed' if aitools_available else 'not installed'}",
            f"Bifrost key: {'saved' if aitools_status['savedToken'] else ('detected' if aitools_status['token'] else 'not configured')}",
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
            vietnamese_diagnostics = self.vietnamese_service.diagnostics()
            vietnamese_status = self.vietnamese_service.classify_status(vietnamese_diagnostics)
        except Exception:
            vietnamese_status = "Unknown"
        try:
            aitools_ready = self.aitools_service.isInstalled()
            aitools_status = self.aitools_service.configStatus(self.aitools_config())
            ai_commands = self.aitools_service.terminalCommandsInstalled()
            ai_key_saved = bool(
                aitools_status.get("codexCli")
                or aitools_status.get("claudeCli")
                or aitools_status.get("savedToken")
                or aitools_status.get("token")
            )
        except Exception:
            aitools_ready = False
            aitools_status = {"token": False}
            ai_commands = False
            ai_key_saved = False
        try:
            style_action = run(["gsettings", "get", DASH_TO_DOCK_SCHEMA, "click-action"], check=False).strip("'")
        except Exception:
            style_action = "unknown"
        try:
            dock_layout = self.dock_layout_label()
        except Exception:
            dock_layout = "Unavailable"

        pills = [
            (
                "AI Tools: Commands" if ai_commands else ("AI Tools: Key saved" if ai_key_saved else "AI Tools: Setup"),
                "ok" if ai_commands else ("warn" if aitools_ready or ai_key_saved else "err"),
            ),
            ("Chrome Profiles: On" if chrome_ready else "Chrome Profiles: Setup", "ok" if chrome_ready else "warn"),
            ("Hover Previews: On" if hover_ready else "Hover Previews: Off", "ok" if hover_ready else "warn"),
            (
                f"Mouse: {self.mouse_preset_label(mouse_detected)}" if mouse_installed else "Mouse: maccel missing",
                "ok" if mouse_installed and mouse_detected not in {"unknown", "default_ubuntu"} else ("warn" if mouse_installed else "err"),
            ),
            ("Clipboard: On" if clipboard_ready else "Clipboard: Off", "ok" if clipboard_ready else "warn"),
            (
                f"Vietnamese: {vietnamese_status}",
                "ok" if vietnamese_status == "Ready" else ("err" if vietnamese_status == "Needs install" else "warn"),
            ),
            (f"Dock: {style_action or 'unknown'}", "ok" if style_action else "warn"),
            (
                f"Dock Layout: {dock_layout}",
                "ok" if dock_layout == "Windows taskbar" else ("err" if dock_layout == "Unavailable" else "warn"),
            ),
        ]
        for text, level in pills:
            self.overview_summary_box.add(self.make_pill(text, level))
        self.overview_summary_box.show_all()
        self.refresh_overview_restore_actions()

    def refresh_overview_restore_actions(self):
        if not hasattr(self, "overview_restore_buttons"):
            return

        try:
            ai_config = self.aitools_service.configStatus(self.aitools_config())
            ai_needed = bool(
                ai_config.get("codexCliCommand")
                or ai_config.get("claudeCliCommand")
                or ai_config.get("codexCliHome")
                or ai_config.get("codexVscodeConfig")
                or ai_config.get("claudeVscodeConfig")
            )
        except Exception:
            ai_needed = False

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

        vietnamese_state = load_app_config().get("vietnameseInput")
        vietnamese_needed = isinstance(vietnamese_state, dict) and bool(
            vietnamese_state.get("originalInputSources") or vietnamese_state.get("previousInputSources")
        )

        try:
            dock_layout_needed = self.dock_layout_restore_available()
        except Exception:
            dock_layout_needed = False
        try:
            dock_style_needed = self.dock_style_restore_available()
        except Exception:
            dock_style_needed = False

        states = {
            "aitools": (ai_needed, ai_needed),
            "chrome": (chrome_needed, chrome_needed),
            "mouse": (mouse_needed, mouse_ready),
            "clipboard": (clipboard_needed, clipboard_needed),
            "vietnamese": (vietnamese_needed, vietnamese_needed),
            "dock_layout": (dock_layout_needed, dock_layout_needed),
            "dock_style": (dock_style_needed, dock_style_needed),
        }
        for key, (visible, sensitive) in states.items():
            button = self.overview_restore_buttons[key]
            button.set_visible(True)
            button.set_sensitive(sensitive)
        self.overview_restore_card.set_visible(True)

    def refresh_aitools_state(self):
        if not hasattr(self, "aitools_status_label"):
            return
        settings = self.aitools_config()
        config = self.aitools_service.configStatus(settings)
        targets = config.get("targets", {})
        all_ready = bool(targets) and all(
            item.get("runtime")
            and (
                (item.get("mode") == "web" and item.get("config"))
                or (item.get("mode") == "bifrost" and item.get("bifrost"))
            )
            for item in targets.values()
        )

        self.set_pill(self.aitools_status_pill, "Ready" if all_ready else "Setup", "ok" if all_ready else "warn")
        if hasattr(self, "aitools_dependency_pills"):
            self.set_pill(
                self.aitools_dependency_pills["codex"],
                "installed" if config.get("personalCodex") else "missing",
                "ok" if config.get("personalCodex") else "err",
            )
            self.set_pill(
                self.aitools_dependency_pills["claude"],
                "installed" if config.get("personalClaude") else "missing",
                "ok" if config.get("personalClaude") else "warn",
            )
            self.set_pill(
                self.aitools_dependency_pills["bicodex"],
                "ready" if config.get("codexCliCommand") else "missing",
                "ok" if config.get("codexCliCommand") else "warn",
            )
            self.set_pill(
                self.aitools_dependency_pills["biclaude"],
                "ready" if config.get("claudeCliCommand") else "missing",
                "ok" if config.get("claudeCliCommand") else "warn",
            )
            has_bifrost = bool(config.get("savedToken") or config.get("token"))
            self.set_pill(
                self.aitools_dependency_pills["bifrost"],
                "saved" if has_bifrost else "not set",
                "ok" if has_bifrost else "warn",
            )
        if hasattr(self, "aitools_codex_cli_pill"):
            pill_map = {
                "codexCli": self.aitools_codex_cli_pill,
                "claudeCli": self.aitools_claude_cli_pill,
                "codexVscode": self.aitools_codex_vscode_pill,
                "claudeVscode": self.aitools_claude_vscode_pill,
            }
            for target, pill in pill_map.items():
                item = targets.get(target, {})
                ready = item.get("runtime") and (
                    (item.get("mode") == "web" and item.get("config"))
                    or (item.get("mode") == "bifrost" and item.get("bifrost"))
                )
                self.set_pill(pill, "Ready" if ready else "Setup", "ok" if ready else "warn")

        if hasattr(self, "aitools_summary_labels"):
            for target, title, tool, path in AITOOLS_TARGETS:
                item = targets.get(target, {})
                mode = item.get("mode", "unknown")
                account = item.get("accountLabel", "")
                source = item.get("source", "")
                base_url = item.get("baseUrl", "")
                model = item.get("model", "")
                if mode == "bifrost":
                    if item.get("bifrost"):
                        details = []
                        if base_url:
                            details.append(f"URL: {base_url}")
                        if model:
                            details.append(f"model: {model}")
                        config_text = "Bifrost" + (f" ({', '.join(details)})" if details else "")
                    else:
                        config_text = "Bifrost key missing"
                else:
                    config_text = f"Web login{f': {account}' if account else ''}"
                    if target in {"codexVscode", "claudeVscode"}:
                        config_text += " (config found)" if item.get("config") else " (not found yet)"
                if source and source != "saved":
                    config_text += f" | source: {source}"
                elif source == "saved":
                    config_text += " | source: Linux Toolbox saved draft"
                if target == "codexCli":
                    runtime_text = "bicodex ready" if item.get("runtime") else f"{tool} missing or wrapper not installed"
                elif target == "claudeCli":
                    runtime_text = "biclaude ready" if item.get("runtime") else f"{tool} missing or wrapper not installed"
                else:
                    runtime_text = f"{path}"
                ready = item.get("runtime") and (
                    (mode == "web" and item.get("config")) or (mode == "bifrost" and item.get("bifrost"))
                )
                self.set_pill(
                    self.aitools_summary_labels[target]["status"],
                    "✓ Configured" if ready else "Setup",
                    "ok" if ready else "warn",
                )
                self.aitools_summary_labels[target]["mode"].set_text("Bifrost" if mode == "bifrost" else "Web login")
                self.aitools_summary_labels[target]["config"].set_text(config_text)
                self.aitools_summary_labels[target]["runtime"].set_text(runtime_text)

        lines = [
            f"{title}: {('Bifrost' if targets.get(target, {}).get('mode') == 'bifrost' else 'Web login')}"
            f" - {'ready' if targets.get(target, {}).get('runtime') and ((targets.get(target, {}).get('mode') == 'web' and targets.get(target, {}).get('config')) or (targets.get(target, {}).get('mode') == 'bifrost' and targets.get(target, {}).get('bifrost'))) else 'needs setup'}"
            for target, title, _tool, _path in AITOOLS_TARGETS
        ] + [
            f"Command folder: {BIN_DIR}",
        ]
        self.aitools_status_label.set_text("\n".join(lines))
        if hasattr(self, "aitools_install_codex_button"):
            codex_installed = bool(config.get("personalCodex"))
            claude_installed = bool(config.get("personalClaude"))
            codex_ready = bool(config.get("codexCli"))
            claude_ready = bool(config.get("claudeCli"))
            has_bifrost = bool(config.get("savedToken") or config.get("token"))
            self.aitools_install_codex_button.set_visible(not codex_installed)
            self.aitools_install_codex_command_button.set_visible(codex_installed and not codex_ready)
            self.aitools_install_claude_command_button.set_visible(claude_installed and not claude_ready)
            self.aitools_bifrost_portal_button.set_visible(has_bifrost)
            restore_needed = bool(
                config.get("codexCliCommand")
                or config.get("claudeCliCommand")
                or config.get("codexCliHome")
                or config.get("codexVscodeConfig")
                or config.get("claudeVscodeConfig")
            )
            self.aitools_restore_button.set_visible(False)
            self.aitools_actions_card.set_visible(
                any(
                    widget.get_visible()
                    for widget in (
                        self.aitools_install_codex_button,
                        self.aitools_install_codex_command_button,
                        self.aitools_install_claude_command_button,
                        self.aitools_bifrost_portal_button,
                    )
                )
            )
        self.refresh_overview_summary()

    def aitools_config(self):
        config = load_app_config().get("aiTools", {})
        return config if isinstance(config, dict) else {}

    def save_aitools_config(self, values):
        config = load_app_config()
        current = config.get("aiTools", {})
        if not isinstance(current, dict):
            current = {}
        current.update(values)
        config["aiTools"] = current
        save_app_config(config)

    def selected_aitools_mode(self):
        return "bifrost"

    def set_aitools_combo(self, combo, value):
        combo.set_active_id(value if value in {"bifrost", "web"} else "bifrost")

    def aitools_combo_value(self, combo):
        return combo.get_active_id() or "bifrost"

    def load_aitools_account_fields(self):
        self.refresh_aitools_state()

    def collect_aitools_account_fields(self):
        return self.aitools_config()

    def update_aitools_mode_controls(self):
        return

    def save_aitools_account_fields(self):
        values = self.aitools_config()
        try:
            self.aitools_service.applyRealtimeConfig(values)
        except Exception:
            pass
        if self.aitools_service.desktopLauncherInstalled() and self.aitools_service.isInstalled():
            self.aitools_service.installDesktopLauncher()
        return values

    def aitools_target_meta(self, target):
        for item in AITOOLS_TARGETS:
            if item[0] == target:
                return item
        raise RuntimeError(f"Unknown AI Tools target: {target}")

    def save_aitools_target_config(self, target, values):
        config = load_app_config()
        current = config.get("aiTools", {})
        if not isinstance(current, dict):
            current = {}
        current["connectionMode"] = "split"
        current[target] = values
        if target == "codexCli":
            current["bifrostBaseUrl"] = values.get("bifrostBaseUrl", "")
            current["bifrostToken"] = values.get("bifrostToken", "")
            current["selectedModel"] = values.get("selectedModel", "")
        config["aiTools"] = current
        save_app_config(config)
        self.aitools_service.applyRealtimeConfig(current)
        return current

    def create_dialog_entry(self, grid, row, label_text, text="", placeholder="", secret=False):
        label = Gtk.Label(label=label_text)
        label.set_xalign(0)
        grid.attach(label, 0, row, 1, 1)

        entry = Gtk.Entry()
        entry.set_text(text or "")
        entry.set_placeholder_text(placeholder)
        entry.set_hexpand(True)
        if secret:
            entry.set_visibility(False)
        grid.attach(entry, 1, row, 2, 1)
        return entry

    def open_aitools_target_dialog(self, target):
        _target, title, tool, path = self.aitools_target_meta(target)
        settings = self.aitools_config()
        values = self.aitools_service.actualTargetConfig(settings, target)

        dialog = Gtk.Dialog(
            title=f"Edit {title}",
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_default_size(560, -1)

        content = dialog.get_content_area()
        content.set_spacing(12)
        content.set_border_width(12)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        content.pack_start(grid, False, False, 0)

        mode_label = Gtk.Label(label="Mode")
        mode_label.set_xalign(0)
        grid.attach(mode_label, 0, 0, 1, 1)
        mode_combo = Gtk.ComboBoxText()
        mode_combo.append("bifrost", "Bifrost")
        mode_combo.append("web", "Web login")
        mode_combo.set_active_id(values.get("connectionMode", self.aitools_service.defaultMode(target)))
        mode_combo.set_hexpand(True)
        grid.attach(mode_combo, 1, 0, 2, 1)

        base_entry = self.create_dialog_entry(
            grid,
            1,
            "Bifrost URL",
            values.get("bifrostBaseUrl", ""),
            "https://bifrost.example.com/anthropic",
        )
        token_entry = self.create_dialog_entry(
            grid,
            2,
            "Bifrost key",
            values.get("bifrostToken", ""),
            "sk-bf-...",
            secret=True,
        )
        model_entry = self.create_dialog_entry(
            grid,
            3,
            "Model",
            values.get("selectedModel", ""),
            "fridaycodex/gpt-5.5" if tool == "codex" else "claude-sonnet-4-5",
        )
        account_entry = self.create_dialog_entry(
            grid,
            4,
            "Web account label",
            values.get("accountLabel", ""),
            "ddwang via web login" if tool == "codex" else "Claude web login",
        )

        path_label = Gtk.Label(label="Config path" if target in {"codexVscode", "claudeVscode"} else "Runtime path")
        path_label.set_xalign(0)
        grid.attach(path_label, 0, 5, 1, 1)
        path_value = Gtk.Label(label=str(path))
        path_value.set_xalign(0)
        path_value.set_selectable(True)
        path_value.set_line_wrap(True)
        path_value.get_style_context().add_class("section-subtitle")
        grid.attach(path_value, 1, 5, 2, 1)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        content.pack_start(actions, False, False, 0)
        web_login_button = Gtk.Button(label=f"{'Codex' if tool == 'codex' else 'Claude'} Web Login")
        web_login_button.set_tooltip_text(f"Run web login for {title}.")
        portal_button = Gtk.Button(label="Bifrost Token Usage")
        portal_button.set_tooltip_text(f"Open {BIFROST_PORTAL_URL}.")
        actions.pack_start(web_login_button, True, True, 0)
        actions.pack_start(portal_button, True, True, 0)

        def update_sensitivity(*_args):
            bifrost = (mode_combo.get_active_id() or "bifrost") == "bifrost"
            for widget in (base_entry, token_entry, model_entry):
                widget.set_sensitive(bifrost)
            account_entry.set_sensitive(not bifrost)
            web_login_button.set_sensitive(not bifrost)
            portal_button.set_sensitive(bifrost)

        def launch_web_login(_button):
            try:
                self.aitools_service.launchLogin(tool)
                self.log(f"Opened {title} web login.")
            except Exception as error:
                self.log(f"Failed to open {title} web login: {error}")

        mode_combo.connect("changed", update_sensitivity)
        web_login_button.connect("clicked", launch_web_login)
        portal_button.connect("clicked", self.on_aitools_open_bifrost_portal)
        update_sensitivity()

        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            new_values = {
                "connectionMode": mode_combo.get_active_id() or self.aitools_service.defaultMode(target),
                "bifrostBaseUrl": base_entry.get_text().strip(),
                "bifrostToken": token_entry.get_text().strip(),
                "selectedModel": model_entry.get_text().strip(),
                "accountLabel": account_entry.get_text().strip(),
            }
            try:
                self.save_aitools_target_config(target, new_values)
                self.log(f"Saved {title} config.")
            except Exception as error:
                self.log(f"Failed to save {title} config: {error}")
        dialog.destroy()
        self.refresh_aitools_state()

    def refresh_vietnamese_input_state(self):
        if not hasattr(self, "vietnamese_status_label"):
            return
        try:
            diagnostics = self.vietnamese_service.diagnostics()
            status = self.vietnamese_service.classify_status(diagnostics)
        except Exception as error:
            diagnostics = {}
            status = "Unknown"
            self.vietnamese_status_label.set_text(f"Could not check Vietnamese input: {error}")

        install_running = self.vietnamese_install_process is not None and self.vietnamese_install_process.poll() is None
        if hasattr(self, "vietnamese_log_card"):
            self.vietnamese_log_card.set_visible(install_running)
        self.vietnamese_install_progress.set_visible(install_running)
        if install_running:
            self.vietnamese_install_progress.set_text("Installing Vietnamese input...")
            self.vietnamese_install_progress.set_show_text(True)
        else:
            self.vietnamese_install_progress.set_fraction(0)
            self.vietnamese_install_progress.set_show_text(False)

        if diagnostics:
            status_level = "ok" if status == "Ready" else ("err" if status == "Needs install" else "warn")
            self.set_pill(self.vietnamese_status_pill, status, status_level)
            self.set_pill(
                self.vietnamese_ibus_pill,
                "installed" if diagnostics["ibusInstalled"] else "missing",
                "ok" if diagnostics["ibusInstalled"] else "err",
            )
            self.set_pill(
                self.vietnamese_bamboo_pill,
                "installed" if diagnostics["bambooInstalled"] else "missing",
                "ok" if diagnostics["bambooInstalled"] else "err",
            )
            self.set_pill(
                self.vietnamese_framework_pill,
                diagnostics["framework"],
                "ok" if diagnostics["framework"] == "IBus" else "warn",
            )
            session_label = {"x11": "Xorg", "wayland": "Wayland"}.get(diagnostics["session"], "Unknown")
            self.set_pill(
                self.vietnamese_session_pill,
                session_label,
                "ok" if diagnostics["session"] == "x11" else ("warn" if diagnostics["session"] == "wayland" else "err"),
            )
            self.set_pill(
                self.vietnamese_source_pill,
                "active" if diagnostics["bambooSourceActive"] else "missing",
                "ok" if diagnostics["bambooSourceActive"] else "warn",
            )
            self.set_pill(self.vietnamese_mode_pill, "Telex", "ok")

            lines = [
                f"Desktop: {diagnostics['desktop']} / {session_label}",
                f"IBus daemon: {'running' if diagnostics['ibusDaemonRunning'] else 'not running'}",
            ]
            if diagnostics["session"] == "wayland":
                lines.append("Wayland warning: if Vietnamese input is unstable, try Xorg.")
            if not diagnostics["bambooConfigExists"]:
                lines.append("Open ibus-bamboo preferences and choose Telex + Unicode after install.")
            self.vietnamese_status_label.set_text("\n".join(lines))

            self.vietnamese_install_button.set_sensitive(
                diagnostics["pkexecAvailable"] and not diagnostics["bambooInstalled"] and not install_running
            )
            self.vietnamese_install_button.set_visible(not diagnostics["bambooInstalled"])
            self.vietnamese_apply_button.set_sensitive(
                diagnostics["ibusInstalled"] and diagnostics["bambooInstalled"] and not install_running
            )
            self.vietnamese_apply_button.set_visible(
                diagnostics["ibusInstalled"] and diagnostics["bambooInstalled"] and status != "Ready"
            )
            self.vietnamese_restart_button.set_sensitive(diagnostics["ibusInstalled"] and not install_running)
            self.vietnamese_restart_button.set_visible(diagnostics["ibusInstalled"] and not diagnostics["ibusDaemonRunning"])
            self.vietnamese_check_button.set_visible(False)
        else:
            for pill in (
                self.vietnamese_status_pill,
                self.vietnamese_ibus_pill,
                self.vietnamese_bamboo_pill,
                self.vietnamese_framework_pill,
                self.vietnamese_session_pill,
                self.vietnamese_source_pill,
            ):
                self.set_pill(pill, "Unknown", "warn")

        state = load_app_config().get("vietnameseInput")
        self.vietnamese_restore_button.set_sensitive(
            isinstance(state, dict) and bool(state.get("originalInputSources") or state.get("previousInputSources"))
        )
        self.vietnamese_restore_button.set_visible(False)
        if hasattr(self, "vietnamese_actions_card"):
            self.vietnamese_actions_card.set_visible(
                install_running
                or self.vietnamese_install_button.get_visible()
                or self.vietnamese_apply_button.get_visible()
                or self.vietnamese_restart_button.get_visible()
            )
        self.vietnamese_compatibility_label.set_text(
            "\n".join(
                [
                    "Chrome / Electron apps: restart the app after changing input method.",
                    "VSCode: restart VSCode if composing text behaves strangely.",
                    "Terminal: restart IBus and reopen terminal tabs after install.",
                    "JetBrains IDEs: restart the IDE after switching input method.",
                    "Wayland session: try Xorg if input is unstable.",
                    "After install: log out and log back in if Bamboo does not appear.",
                ]
            )
        )
        self.refresh_vietnamese_log_view()
        self.refresh_overview_summary()

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
        self.refresh_current_style()
        self.refresh_dock_layout_state()
        self.refresh_aitools_state()
        self.refresh_profiles()
        self.refresh_feature_state()
        self.refresh_mouse_movement_state()
        self.refresh_vietnamese_input_state()
        self.refresh_overview_summary()

    def text_view_text(self, view):
        buffer = view.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True).strip()

    def set_text_view_text(self, view, text):
        buffer = view.get_buffer()
        buffer.set_text(text)
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        view.scroll_mark_onscreen(mark)

    def on_aitools_field_changed(self, _entry):
        if getattr(self, "syncing_aitools_fields", False):
            return
        self.update_aitools_mode_controls()
        self.save_aitools_account_fields()
        self.refresh_aitools_state()

    def on_aitools_edit_target(self, _button, target):
        self.open_aitools_target_dialog(target)

    def on_aitools_open_bifrost_portal(self, _button):
        try:
            Gtk.show_uri_on_window(self, BIFROST_PORTAL_URL, Gdk.CURRENT_TIME)
            self.log("Opened Bifrost token usage portal.")
        except Exception:
            try:
                webbrowser.open(BIFROST_PORTAL_URL)
                self.log("Opened Bifrost token usage portal.")
            except Exception as error:
                self.log(f"Failed to open Bifrost token usage portal: {error}")

    def on_aitools_install_commands(self, _button):
        try:
            values = self.aitools_config()
            installed = self.aitools_service.installTerminalCommands(values)
            self.log(f"Installed terminal commands: {', '.join(installed)}.")
        except Exception as error:
            self.log(f"Failed to install AI terminal commands: {error}")
        self.refresh_aitools_state()

    def on_aitools_install_codex_command(self, _button):
        try:
            values = self.aitools_config()
            self.aitools_service.installCodexCliCommand(values)
            self.log("Installed Codex CLI Bifrost command: bicodex.")
        except Exception as error:
            self.log(f"Failed to install Codex CLI command: {error}")
        self.refresh_aitools_state()

    def on_aitools_install_claude_command(self, _button):
        try:
            values = self.aitools_config()
            self.aitools_service.installClaudeCliCommand(values)
            self.log("Installed Claude CLI Bifrost command: biclaude.")
        except Exception as error:
            self.log(f"Failed to install Claude CLI command: {error}")
        self.refresh_aitools_state()

    def on_aitools_openai_login(self, _button):
        try:
            self.save_aitools_account_fields()
            self.aitools_service.launchLogin("codex")
            self.log("Opened Codex web login for VS Code/global ~/.codex config.")
        except Exception as error:
            self.log(f"Failed to open OpenAI/Codex login: {error}")
        self.refresh_aitools_state()

    def on_aitools_claude_login(self, _button):
        try:
            self.save_aitools_account_fields()
            self.aitools_service.launchLogin("claude")
            self.log("Opened Claude web login for VS Code/global ~/.claude config.")
        except Exception as error:
            self.log(f"Failed to open Claude web login: {error}")
        self.refresh_aitools_state()

    def on_aitools_install_codex(self, _button):
        try:
            self.aitools_service.setupCodexCli()
            self.log("Started Codex CLI install in a terminal.")
        except Exception as error:
            self.log(f"Failed to start Codex CLI install: {error}")
        self.refresh_aitools_state()

    def on_aitools_clear_bifrost(self, _button):
        config = load_app_config()
        ai_tools = config.get("aiTools", {})
        if isinstance(ai_tools, dict):
            for target, _title, _tool, _path in AITOOLS_TARGETS:
                target_config = ai_tools.get(target)
                if isinstance(target_config, dict):
                    target_config["bifrostToken"] = ""
            ai_tools["bifrostToken"] = ""
            config["aiTools"] = ai_tools
            save_app_config(config)
        self.log("Saved CLI Bifrost keys cleared.")
        self.refresh_aitools_state()

    def on_aitools_restore_original(self, _button):
        try:
            config = load_app_config()
            ai_tools = config.get("aiTools", {}) if isinstance(config.get("aiTools"), dict) else {}
            self.aitools_service.restoreOriginal(ai_tools)
            config.pop("aiTools", None)
            save_app_config(config)
            self.log("Original AI tool setup restored. Personal web logins were left untouched.")
        except Exception as error:
            self.log(f"Failed to restore original AI tool setup: {error}")
        self.refresh_aitools_state()

    def on_vietnamese_check(self, _button):
        self.log("Checking OS...")
        self.log("Checking IBus...")
        self.log("Checking ibus-bamboo...")
        self.log("Checking input sources...")
        self.refresh_vietnamese_input_state()
        try:
            diagnostics = self.vietnamese_service.diagnostics()
            status = self.vietnamese_service.classify_status(diagnostics)
            self.log(f"Vietnamese input check: {status}.")
        except Exception as error:
            self.log(f"Vietnamese input check failed: {error}")

    def show_vietnamese_ppa_dialog(self):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="ibus-bamboo is not available from your current apt sources.",
        )
        dialog.format_secondary_text("Add the official ibus-bamboo PPA?")
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        add_button = dialog.add_button("Add PPA", Gtk.ResponseType.OK)
        add_button.get_style_context().add_class("suggested-action")
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def on_vietnamese_install(self, _button):
        try:
            diagnostics = self.vietnamese_service.diagnostics()
            if not diagnostics["pkexecAvailable"]:
                self.log("pkexec is missing, cannot install Vietnamese input packages.")
                return
            add_ppa = False
            if not diagnostics["bambooInstalled"] and not diagnostics["aptBambooAvailable"]:
                add_ppa = self.show_vietnamese_ppa_dialog()
                if not add_ppa:
                    self.log("Vietnamese input install cancelled. PPA was not added.")
                    return
            self.vietnamese_install_button.set_sensitive(False)
            self.log("Installing UniKey-like Vietnamese Input. Ubuntu may ask for your password.")
            self.vietnamese_install_process = self.vietnamese_service.start_install(add_ppa=add_ppa)
            GLib.child_watch_add(self.vietnamese_install_process.pid, self.on_vietnamese_install_finished)
            if self.vietnamese_install_timer_id is None:
                self.vietnamese_install_timer_id = GLib.timeout_add(700, self.pulse_vietnamese_install_progress)
        except Exception as error:
            self.log(f"Failed to install Vietnamese input: {error}")
            self.vietnamese_install_process = None
        self.refresh_vietnamese_input_state()

    def pulse_vietnamese_install_progress(self):
        if self.vietnamese_install_process is None or self.vietnamese_install_process.poll() is not None:
            self.vietnamese_install_timer_id = None
            return False
        self.vietnamese_install_progress.pulse()
        self.refresh_vietnamese_log_view()
        return True

    def on_vietnamese_install_finished(self, _pid, status):
        exit_code = status >> 8
        if self.vietnamese_install_process is not None:
            self.vietnamese_install_process.wait()
        self.vietnamese_install_process = None
        self.vietnamese_install_timer_id = None

        if exit_code == 0:
            self.log("Vietnamese input packages installed. Applying UniKey-like fixes...")
            try:
                self.vietnamese_service.apply_unikey_like_fixes()
                self.log("You may need to log out and log back in for Vietnamese input to appear.")
            except Exception as error:
                self.log(f"Packages installed, but fixes failed: {error}")
        elif exit_code == 42:
            self.log("ibus-bamboo was not available from apt sources and PPA was not approved.")
        else:
            detail = self.latest_vietnamese_log_line()
            message = "Vietnamese input install failed."
            if detail:
                message += f" Last log: {detail}"
            message += f" Check {VIETNAMESE_INPUT_LOG}."
            self.log(message)
        self.refresh_vietnamese_input_state()

    def on_vietnamese_apply_fixes(self, _button):
        try:
            self.vietnamese_service.apply_unikey_like_fixes()
            self.log("UniKey-like Vietnamese Input fixes applied. Reopen apps if typing still behaves strangely.")
        except Exception as error:
            self.log(f"Failed to apply Vietnamese input fixes: {error}")
        self.refresh_vietnamese_input_state()

    def on_vietnamese_restart(self, _button):
        try:
            self.vietnamese_service.restart_input_method()
            self.log("Input method restarted. Reopen apps if typing still behaves strangely.")
        except Exception as error:
            self.log(f"Failed to restart input method: {error}")
        self.refresh_vietnamese_input_state()

    def on_vietnamese_restore(self, _button):
        try:
            self.vietnamese_service.restore_previous_settings()
            self.log("Original Vietnamese input settings restored.")
        except Exception as error:
            self.log(f"Failed to restore original Vietnamese input settings: {error}")
        self.refresh_vietnamese_input_state()

    def refresh_vietnamese_log_view(self):
        if not hasattr(self, "vietnamese_log_view"):
            return
        text = self.vietnamese_service.latest_log_text()
        buffer = self.vietnamese_log_view.get_buffer()
        current = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        if current == text:
            return
        buffer.set_text(text)
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.vietnamese_log_view.scroll_mark_onscreen(mark)

    def latest_vietnamese_log_line(self):
        text = self.vietnamese_service.latest_log_text()
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line:
                return line[:180]
        return ""

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
        self.refresh_vietnamese_input_state()
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

    def install_hover_extension(self):
        EXT_DIR.mkdir(parents=True, exist_ok=True)
        (EXT_DIR / "metadata.json").write_text(load_text("hover-extension/metadata.json"), encoding="utf-8")
        (EXT_DIR / "extension.js").write_text(load_text("hover-extension/extension.js"), encoding="utf-8")
        (EXT_DIR / "stylesheet.css").write_text(load_text("hover-extension/stylesheet.css"), encoding="utf-8")

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
        super().__init__(application_id="local.linux_toolbox")
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
