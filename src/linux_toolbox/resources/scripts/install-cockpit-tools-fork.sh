#!/usr/bin/env bash
set -Eeuo pipefail

# Linux Toolbox installer for the Cockpit Tools fork.
#
# The fork currently has no published Linux release assets, so this script
# builds its Debian package locally.  It deliberately builds and validates the
# package before removing an existing Cockpit Tools package.  User account data
# is never purged.

readonly FORK_REPOSITORY="https://github.com/HNam1234/cockpit-tools-linux-codex.git"
readonly FORK_BRANCH="main"
readonly UPSTREAM_REPOSITORY="${COCKPIT_UPSTREAM_REPOSITORY:-https://github.com/jlcodes99/cockpit-tools.git}"
readonly UPSTREAM_BRANCH="${COCKPIT_UPSTREAM_BRANCH:-main}"
readonly PATCH_SET="codex-fork-endpoints-v1"
readonly PACKAGE_NAME="cockpit-tools"
readonly PACKAGE_BINARY="/usr/bin/cockpit-tools"
readonly DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
readonly CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
readonly STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
readonly TOOLBOX_DATA_DIR="$DATA_HOME/linux-toolbox"
readonly APPLICATIONS_DIR="$DATA_HOME/applications"
readonly BUILD_ROOT="$CACHE_HOME/linux-toolbox/cockpit-tools-fork"
readonly SOURCE_DIR="$BUILD_ROOT/source"
readonly ARTIFACT_DIR="$BUILD_ROOT/artifacts"
readonly INSTALL_LOG="$STATE_HOME/linux-toolbox/cockpit-tools-fork-install.log"
readonly MARKER_PATH="$TOOLBOX_DATA_DIR/cockpit-tools-fork.json"
readonly LOCK_PATH="$BUILD_ROOT/install.lock"

# Desktop launchers do not always source a user's shell profile.
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:/usr/local/bin:$PATH"

stop_running=false
command_name="${1:-install}"
if [ "${2:-}" = "--stop-running" ]; then
  stop_running=true
fi
source_ref_used="$UPSTREAM_BRANCH"

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
    log "Installer stopped with exit code $exit_code. Existing user data was not purged."
  fi
}
trap on_exit EXIT

if [ "${EUID:-$(id -u)}" -eq 0 ]; then
  die "Run this installer as your desktop user, not with sudo. It uses pkexec only for package operations."
fi

if [ "$(uname -s)" != "Linux" ]; then
  die "This installer currently supports Linux only."
fi

if ! command -v flock >/dev/null 2>&1; then
  die "The flock command is missing. Install util-linux first."
fi

exec 9>"$LOCK_PATH"
if ! flock -n 9; then
  die "Another Cockpit Tools fork operation is already running."
fi

package_installed() {
  dpkg-query -W -f='${Status}' "$PACKAGE_NAME" 2>/dev/null | grep -q '^install ok installed$'
}

package_version() {
  dpkg-query -W -f='${Version}' "$PACKAGE_NAME" 2>/dev/null || true
}

marker_repository() {
  if [ ! -f "$MARKER_PATH" ] || ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  python3 - "$MARKER_PATH" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as stream:
        marker = json.load(stream)
except (OSError, ValueError):
    marker = {}
print(marker.get("repository", ""))
PY
}

running_pids() {
  if ! command -v pgrep >/dev/null 2>&1; then
    return 0
  fi
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

require_command() {
  local command_name_to_check="$1"
  command -v "$command_name_to_check" >/dev/null 2>&1 || die "Required command is missing: $command_name_to_check"
}

run_as_root() {
  require_command pkexec
  pkexec "$@"
}

apt_package_installed() {
  dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q '^install ok installed$'
}

ensure_apt_build_dependencies() {
  require_command apt-get
  require_command dpkg-query

  local required_packages=(
    build-essential
    curl
    file
    libssl-dev
    libgtk-3-dev
    libayatana-appindicator3-dev
    librsvg2-dev
    patchelf
    pkg-config
    libsoup-3.0-dev
    javascriptcoregtk-4.1
    libjavascriptcoregtk-4.1-dev
    libwebkit2gtk-4.1-dev
    libnm-dev
    xdg-utils
  )
  local missing_packages=()
  local package_name_to_check
  for package_name_to_check in "${required_packages[@]}"; do
    if ! apt_package_installed "$package_name_to_check"; then
      missing_packages+=("$package_name_to_check")
    fi
  done

  if [ "${#missing_packages[@]}" -eq 0 ]; then
    return 0
  fi
  if [ "${COCKPIT_FORK_SKIP_APT:-0}" = "1" ]; then
    die "Missing build packages: ${missing_packages[*]}. Re-run without COCKPIT_FORK_SKIP_APT=1."
  fi

  log "Installing missing Linux build packages: ${missing_packages[*]}"
  run_as_root apt-get update
  run_as_root apt-get install -y "${missing_packages[@]}"
}

ensure_toolchain() {
  local required_commands=(git node npm npx cargo rustc go python3 dpkg dpkg-deb)
  local missing_commands=()
  local command_to_check
  for command_to_check in "${required_commands[@]}"; do
    if ! command -v "$command_to_check" >/dev/null 2>&1; then
      missing_commands+=("$command_to_check")
    fi
  done

  if [ "${#missing_commands[@]}" -gt 0 ]; then
    if [ "${COCKPIT_FORK_SKIP_APT:-0}" = "1" ]; then
      die "Missing build tools: ${missing_commands[*]}. Re-run without COCKPIT_FORK_SKIP_APT=1 or install them manually."
    fi
    log "Installing missing build tools: ${missing_commands[*]}"
    run_as_root apt-get update
    run_as_root apt-get install -y git nodejs npm cargo rustc golang-go python3 dpkg
  fi

  local node_major npm_major
  node_major="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || printf '0')"
  npm_major="$(npm --version 2>/dev/null | cut -d. -f1 || printf '0')"
  if [ "${node_major:-0}" -lt 18 ]; then
    die "Node.js 18+ is required by the fork; found $(node --version 2>/dev/null || printf unknown)."
  fi
  if [ "${npm_major:-0}" -lt 9 ]; then
    die "npm 9+ is required by the fork; found $(npm --version 2>/dev/null || printf unknown)."
  fi
}

prepare_source() {
  mkdir -p "$BUILD_ROOT"
  local source_ref="$UPSTREAM_BRANCH"
  if [ "$command_name" = "repair" ] || [ "$command_name" = "patch" ]; then
    local installed_version="$(package_version)"
    if [ -n "$installed_version" ] && git ls-remote --exit-code "$UPSTREAM_REPOSITORY" "refs/tags/v$installed_version" >/dev/null 2>&1; then
      source_ref="v$installed_version"
      log "Repair mode: using upstream tag $source_ref to match the installed package."
    else
      log "Repair mode: no matching upstream tag was found; using branch $UPSTREAM_BRANCH."
    fi
  fi
  source_ref_used="$source_ref"
  if [ -d "$SOURCE_DIR/.git" ]; then
    log "Updating cached upstream source."
    git -C "$SOURCE_DIR" remote set-url origin "$UPSTREAM_REPOSITORY"
    git -C "$SOURCE_DIR" fetch --depth 1 origin "$source_ref"
    git -C "$SOURCE_DIR" checkout --detach --force FETCH_HEAD
  else
    if [ -e "$SOURCE_DIR" ]; then
      die "Build source path exists but is not a Git checkout: $SOURCE_DIR"
    fi
    log "Cloning upstream source from $UPSTREAM_REPOSITORY (ref $source_ref)."
    git clone --depth 1 --branch "$source_ref" "$UPSTREAM_REPOSITORY" "$SOURCE_DIR"
  fi
}

patch_fork_endpoints() {
  local source_path="${1:-$SOURCE_DIR}"
  log "Applying local patch set $PATCH_SET to the upstream source."
  python3 - "$source_path" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
upstream_repo = "https://github.com/jlcodes99/cockpit-tools"
upstream_raw = "https://raw.githubusercontent.com/jlcodes99/cockpit-tools/main"
fork_repo = "https://github.com/HNam1234/cockpit-tools-linux-codex"
fork_raw = "https://raw.githubusercontent.com/HNam1234/cockpit-tools-linux-codex/main"

patched_files = 0
for relative in (
    "src-tauri/src/modules/remote_config.rs",
    "src-tauri/src/modules/announcement.rs",
    "src/utils/updaterReleaseNotes.ts",
    "src/pages/SettingsPage.tsx",
):
    path = root / relative
    if not path.exists():
        raise SystemExit(f"Patch target is missing: {relative}")
    text = path.read_text(encoding="utf-8")
    patched = text.replace(upstream_repo, fork_repo).replace(upstream_raw, fork_raw)
    if patched == text and fork_repo not in text and fork_raw not in text:
        raise SystemExit(f"Patch anchor was not found in: {relative}")
    if patched != text:
        patched_files += 1
        path.write_text(patched, encoding="utf-8")

config_path = root / "src-tauri/tauri.conf.json"
if config_path.exists():
    config = json.loads(config_path.read_text(encoding="utf-8"))
    updater = config.setdefault("plugins", {}).setdefault("updater", {})
    updater["endpoints"] = [
        f"{fork_repo}/releases/latest/download/latest-{{{{target}}}}.json",
        f"{fork_repo}/releases/latest/download/latest.json",
    ]
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    patched_files += 1

if not config_path.exists():
    raise SystemExit("src-tauri/tauri.conf.json was not found")
print(f"Applied {patched_files} patched source files.")
PY
}

build_deb() {
  ensure_toolchain
  ensure_apt_build_dependencies
  prepare_source
  patch_fork_endpoints

  log "Installing JavaScript dependencies with npm ci."
  (
    cd "$SOURCE_DIR"
    npm ci --no-audit --no-fund
  )

  log "Building the patched Linux .deb package. This can take several minutes."
  (
    cd "$SOURCE_DIR"
    npx tauri build --ci
  )

  local deb_path package_arch package_id
  deb_path="$(find "$SOURCE_DIR/target/release/bundle/deb" -maxdepth 1 -type f -name '*.deb' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -n 1 | cut -d' ' -f2-)"
  [ -n "$deb_path" ] || die "The fork build completed without producing a .deb package."
  package_id="$(dpkg-deb -f "$deb_path" Package)"
  package_arch="$(dpkg-deb -f "$deb_path" Architecture)"
  [ "$package_id" = "$PACKAGE_NAME" ] || die "Unexpected package name in build: $package_id"
  [ "$package_arch" = "$(dpkg --print-architecture)" ] || die "Package architecture $package_arch does not match $(dpkg --print-architecture)."

  mkdir -p "$ARTIFACT_DIR"
  local artifact_path="$ARTIFACT_DIR/$(basename "$deb_path")"
  install -m 0644 "$deb_path" "$artifact_path"
  BUILT_ARTIFACT="$artifact_path"
}

write_marker() {
  local version="$1"
  local commit="$2"
  local binary_hash="$3"
  mkdir -p "$TOOLBOX_DATA_DIR"
  python3 - "$MARKER_PATH" "$version" "$commit" "$binary_hash" "$FORK_REPOSITORY" "$UPSTREAM_REPOSITORY" "$PATCH_SET" "$source_ref_used" <<'PY'
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

target = pathlib.Path(sys.argv[1])
marker = {
    "managedBy": "Linux Toolbox",
    "repository": sys.argv[5],
    "branch": "main",
    "sourceRepository": sys.argv[6],
    "patchSet": sys.argv[7],
    "sourceRef": sys.argv[8],
    "version": sys.argv[2],
    "commit": sys.argv[3],
    "binarySha256": sys.argv[4],
    "installedAt": datetime.now(timezone.utc).isoformat(),
}
temporary = target.with_name(f"{target.name}.tmp.{os.getpid()}")
temporary.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
temporary.chmod(0o600)
os.replace(temporary, target)
PY
}

install_package() {
  local artifact_path="$1"
  stop_running_app

  if package_installed; then
    log "Removing the existing $PACKAGE_NAME package without purging user data."
    run_as_root dpkg --remove "$PACKAGE_NAME"
  fi

  log "Installing fork package: $(basename "$artifact_path")"
  if ! run_as_root dpkg --install "$artifact_path"; then
    log "dpkg reported missing dependencies; repairing the package state with apt."
    run_as_root apt-get -f install -y
    run_as_root dpkg --install "$artifact_path"
  fi
  package_installed || die "The fork package did not reach the installed state."

  local version commit binary_hash
  version="$(package_version)"
  commit="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
  binary_hash="$(sha256sum "$PACKAGE_BINARY" | cut -d' ' -f1)"
  write_marker "$version" "$commit" "$binary_hash"
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
  log "Cockpit Tools Codex patch installed (version $version, upstream commit ${commit:0:12})."
  log "Account/config data was preserved. Open Cockpit Tools from Applications."
}

uninstall_managed_fork() {
  if ! package_installed; then
    rm -f "$MARKER_PATH"
    log "Cockpit Tools is not installed. No user data was removed."
    return 0
  fi

  if [ "$(marker_repository)" != "$FORK_REPOSITORY" ]; then
    die "The installed package is official or unknown. Use the fork install action if you want to replace it."
  fi
  stop_running_app
  log "Removing the Linux Toolbox-managed Cockpit Tools fork without purging user data."
  run_as_root dpkg --remove "$PACKAGE_NAME"
  rm -f "$MARKER_PATH"
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
  log "Managed fork removed. Cockpit account/config data was kept."
}

show_status() {
  local package_state="missing"
  if package_installed; then
    package_state="installed $(package_version)"
  fi
  local marker_state="none"
  if [ -f "$MARKER_PATH" ]; then
    marker_state="$(marker_repository)"
  fi
  local patch_state="none"
  if [ -f "$MARKER_PATH" ]; then
    patch_state="$(python3 - "$MARKER_PATH" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as stream:
        marker = json.load(stream)
except (OSError, ValueError):
    marker = {}
print(marker.get("patchSet", "unknown"))
PY
)"
  fi
  local pids="$(running_pids)"
  printf 'package: %s\n' "$package_state"
  printf 'fork-marker: %s\n' "$marker_state"
  printf 'patch-set: %s\n' "$patch_state"
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
    require_command dpkg-query
    require_command dpkg
    require_command dpkg-deb
    if [ "$command_name" = "install" ]; then
      log "Preparing Cockpit Tools Codex fork installation."
    else
      log "Reapplying the Cockpit Tools Codex patch to the current upstream source."
    fi
    BUILT_ARTIFACT=""
    build_deb
    [ -n "$BUILT_ARTIFACT" ] || die "The fork build did not produce an installable artifact."
    install_package "$BUILT_ARTIFACT"
    ;;
  uninstall)
    require_command dpkg-query
    require_command dpkg
    uninstall_managed_fork
    ;;
  *)
    die "Usage: $0 {status|install|repair|patch|uninstall} [--stop-running]"
    ;;
esac
