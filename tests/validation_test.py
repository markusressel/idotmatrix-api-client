from unittest.mock import AsyncMock, patch

from idotmatrix.modules.chronograph import ChronographModule
from idotmatrix.modules.clock import ClockModule
from idotmatrix.modules.countdown import CountdownModule
from idotmatrix.modules.eco import EcoModule
from idotmatrix.modules.effect import EffectModule
from idotmatrix.modules.fullscreen_color import FullscreenColorModule
from idotmatrix.modules.graffiti import GraffitiModule, MAX_PIXEL_LIST_LENGTH
from idotmatrix.modules.text import TextModule, TextColorMode
from tests import TestBase


@patch("idotmatrix.modules.sleep", new=AsyncMock())
class TestModuleValidation(TestBase):
    """Invalid arguments must raise ValueError and must not send anything."""

    def setUp(self):
        self.cm = AsyncMock()

    def tearDown(self):
        self.cm.send_bytes.assert_not_awaited()
        self.cm.send_packets.assert_not_awaited()

    async def test_clock_invalid_style(self):
        for style in (-1, 8):
            with self.subTest(style=style), self.assertRaises(ValueError):
                await ClockModule(self.cm).show(style=style)

    async def test_clock_invalid_color(self):
        for color in ((1, 2), (1, 2, 256), (1, 2, 3.0), "notacolor"):
            with self.subTest(color=color), self.assertRaises(ValueError):
                await ClockModule(self.cm).show(color=color)

    async def test_chronograph_invalid_mode(self):
        for mode in (-1, 4):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                await ChronographModule(self.cm)._set_mode(mode)

    async def test_countdown_invalid_mode(self):
        for mode in (-1, 4):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                await CountdownModule(self.cm)._set_mode(mode=mode, minutes=1, seconds=1)

    async def test_countdown_invalid_time(self):
        for minutes, seconds in ((60, 0), (-1, 0), (0, 60), (0, -1)):
            with self.subTest(minutes=minutes, seconds=seconds), self.assertRaises(ValueError):
                await CountdownModule(self.cm).start(minutes=minutes, seconds=seconds)

    async def test_eco_invalid_values(self):
        for kwargs in (
            {"start_hour": 24}, {"start_hour": -1}, {"end_hour": 24},
            {"start_minute": 60}, {"end_minute": 60}, {"end_minute": -1},
            {"eco_brightness": 256}, {"eco_brightness": -1},
        ):
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                await EcoModule(self.cm).set_mode(**kwargs)

    async def test_effect_invalid_style(self):
        for style in (-1, 7):
            with self.subTest(style=style), self.assertRaises(ValueError):
                await EffectModule(self.cm).show(style=style, colors=[(1, 2, 3), (4, 5, 6)])

    async def test_effect_invalid_color_count(self):
        for count in (0, 1, 8):
            with self.subTest(count=count), self.assertRaises(ValueError):
                await EffectModule(self.cm).show(style=0, colors=[(1, 2, 3)] * count)

    async def test_fullscreen_color_invalid_rgb(self):
        for rgb in ((256, 0, 0), (0, 256, 0), (0, 0, 256), (-1, 0, 0)):
            with self.subTest(rgb=rgb), self.assertRaises(ValueError):
                await FullscreenColorModule(self.cm)._show_color_rgb(*rgb)

    async def test_graffiti_too_many_pixels(self):
        xys = [(0, 0)] * (MAX_PIXEL_LIST_LENGTH + 1)
        with self.assertRaises(ValueError):
            await GraffitiModule(self.cm).set_pixels(color=(1, 2, 3), xys=xys)

    async def test_text_rgb_mode_requires_color(self):
        with self.assertRaises(ValueError):
            await TextModule(self.cm).show_text("hi", text_color_mode=TextColorMode.RGB)
