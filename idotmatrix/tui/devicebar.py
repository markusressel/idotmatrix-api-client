from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal

from idotmatrix.tui.widgets import PlainStatic, Slider

MIN_BRIGHTNESS = 5
MAX_BRIGHTNESS = 100


class PowerButton(PlainStatic):
    """Turns the display on or off."""

    ALLOW_SELECT = False
    DEFAULT_CSS = "PowerButton { width: 9; height: 1; padding: 0 1; }"

    def on_click(self, event: events.Click) -> None:
        self.app.toggle_power()


class DeviceBar(Horizontal):
    """Brightness and power of the display, on every page: drag or click the bar, or use the keys."""

    ALLOW_SELECT = False

    DEFAULT_CSS = """
    DeviceBar { height: 1; padding: 0 1; background: $surface; }
    DeviceBar > #label { width: 12; color: $text-muted; }
    DeviceBar > Slider { width: 1fr; max-width: 50; }
    DeviceBar > #percent { width: 6; padding: 0 1; text-align: right; }
    DeviceBar > #hint { width: auto; padding: 0 1; color: $text-muted; }
    """

    def compose(self) -> ComposeResult:
        yield PlainStatic("Brightness", id="label")
        yield Slider(MIN_BRIGHTNESS, MAX_BRIGHTNESS, self.app.brightness)
        yield PlainStatic("", id="percent")
        yield PowerButton()
        yield PlainStatic("F5 dimmer  F6 brighter  F7 power", id="hint")

    def on_mount(self) -> None:
        self.refresh_state()

    def refresh_state(self) -> None:
        app = self.app
        self.query_one(Slider).value = app.brightness
        self.query_one("#percent", PlainStatic).update(f"{app.brightness}%")
        power = Text(" ⏻ on  " if app.screen_on else " ⏻ off ",
                     style="bold white on green" if app.screen_on else "bold white on red")
        self.query_one(PowerButton).update(power)

    def on_slider_changed(self, event: Slider.Changed) -> None:
        event.stop()
        self.app.set_brightness(event.value)
