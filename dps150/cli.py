"""Command-line interface for the FNIRSI DPS150."""

import sys
import time
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box

from .driver import DPS150, DEFAULT_PORT, PROTECTION_NAMES, MODE_NAMES

console = Console()


def make_driver(port: str | None, rtscts: bool) -> DPS150:
    return DPS150(port=port, rtscts=rtscts)


def _connect_and_wait(dev: DPS150, extra_wait: float = 0.0) -> None:
    try:
        dev.connect()
        if extra_wait:
            time.sleep(extra_wait)
    except Exception as e:
        console.print(f"[red]Connection failed:[/red] {e}")
        console.print(f"[dim]Port: {dev.port}[/dim]")
        console.print(
            "[yellow]Tip:[/yellow] If permission denied, run: "
            "[cyan]sudo usermod -aG dialout $USER[/cyan] then log out/in."
        )
        sys.exit(1)


def _print_status(state) -> None:
    out_color = "green" if state.output_enabled else "red"
    out_str = "● ON" if state.output_enabled else "○ OFF"
    mode_color = "yellow" if state.mode == 0 else "green"
    prot_color = "red" if state.protection_status else "green"

    meas = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    meas.add_column("label", style="dim", no_wrap=True)
    meas.add_column("value", style="bold", no_wrap=True)
    meas.add_row("In Voltage",  f"[cyan]{state.input_voltage:8.3f}[/cyan] V")
    meas.add_row("Out Voltage", f"[green]{state.output_voltage:8.3f}[/green] V")
    meas.add_row("Out Current", f"[yellow]{state.output_current:8.3f}[/yellow] A")
    meas.add_row("Out Power",   f"[magenta]{state.output_power:8.3f}[/magenta] W")
    meas.add_row("Temperature", f"{state.temperature:8.1f} °C")

    cfg = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    cfg.add_column("label", style="dim", no_wrap=True)
    cfg.add_column("value", style="bold", no_wrap=True)
    cfg.add_row("Set Voltage",  f"{state.voltage_set:.3f} V")
    cfg.add_row("Set Current",  f"{state.current_set:.3f} A")
    cfg.add_row("Output",       f"[{out_color}]{out_str}[/{out_color}]")
    cfg.add_row("Mode",         f"[{mode_color}]{state.mode_name}[/{mode_color}]")
    cfg.add_row("Protection",   f"[{prot_color}]{state.protection_name}[/{prot_color}]")
    cfg.add_row("Capacity",     f"{state.capacity_ah:.4f} Ah")
    cfg.add_row("Energy",       f"{state.energy_wh:.4f} Wh")

    model = state.model or "DPS150"
    hw = f"  HW:{state.hw_version}" if state.hw_version else ""
    fw = f"  FW:{state.fw_version}" if state.fw_version else ""

    console.print(Panel(
        Columns([
            Panel(meas, title="Measurements", border_style="cyan"),
            Panel(cfg,  title="Settings / Status", border_style="green"),
        ]),
        title=f"[bold]FNIRSI {model}{hw}{fw}[/bold]",
        border_style="blue",
    ))


@click.group()
@click.option("--port", "-p", default=None, envvar="DPS150_PORT",
              help="Serial port. Default: auto-detect by USB ID. Env: DPS150_PORT")
@click.option("--rtscts", is_flag=True, default=False,
              help="Enable RTS/CTS hardware flow control (rarely needed)")
@click.pass_context
def cli(ctx: click.Context, port: str | None, rtscts: bool) -> None:
    """FNIRSI DPS150 power supply controller."""
    ctx.ensure_object(dict)
    ctx.obj["port"] = port
    ctx.obj["rtscts"] = rtscts


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current device status."""
    dev = make_driver(ctx.obj["port"], ctx.obj["rtscts"])
    _connect_and_wait(dev)
    with dev:
        _print_status(dev.state)


@cli.command("set-voltage")
@click.argument("voltage", type=float)
@click.pass_context
def set_voltage(ctx: click.Context, voltage: float) -> None:
    """Set output voltage (V)."""
    dev = make_driver(ctx.obj["port"], ctx.obj["rtscts"])
    with dev:
        state = dev.state
        if voltage < 0 or (state.max_voltage and voltage > state.max_voltage):
            console.print(f"[red]Voltage {voltage} V out of range "
                          f"(0 – {state.max_voltage:.1f} V)[/red]")
            sys.exit(1)
        dev.set_voltage(voltage)
        console.print(f"[green]Voltage set to[/green] [bold]{voltage:.3f} V[/bold]")


@cli.command("set-current")
@click.argument("current", type=float)
@click.pass_context
def set_current(ctx: click.Context, current: float) -> None:
    """Set current limit (A)."""
    dev = make_driver(ctx.obj["port"], ctx.obj["rtscts"])
    with dev:
        state = dev.state
        if current < 0 or (state.max_current and current > state.max_current):
            console.print(f"[red]Current {current} A out of range "
                          f"(0 – {state.max_current:.2f} A)[/red]")
            sys.exit(1)
        dev.set_current(current)
        console.print(f"[green]Current limit set to[/green] [bold]{current:.3f} A[/bold]")


@cli.command()
@click.argument("state", type=click.Choice(["on", "off"], case_sensitive=False))
@click.pass_context
def output(ctx: click.Context, state: str) -> None:
    """Enable or disable output (on/off)."""
    dev = make_driver(ctx.obj["port"], ctx.obj["rtscts"])
    with dev:
        enabled = state.lower() == "on"
        dev.set_output(enabled)
        color = "green" if enabled else "red"
        console.print(f"[{color}]Output turned {state.upper()}[/{color}]")


@cli.command()
@click.pass_context
def toggle(ctx: click.Context) -> None:
    """Toggle output on/off."""
    dev = make_driver(ctx.obj["port"], ctx.obj["rtscts"])
    with dev:
        before = dev.state.output_enabled
        dev.toggle_output()
        after = not before
        color = "green" if after else "red"
        state_str = "ON" if after else "OFF"
        console.print(f"[{color}]Output toggled → {state_str}[/{color}]")


@cli.command()
@click.pass_context
def reset_counters(ctx: click.Context) -> None:
    """Reset Ah / Wh energy counters."""
    dev = make_driver(ctx.obj["port"], ctx.obj["rtscts"])
    with dev:
        dev.reset_counters()
        console.print("[green]Energy counters reset.[/green]")


@cli.command()
@click.argument("preset", type=click.IntRange(1, 6))
@click.argument("voltage", type=float)
@click.argument("current", type=float)
@click.pass_context
def set_preset(ctx: click.Context, preset: int, voltage: float, current: float) -> None:
    """Write a memory preset (1-6) with VOLTAGE and CURRENT."""
    dev = make_driver(ctx.obj["port"], ctx.obj["rtscts"])
    with dev:
        dev.set_preset(preset, voltage, current)
        console.print(
            f"[green]Preset M{preset} set to[/green] "
            f"[bold]{voltage:.3f} V / {current:.3f} A[/bold]"
        )


@cli.command()
@click.option("--voltage",    "-v", type=float, default=None, help="Set voltage setpoint")
@click.option("--current",    "-i", type=float, default=None, help="Set current limit")
@click.option("--ovp",              type=float, default=None, help="Over-voltage protection (V)")
@click.option("--ocp",              type=float, default=None, help="Over-current protection (A)")
@click.option("--brightness", "-b", type=click.IntRange(0, 5), default=None, help="Screen brightness 0-5")
@click.pass_context
def configure(ctx: click.Context, voltage, current, ovp, ocp, brightness) -> None:
    """Apply multiple settings at once."""
    if all(v is None for v in [voltage, current, ovp, ocp, brightness]):
        console.print("[yellow]No settings specified. Use --help for options.[/yellow]")
        return
    dev = make_driver(ctx.obj["port"], ctx.obj["rtscts"])
    with dev:
        if voltage is not None:
            dev.set_voltage(voltage)
            console.print(f"  Voltage  → [bold]{voltage:.3f} V[/bold]")
        if current is not None:
            dev.set_current(current)
            console.print(f"  Current  → [bold]{current:.3f} A[/bold]")
        if ovp is not None:
            dev.set_ovp(ovp)
            console.print(f"  OVP      → [bold]{ovp:.3f} V[/bold]")
        if ocp is not None:
            dev.set_ocp(ocp)
            console.print(f"  OCP      → [bold]{ocp:.3f} A[/bold]")
        if brightness is not None:
            dev.set_brightness(brightness)
            console.print(f"  Brightness → [bold]{brightness}[/bold]")


@cli.command()
@click.pass_context
def tui(ctx: click.Context) -> None:
    """Open the interactive terminal UI."""
    from .tui import DPS150App
    dev = make_driver(ctx.obj["port"], ctx.obj["rtscts"])
    _connect_and_wait(dev)
    try:
        app = DPS150App(dev)
        app.run()
    finally:
        dev.disconnect()


@cli.command()
@click.pass_context
def monitor(ctx: click.Context) -> None:
    """Stream live measurements to the terminal (Ctrl+C to stop)."""
    import signal
    dev = make_driver(ctx.obj["port"], ctx.obj["rtscts"])
    _connect_and_wait(dev)

    console.print("[dim]Streaming measurements — press Ctrl+C to stop[/dim]\n")
    header = f"{'Time':>8}  {'Vin':>7}  {'Vout':>7}  {'Iout':>7}  {'Pout':>7}  {'Temp':>6}  {'Mode':>4}  {'Out':>4}"
    console.print(f"[bold dim]{header}[/bold dim]")
    console.print("[dim]" + "─" * len(header) + "[/dim]")

    start = time.time()
    try:
        while True:
            s = dev.state
            elapsed = time.time() - start
            out_str = "[green]ON[/green]" if s.output_enabled else "[red]OFF[/red]"
            mode_str = s.mode_name
            line = (
                f"{elapsed:8.1f}  "
                f"{s.input_voltage:7.3f}  "
                f"[green]{s.output_voltage:7.3f}[/green]  "
                f"[yellow]{s.output_current:7.3f}[/yellow]  "
                f"[magenta]{s.output_power:7.3f}[/magenta]  "
                f"{s.temperature:6.1f}  "
                f"{mode_str:>4}  "
                f"{out_str}"
            )
            console.print(line)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        dev.disconnect()
        console.print("\n[dim]Disconnected.[/dim]")
