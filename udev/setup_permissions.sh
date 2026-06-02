#!/usr/bin/env bash
# Install udev rule so the FNIRSI DPS150 is accessible without sudo.
# Run with: sudo udev/setup_permissions.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (use sudo)." >&2
    exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULE_FILE="99-fnirsi-dps150.rules"
DEST="/etc/udev/rules.d/${RULE_FILE}"

install -m 0644 "${SRC_DIR}/${RULE_FILE}" "${DEST}"
echo "Installed ${DEST}"

udevadm control --reload-rules
udevadm trigger --subsystem-match=tty
echo "Done. Re-plug the DPS150 USB cable."
echo "The device will appear as /dev/dps150 and be accessible by the 'plugdev' group."
