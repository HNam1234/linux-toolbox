#!/usr/bin/env bash
set -Eeuo pipefail

# Linux Toolbox installer for the Cockpit Tools fork.
#
# The fork currently has no published Linux release assets, so this script
# builds its Debian package locally.  It deliberately builds and validates the
# package before removing an existing Cockpit Tools package.  User account data
# is never purged.

readonly FORK_REPOSITORY="https://github.com/HNam1234/cockpit-tools-linux-codex.git"
readonly FORK_BRANCH="${COCKPIT_FORK_BRANCH:-linux-codex-desktop-support}"
readonly UPSTREAM_REPOSITORY="${COCKPIT_UPSTREAM_REPOSITORY:-https://github.com/jlcodes99/cockpit-tools.git}"
readonly UPSTREAM_BRANCH="${COCKPIT_UPSTREAM_BRANCH:-main}"
readonly PATCH_SET="codex-linux-desktop-v1+fork-endpoints-v1+debian-bundle-v1"
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
readonly GO_BOOTSTRAP_VERSION="1.26.5"
readonly GO_BOOTSTRAP_ROOT="$BUILD_ROOT/go$GO_BOOTSTRAP_VERSION"

# Desktop launchers do not always source a user's shell profile.
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:/usr/local/bin:$PATH"

stop_running=false
command_name="${1:-install}"
if [ "${2:-}" = "--stop-running" ]; then
  stop_running=true
fi
source_ref_used="$UPSTREAM_BRANCH"
fork_patch_commit=""

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
  local required_commands=(git node npm npx cargo rustc python3 dpkg dpkg-deb)
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
    run_as_root apt-get install -y git nodejs npm cargo rustc python3 dpkg
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

go_version_is_supported() {
  local go_binary="$1"
  local version_text major minor
  version_text="$("$go_binary" version 2>/dev/null || true)"
  if [[ "$version_text" =~ go([0-9]+)\.([0-9]+)(\.[0-9]+)? ]]; then
    major="${BASH_REMATCH[1]}"
    minor="${BASH_REMATCH[2]}"
    [ "$major" -gt 1 ] || { [ "$major" -eq 1 ] && [ "$minor" -ge 26 ]; }
    return
  fi
  return 1
}

ensure_go_toolchain() {
  local system_go=""
  if command -v go >/dev/null 2>&1; then
    system_go="$(command -v go)"
  fi
  if [ -n "$system_go" ] && go_version_is_supported "$system_go"; then
    log "Using system Go toolchain: $($system_go version)"
    return 0
  fi

  require_command curl
  require_command tar
  require_command sha256sum

  local go_arch go_sha256
  case "$(uname -m)" in
    x86_64|amd64)
      go_arch="amd64"
      go_sha256="5c2c3b16caefa1d968a94c1daca04a7ca301a496d9b086e17ad77bb81393f053"
      ;;
    aarch64|arm64)
      go_arch="arm64"
      go_sha256="fe4789e92b1f33358680864bbe8704289e7bb5fc207d80623c308935bd696d49"
      ;;
    *)
      die "Cockpit Tools requires Go 1.26+; automatic bootstrap supports x86_64 and arm64 only (found $(uname -m))."
      ;;
  esac

  local archive_name="go${GO_BOOTSTRAP_VERSION}.linux-${go_arch}.tar.gz"
  local archive_path="$BUILD_ROOT/$archive_name"
  local archive_hash=""
  if [ -f "$archive_path" ]; then
    archive_hash="$(sha256sum "$archive_path" | cut -d' ' -f1)"
  fi
  if [ "$archive_hash" != "$go_sha256" ]; then
    local download_path="$archive_path.download.$$"
    log "Downloading Go $GO_BOOTSTRAP_VERSION for the Cockpit sidecar build."
    curl --fail --location --retry 3 --output "$download_path" \
      "https://go.dev/dl/$archive_name"
    archive_hash="$(sha256sum "$download_path" | cut -d' ' -f1)"
    [ "$archive_hash" = "$go_sha256" ] \
      || die "Downloaded Go archive checksum did not match the official Go release checksum."
    mv "$download_path" "$archive_path"
  fi

  if [ ! -x "$GO_BOOTSTRAP_ROOT/bin/go" ]; then
    local extraction_dir backup_path
    extraction_dir="$(mktemp -d "$BUILD_ROOT/go-bootstrap.XXXXXX")"
    tar -C "$extraction_dir" -xzf "$archive_path"
    [ -x "$extraction_dir/go/bin/go" ] || die "Go bootstrap archive did not contain a usable go binary."
    if [ -e "$GO_BOOTSTRAP_ROOT" ]; then
      backup_path="$GO_BOOTSTRAP_ROOT.replaced.$(date +%s)"
      mv "$GO_BOOTSTRAP_ROOT" "$backup_path"
      log "Moved an unusable cached Go toolchain to $backup_path."
    fi
    mv "$extraction_dir/go" "$GO_BOOTSTRAP_ROOT"
    rmdir "$extraction_dir"
  fi

  go_version_is_supported "$GO_BOOTSTRAP_ROOT/bin/go" \
    || die "Cached Go bootstrap is not Go 1.26+ as expected."
  export PATH="$GO_BOOTSTRAP_ROOT/bin:$PATH"
  log "Using Linux Toolbox Go toolchain: $($GO_BOOTSTRAP_ROOT/bin/go version)"
}

ensure_safe_build_resources() {
  local available_kib swap_free_kib total_available_kib
  if [ ! -r /proc/meminfo ]; then
    log "Could not inspect available memory; using the conservative single-job build profile."
    return 0
  fi

  available_kib="$(awk '/^MemAvailable:/ { print $2; exit }' /proc/meminfo)"
  swap_free_kib="$(awk '/^SwapFree:/ { print $2; exit }' /proc/meminfo)"
  available_kib="${available_kib:-0}"
  swap_free_kib="${swap_free_kib:-0}"
  total_available_kib=$((available_kib + swap_free_kib))
  if [ "$total_available_kib" -lt $((4 * 1024 * 1024)) ]; then
    die "Cockpit Tools source build needs at least 4 GiB of currently available RAM plus swap; only $((total_available_kib / 1024)) MiB is available. Close memory-heavy apps and retry."
  fi
  log "Build memory preflight passed: $((available_kib / 1024)) MiB RAM and $((swap_free_kib / 1024)) MiB swap available."
}

safe_build_jobs() {
  local requested_jobs="${COCKPIT_FORK_BUILD_JOBS:-1}"
  [[ "$requested_jobs" =~ ^[1-9][0-9]*$ ]] \
    || die "COCKPIT_FORK_BUILD_JOBS must be a positive integer (default: 1)."
  printf '%s\n' "$requested_jobs"
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
    bundle = config.setdefault("bundle", {})
    # Linux Toolbox installs only the Debian artifact. Building every Linux
    # bundle downloads AppImage tooling and, with updater artifacts enabled,
    # requires the fork's private Tauri signing key even though no updater
    # artifact is used by this installer.
    bundle["targets"] = ["deb"]
    bundle["createUpdaterArtifacts"] = False
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

normalize_go_module_directives() {
  local source_path="${1:-$SOURCE_DIR}"
  local sidecar_path="$source_path/sidecars/cockpit-cliproxy"
  [ -d "$sidecar_path" ] || die "Cockpit CLIProxy sidecar source is missing: $sidecar_path"
  python3 - "$sidecar_path" <<'PY'
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
updated = []
for path in root.rglob("go.mod"):
    text = path.read_text(encoding="utf-8")
    normalized = re.sub(r"(?m)^go ([0-9]+\.[0-9]+)\.0$", r"go \1", text)
    if normalized != text:
        path.write_text(normalized, encoding="utf-8")
        updated.append(str(path.relative_to(root)))
print("Normalized Go module directives: " + (", ".join(updated) if updated else "none needed"))
PY
}

apply_linux_codex_patch() {
  local source_path="${1:-$SOURCE_DIR}"
  local fork_ref="refs/remotes/codex-fork/$FORK_BRANCH"
  local patch_path="$BUILD_ROOT/linux-codex-desktop.patch"
  local patch_parent

  log "Fetching Linux Codex Desktop support patch from $FORK_BRANCH."
  git -C "$source_path" fetch --force --depth 2 "$FORK_REPOSITORY" \
    "refs/heads/$FORK_BRANCH:$fork_ref"
  fork_patch_commit="$(git -C "$source_path" rev-parse "$fork_ref")"
  patch_parent="$(git -C "$source_path" rev-parse "$fork_ref^")"

  git -C "$source_path" diff --binary "$patch_parent" "$fork_ref" -- \
    src-tauri/src/modules/process.rs > "$patch_path"
  [ -s "$patch_path" ] || die "Fork branch $FORK_BRANCH contains no Linux Codex process patch."

  if grep -q 'CODEX_MULTI_LAUNCH' "$source_path/src-tauri/src/modules/process.rs" \
    && grep -q 'detect_codex_exec_path_linux' "$source_path/src-tauri/src/modules/process.rs"; then
    log "Upstream source already contains Linux Codex Desktop switching support; no code patch was needed."
    return 0
  fi

  if ! git -C "$source_path" apply --check --3way "$patch_path"; then
    die "The Linux Codex Desktop patch no longer applies cleanly to $source_ref_used. The installed package was not changed."
  fi
  git -C "$source_path" apply --3way "$patch_path"

  grep -q 'CODEX_MULTI_LAUNCH' "$source_path/src-tauri/src/modules/process.rs" \
    || die "Linux Codex patch validation failed: CODEX_MULTI_LAUNCH support is missing."
  grep -q 'detect_codex_exec_path_linux' "$source_path/src-tauri/src/modules/process.rs" \
    || die "Linux Codex patch validation failed: launcher detection is missing."
  log "Applied Linux Codex Desktop switching patch ${fork_patch_commit:0:12}."
}

build_deb() {
  ensure_toolchain
  ensure_apt_build_dependencies
  ensure_go_toolchain
  ensure_safe_build_resources
  prepare_source
  apply_linux_codex_patch
  patch_fork_endpoints
  normalize_go_module_directives

  log "Installing JavaScript dependencies with npm ci."
  (
    cd "$SOURCE_DIR"
    npm ci --no-audit --no-fund
  )

  local build_jobs
  build_jobs="$(safe_build_jobs)"
  log "Building the patched Linux .deb package with a safe $build_jobs-job limit. This can take several minutes."
  (
    cd "$SOURCE_DIR"
    export CARGO_BUILD_JOBS="$build_jobs"
    export GOMAXPROCS="$build_jobs"
    export GOFLAGS="-p=$build_jobs"
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
  python3 - "$MARKER_PATH" "$version" "$commit" "$binary_hash" "$FORK_REPOSITORY" "$FORK_BRANCH" "$UPSTREAM_REPOSITORY" "$PATCH_SET" "$source_ref_used" "$fork_patch_commit" <<'PY'
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

target = pathlib.Path(sys.argv[1])
marker = {
    "managedBy": "Linux Toolbox",
    "repository": sys.argv[5],
    "branch": sys.argv[6],
    "sourceRepository": sys.argv[7],
    "patchSet": sys.argv[8],
    "sourceRef": sys.argv[9],
    "forkPatchCommit": sys.argv[10],
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
