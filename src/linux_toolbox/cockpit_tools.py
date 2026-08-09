"""Cockpit Tools fork detection and release-package installation."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from linux_toolbox.resources import load_text


HOME = Path.home()
BIN_DIR = HOME / ".local/bin"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", str(HOME / ".local/share"))) / "linux-toolbox"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", str(HOME / ".local/state"))) / "linux-toolbox"
INSTALLER_PATH = BIN_DIR / "linux-toolbox-install-cockpit-tools"
INSTALL_LOG_PATH = STATE_DIR / "cockpit-tools-fork-install.log"
MARKER_PATH = DATA_DIR / "cockpit-tools-fork.json"
PACKAGE_NAME = "cockpit-tools"
PACKAGE_BINARY = Path("/usr/bin/cockpit-tools")
FORK_REPOSITORY = "https://github.com/HNam1234/cockpit-tools-linux-codex.git"
FORK_BRANCH = "linux-codex-desktop-support"


def _run(command):
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed


class CockpitToolsService:
    """Read Cockpit state and start the bundled fork installer."""

    def __init__(self):
        self._binary_hash_key = None
        self._binary_hash = None

    def ensure_installer(self):
        """Install/update the CLI entry point used by the GTK tab."""
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        script = load_text("scripts/install-cockpit-tools-fork.sh")
        INSTALLER_PATH.write_text(script, encoding="utf-8")
        INSTALLER_PATH.chmod(0o755)
        return INSTALLER_PATH

    def is_supported_platform(self):
        return os.name == "posix" and shutil.which("dpkg") is not None

    def is_running(self):
        if shutil.which("pgrep") is None:
            return False
        completed = _run(["pgrep", "-u", str(os.getuid()), "-x", "cockpit-tools"])
        return completed.returncode == 0 and bool(completed.stdout.strip())

    def package_info(self):
        if shutil.which("dpkg-query") is None:
            return {"installed": False, "version": "", "status": "unavailable"}
        completed = _run(
            [
                "dpkg-query",
                "-W",
                "-f=${Status}\t${Version}\t${Architecture}",
                PACKAGE_NAME,
            ]
        )
        raw = completed.stdout.strip()
        if completed.returncode != 0 or not raw:
            return {"installed": False, "version": "", "status": "missing"}
        parts = raw.split("\t")
        status = parts[0] if parts else ""
        return {
            "installed": status == "install ok installed",
            "version": parts[1] if len(parts) > 1 else "",
            "architecture": parts[2] if len(parts) > 2 else "",
            "status": status or "unknown",
        }

    def _read_marker(self):
        if not MARKER_PATH.exists():
            return {}
        try:
            value = json.loads(MARKER_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def _current_binary_hash(self):
        try:
            stat_result = PACKAGE_BINARY.stat()
        except OSError:
            self._binary_hash_key = None
            self._binary_hash = None
            return ""

        key = (stat_result.st_mtime_ns, stat_result.st_size, stat_result.st_ino)
        if key == self._binary_hash_key:
            return self._binary_hash or ""

        digest = hashlib.sha256()
        try:
            with PACKAGE_BINARY.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            self._binary_hash_key = None
            self._binary_hash = None
            return ""

        self._binary_hash_key = key
        self._binary_hash = digest.hexdigest()
        return self._binary_hash

    def get_status(self):
        package = self.package_info()
        marker = self._read_marker()
        marker_repository = str(marker.get("repository", "")).strip()
        marker_hash = str(marker.get("binarySha256", "")).strip()
        current_hash = self._current_binary_hash() if package["installed"] else ""
        marker_for_this_fork = marker_repository == FORK_REPOSITORY
        binary_matches_marker = bool(marker_hash and current_hash and marker_hash == current_hash)
        managed_fork = package["installed"] and marker_for_this_fork and (
            not marker_hash or binary_matches_marker
        )

        if managed_fork:
            source = "Codex fork"
        elif package["installed"] and marker_for_this_fork:
            source = "Fork marker · binary changed"
        elif package["installed"]:
            source = "Official / unknown"
        elif marker_for_this_fork:
            source = "Fork marker · package missing"
        elif PACKAGE_BINARY.exists():
            source = "Unmanaged binary"
        else:
            source = "Not installed"

        return {
            "packageInstalled": package["installed"],
            "packageVersion": package.get("version", ""),
            "packageStatus": package.get("status", ""),
            "source": source,
            "managedFork": managed_fork,
            "marker": marker,
            "running": self.is_running(),
            "supported": self.is_supported_platform(),
            "installerPath": str(INSTALLER_PATH),
            "installLogPath": str(INSTALL_LOG_PATH),
        }

    def start_install(self, stop_running=False):
        return self._start_action("install", stop_running=stop_running)

    def start_repair(self, stop_running=False):
        return self._start_action("repair", stop_running=stop_running)

    def start_uninstall(self, stop_running=False):
        return self._start_action("uninstall", stop_running=stop_running)

    def _start_action(self, action, stop_running=False):
        installer = self.ensure_installer()
        command = [str(installer), action]
        if stop_running:
            command.append("--stop-running")
        return subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def read_install_log(self, line_limit=240):
        if not INSTALL_LOG_PATH.exists():
            return ""
        try:
            lines = INSTALL_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as error:
            return f"Could not read Cockpit installer log: {error}"
        return "\n".join(lines[-line_limit:])

    def latest_install_log_line(self):
        text = self.read_install_log(line_limit=40)
        for line in reversed(text.splitlines()):
            if line.strip():
                return line.strip()[:220]
        return ""
