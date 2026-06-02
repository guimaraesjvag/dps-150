#!/usr/bin/env bash
# Install the FNIRSI DPS150 driver so `dps150` is available as a command
# in every shell. Uses pipx for an isolated, system-wide install.
#
# Usage:
#   bash install.sh             # install / re-install
#   bash install.sh --uninstall
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="fnirsi-dps150"

if [[ "${1:-}" == "--uninstall" ]]; then
    pipx uninstall "${APP_NAME}"
    echo "Removed ${APP_NAME}."
    exit 0
fi

if ! command -v pipx >/dev/null; then
    echo "pipx not found. Installing it (needs sudo)..."
    sudo apt-get update
    sudo apt-get install -y pipx
fi

pipx ensurepath >/dev/null

pipx install --editable --force "${SRC_DIR}"

echo
echo "Installed. Open a new shell (or 'source ~/.zshrc') and try:"
echo "    dps150 status"
echo
echo "If you get 'Permission denied' on the USB device, run:"
echo "    sudo ${SRC_DIR}/udev/setup_permissions.sh"
