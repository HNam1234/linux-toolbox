import io
import json
import stat
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from linux_toolbox.gnome_extensions import (
    ExtensionOperationError,
    GnomeExtensionService,
)


TEST_UUID = "linux-toolbox-test@example.com"


def extension_bundle(uuid=TEST_UUID, extra_entries=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("metadata.json", json.dumps({"uuid": uuid, "shell-version": ["46"]}))
        archive.writestr("extension.js", "export default class TestExtension {}")
        for name, value in extra_entries or []:
            archive.writestr(name, value)
    return output.getvalue()


class BundleValidationTests(unittest.TestCase):
    def test_accepts_matching_extension_bundle(self):
        GnomeExtensionService._validate_bundle(extension_bundle(), TEST_UUID)

    def test_rejects_mismatched_uuid(self):
        with self.assertRaises(ExtensionOperationError):
            GnomeExtensionService._validate_bundle(extension_bundle("wrong@example.com"), TEST_UUID)

    def test_rejects_parent_path(self):
        bundle = extension_bundle(extra_entries=[("../outside", "unsafe")])
        with self.assertRaises(ExtensionOperationError):
            GnomeExtensionService._validate_bundle(bundle, TEST_UUID)

    def test_rejects_symlink(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("metadata.json", json.dumps({"uuid": TEST_UUID}))
            link = zipfile.ZipInfo("unsafe-link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "target")
        with self.assertRaises(ExtensionOperationError):
            GnomeExtensionService._validate_bundle(output.getvalue(), TEST_UUID)


class OrchestrationTests(unittest.TestCase):
    def test_detects_user_extension(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = GnomeExtensionService(home=temporary)
            extension_dir = Path(temporary) / ".local/share/gnome-shell/extensions" / TEST_UUID
            extension_dir.mkdir(parents=True)
            (extension_dir / "metadata.json").write_text(
                json.dumps({"uuid": TEST_UUID}), encoding="utf-8"
            )
            self.assertTrue(service.installed(TEST_UUID))

    def test_direct_bundle_fallback_installs_into_user_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = GnomeExtensionService(home=temporary)
            with mock.patch(
                "linux_toolbox.gnome_extensions.shutil.which", return_value=None
            ):
                source = service._install_bundle(TEST_UUID, extension_bundle())
            extension_dir = Path(temporary) / ".local/share/gnome-shell/extensions" / TEST_UUID
            self.assertEqual(source, "direct")
            self.assertTrue((extension_dir / "metadata.json").exists())
            self.assertTrue((extension_dir / "extension.js").exists())

    def test_extension_install_continues_when_manager_bootstrap_fails(self):
        class RecoverableService(GnomeExtensionService):
            def ensure_manager(self):
                raise ExtensionOperationError("manager unavailable")

            def install(self, uuid):
                self.installed_uuid = uuid
                return "gnome-shell"

            def set_enabled(self, uuid, enabled):
                return {"enabled": enabled, "active": enabled, "restartRequired": False}

        service = RecoverableService()
        result = service.ensure_enabled(TEST_UUID)
        self.assertEqual(service.installed_uuid, TEST_UUID)
        self.assertEqual(result["managerSource"], "unavailable")
        self.assertEqual(result["warnings"], ["manager unavailable"])
        self.assertTrue(result["active"])

    def test_inactive_installed_extension_is_force_repaired(self):
        class RepairService(GnomeExtensionService):
            def __init__(self):
                super().__init__()
                self.enable_attempts = 0
                self.force_install = None

            def ensure_manager(self):
                return "present"

            def installed(self, uuid):
                return True

            def install(self, uuid, force=False):
                self.force_install = force
                return "gnome-extensions"

            def set_enabled(self, uuid, enabled):
                self.enable_attempts += 1
                active = self.enable_attempts > 1
                return {"enabled": enabled, "active": active, "restartRequired": not active}

        service = RepairService()
        result = service.ensure_enabled(TEST_UUID)
        self.assertTrue(service.force_install)
        self.assertEqual(service.enable_attempts, 2)
        self.assertTrue(result["active"])

    def test_missing_manager_is_installed_with_apt(self):
        class AptBootstrapService(GnomeExtensionService):
            def __init__(self):
                super().__init__()
                self.manager_ready = False
                self.commands = []

            def manager_installed(self):
                return self.manager_ready

            def _run(self, command, timeout=120):
                self.commands.append(command)
                if command[:2] == ["apt-cache", "policy"]:
                    return subprocess.CompletedProcess(command, 0, "Candidate: 1.0\n", "")
                if command[:3] == ["pkexec", "apt-get", "install"]:
                    self.manager_ready = True
                    return subprocess.CompletedProcess(command, 0, "", "")
                return subprocess.CompletedProcess(command, 1, "", "unexpected command")

        available = {"apt-get", "apt-cache", "pkexec"}
        with mock.patch(
            "linux_toolbox.gnome_extensions.shutil.which",
            side_effect=lambda command: f"/usr/bin/{command}" if command in available else None,
        ):
            service = AptBootstrapService()
            self.assertEqual(service.ensure_manager(), "apt")
        self.assertIn(
            ["pkexec", "apt-get", "install", "-y", "gnome-shell-extension-manager"],
            service.commands,
        )


if __name__ == "__main__":
    unittest.main()
