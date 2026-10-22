from idotmatrix.util import color_utils
from tests import TestBase


class TestColorUtils(TestBase):

    def test_none(self):
        self.assertIsNone(color_utils.parse_color_rgb(None))

    def test_int(self):
        self.assertEqual((0x12, 0x34, 0x56), color_utils.parse_color_rgb(0x123456))

    def test_int_bounds(self):
        self.assertEqual((0, 0, 0), color_utils.parse_color_rgb(0))
        self.assertEqual((255, 255, 255), color_utils.parse_color_rgb(0xFFFFFF))

    def test_int_out_of_range(self):
        with self.assertRaises(ValueError):
            color_utils.parse_color_rgb(-1)
        with self.assertRaises(ValueError):
            color_utils.parse_color_rgb(0x1000000)

    def test_hex_string(self):
        self.assertEqual((255, 128, 0), color_utils.parse_color_rgb("#ff8000"))

    def test_0x_string(self):
        self.assertEqual((255, 128, 0), color_utils.parse_color_rgb("0xff8000"))

    def test_hex_shorthand(self):
        self.assertEqual((255, 255, 255), color_utils.parse_color_rgb("#fff"))

    def test_hex_wrong_length(self):
        for value in ("#ff", "#ff80", "#ff800000", "0xff80"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                color_utils.parse_color_rgb(value)

    def test_hex_invalid_digits(self):
        with self.assertRaises(ValueError):
            color_utils.parse_color_rgb("#GGGGGG")

    def test_named_color(self):
        self.assertEqual((255, 0, 0), color_utils.parse_color_rgb("red"))

    def test_named_color_rounds(self):
        # matplotlib "gray" is 128/255 (0.50196...), must not be truncated to 127
        self.assertEqual((128, 128, 128), color_utils.parse_color_rgb("gray"))

    def test_invalid_named_color(self):
        with self.assertRaises(ValueError):
            color_utils.parse_color_rgb("notacolor")

    def test_tuple(self):
        self.assertEqual((1, 2, 3), color_utils.parse_color_rgb((1, 2, 3)))

    def test_tuple_wrong_length(self):
        with self.assertRaises(ValueError):
            color_utils.parse_color_rgb((1, 2))

    def test_tuple_non_int(self):
        with self.assertRaises(ValueError):
            color_utils.parse_color_rgb((1, 2, 3.5))

    def test_tuple_out_of_range(self):
        with self.assertRaises(ValueError):
            color_utils.parse_color_rgb((1, 2, 256))
        with self.assertRaises(ValueError):
            color_utils.parse_color_rgb((-1, 2, 3))

    def test_unsupported_type(self):
        with self.assertRaises(ValueError):
            color_utils.parse_color_rgb([1, 2, 3])

    def test_bool_rejected(self):
        with self.assertRaises(ValueError):
            color_utils.parse_color_rgb(True)

    def test_list(self):
        self.assertEqual(
            [(255, 0, 0), (0, 0, 255), (1, 2, 3)],
            color_utils.parse_color_rgb_list(["#ff0000", 0x0000FF, (1, 2, 3)]),
        )

    def test_list_empty(self):
        self.assertEqual([], color_utils.parse_color_rgb_list([]))
