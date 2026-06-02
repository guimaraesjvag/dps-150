# FNIRSI DPS150 Driver

Python driver, CLI, and interactive TUI for the **FNIRSI DPS150** USB programmable power supply.

```
╭──────────────────── FNIRSI DPS-150  HW:V1.0  FW:V1.2 ────────────────────╮
│ ╭──────── Measurements ─────────╮ ╭───── Settings / Status ─────╮         │
│ │   In Voltage      30.406 V    │ │   Set Voltage    5.000 V    │         │
│ │   Out Voltage      5.001 V    │ │   Set Current    1.000 A    │         │
│ │   Out Current      0.998 A    │ │   Output         ● ON       │         │
│ │   Out Power        4.991 W    │ │   Mode           CV         │         │
│ │   Temperature       31.2 °C   │ │   Protection     Normal     │         │
│ ╰───────────────────────────────╯ ╰─────────────────────────────╯         │
╰────────────────────────────────────────────────────────────────────────────╯
```

## Requirements

- Linux (tested on Ubuntu 22.04+)
- Python 3.10+
- FNIRSI DPS150 connected via USB-C

## Installation

### 1 — USB permissions

The device shows up as a CDC ACM serial port. By default only root and the
`dialout` group can access it. This script installs a udev rule that grants
access to the `plugdev` group (which most desktop users are already in) and
creates a stable `/dev/dps150` symlink.

```bash
sudo udev/setup_permissions.sh
# Then re-plug the USB cable once.
```

### 2 — Install the `dps150` command

**Option A — pipx (recommended, isolated environment):**

```bash
bash install.sh
# Open a new shell, then:
dps150 status
```

**Option B — pip (system-wide):**

```bash
pip install -e .
dps150 status
```

**Option C — no install, run directly:**

```bash
pip install pyserial click rich textual
python3 -m dps150 status
```

---

## CLI Reference

All commands auto-detect the device. Pass `--port /dev/ttyACM0` to override,
or set the `DPS150_PORT` environment variable.

```
dps150 [--port PORT] <command>
```

### `status` — snapshot of the current device state

```bash
dps150 status
```

```
╭──── FNIRSI DPS-150  HW:V1.0  FW:V1.2 ────╮
│  In Voltage     30.406 V                   │
│  Out Voltage     0.000 V   Set Voltage  5.000 V  │
│  Out Current     0.000 A   Set Current  1.000 A  │
│  Out Power       0.000 W   Output       ○ OFF    │
│  Temperature    30.5  °C   Mode         CV       │
╰────────────────────────────────────────────╯
```

### `set-voltage` — set the output voltage

```bash
dps150 set-voltage 5.0       # set to 5 V
dps150 set-voltage 12.5      # set to 12.5 V
```

### `set-current` — set the current limit

```bash
dps150 set-current 1.0       # limit to 1 A
dps150 set-current 0.5       # limit to 500 mA
```

### `output` — enable or disable output

```bash
dps150 output on
dps150 output off
```

### `toggle` — flip the output state

```bash
dps150 toggle
```

### `configure` — apply multiple settings at once

```bash
dps150 configure -v 5.0 -i 2.0            # set voltage + current
dps150 configure -v 12.0 --ovp 13.0       # set voltage + OVP threshold
dps150 configure --brightness 3           # screen brightness (0–5)
```

| Flag | Description |
|------|-------------|
| `-v`, `--voltage` | Output voltage setpoint (V) |
| `-i`, `--current` | Current limit (A) |
| `--ovp` | Over-voltage protection threshold (V) |
| `--ocp` | Over-current protection threshold (A) |
| `-b`, `--brightness` | Screen brightness 0–5 |

### `set-preset` — write a memory preset (M1–M6)

```bash
dps150 set-preset 1 5.0 1.0    # M1 → 5 V / 1 A
dps150 set-preset 2 12.0 2.0   # M2 → 12 V / 2 A
```

### `reset-counters` — reset the Ah / Wh energy counters

```bash
dps150 reset-counters
```

### `monitor` — stream live measurements (Ctrl+C to stop)

```bash
dps150 monitor
```

```
    Time     Vin      Vout     Iout     Pout    Temp  Mode   Out
────────────────────────────────────────────────────────────────
     0.0   30.406    5.001    0.998    4.991    31.2    CV    ON
     0.5   30.406    5.001    0.999    4.992    31.2    CV    ON
     1.0   30.405    5.000    1.000    5.000    31.3    CV    ON
```

### `tui` — interactive terminal UI

```bash
dps150 tui
```

See [TUI section](#tui) below.

---

## TUI

The TUI gives a live dashboard with interactive controls.

```bash
dps150 tui
```

### Layout

```
┌─ LIVE MEASUREMENTS ─┐   ┌─ STATUS ────────────┐
│  In Voltage  30.406 V│   │  Output   ● ON      │
│  Out Voltage  5.001 V│   │  Mode     CV        │
│  Out Current  0.998 A│   │  Protection  Normal │
│  Out Power    4.991 W│   │                     │
│  Temperature  31.2 °C│   │  Set Voltage  5.000 V│
└─────────────────────┘   │  Set Current  1.000 A│
                           └─────────────────────┘
┌─ ENERGY ────────────┐   ┌─ CONTROLS ──────────┐
│  Capacity  0.2287 Ah│   │  Set Voltage (V):   │
│  Energy    5.4079 Wh│   │  [5.000           ] │
└─────────────────────┘   │  Set Current (A):   │
                           │  [1.000           ] │
┌─ PROTECTION ────────┐   │  [Turn Output OFF ] │
│  OVP  30.000 V      │   │  [Reset Counters  ] │
│  OCP   5.000 A      │   └─────────────────────┘
│  OPP 150.000 W      │
│  OTP  80.0   °C     │
│  LVP   5.000 V      │
└─────────────────────┘
```

### Setting voltage / current

1. Click the **Set Voltage** or **Set Current** input field (or Tab to it).
2. Type the new value.
3. Press **Enter** — a toast confirms the command was sent.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `O` | Toggle output on / off |
| `R` | Reset Ah / Wh energy counters |
| `P` | Force-poll all registers |
| `Q` | Quit |
| `Tab` | Move focus between fields |

---

## Troubleshooting

### `Permission denied` on `/dev/ttyACM*`

```bash
sudo udev/setup_permissions.sh
# Re-plug the USB cable, then retry.
```

Alternatively, add yourself to the `dialout` group (requires logout):

```bash
sudo usermod -aG dialout $USER
```

### Device not detected

Check the device is visible to the system:

```bash
lsusb | grep 2e3c
# Should show: Artery AT32 Virtual Com Port  (VID:PID 2e3c:5740)
```

Check which port it is on:

```bash
ls -l /dev/serial/by-id/ | grep Artery
```

Pass the port explicitly if auto-detection fails:

```bash
dps150 --port /dev/ttyACM0 status
```

### Commands sent but device doesn't respond

The driver disables RTS/CTS flow control by default. If your setup requires
it (unusual), enable it explicitly:

```bash
dps150 --rtscts status
```

---

## Protocol notes

The DPS150 communicates over USB CDC ACM (115200 8N1) using a binary
framing protocol reverse-engineered by
[cho45](https://github.com/cho45/fnirsi-dps-150).

**Packet format:**

```
[Header:1] [Command:1] [Register:1] [Length:1] [Data:N] [Checksum:1]
```

| Field | Host→Device | Device→Host |
|-------|-------------|-------------|
| Header | `0xF1` | `0xF0` |
| Checksum | `(reg + len + sum(data)) & 0xFF` | same |

**Key commands:**

| Command | Byte | Description |
|---------|------|-------------|
| GET | `0xA1` | Read a register |
| SET | `0xB1` | Write a register |
| SESSION | `0xC1` | Connect / disconnect handshake |

The device streams live measurements unsolicited at ~500 ms intervals once
the port is opened. A connect handshake (`F1 C1 00 01 01 02`) is sent on
open and a disconnect handshake (`F1 C1 00 01 00 01`) on close.
