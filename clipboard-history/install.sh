#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
"$script_dir/clipboard_history.py" --install

echo "Clipboard History installed."
echo "Use Super+V to open history."
echo "It will also start automatically on login."
