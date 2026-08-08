"""Set-and-forget GNOME Shell extension lifecycle support."""

import ast
import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


EXTENSION_MANAGER_APP_ID = "com.mattjakeman.ExtensionManager"
EXTENSION_MANAGER_APT_PACKAGE = "gnome-shell-extension-manager"
FLATHUB_REPOSITORY_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
EGO_BASE_URL = "https://extensions.gnome.org"
SHELL_EXTENSIONS_BUS = "org.gnome.Shell.Extensions"
SHELL_EXTENSIONS_PATH = "/org/gnome/Shell/Extensions"
SHELL_EXTENSIONS_INTERFACE = "org.gnome.Shell.Extensions"


class ExtensionOperationError(RuntimeError):
    """A user-facing GNOME extension lifecycle error."""


class GnomeExtensionService:
    """Install, enable, disable, and verify GNOME Shell extensions.

    GNOME Shell's D-Bus extension API is the primary path because it is the
    same interface used by Extension Manager and can activate a newly installed
    extension in the current session.  The official ``gnome-extensions`` CLI
    and extensions.gnome.org bundle API provide a fallback.
    """

    def __init__(self, home=None):
        self.home = Path(home) if home is not None else Path.home()
        self.user_extension_root = self.home / ".local/share/gnome-shell/extensions"
        self.extension_roots = (
            self.user_extension_root,
            Path("/usr/local/share/gnome-shell/extensions"),
            Path("/usr/share/gnome-shell/extensions"),
        )

    def _run(self, command, timeout=120):
        try:
            return subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        except FileNotFoundError as error:
            raise ExtensionOperationError(f"Required command is missing: {command[0]}") from error
        except subprocess.TimeoutExpired as error:
            raise ExtensionOperationError(f"Command timed out: {command[0]}") from error

    @staticmethod
    def _command_error(completed, fallback):
        text = (completed.stderr or completed.stdout or fallback).strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return " | ".join(lines[-8:])[-1200:] or fallback

    def manager_installed(self):
        if shutil.which("extension-manager"):
            return True
        if not shutil.which("flatpak"):
            return False
        for scope in ("--user", "--system"):
            completed = self._run(
                ["flatpak", "info", scope, EXTENSION_MANAGER_APP_ID],
                timeout=30,
            )
            if completed.returncode == 0:
                return True
        return False

    def ensure_manager(self):
        """Install Extension Manager if missing and return its install source."""
        if self.manager_installed():
            return "present"

        errors = []
        if shutil.which("apt-get") and shutil.which("pkexec"):
            candidate_available = True
            if shutil.which("apt-cache"):
                policy = self._run(
                    ["apt-cache", "policy", EXTENSION_MANAGER_APT_PACKAGE],
                    timeout=30,
                )
                candidate_available = (
                    "Candidate:" in policy.stdout and "Candidate: (none)" not in policy.stdout
                )
            if not candidate_available:
                refreshed = self._run(["pkexec", "apt-get", "update"], timeout=900)
                candidate_available = refreshed.returncode == 0
                if refreshed.returncode != 0:
                    errors.append(self._command_error(refreshed, "APT metadata refresh failed"))
            if candidate_available:
                completed = self._run(
                    ["pkexec", "apt-get", "install", "-y", EXTENSION_MANAGER_APT_PACKAGE],
                    timeout=900,
                )
                if completed.returncode == 0 and self.manager_installed():
                    return "apt"
                if completed.returncode in (126, 127):
                    raise ExtensionOperationError(
                        "Extension Manager installation authorization was cancelled."
                    )
                errors.append(self._command_error(completed, "APT installation failed"))

        if not shutil.which("flatpak") and shutil.which("apt-get") and shutil.which("pkexec"):
            completed = self._run(
                ["pkexec", "apt-get", "install", "-y", "flatpak"],
                timeout=900,
            )
            if completed.returncode != 0:
                errors.append(self._command_error(completed, "Flatpak installation failed"))

        if shutil.which("flatpak"):
            remote = self._run(
                [
                    "flatpak",
                    "remote-add",
                    "--user",
                    "--if-not-exists",
                    "flathub",
                    FLATHUB_REPOSITORY_URL,
                ],
                timeout=180,
            )
            if remote.returncode == 0:
                completed = self._run(
                    [
                        "flatpak",
                        "install",
                        "--user",
                        "--noninteractive",
                        "-y",
                        "flathub",
                        EXTENSION_MANAGER_APP_ID,
                    ],
                    timeout=1200,
                )
                if completed.returncode == 0 and self.manager_installed():
                    return "flatpak"
                errors.append(self._command_error(completed, "Flatpak app installation failed"))
            else:
                errors.append(self._command_error(remote, "Could not configure Flathub"))

        detail = "; ".join(item for item in errors if item)
        raise ExtensionOperationError(
            "Could not install Extension Manager automatically"
            + (f": {detail}" if detail else ". Install Extension Manager and retry.")
        )

    def extension_directory(self, uuid):
        for root in self.extension_roots:
            candidate = root / uuid
            if (candidate / "metadata.json").exists():
                return candidate
        return self.user_extension_root / uuid

    def installed(self, uuid):
        return (self.extension_directory(uuid) / "metadata.json").exists()

    def _enabled_extensions(self):
        if not shutil.which("gsettings"):
            return []
        completed = self._run(
            ["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
            timeout=30,
        )
        if completed.returncode != 0:
            return []
        raw = completed.stdout.strip()
        if raw.startswith("@as "):
            raw = raw[4:].strip()
        try:
            value = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            return []
        return [str(item) for item in value] if isinstance(value, (list, tuple)) else []

    def enabled(self, uuid):
        return uuid in self._enabled_extensions()

    def active(self, uuid):
        if not shutil.which("gnome-extensions"):
            return self.enabled(uuid)
        completed = self._run(["gnome-extensions", "list", "--active"], timeout=30)
        if completed.returncode == 0:
            return uuid in {line.strip() for line in completed.stdout.splitlines()}
        completed = self._run(["gnome-extensions", "info", uuid], timeout=30)
        return completed.returncode == 0 and "ACTIVE" in completed.stdout.upper()

    def status(self, uuid):
        return {
            "installed": self.installed(uuid),
            "enabled": self.enabled(uuid),
            "active": self.active(uuid),
        }

    def _set_enabled_preference(self, uuid, enabled):
        if not shutil.which("gsettings"):
            raise ExtensionOperationError("gsettings is required to persist extension state.")
        current = [item for item in self._enabled_extensions() if item != uuid]
        if enabled:
            current.append(uuid)
        value = "[" + ", ".join(repr(item) for item in current) + "]"
        completed = self._run(
            ["gsettings", "set", "org.gnome.shell", "enabled-extensions", value],
            timeout=30,
        )
        if completed.returncode != 0:
            raise ExtensionOperationError(
                self._command_error(completed, "Could not save the extension enabled state")
            )

    def _allow_user_extensions(self):
        if not shutil.which("gsettings"):
            return
        completed = self._run(
            ["gsettings", "set", "org.gnome.shell", "disable-user-extensions", "false"],
            timeout=30,
        )
        if completed.returncode != 0:
            raise ExtensionOperationError(
                self._command_error(completed, "Could not enable user GNOME extensions")
            )

    def _dbus_call(self, method, *arguments, timeout=120):
        if not shutil.which("gdbus"):
            raise ExtensionOperationError("gdbus is unavailable.")
        return self._run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                SHELL_EXTENSIONS_BUS,
                "--object-path",
                SHELL_EXTENSIONS_PATH,
                "--method",
                f"{SHELL_EXTENSIONS_INTERFACE}.{method}",
                *arguments,
            ],
            timeout=timeout,
        )

    def _wait_for_install(self, uuid, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.installed(uuid):
                return True
            time.sleep(0.25)
        return self.installed(uuid)

    def _install_with_shell(self, uuid):
        completed = self._dbus_call("InstallRemoteExtension", uuid, timeout=300)
        output = (completed.stdout + completed.stderr).lower()
        if "cancelled" in output:
            raise ExtensionOperationError("GNOME Shell extension installation was cancelled.")
        if completed.returncode != 0:
            raise ExtensionOperationError(
                self._command_error(completed, "GNOME Shell remote installation failed")
            )
        if "successful" not in output and not self._wait_for_install(uuid):
            raise ExtensionOperationError(f"GNOME Shell did not install {uuid}.")
        self._wait_for_install(uuid)
        return "gnome-shell"

    def _shell_major_version(self):
        if shutil.which("gnome-shell"):
            completed = self._run(["gnome-shell", "--version"], timeout=30)
            for token in completed.stdout.replace("-", " ").split():
                major = token.split(".", 1)[0]
                if major.isdigit():
                    return int(major)
        raise ExtensionOperationError("Could not detect the GNOME Shell version.")

    def _download_extension_bundle(self, uuid):
        query = urllib.parse.urlencode(
            {"uuid": uuid, "shell_version": str(self._shell_major_version())}
        )
        request = urllib.request.Request(
            f"{EGO_BASE_URL}/extension-info/?{query}",
            headers={"User-Agent": "Linux-Toolbox/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                metadata = json.loads(response.read().decode("utf-8"))
            download_path = metadata.get("download_url")
            if metadata.get("uuid") != uuid or not download_path:
                raise ExtensionOperationError(
                    f"No compatible extensions.gnome.org release was found for {uuid}."
                )
            download_url = urllib.parse.urljoin(EGO_BASE_URL, download_path)
            download_request = urllib.request.Request(
                download_url,
                headers={"User-Agent": "Linux-Toolbox/1.0"},
            )
            with urllib.request.urlopen(download_request, timeout=60) as response:
                bundle = response.read(100 * 1024 * 1024 + 1)
        except ExtensionOperationError:
            raise
        except Exception as error:
            raise ExtensionOperationError(f"Extension download failed: {error}") from error
        if len(bundle) > 100 * 1024 * 1024:
            raise ExtensionOperationError("The extension bundle exceeded the 100 MB safety limit.")
        self._validate_bundle(bundle, uuid)
        return bundle

    @staticmethod
    def _validate_bundle(bundle, uuid):
        try:
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                metadata = json.loads(archive.read("metadata.json").decode("utf-8"))
                if metadata.get("uuid") != uuid:
                    raise ExtensionOperationError("The downloaded extension UUID did not match.")
                unpacked_size = 0
                for member in archive.infolist():
                    path = PurePosixPath(member.filename)
                    mode = member.external_attr >> 16
                    unpacked_size += member.file_size
                    if unpacked_size > 250 * 1024 * 1024:
                        raise ExtensionOperationError(
                            "The extension bundle exceeded the 250 MB unpacked safety limit."
                        )
                    if path.is_absolute() or ".." in path.parts:
                        raise ExtensionOperationError("The extension bundle contains an unsafe path.")
                    if stat.S_ISLNK(mode):
                        raise ExtensionOperationError("The extension bundle contains an unsafe symlink.")
        except ExtensionOperationError:
            raise
        except (KeyError, ValueError, zipfile.BadZipFile, UnicodeDecodeError) as error:
            raise ExtensionOperationError(f"Invalid GNOME extension bundle: {error}") from error

    def _install_bundle(self, uuid, bundle):
        if shutil.which("gnome-extensions"):
            with tempfile.TemporaryDirectory(prefix="linux-toolbox-extension-") as temporary:
                bundle_path = Path(temporary) / f"{uuid}.shell-extension.zip"
                bundle_path.write_bytes(bundle)
                completed = self._run(
                    ["gnome-extensions", "install", "--force", str(bundle_path)],
                    timeout=180,
                )
                if completed.returncode != 0:
                    raise ExtensionOperationError(
                        self._command_error(completed, "gnome-extensions install failed")
                    )
            return "gnome-extensions"

        self.user_extension_root.mkdir(parents=True, exist_ok=True)
        target = self.user_extension_root / uuid
        with tempfile.TemporaryDirectory(
            prefix=f".{uuid}.stage-", dir=self.user_extension_root
        ) as temporary:
            staging = Path(temporary)
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                for member in archive.infolist():
                    relative = PurePosixPath(member.filename)
                    destination = staging.joinpath(*relative.parts)
                    if member.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    mode = (member.external_attr >> 16) & 0o777
                    if mode:
                        destination.chmod(mode)
            backup = self.user_extension_root / f".{uuid}.backup-{os.getpid()}"
            if backup.exists():
                shutil.rmtree(backup)
            if target.exists():
                target.rename(backup)
            try:
                shutil.copytree(staging, target)
            except Exception:
                if target.exists():
                    shutil.rmtree(target)
                if backup.exists():
                    backup.rename(target)
                raise
            if backup.exists():
                shutil.rmtree(backup)
        schema_dir = target / "schemas"
        if schema_dir.exists() and shutil.which("glib-compile-schemas"):
            self._run(["glib-compile-schemas", str(schema_dir)], timeout=60)
        return "direct"

    def install(self, uuid, force=False):
        if self.installed(uuid) and not force:
            return "present"
        shell_error = None
        try:
            source = self._install_with_shell(uuid)
            if self.installed(uuid):
                return source
        except ExtensionOperationError as error:
            if "cancelled" in str(error).lower():
                raise
            shell_error = str(error)

        try:
            bundle = self._download_extension_bundle(uuid)
            source = self._install_bundle(uuid, bundle)
        except ExtensionOperationError as error:
            detail = f"{shell_error}; {error}" if shell_error else str(error)
            raise ExtensionOperationError(detail) from error
        if not self.installed(uuid):
            raise ExtensionOperationError(f"{uuid} was not detected after installation.")
        return source

    def set_enabled(self, uuid, enabled):
        if enabled and not self.installed(uuid):
            raise ExtensionOperationError(f"{uuid} is not installed.")
        if enabled:
            self._allow_user_extensions()
        self._set_enabled_preference(uuid, enabled)

        method = "EnableExtension" if enabled else "DisableExtension"
        try:
            completed = self._dbus_call(method, uuid, timeout=60)
            if completed.returncode != 0 and enabled:
                self._dbus_call("ReloadExtension", uuid, timeout=60)
                self._dbus_call(method, uuid, timeout=60)
        except ExtensionOperationError:
            pass

        if shutil.which("gnome-extensions"):
            action = "enable" if enabled else "disable"
            self._run(["gnome-extensions", action, uuid], timeout=60)
        self._set_enabled_preference(uuid, enabled)
        active = self.active(uuid) if enabled else False
        return {
            "enabled": self.enabled(uuid),
            "active": active,
            "restartRequired": enabled and not active,
        }

    def ensure_enabled(self, uuid):
        warnings = []
        try:
            manager_source = self.ensure_manager()
        except ExtensionOperationError as error:
            manager_source = "unavailable"
            warnings.append(str(error))
        was_installed = self.installed(uuid)
        install_source = "present"
        if was_installed:
            state = self.set_enabled(uuid, True)
            if not state["active"]:
                install_source = self.install(uuid, force=True)
                state = self.set_enabled(uuid, True)
        else:
            install_source = self.install(uuid)
            state = self.set_enabled(uuid, True)
        state.update(
            {
                "managerSource": manager_source,
                "installSource": install_source,
                "warnings": warnings,
            }
        )
        return state
