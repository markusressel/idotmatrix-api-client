from idotmatrix import protocol
from idotmatrix.connection_manager import HEARTBEAT_COMMAND
from idotmatrix.protocol import Command, build_command
from tests import TestBase


class TestBuildCommand(TestBase):

    def test_length_is_the_length_of_the_message(self):
        self.assertEqual(bytearray([5, 0, 4, 128, 50]), build_command(protocol.BRIGHTNESS, 50))
        self.assertEqual(bytearray([4, 0, 3, 128]), build_command(protocol.RESET))

    def test_length_has_two_bytes(self):
        message = build_command(Command(5, 1), *[7] * 300)

        self.assertEqual(304, len(message))
        self.assertEqual((304 % 256, 304 // 256), (message[0], message[1]))

    def test_length_can_be_overridden(self):
        self.assertEqual(bytearray([9, 0, 3, 2, 1]), build_command(protocol.EFFECT, 1, length=9))

    def test_bytes_have_to_be_in_range(self):
        with self.assertRaises(ValueError):
            build_command(protocol.BRIGHTNESS, 256)

    def test_returns_a_bytearray(self):
        self.assertIsInstance(build_command(protocol.RESET), bytearray)


class TestCommands(TestBase):

    def test_the_heartbeat_is_a_rejected_brightness(self):
        self.assertEqual(bytes([5, 0, 4, 128, 255]), HEARTBEAT_COMMAND)

    def test_commands_are_unique(self):
        commands = [value for name, value in vars(protocol).items() if isinstance(value, Command)]

        # the same pair would mean two names for one command, f.e. when copying a line
        self.assertEqual(len(commands), len(set(commands)))
