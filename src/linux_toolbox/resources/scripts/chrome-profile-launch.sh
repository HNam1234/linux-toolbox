#!/usr/bin/env bash
set -u

if [ "$#" -lt 2 ]; then
  exit 64
fi

profile_dir=$1
wm_class=$2
shift 2

chrome=$(command -v google-chrome || command -v google-chrome-stable || command -v chromium || command -v chromium-browser || true)
if [ -z "${chrome:-}" ]; then
  echo "Chrome/Chromium executable was not found." >&2
  exit 127
fi

can_reclassify=false
if command -v xdotool >/dev/null 2>&1 && command -v xprop >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then
  can_reclassify=true

  # Chrome forwards later profile launches to its existing browser process. In
  # that case --class is ignored, so the new window must be reclassified below.
  # Serialize launch-and-detect cycles so simultaneous profile clicks cannot
  # both claim the same newly-created window.
  if command -v flock >/dev/null 2>&1; then
    lock_dir=${XDG_RUNTIME_DIR:-/tmp}
    exec 9>"$lock_dir/chrome-profile-launch-${UID}.lock"
    flock 9
  fi
fi

before_ids=""
if [ "$can_reclassify" = true ]; then
  before_ids=$(xdotool search --onlyvisible . 2>/dev/null | sort -u || true)
fi

# Do not let Chrome inherit the launcher lock descriptor. A newly-started
# browser process can otherwise keep later profile launches blocked forever.
"$chrome" --ozone-platform=x11 --profile-directory="$profile_dir" --class="$wm_class" "$@" 9>&- &

if [ "$can_reclassify" != true ]; then
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
  # getwindowclassname is not an xdotool command on supported Ubuntu releases.
  # Read the standard X11 property directly instead.
  window_class=$(xprop -id "$1" WM_CLASS 2>/dev/null || true)
  case "${window_class,,}" in
    *google-chrome*|*chrome*|*chromium*) return 0 ;;
  esac

  # Some windows expose WM_CLASS a moment after they become visible. Keep a
  # process-based fallback so they can still be recognized during that gap.
  pid=$(xdotool getwindowpid "$1" 2>/dev/null || true)
  [ -n "${pid:-}" ] || return 1
  executable=$(readlink "/proc/$pid/exe" 2>/dev/null || true)
  case "${executable,,}" in
    *google-chrome*|*/chrome|*/chromium|*/chromium-browser) return 0 ;;
    *) return 1 ;;
  esac
}

i=0
while [ "$i" -lt 150 ]; do
  window_ids=$(xdotool search --onlyvisible . 2>/dev/null | sort -u || true)
  for window_id in $window_ids; do
    if ! is_before_window "$window_id" && is_chrome_window "$window_id"; then
      xdotool set_window --class "$wm_class" "$window_id" 2>/dev/null || true
      exit 0
    fi
  done

  sleep 0.1
  i=$((i + 1))
done

exit 0
