from idotmatrix.util.device_material import convert_display_time
from tests import TestBase


class TestConvertDisplayTime(TestBase):

    def test_known_time_signs(self):
        self.assertEqual({1: 10, 2: 30, 3: 60, 4: 300}, {key: convert_display_time(key) for key in (1, 2, 3, 4)})

    def test_default(self):
        for time_sign in (0, 5, -1):
            with self.subTest(time_sign=time_sign):
                self.assertEqual(5, convert_display_time(time_sign))
