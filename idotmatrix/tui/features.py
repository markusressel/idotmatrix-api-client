"""The features of the display that the controls page shows: what to ask for and which calls of the library to make."""
from datetime import datetime

from rich.text import Text

from idotmatrix.modules.clock import ClockStyle
from idotmatrix.modules.effect import EffectStyle
from idotmatrix.modules.text import TextColorMode, TextMode
from idotmatrix.tui.forms import Action, Feature, Field
from idotmatrix.tui.scoreboard import ScoreboardForm
from idotmatrix.tui.widgets import rainbow


CLOCK_STYLES = {
    ClockStyle.RGBSwipeOutline: "RGB swipe outline", ClockStyle.ChristmasTree: "Christmas tree",
    ClockStyle.Checkers: "Checkers", ClockStyle.Color: "Color", ClockStyle.Hourglass: "Hourglass",
    ClockStyle.AlarmClock: "Alarm clock", ClockStyle.Outlines: "Outlines", ClockStyle.RGBCorners: "RGB corners",
}


# what the styles look like on a 64x64, as far as it was looked at (see docs/DEVICE-PROTOCOL.md)
EFFECT_STYLES = {
    EffectStyle.GRADIENT_HORIZONTAL_RAINBOW: "Smooth rainbow, horizontal stripes",
    EffectStyle.VERTICAL_RAINBOW: "Hard rainbow, vertical stripes",
    EffectStyle.DIAGONAL_RIGHT_RAINBOW: "Hard rainbow, diagonal stripes",
}


def _choices(enum, names: dict | None = None) -> tuple:
    """The members of an enum as (label, value) for a list."""
    return tuple(((names or {}).get(member) or member.name.replace("_", " ").capitalize(), member.value)
                 for member in enum)


async def _clock(client, v: dict):
    await client.clock.show(style=v["style"], show_date=v["show_date"], hour24=v["hour24"], color=v["color"])


async def _text(client, v: dict):
    await client.text.show_text(
        v["text"], font_size=v["font_size"], text_mode=v["mode"], speed=v["speed"], text_color_mode=v["color_mode"],
        text_color=v["color"], text_bg_color=v["background"])


async def _color(client, v: dict):
    await client.color.show_color(v["color"])


async def _effect(client, v: dict):
    await client.effect.show(v["style"], v["colors"])


async def _normal(client, v: dict):
    await client.common.set_screen_flipped(False)


async def _flipped(client, v: dict):
    await client.common.set_screen_flipped(True)


async def _count_start(client, v: dict):
    minutes, seconds = v["time"]
    await client.countdown.start(minutes, seconds)


async def _count_pause(client, v: dict):
    await client.countdown.pause()


async def _count_restart(client, v: dict):
    await client.countdown.restart()


async def _count_stop(client, v: dict):
    await client.countdown.stop()


async def _chrono_start(client, v: dict):
    await client.chronograph.start_from_zero()


async def _chrono_pause(client, v: dict):
    await client.chronograph.pause()


async def _chrono_resume(client, v: dict):
    await client.chronograph.resume()


async def _chrono_reset(client, v: dict):
    await client.chronograph.reset()


async def _eco(client, v: dict):
    (start_hour, start_minute), (end_hour, end_minute) = v["start"], v["end"]
    await client.eco.set_mode(enabled=v["enabled"], start_hour=start_hour, start_minute=start_minute,
                              end_hour=end_hour, end_minute=end_minute, eco_brightness=v["brightness"])


async def _music(client, v: dict):
    await client.music_sync.set_mic_type(v["scene"], v["sensitivity"])


async def _sync_time(client, v: dict):
    await client.common.set_time(datetime.now())
    return "The time of the display is set"


async def _info(client, v: dict):
    info = await client.common.get_device_info()
    if info is None:
        return "The display did not answer"
    size = info.screen_size
    protected = ", password protected" if info.password_protected else ""
    return f"Firmware {info.firmware_version}, screen {size.name if size else info.screen_type}{protected}"


async def _reset(client, v: dict):
    await client.common.reset()


async def _delete_data(client, v: dict):
    await client.system.delete_device_data()


COLOR_HINT = "#rrggbb or a name"

def _color_modes() -> tuple:
    labels = {TextColorMode.WHITE: Text("White", style="bold white"), TextColorMode.RGB: Text("The color below")}
    return tuple((labels.get(mode) or rainbow(f"Rainbow {mode.value - 1}"), mode.value) for mode in TextColorMode)


FEATURES = (
    Feature(
        "clock", "Clock", "Shows the time on the display.",
        fields=(
            Field("style", "Style", "choice", ClockStyle.RGBSwipeOutline.value, choices=_choices(ClockStyle, CLOCK_STYLES)),
            Field("show_date", "Show the date", "bool", True),
            Field("hour24", "24 hour format", "bool", True),
            Field("color", "Color", "color", "#ffffff", placeholder=COLOR_HINT),
        ),
        actions=(Action("Show the clock", _clock, "primary", icon="▶"),),
        live=True,
    ),
    Feature(
        "text", "Text", "Scrolls or shows a text. Enter in any field, or Ctrl+J, shows it.",
        fields=(
            Field("text", "Text", "text", "Hello"),
            Field("font_size", "Font size", "int", 16, low=6, high=64),
            Field("mode", "Mode", "choice", TextMode.MARQUEE.value, choices=_choices(TextMode)),
            Field("speed", "Speed in percent", "int", 95, low=5, high=100),
            Field("color_mode", "Color mode", "choice", TextColorMode.WHITE.value, choices=_color_modes()),
            Field("color", "Color", "color", "#ffffff", placeholder=COLOR_HINT),
            Field("background", "Background (empty: black)", "color", "", placeholder=COLOR_HINT, required=False),
        ),
        actions=(Action("Show the text", _text, "primary", icon="▶"),),
        preview="text",
    ),
    Feature(
        "color", "Color", "Fills the display with one color.",
        fields=(Field("color", "Color", "color", "#ff0000", placeholder=COLOR_HINT),),
        actions=(Action("Show the color", _color, "primary", icon="▶"),),
        live=True,
    ),
    Feature(
        "effect", "Effects", "Animated backgrounds, with 2 to 7 colors.",
        fields=(
            Field("style", "Style", "choice", EffectStyle.GRADIENT_HORIZONTAL_RAINBOW.value,
                  choices=_choices(EffectStyle, EFFECT_STYLES)),
            Field("colors", "Colors", "colors", ["#ff0000", "#00ff00", "#0000ff"]),
        ),
        actions=(Action("Show the effect", _effect, "primary", icon="▶"),),
        live=True,
        preview="effect",
    ),
    Feature(
        "countdown", "Countdown", "Counts down on the display.",
        fields=(Field("time", "Time (minutes:seconds)", "duration", "05:00", placeholder="12:34"),),
        actions=(
            Action("Start", _count_start, "primary", icon="▶"),
            Action("Pause", _count_pause, icon="⏸"),
            Action("Restart", _count_restart, icon="↻"),
            Action("Stop", _count_stop, icon="■"),
        ),
    ),
    Feature(
        "chronograph", "Stopwatch", "Counts up from zero.",
        actions=(
            Action("Start", _chrono_start, "primary", icon="▶"),
            Action("Pause", _chrono_pause, icon="⏸"),
            Action("Resume", _chrono_resume, icon="⏵"),
            Action("Reset", _chrono_reset, icon="■"),
        ),
    ),
    Feature(
        "scoreboard", "Scoreboard", "Two counters, 0 to 999, sent as you count. Up and Down count, Left and Right "
                                    "pick the side, or click and use the wheel.",
        fields=(Field("first", "Home", "int", 0, low=0, high=999), Field("second", "Guest", "int", 0, low=0, high=999)),
        live=True,
        form=ScoreboardForm,
    ),
    Feature(
        "eco", "Eco mode", "Lowers the brightness between two times of the day.",
        fields=(
            Field("enabled", "Eco mode on", "bool", True),
            Field("start", "From (hours:minutes)", "time", "22:00"),
            Field("end", "Until (hours:minutes)", "time", "06:00"),
            Field("brightness", "Brightness in percent", "int", 10, low=0, high=100),
        ),
        actions=(Action("Apply", _eco, "primary"),),
    ),
    Feature(
        "music", "Music", "The display reacts to sound with its own microphone. There is no command to leave this, "
                          "show something else instead.",
        fields=(
            Field("scene", "Scene", "int", 1, low=1, high=10),
            Field("sensitivity", "Sensitivity, 0 to 100", "int", 50, low=0, high=100),
        ),
        actions=(Action("Start", _music, "primary"),),
    ),
    Feature(
        "device", "Device", "Rotation, the time, what the display knows about itself, and resets. Brightness and "
                            "power are at the bottom of every page.",
        actions=(
            Action("Normal", _normal, "primary", icon="⟲"),
            Action("Upside down", _flipped, icon="⟳"),
            Action("Set the time", _sync_time, icon="◷"),
            Action("Info", _info, icon="ⓘ"),
            Action("Reset", _reset, "warning", "Reset the display and its internals? It can fix issues that appear "
                                                "over time.", icon="⚠"),
            Action("Delete data", _delete_data, "error", "Delete the data of the display and reset it to defaults? "
                                                         "The stored pictures are gone.", icon="✖"),
        ),
    ),
)
