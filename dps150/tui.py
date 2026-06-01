"""Textual TUI for the FNIRSI DPS150."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import Header, Footer, Static, Button, Input, Label
from textual.reactive import reactive

from .driver import DPS150, DeviceState

PROT_COLORS = {0: "green", 1: "red", 2: "red", 3: "red", 4: "red", 5: "red", 6: "red"}

APP_CSS = """
Screen {
    background: $background;
    layout: vertical;
}

#main-row {
    height: 1fr;
}

#left-col {
    width: 1fr;
    padding: 0 1;
}

#right-col {
    width: 1fr;
    padding: 0 1;
}

.section {
    border: solid $primary;
    padding: 1 2;
    margin-bottom: 1;
    height: auto;
}

.section-title {
    color: $accent;
    text-style: bold;
    margin-bottom: 1;
}

#controls Label {
    margin-top: 1;
    color: $text-muted;
}

Input {
    margin-bottom: 0;
    width: 100%;
}

Button {
    margin-top: 1;
    width: 100%;
}

#toggle-btn.on {
    background: $error;
}

#toggle-btn.off {
    background: $success;
}
"""


class MeasurementSection(Static):
    def render_state(self, state: DeviceState) -> str:
        temp_color = "red" if state.temperature > 65 else "yellow" if state.temperature > 50 else "green"
        return (
            "[bold $accent]LIVE MEASUREMENTS[/]\n"
            f"  [dim]In Voltage :[/]  [bold cyan]{state.input_voltage:8.3f}[/]  V\n"
            f"  [dim]Out Voltage:[/]  [bold green]{state.output_voltage:8.3f}[/]  V\n"
            f"  [dim]Out Current:[/]  [bold yellow]{state.output_current:8.3f}[/]  A\n"
            f"  [dim]Out Power  :[/]  [bold magenta]{state.output_power:8.3f}[/]  W\n"
            f"  [dim]Temperature:[/]  [bold {temp_color}]{state.temperature:8.1f}[/]  °C"
        )


class StatusSection(Static):
    def render_state(self, state: DeviceState) -> str:
        out_str = "[bold green]● ON [/]" if state.output_enabled else "[bold red]○ OFF[/]"
        mode_color = "yellow" if state.mode == 0 else "green"
        prot_color = PROT_COLORS.get(state.protection_status, "red")
        return (
            "[bold $accent]STATUS[/]\n"
            f"  [dim]Output    :[/]  {out_str}\n"
            f"  [dim]Mode      :[/]  [bold {mode_color}]{state.mode_name:4}[/]\n"
            f"  [dim]Protection:[/]  [bold {prot_color}]{state.protection_name}[/]\n"
            "\n[bold $accent]SETPOINTS[/]\n"
            f"  [dim]Voltage   :[/]  [bold]{state.voltage_set:8.3f}[/]  V\n"
            f"  [dim]Current   :[/]  [bold]{state.current_set:8.3f}[/]  A"
        )


class EnergySection(Static):
    def render_state(self, state: DeviceState) -> str:
        return (
            "[bold $accent]ENERGY COUNTERS[/]\n"
            f"  [dim]Capacity:[/]  [bold]{state.capacity_ah:8.4f}[/]  Ah\n"
            f"  [dim]Energy  :[/]  [bold]{state.energy_wh:8.4f}[/]  Wh"
        )


class ProtectionSection(Static):
    def render_state(self, state: DeviceState) -> str:
        return (
            "[bold $accent]PROTECTION THRESHOLDS[/]\n"
            f"  [dim]OVP (over-voltage):[/]  {state.ovp:.3f} V\n"
            f"  [dim]OCP (over-current):[/]  {state.ocp:.3f} A\n"
            f"  [dim]OPP (over-power)  :[/]  {state.opp:.2f} W\n"
            f"  [dim]OTP (over-temp)   :[/]  {state.otp:.1f} °C\n"
            f"  [dim]LVP (low-voltage) :[/]  {state.lvp:.3f} V"
        )


class DPS150App(App):
    TITLE = "FNIRSI DPS150 Controller"
    CSS = APP_CSS
    BINDINGS = [
        ("o", "toggle_output", "Toggle Output"),
        ("r", "reset_counters", "Reset Counters"),
        ("p", "poll", "Poll"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, driver: DPS150):
        super().__init__()
        self.driver = driver

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-row"):
            with Vertical(id="left-col"):
                yield MeasurementSection(classes="section", id="meas")
                yield EnergySection(classes="section", id="energy")
                yield ProtectionSection(classes="section", id="prot")
            with Vertical(id="right-col"):
                yield StatusSection(classes="section", id="status")
                with Container(classes="section", id="controls"):
                    yield Static("[bold $accent]CONTROLS[/]", classes="section-title")
                    yield Label("Set Voltage (V):")
                    yield Input(placeholder="e.g. 5.000", id="v-input")
                    yield Label("Set Current (A):")
                    yield Input(placeholder="e.g. 1.000", id="i-input")
                    yield Button("Turn Output ON", id="toggle-btn", variant="success")
                    yield Button("Reset Energy Counters", id="reset-btn", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(0.25, self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        state = self.driver.state
        self.query_one("#meas", MeasurementSection).update(
            self.query_one("#meas", MeasurementSection).render_state(state)
        )
        self.query_one("#energy", EnergySection).update(
            self.query_one("#energy", EnergySection).render_state(state)
        )
        self.query_one("#prot", ProtectionSection).update(
            self.query_one("#prot", ProtectionSection).render_state(state)
        )
        self.query_one("#status", StatusSection).update(
            self.query_one("#status", StatusSection).render_state(state)
        )

        btn = self.query_one("#toggle-btn", Button)
        if state.output_enabled:
            btn.label = "Turn Output OFF  [O]"
            btn.variant = "error"
        else:
            btn.label = "Turn Output ON   [O]"
            btn.variant = "success"

        model = state.model or "DPS150"
        hw = state.hw_version
        fw = state.fw_version
        parts = [f"FNIRSI {model}"]
        if hw:
            parts.append(f"HW:{hw}")
        if fw:
            parts.append(f"FW:{fw}")
        self.title = "  ".join(parts)

        inp_v = self.query_one("#v-input", Input)
        inp_i = self.query_one("#i-input", Input)
        if not inp_v.has_focus and state.voltage_set > 0 and inp_v.value == "":
            inp_v.value = f"{state.voltage_set:.3f}"
        if not inp_i.has_focus and state.current_set > 0 and inp_i.value == "":
            inp_i.value = f"{state.current_set:.3f}"

    def action_toggle_output(self) -> None:
        self.driver.toggle_output()

    def action_reset_counters(self) -> None:
        self.driver.reset_counters()
        self.notify("Energy counters reset", severity="information")

    def action_poll(self) -> None:
        self.driver.poll()

    def action_quit(self) -> None:
        self.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "toggle-btn":
            self.driver.toggle_output()
        elif event.button.id == "reset-btn":
            self.action_reset_counters()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "v-input":
            try:
                v = float(event.value)
                state = self.driver.state
                v = max(0.0, min(v, state.max_voltage or 30.0))
                self.driver.set_voltage(v)
                event.input.value = f"{v:.3f}"
                self.notify(f"Voltage → {v:.3f} V", severity="information")
            except ValueError:
                self.notify("Invalid voltage", severity="error")
        elif event.input.id == "i-input":
            try:
                c = float(event.value)
                state = self.driver.state
                c = max(0.0, min(c, state.max_current or 5.0))
                self.driver.set_current(c)
                event.input.value = f"{c:.3f}"
                self.notify(f"Current → {c:.3f} A", severity="information")
            except ValueError:
                self.notify("Invalid current", severity="error")
