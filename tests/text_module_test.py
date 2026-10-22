import os
import zlib
from unittest.mock import AsyncMock

from idotmatrix.modules.text import TextModule, TextColorMode, TextMode
from tests import TestBase

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "idotmatrix", "fonts")
FONT = os.path.join(FONT_DIR, "Rain-DRM3.otf")

COMPACT_SEPARATOR = bytes([0x02, 0xFF, 0xFF, 0xFF])
FULL_SEPARATOR = bytes([0x05, 0xFF, 0xFF, 0xFF])
# separator + 8x16 cell (1 byte per row) resp. 16x32 cell (2 bytes per row)
COMPACT_CHAR_SIZE = 4 + 16
FULL_CHAR_SIZE = 4 + 64
# header (16 bytes) + metadata (num_chars, 0, 1, mode, speed, color mode, rgb, bg mode, rgb)
HEADER_SIZE = 16
METADATA_SIZE = 14


class TestTextModule(TestBase):

    async def test_show(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = TextModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.show_text(
            text="HELLO WORLD!",
            font_size=16,
            text_mode=TextMode.MARQUEE,
            speed=95,
            text_color_mode=TextColorMode.WHITE,
            text_color=(255, 0, 0),
            text_bg_color=(0, 20, 0),
            font_path="../idotmatrix/fonts/Rain-DRM3.otf",
        )

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(
                b'N\x03\x03\x00\x00>\x03\x00\x00\xac\xe7\xbd\xf6\x00\x00\x0c\x0c\x00\x00\x01\x01_\x00\xff\x00\x00\x01\x00\x14\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x008\x0e8\x0e8\x0e8\x0e\xf8\x0f\xf8\x0f\xf8\x0f8\x0e8\x0e8\x0e8\x0e\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xf0\x07\xf0\x07p\x00p\x00\xf0\x07\xf0\x07p\x00p\x00p\x00\xf0\x07\xf0\x07\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00p\x00p\x00p\x00p\x00p\x00p\x00p\x00p\x00\xf0\x07\xf0\x07\xf0\x07\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00p\x00p\x00p\x00p\x00p\x00p\x00p\x00p\x00\xf0\x07\xf0\x07\xf0\x07\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc0\x03\xf0\x0f\xf8\x1f8\x1c8\x1c888\x1c8\x1c\xf8\x1f\xf0\x0f\xc0\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x8eq\x8eq\xde{\xdc;\xdc;\xfc?\xf8\x1fx\x1ex\x1ex\x0e0\x0c\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc0\x03\xf0\x0f\xf8\x1f8\x1c8\x1c888\x1c8\x1c\xf8\x1f\xf0\x0f\xc0\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xf8\x01\xf8\x07\xf8\x078\x078\x07\xf8\x07\xf8\x03\xf8\x01\xb8\x03\xb8\x078\x0f\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00p\x00p\x00p\x00p\x00p\x00p\x00p\x00p\x00\xf0\x07\xf0\x07\xf0\x07\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xf8\x01\xf8\x07\xf8\x0f8\x0e8\x1e8\x1c8\x0e8\x0e\xf8\x0f\xf8\x07\xf8\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x80\x01\x80\x01\x80\x01\x80\x01\x80\x01\x80\x01\x80\x01\x00\x00\x80\x01\x80\x01\x80\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            ),
            response=False,
        )


class TestTextCellSelection(TestBase):
    """The compact 8x16 cell is used when every glyph fits, else the full 16x32 cell."""

    def _module(self):
        self.connection_manager = AsyncMock()
        return TextModule(connection_manager=self.connection_manager)

    async def test_small_font_uses_compact_cell(self):
        # GIVEN
        under_test = self._module()

        # WHEN
        result = under_test._string_to_bitmaps(text="Hello 123", font_path=FONT, font_size=8)

        # THEN
        self.assertEqual(COMPACT_CHAR_SIZE * 9, len(result))
        for i in range(9):
            offset = i * COMPACT_CHAR_SIZE
            self.assertEqual(COMPACT_SEPARATOR, bytes(result[offset:offset + 4]))

    async def test_large_font_uses_full_cell(self):
        # GIVEN
        under_test = self._module()

        # WHEN
        result = under_test._string_to_bitmaps(text="Hello 123", font_path=FONT, font_size=16)

        # THEN
        self.assertEqual(FULL_CHAR_SIZE * 9, len(result))
        for i in range(9):
            offset = i * FULL_CHAR_SIZE
            self.assertEqual(FULL_SEPARATOR, bytes(result[offset:offset + 4]))

    async def test_cell_is_chosen_for_the_whole_string(self):
        # GIVEN
        under_test = self._module()
        text = "Hello 123"

        # WHEN
        result = under_test._string_to_bitmaps(text=text, font_path=FONT, font_size=16)

        # THEN
        self.assertNotIn(COMPACT_SEPARATOR, bytes(result)[::FULL_CHAR_SIZE])

    async def test_empty_text(self):
        self.assertEqual(bytearray(), self._module()._string_to_bitmaps(text="", font_path=FONT, font_size=8))

    async def test_compact_cell_is_not_blank(self):
        # GIVEN
        under_test = self._module()

        # WHEN
        result = under_test._string_to_bitmaps(text="H", font_path=FONT, font_size=8)

        # THEN
        self.assertTrue(any(result[4:]))

    async def test_whitespace_is_blank(self):
        # GIVEN
        under_test = self._module()

        # WHEN
        result = under_test._string_to_bitmaps(text=" ", font_path=FONT, font_size=8)

        # THEN
        self.assertFalse(any(result[4:]))

    async def test_default_font_is_used_without_font_path(self):
        # WHEN
        result = self._module()._string_to_bitmaps(text="A", font_size=8)

        # THEN
        self.assertEqual(COMPACT_CHAR_SIZE, len(result))

    async def test_show_text_sends_character_count_in_compact_mode(self):
        # GIVEN
        under_test = self._module()

        # WHEN
        await under_test.show_text(text="Hello 123", font_size=8, font_path=FONT)

        # THEN
        data = self.connection_manager.send_bytes.await_args.kwargs["data"]
        self.assertEqual(9, int.from_bytes(data[HEADER_SIZE:HEADER_SIZE + 2], "little"))
        self.assertEqual(COMPACT_SEPARATOR, bytes(data[HEADER_SIZE + METADATA_SIZE:HEADER_SIZE + METADATA_SIZE + 4]))

    async def test_show_text_sends_character_count_in_full_mode(self):
        # GIVEN
        under_test = self._module()

        # WHEN
        await under_test.show_text(text="Hello 123", font_size=16, font_path=FONT)

        # THEN
        data = self.connection_manager.send_bytes.await_args.kwargs["data"]
        self.assertEqual(9, int.from_bytes(data[HEADER_SIZE:HEADER_SIZE + 2], "little"))
        self.assertEqual(FULL_SEPARATOR, bytes(data[HEADER_SIZE + METADATA_SIZE:HEADER_SIZE + METADATA_SIZE + 4]))

    async def test_show_text_packet_lengths_and_crc(self):
        # GIVEN
        under_test = self._module()

        # WHEN
        await under_test.show_text(text="Hi", font_size=8, font_path=FONT)

        # THEN
        data = self.connection_manager.send_bytes.await_args.kwargs["data"]
        payload = bytes(data[HEADER_SIZE:])
        self.assertEqual(len(data), int.from_bytes(data[0:2], "little"))
        self.assertEqual(len(payload), int.from_bytes(data[5:9], "little"))
        self.assertEqual(zlib.crc32(payload), int.from_bytes(data[9:13], "little"))
        self.assertEqual(METADATA_SIZE + 2 * COMPACT_CHAR_SIZE, len(payload))

    async def test_character_count_ignores_separator_bytes_in_bitmaps(self):
        # GIVEN a bitmap that happens to contain the full cell separator
        under_test = self._module()
        bitmaps = bytearray(FULL_SEPARATOR * 3)

        # WHEN
        data = under_test._build_string_packet(text_bitmaps=bitmaps, num_chars=1, text_mode=1)

        # THEN
        self.assertEqual(1, int.from_bytes(data[HEADER_SIZE:HEADER_SIZE + 2], "little"))


class TestBundledFonts(TestBase):

    def test_fonts_are_inside_the_package(self):
        import idotmatrix
        package_fonts = os.path.join(os.path.dirname(idotmatrix.__file__), "fonts")
        self.assertEqual(os.path.realpath(FONT_DIR), os.path.realpath(package_fonts))
        self.assertTrue(os.path.isfile(FONT))

    def test_every_font_has_a_license_file(self):
        files = os.listdir(FONT_DIR)
        licenses = " ".join(f.lower() for f in files if "license" in f.lower())
        fonts = [f for f in files if f.lower().endswith((".ttf", ".otf"))]
        self.assertTrue(fonts)
        for font in fonts:
            # strip size prefix (16-, 32-, 16_32-) and the variant / download suffix
            family = font.split("-", 1)[1] if font[0].isdigit() else font
            family = family.split("-")[0].split(".")[0].lower()
            for known, key in (("erbos", "erbos"), ("minecraft", "minecraft"), ("pixelify", "pixelify")):
                if known in family:
                    family = key
            with self.subTest(font=font):
                self.assertIn(family[:6], licenses)
