#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$script_dir/../src/linux_toolbox/resources/scripts/install-cockpit-tools-fork.sh" "$@"
