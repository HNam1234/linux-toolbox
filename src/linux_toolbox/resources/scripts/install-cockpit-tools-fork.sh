#!/usr/bin/env bash
set -Eeuo pipefail

# Install the prebuilt Cockpit Tools Codex fork. This deliberately never
# compiles Rust, Go, Node, or Tauri on the desktop machine.

readonly FORK_REPOSITORY="https://github.com/HNam1234/cockpit-tools-linux-codex.git"
readonly RELEASE_TAG="linux-codex-desktop-latest"
readonly RELEASE_BASE_URL="${FORK_REPOSITORY%.git}/releases/download/$RELEASE_TAG"
readonly PACKAGE_NAME="cockpit-tools"
readonly PACKAGE_BINARY="/usr/bin/cockpit-tools"
readonly DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
readonly CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
readonly STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
readonly TOOLBOX_DATA_DIR="$DATA_HOME/linux-toolbox"
readonly BUILD_ROOT="$CACHE_HOME/linux-toolbox/cockpit-tools-fork"
readonly INSTALL_LOG="$STATE_HOME/linux-toolbox/cockpit-tools-fork-install.log"
readonly MARKER_PATH="$TOOLBOX_DATA_DIR/cockpit-tools-fork.json"
readonly LOCK_PATH="$BUILD_ROOT/install.lock"

stop_running=false
command_name="${1:-install}"
if [ "${2:-}" = "--stop-running" ]; then
  stop_running=true
fi

mkdir -p "$(dirname "$INSTALL_LOG")" "$BUILD_ROOT"
exec > >(tee -a "$INSTALL_LOG") 2>&1

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

on_exit() {
  local exit_code=$?
  if [ "$exit_code" -ne 0 ]; then
    log "Installer stopped with exit code $exit_code. The installed package and user data were left unchanged."
  fi
}
trap on_exit EXIT

if [ "${EUID:-$(id -u)}" -eq 0 ]; then
  die "Run this installer as your desktop user, not with sudo. It uses pkexec only for package operations."
fi

if [ "$(uname -s)" != "Linux" ]; then
  die "This installer supports Linux only."
fi

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command is missing: $1"
}

run_as_root() {
  require_command pkexec
  pkexec "$@"
}

package_installed() {
  dpkg-query -W -f='${Status}' "$PACKAGE_NAME" 2>/dev/null | grep -q '^install ok installed$'
}

package_version() {
  dpkg-query -W -f='${Version}' "$PACKAGE_NAME" 2>/dev/null || true
}

marker_repository() {
  if [ ! -f "$MARKER_PATH" ]; then
    return 0
  fi
  python3 - "$MARKER_PATH" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as stream:
        print(json.load(stream).get("repository", ""))
except (OSError, ValueError):
    pass
PY
}

running_pids() {
  pgrep -u "$(id -u)" -x cockpit-tools 2>/dev/null || true
}

stop_running_app() {
  local pids
  pids="$(running_pids)"
  if [ -z "$pids" ]; then
    return 0
  fi
  if [ "$stop_running" != true ]; then
    die "Cockpit Tools is running (PID $pids). Close it and retry, or pass --stop-running."
  fi

  log "Requesting Cockpit Tools to close: $pids"
  pkill -TERM -u "$(id -u)" -x cockpit-tools 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    if [ -z "$(running_pids)" ]; then
      log "Cockpit Tools closed cleanly."
      return 0
    fi
  done
  die "Cockpit Tools did not close after SIGTERM. Close it manually; no package was changed."
}

release_asset_name() {
  case "$(dpkg --print-architecture)" in
    amd64)
      printf '%s\n' 'cockpit-tools-linux-amd64.deb'
      ;;
    *)
      die "No prebuilt Cockpit Tools Codex fork package is published for $(dpkg --print-architecture)."
      ;;
  esac
}

download_release_package() {
  require_command curl
  require_command sha256sum
  require_command dpkg-deb

  local asset_name package_path checksum_path expected_hash actual_hash cache_bust
  asset_name="$(release_asset_name)"
  package_path="$(mktemp "$BUILD_ROOT/$asset_name.XXXXXX")"
  checksum_path="$(mktemp "$BUILD_ROOT/SHA256SUMS.txt.XXXXXX")"
  cache_bust="$(date +%s%N)"

  log "Downloading prebuilt Cockpit Tools Codex fork package."
  # GitHub release assets are cached aggressively. The unique query keeps a
  # replacement checksum asset from being paired with a stale CDN response.
  curl --fail --location --retry 3 --output "$package_path" "$RELEASE_BASE_URL/$asset_name?cache=$cache_bust"
  curl --fail --location --retry 3 --output "$checksum_path" "$RELEASE_BASE_URL/SHA256SUMS.txt?cache=$cache_bust"
  # Accept the usual SHA256SUMS forms: a bare filename, an optional leading
  # asterisk (binary-mode output), or a path produced by sha256sum.
  expected_hash="$(awk -v asset="$asset_name" '
    {
      filename = $2
      sub(/^\\*/, "", filename)
      sub(/^.*\//, "", filename)
      if (filename == asset) {
        print $1
        exit
      }
    }
  ' "$checksum_path")"
  [[ "$expected_hash" =~ ^[a-fA-F0-9]{64}$ ]] \
    || die "Release checksum file does not contain a SHA256 for $asset_name."
  actual_hash="$(sha256sum "$package_path" | cut -d' ' -f1)"
  [ "$actual_hash" = "$expected_hash" ] \
    || die "Downloaded Cockpit Tools package failed SHA256 verification."
  [ "$(dpkg-deb -f "$package_path" Package)" = "$PACKAGE_NAME" ] \
    || die "Downloaded package has an unexpected name."
  [ "$(dpkg-deb -f "$package_path" Architecture)" = "$(dpkg --print-architecture)" ] \
    || die "Downloaded package has an unexpected architecture."

  RELEASE_PACKAGE="$package_path"
  RELEASE_HASH="$actual_hash"
}

write_marker() {
  local version="$1"
  local hash="$2"
  mkdir -p "$TOOLBOX_DATA_DIR"
  python3 - "$MARKER_PATH" "$version" "$hash" "$FORK_REPOSITORY" "$RELEASE_TAG" <<'PY'
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

target = pathlib.Path(sys.argv[1])
marker = {
    "managedBy": "Linux Toolbox",
    "repository": sys.argv[4],
    "releaseTag": sys.argv[5],
    "version": sys.argv[2],
    "packageSha256": sys.argv[3],
    "installedAt": datetime.now(timezone.utc).isoformat(),
}
temporary = target.with_name(f"{target.name}.tmp.{os.getpid()}")
temporary.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
temporary.chmod(0o600)
os.replace(temporary, target)
PY
}

install_release_package() {
  download_release_package
  stop_running_app

  if package_installed; then
    log "Removing the existing cockpit-tools package without purging user data."
    run_as_root dpkg --remove "$PACKAGE_NAME"
  fi

  log "Installing verified Cockpit Tools Codex fork package."
  if ! run_as_root dpkg --install "$RELEASE_PACKAGE"; then
    log "dpkg reported missing dependencies; repairing package state with apt."
    run_as_root apt-get -f install -y
    run_as_root dpkg --install "$RELEASE_PACKAGE"
  fi
  package_installed || die "Cockpit Tools did not reach the installed state."

  write_marker "$(package_version)" "$RELEASE_HASH"
  update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
  log "Cockpit Tools Codex fork installed. Account/config data was preserved."
}

uninstall_managed_fork() {
  if ! package_installed; then
    rm -f "$MARKER_PATH"
    log "Cockpit Tools is not installed. No user data was removed."
    return 0
  fi
  if [ "$(marker_repository)" != "$FORK_REPOSITORY" ]; then
    die "The installed package is official or unknown. Refusing to remove it."
  fi
  stop_running_app
  log "Removing the Linux Toolbox-managed Cockpit Tools fork without purging user data."
  run_as_root dpkg --remove "$PACKAGE_NAME"
  rm -f "$MARKER_PATH"
  update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
  log "Managed fork removed. Cockpit account/config data was kept."
}

show_status() {
  local package_state="missing" marker_state pids
  if package_installed; then
    package_state="installed $(package_version)"
  fi
  marker_state="$(marker_repository)"
  pids="$(running_pids)"
  printf 'package: %s\n' "$package_state"
  printf 'fork-marker: %s\n' "${marker_state:-none}"
  printf 'release: %s\n' "$RELEASE_TAG"
  printf 'running-pids: %s\n' "${pids:-none}"
  printf 'installer-log: %s\n' "$INSTALL_LOG"
}

case "$command_name" in
  status)
    require_command dpkg-query
    require_command python3
    show_status
    ;;
  install|repair|patch)
    require_command dpkg
    require_command dpkg-query
    install_release_package
    ;;
  uninstall)
    require_command dpkg
    require_command dpkg-query
    uninstall_managed_fork
    ;;
  *)
    die "Usage: $0 {status|install|repair|patch|uninstall} [--stop-running]"
    ;;
esac
