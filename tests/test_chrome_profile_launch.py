import os
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


LAUNCHER = (
    Path(__file__).parents[1]
    / "src/linux_toolbox/resources/scripts/chrome-profile-launch.sh"
)


class ChromeProfileLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bin_dir = self.root / "bin"
        self.runtime_dir = self.root / "runtime"
        self.bin_dir.mkdir()
        self.runtime_dir.mkdir()
        self.state_file = self.root / "windows"
        self.set_log = self.root / "set-window.log"
        self.chrome_log = self.root / "chrome.log"

        self._write_executable(
            "google-chrome",
            """
            profile=""
            for argument in "$@"; do
              case "$argument" in
                --profile-directory=*) profile=${argument#*=} ;;
              esac
            done
            exec 8>"$TEST_STATE.lock"
            flock 8
            count=$(wc -l <"$TEST_STATE" 2>/dev/null || printf '0')
            window_id=$((201 + count))
            printf '%s %s\n' "$window_id" "$profile" >>"$TEST_STATE"
            printf '%s\n' "$*" >>"$TEST_CHROME_LOG"
            """,
        )
        self._write_executable(
            "xdotool",
            """
            command=$1
            shift
            case "$command" in
              search)
                printf '100\n'
                if [ -f "$TEST_STATE" ]; then
                  cut -d' ' -f1 "$TEST_STATE"
                fi
                ;;
              set_window)
                printf '%s\n' "$*" >>"$TEST_SET_LOG"
                ;;
              getwindowpid)
                exit 1
                ;;
              *)
                printf 'Unsupported xdotool command: %s\n' "$command" >&2
                exit 2
                ;;
            esac
            """,
        )
        self._write_executable(
            "xprop",
            """
            window_id=""
            while [ "$#" -gt 0 ]; do
              if [ "$1" = -id ]; then
                window_id=$2
                shift 2
              else
                shift
              fi
            done
            if [ "$window_id" = 100 ] || grep -q "^$window_id " "$TEST_STATE" 2>/dev/null; then
              printf 'WM_CLASS(STRING) = "google-chrome", "Google-chrome"\n'
              exit 0
            fi
            exit 1
            """,
        )

        self.environment = os.environ.copy()
        self.environment.update(
            {
                "DISPLAY": ":99",
                "PATH": f"{self.bin_dir}:{self.environment['PATH']}",
                "XDG_RUNTIME_DIR": str(self.runtime_dir),
                "TEST_STATE": str(self.state_file),
                "TEST_SET_LOG": str(self.set_log),
                "TEST_CHROME_LOG": str(self.chrome_log),
            }
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _write_executable(self, name, body):
        path = self.bin_dir / name
        path.write_text(
            "#!/usr/bin/env bash\nset -eu\n" + textwrap.dedent(body),
            encoding="utf-8",
        )
        path.chmod(0o755)

    def _run_launcher(self, profile, window_class):
        return subprocess.Popen(
            ["bash", str(LAUNCHER), profile, window_class, "--new-window"],
            env=self.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def test_reclassifies_new_window_without_getwindowclassname(self):
        completed = subprocess.run(
            [
                "bash",
                str(LAUNCHER),
                "Profile 1",
                "ChromeProfile1",
                "--new-window",
            ],
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=5,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            self.set_log.read_text(encoding="utf-8").strip(),
            "--class ChromeProfile1 201",
        )
        chrome_arguments = self.chrome_log.read_text(encoding="utf-8")
        self.assertIn("--profile-directory=Profile 1", chrome_arguments)
        self.assertIn("--class=ChromeProfile1", chrome_arguments)

    def test_concurrent_launches_claim_their_own_windows(self):
        first = self._run_launcher("Profile 1", "ChromeProfile1")
        time.sleep(0.05)
        second = self._run_launcher("Profile 2", "ChromeProfile2")

        for process in (first, second):
            _stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)

        windows = {}
        for line in self.state_file.read_text(encoding="utf-8").splitlines():
            window_id, profile = line.split(" ", 1)
            windows[window_id] = profile

        assignments = {}
        for line in self.set_log.read_text(encoding="utf-8").splitlines():
            _option, window_class, window_id = line.split()
            assignments[windows[window_id]] = window_class

        self.assertEqual(
            assignments,
            {"Profile 1": "ChromeProfile1", "Profile 2": "ChromeProfile2"},
        )


if __name__ == "__main__":
    unittest.main()
