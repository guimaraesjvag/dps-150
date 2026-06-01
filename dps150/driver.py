"""
FNIRSI DPS150 serial driver.

Protocol: 115200 8N1, hardware flow control (RTS/CTS)
Packet format (host→device): F1 <cmd> <reg> <len> [data...] <checksum>
Packet format (device→host): F0 <cmd> <reg> <len> [data...] <checksum>
Checksum: (reg + len + sum(data)) & 0xFF
"""

import glob
import os
import serial
import struct
import threading
import time
from typing import Optional, Callable, List, Tuple

# Packet headers
HEADER_HOST = 0xF1
HEADER_DEVICE = 0xF0

# Commands
CMD_GET = 0xA1
CMD_BAUD = 0xB0
CMD_SET = 0xB1
CMD_SESSION = 0xC1

# Registers
REG_INPUT_VOLTAGE = 0xC0   # float32
REG_VOLTAGE_SET   = 0xC1   # float32
REG_CURRENT_SET   = 0xC2   # float32
REG_OUTPUT        = 0xC3   # 3×float32: V, I, P
REG_TEMPERATURE   = 0xC4   # float32
REG_PRESET_BASE   = 0xC5   # M1 voltage; M1_I at 0xC6, M2_V at 0xC7, ...
REG_OVP           = 0xD1   # float32
REG_OCP           = 0xD2   # float32
REG_OPP           = 0xD3   # float32
REG_OTP           = 0xD4   # float32
REG_LVP           = 0xD5   # float32
REG_BRIGHTNESS    = 0xD6   # uint8 0-5
REG_VOLUME        = 0xD7   # uint8
REG_METERING      = 0xD8   # uint8
REG_CAPACITY      = 0xD9   # float32 Ah
REG_ENERGY        = 0xDA   # float32 Wh
REG_OUTPUT_ENABLE = 0xDB   # uint8
REG_PROTECTION    = 0xDC   # uint8
REG_MODE          = 0xDD   # uint8: 0=CC, 1=CV
REG_MODEL         = 0xDE   # string
REG_HW_VERSION    = 0xDF   # string
REG_FW_VERSION    = 0xE0   # string
REG_ADDRESS       = 0xE1   # uint8
REG_MAX_VOLTAGE   = 0xE2   # float32
REG_MAX_CURRENT   = 0xE3   # float32
REG_ALL           = 0xFF   # full state dump (139 bytes)

PROTECTION_NAMES = ["Normal", "OVP", "OCP", "OPP", "OTP", "LVP", "REP"]
MODE_NAMES = ["CC", "CV"]

DEFAULT_PORT = "/dev/serial/by-id/usb-Artery_AT32_Virtual_Com_Port_10FAB7D04055-if00"

# USB VID:PID for the FNIRSI DPS150 (Artery AT32 virtual COM)
_USB_VID = "2e3c"
_USB_PID = "5740"


def find_port() -> str:
    """Auto-detect the DPS150 serial port. Returns the first match found."""
    # 1. udev symlink created by the 99-fnirsi-dps150.rules rule
    if os.path.exists("/dev/dps150"):
        return "/dev/dps150"
    # 2. by-id path that embeds the Artery USB serial number
    for p in glob.glob("/dev/serial/by-id/*Artery*"):
        return p
    # 3. scan /sys for our VID:PID
    for path in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        with open(path) as f:
            if f.read().strip() == _USB_VID:
                pid_path = os.path.join(os.path.dirname(path), "idProduct")
                if os.path.exists(pid_path):
                    with open(pid_path) as f2:
                        if f2.read().strip() == _USB_PID:
                            # Found the USB device — now find its tty
                            base = os.path.dirname(path)
                            for tty in glob.glob(os.path.join(base, "**/tty*"), recursive=True):
                                if os.path.basename(tty).startswith("tty"):
                                    return os.path.join("/dev", os.path.basename(tty))
    # 4. fall back to the hardcoded by-id path
    return DEFAULT_PORT


class DeviceState:
    __slots__ = [
        "input_voltage", "output_voltage", "output_current", "output_power",
        "temperature", "voltage_set", "current_set", "output_enabled",
        "protection_status", "mode", "max_voltage", "max_current",
        "capacity_ah", "energy_wh", "ovp", "ocp", "opp", "otp", "lvp",
        "model", "hw_version", "fw_version", "brightness", "volume",
        "presets", "connected",
    ]

    def __init__(self):
        self.input_voltage: float = 0.0
        self.output_voltage: float = 0.0
        self.output_current: float = 0.0
        self.output_power: float = 0.0
        self.temperature: float = 0.0
        self.voltage_set: float = 0.0
        self.current_set: float = 0.0
        self.output_enabled: bool = False
        self.protection_status: int = 0
        self.mode: int = 0
        self.max_voltage: float = 30.0
        self.max_current: float = 5.0
        self.capacity_ah: float = 0.0
        self.energy_wh: float = 0.0
        self.ovp: float = 0.0
        self.ocp: float = 0.0
        self.opp: float = 0.0
        self.otp: float = 0.0
        self.lvp: float = 0.0
        self.model: str = ""
        self.hw_version: str = ""
        self.fw_version: str = ""
        self.brightness: int = 0
        self.volume: int = 0
        self.presets: List[Tuple[float, float]] = [(0.0, 0.0)] * 6
        self.connected: bool = False

    @property
    def protection_name(self) -> str:
        if 0 <= self.protection_status < len(PROTECTION_NAMES):
            return PROTECTION_NAMES[self.protection_status]
        return "Unknown"

    @property
    def mode_name(self) -> str:
        if 0 <= self.mode < len(MODE_NAMES):
            return MODE_NAMES[self.mode]
        return "?"

    def copy(self) -> "DeviceState":
        s = DeviceState()
        for attr in self.__slots__:
            val = getattr(self, attr)
            setattr(s, attr, list(val) if isinstance(val, list) else val)
        return s


class DPS150:
    def __init__(self, port: Optional[str] = None, rtscts: bool = False):
        self.port = port or find_port()
        self.rtscts = rtscts
        self._serial: Optional[serial.Serial] = None
        self._state = DeviceState()
        self._lock = threading.RLock()
        self._running = False
        self._reader_thread: Optional[threading.Thread] = None
        self._buffer = b""
        self._callbacks: List[Callable] = []

    @property
    def state(self) -> DeviceState:
        with self._lock:
            return self._state.copy()

    def on_state_update(self, callback: Callable[[DeviceState], None]) -> None:
        self._callbacks.append(callback)

    def connect(self) -> None:
        self._serial = serial.Serial(
            self.port,
            baudrate=115200,
            bytesize=serial.EIGHTBITS,
            stopbits=serial.STOPBITS_ONE,
            parity=serial.PARITY_NONE,
            rtscts=self.rtscts,
            timeout=0.05,
        )
        self._buffer = b""
        self._running = True
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

        self._send_session(True)
        time.sleep(0.2)
        self._request_initial_state()
        time.sleep(0.8)

        with self._lock:
            self._state.connected = True

    def disconnect(self) -> None:
        with self._lock:
            self._state.connected = False
        try:
            self._send_session(False)
            time.sleep(0.05)
        except Exception:
            pass
        self._running = False
        if self._reader_thread:
            self._reader_thread.join(timeout=1.0)
        if self._serial:
            self._serial.close()
            self._serial = None

    def __enter__(self) -> "DPS150":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    # ── setters ──────────────────────────────────────────────────────────────

    def set_voltage(self, voltage: float) -> None:
        self._send_packet(CMD_SET, REG_VOLTAGE_SET, struct.pack("<f", voltage))
        with self._lock:
            self._state.voltage_set = voltage

    def set_current(self, current: float) -> None:
        self._send_packet(CMD_SET, REG_CURRENT_SET, struct.pack("<f", current))
        with self._lock:
            self._state.current_set = current

    def set_output(self, enabled: bool) -> None:
        self._send_packet(CMD_SET, REG_OUTPUT_ENABLE, bytes([1 if enabled else 0]))
        with self._lock:
            self._state.output_enabled = enabled

    def output_on(self) -> None:
        self.set_output(True)

    def output_off(self) -> None:
        self.set_output(False)

    def toggle_output(self) -> None:
        with self._lock:
            enabled = self._state.output_enabled
        self.set_output(not enabled)

    def set_brightness(self, value: int) -> None:
        self._send_packet(CMD_SET, REG_BRIGHTNESS, bytes([max(0, min(5, value))]))

    def set_ovp(self, voltage: float) -> None:
        self._send_packet(CMD_SET, REG_OVP, struct.pack("<f", voltage))

    def set_ocp(self, current: float) -> None:
        self._send_packet(CMD_SET, REG_OCP, struct.pack("<f", current))

    def set_preset(self, preset: int, voltage: float, current: float) -> None:
        if not 1 <= preset <= 6:
            raise ValueError("Preset must be 1–6")
        base = REG_PRESET_BASE + (preset - 1) * 2
        self._send_packet(CMD_SET, base, struct.pack("<f", voltage))
        time.sleep(0.05)
        self._send_packet(CMD_SET, base + 1, struct.pack("<f", current))

    def reset_counters(self) -> None:
        zero = struct.pack("<f", 0.0)
        self._send_packet(CMD_SET, REG_CAPACITY, zero)
        time.sleep(0.05)
        self._send_packet(CMD_SET, REG_ENERGY, zero)
        with self._lock:
            self._state.capacity_ah = 0.0
            self._state.energy_wh = 0.0

    def poll(self) -> None:
        """Request fresh live measurements from the device."""
        for reg in [REG_INPUT_VOLTAGE, REG_OUTPUT, REG_TEMPERATURE,
                    REG_OUTPUT_ENABLE, REG_PROTECTION, REG_MODE]:
            self._request_register(reg)
            time.sleep(0.02)

    # ── internals ────────────────────────────────────────────────────────────

    def _checksum(self, reg: int, data: bytes) -> int:
        return (reg + len(data) + sum(data)) & 0xFF

    def _send_packet(self, cmd: int, reg: int, data: bytes = b"") -> None:
        cs = self._checksum(reg, data)
        packet = bytes([HEADER_HOST, cmd, reg, len(data)]) + data + bytes([cs])
        if self._serial and self._serial.is_open:
            self._serial.write(packet)

    def _send_session(self, connected: bool) -> None:
        self._send_packet(CMD_SESSION, 0x00, bytes([0x01 if connected else 0x00]))

    def _request_register(self, reg: int) -> None:
        self._send_packet(CMD_GET, reg)

    def _request_initial_state(self) -> None:
        regs = [
            REG_MODEL, REG_HW_VERSION, REG_FW_VERSION,
            REG_MAX_VOLTAGE, REG_MAX_CURRENT,
            REG_VOLTAGE_SET, REG_CURRENT_SET,
            REG_OUTPUT_ENABLE, REG_PROTECTION, REG_MODE,
            REG_INPUT_VOLTAGE, REG_OUTPUT, REG_TEMPERATURE,
            REG_OVP, REG_OCP, REG_OPP, REG_OTP, REG_LVP,
            REG_CAPACITY, REG_ENERGY, REG_BRIGHTNESS,
        ]
        for reg in regs:
            self._request_register(reg)
            time.sleep(0.04)

    def _reader_loop(self) -> None:
        while self._running:
            try:
                data = self._serial.read(256)
                if data:
                    self._buffer += data
                    self._process_buffer()
            except serial.SerialException:
                if self._running:
                    time.sleep(0.1)
            except Exception:
                time.sleep(0.01)

    def _process_buffer(self) -> None:
        buf = self._buffer
        while len(buf) >= 5:
            if buf[0] != HEADER_DEVICE:
                buf = buf[1:]
                continue
            length = buf[3]
            packet_size = 5 + length  # header(1) + cmd(1) + reg(1) + len(1) + data(N) + cs(1)
            if len(buf) < packet_size:
                break
            packet = buf[:packet_size]
            buf = buf[packet_size:]
            self._handle_packet(packet)
        self._buffer = buf

    def _handle_packet(self, packet: bytes) -> None:
        reg = packet[2]
        length = packet[3]
        data = packet[4:4 + length]
        expected_cs = self._checksum(reg, data)
        if packet[4 + length] != expected_cs:
            return

        with self._lock:
            self._parse_register(reg, data)

        state = self.state
        for cb in self._callbacks:
            try:
                cb(state)
            except Exception:
                pass

    def _parse_register(self, reg: int, data: bytes) -> None:
        try:
            if reg == REG_INPUT_VOLTAGE and len(data) >= 4:
                self._state.input_voltage = struct.unpack("<f", data[:4])[0]
            elif reg == REG_VOLTAGE_SET and len(data) >= 4:
                self._state.voltage_set = struct.unpack("<f", data[:4])[0]
            elif reg == REG_CURRENT_SET and len(data) >= 4:
                self._state.current_set = struct.unpack("<f", data[:4])[0]
            elif reg == REG_OUTPUT and len(data) >= 12:
                self._state.output_voltage = struct.unpack("<f", data[0:4])[0]
                self._state.output_current = struct.unpack("<f", data[4:8])[0]
                self._state.output_power   = struct.unpack("<f", data[8:12])[0]
            elif reg == REG_TEMPERATURE and len(data) >= 4:
                self._state.temperature = struct.unpack("<f", data[:4])[0]
            elif reg == REG_OUTPUT_ENABLE and len(data) >= 1:
                self._state.output_enabled = bool(data[0])
            elif reg == REG_PROTECTION and len(data) >= 1:
                self._state.protection_status = data[0]
            elif reg == REG_MODE and len(data) >= 1:
                self._state.mode = data[0]
            elif reg == REG_MAX_VOLTAGE and len(data) >= 4:
                self._state.max_voltage = struct.unpack("<f", data[:4])[0]
            elif reg == REG_MAX_CURRENT and len(data) >= 4:
                self._state.max_current = struct.unpack("<f", data[:4])[0]
            elif reg == REG_CAPACITY and len(data) >= 4:
                self._state.capacity_ah = struct.unpack("<f", data[:4])[0]
            elif reg == REG_ENERGY and len(data) >= 4:
                self._state.energy_wh = struct.unpack("<f", data[:4])[0]
            elif reg == REG_OVP and len(data) >= 4:
                self._state.ovp = struct.unpack("<f", data[:4])[0]
            elif reg == REG_OCP and len(data) >= 4:
                self._state.ocp = struct.unpack("<f", data[:4])[0]
            elif reg == REG_OPP and len(data) >= 4:
                self._state.opp = struct.unpack("<f", data[:4])[0]
            elif reg == REG_OTP and len(data) >= 4:
                self._state.otp = struct.unpack("<f", data[:4])[0]
            elif reg == REG_LVP and len(data) >= 4:
                self._state.lvp = struct.unpack("<f", data[:4])[0]
            elif reg == REG_BRIGHTNESS and len(data) >= 1:
                self._state.brightness = data[0]
            elif reg == REG_VOLUME and len(data) >= 1:
                self._state.volume = data[0]
            elif reg == REG_MODEL:
                self._state.model = data.rstrip(b"\x00").decode("ascii", errors="replace").strip()
            elif reg == REG_HW_VERSION:
                self._state.hw_version = data.rstrip(b"\x00").decode("ascii", errors="replace").strip()
            elif reg == REG_FW_VERSION:
                self._state.fw_version = data.rstrip(b"\x00").decode("ascii", errors="replace").strip()
            elif reg == REG_ALL and len(data) >= 119:
                self._parse_full_state(data)
            elif REG_PRESET_BASE <= reg <= 0xD0 and len(data) >= 4:
                idx = reg - REG_PRESET_BASE
                preset_idx = idx // 2
                field = idx % 2   # 0=voltage, 1=current
                val = struct.unpack("<f", data[:4])[0]
                presets = list(self._state.presets)
                p = list(presets[preset_idx])
                p[field] = val
                presets[preset_idx] = tuple(p)
                self._state.presets = presets
        except Exception:
            pass

    def _parse_full_state(self, data: bytes) -> None:
        """Parse the 139-byte full state dump (register 0xFF)."""
        try:
            i = 0
            def f32() -> float:
                nonlocal i
                v = struct.unpack_from("<f", data, i)[0]
                i += 4
                return v
            def u8() -> int:
                nonlocal i
                v = data[i]
                i += 1
                return v

            self._state.input_voltage  = f32()
            self._state.voltage_set    = f32()
            self._state.current_set    = f32()
            self._state.output_voltage = f32()
            self._state.output_current = f32()
            self._state.output_power   = f32()
            self._state.temperature    = f32()

            presets = []
            for _ in range(6):
                v, c = f32(), f32()
                presets.append((v, c))
            self._state.presets = presets

            self._state.ovp = f32()
            self._state.ocp = f32()
            self._state.opp = f32()
            self._state.otp = f32()
            self._state.lvp = f32()

            self._state.brightness = u8()
            self._state.volume     = u8()
            u8()  # metering enable

            self._state.capacity_ah = f32()
            self._state.energy_wh   = f32()

            self._state.output_enabled    = bool(u8())
            self._state.protection_status = u8()
            self._state.mode              = u8()
            u8()  # device address

            self._state.max_voltage = f32()
            self._state.max_current = f32()
        except Exception:
            pass
