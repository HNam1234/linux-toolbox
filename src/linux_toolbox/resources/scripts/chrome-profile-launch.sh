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

before_ids=""
if command -v xdotool >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then
  before_ids=$(xdotool search --onlyvisible . 2>/dev/null | sort -u || true)
fi

"$chrome" --ozone-platform=x11 --profile-directory="$profile_dir" --class="$wm_class" "$@" &

if ! command -v xdotool >/dev/null 2>&1 || [ -z "${DISPLAY:-}" ]; then
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
  pid=$(xdotool getwindowpid "$1" 2>/dev/null || true)
  [ -n "${pid:-}" ] || return 1

  exe=""
  if [ -e "/proc/$pid/exe" ]; then
    exe=$(readlink "/proc/$pid/exe" 2>/dev/null || true)
  fi

  cmdline=""
  if [ -r "/proc/$pid/cmdline" ]; then
    cmdline=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)
  fi

  case "$exe $cmdline" in
    *google-chrome*|*chrome*|*chromium*) return 0 ;;
    *) return 1 ;;
  esac
}

i=0
while [ "$i" -lt 150 ]; do
  window_ids=$(xdotool search --onlyvisible . 2>/dev/null | sort -u || true)
  for window_id in $window_ids; do
    if ! is_before_window "$window_id" && is_chrome_window "$window_id"; then
      xdotool set_window --class "$wm_class" --classname "$wm_class" "$window_id" 2>/dev/null || true
      exit 0
    fi
  done

  sleep 0.1
  i=$((i + 1))
done

exit 0
