#!/bin/bash
# Install udev rule so the DPS150 is accessible without sudo.
# This grants the 'plugdev' group (which your user is already in) access to the device.
set -e

RULE_SRC="$(dirname "$0")/99-fnirsi-dps150.rules"
RULE_DST="/etc/udev/rules.d/99-fnirsi-dps150.rules"

echo "Installing udev rule → $RULE_DST"
sudo cp "$RULE_SRC" "$RULE_DST"
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
sleep 1

if [ -e /dev/dps150 ]; then
    echo "✓ /dev/dps150 symlink created successfully."
    ls -la /dev/dps150
else
    echo "Rule installed. Unplug and replug the USB cable, or reboot."
fi
