import logging
from datetime import datetime
from typing import Optional

from idotmatrix.modules import IDotMatrixModule


class CommonModule(IDotMatrixModule):
    """
    This class contains generic Bluetooth functions for the iDotMatrix.
    Based on the BleProtocolN.java file of the iDotMatrix Android App.
    """

    logging = logging.getLogger(__name__)

    async def freeze_screen(self):
        """
        Freezes or unfreezes the screen.

        Returns:
            bytearray: Command to be sent to the device.
        """
        data = bytearray(
            [
                4,
                0,
                3,
                0,
            ]
        )
        await self._send_bytes(data=data, response=True)

    async def turn_off(self):
        """
        Turns the screen off.

        Returns:
            bytearray: Command to be sent to the device.
        """
        data = bytearray(
            [
                5,
                0,
                7,
                1,
                0,
            ]
        )
        await self._send_bytes(data=data, response=True)

    async def turn_on(self):
        """
        Turns the screen on.

        Returns:
            bytearray: Command to be sent to the device.
        """
        data = bytearray(
            [
                5,
                0,
                7,
                1,
                1,
            ]
        )
        await self._send_bytes(data=data)

    async def set_screen_state(self, is_on: bool):
        """
        Sets the screen state to on or off.

        Args:
            is_on (bool): True = on, False = off.
        """

        data = bytearray(
            [
                5,
                0,
                7,
                1,
                1 if is_on else 0,
            ]
        )
        await self._send_bytes(data=data)

    async def set_screen_flipped(self, flip: bool = True):
        """
        Rotates the screen 180 degrees.

        Args:
            flip (bool): False = normal, True = rotated. Defaults to True.
        """
        data = bytearray(
            [
                5,
                0,
                6,
                128,
                1 if flip else 0,
            ]
        )
        await self._send_bytes(data=data, response=True)

    async def set_brightness(self, brightness_percent: int):
        """
        Set screen brightness. Range 5-100 (%).

        Args:
            brightness_percent (int): Set the brightness in percent.
        """
        if brightness_percent not in range(5, 101):
            raise ValueError("Common.setBrightness parameter brightness_percent is not in range between 5 and 100")
        data = bytearray(
            [
                5,
                0,
                4,
                128,
                brightness_percent,
            ]
        )
        await self._send_bytes(data=data, response=True)

    async def set_speed(self, speed: int):
        """
        Sets the speed of ? - not referenced anywhere in the iDotMatrix Android App.

        Args:
            speed (int): Set the speed.
        """
        data = bytearray(
            [
                5,
                0,
                3,
                1,
                speed,
            ]
        )
        await self._send_bytes(data=data)

    async def set_time(self, time: datetime):
        """
        Sets the date and time of the device.

        Args:
            time (datetime): The datetime object representing the date and time to set. Accuracy is to the second.

        Returns:
            Optional[bytearray]: Command to be sent to the device or None if error.
        """
        year = time.year
        month = time.month
        day = time.day
        hour = time.hour
        minute = time.minute
        second = time.second
        if not (0 <= month <= 12):
            raise ValueError("Common.setTime parameter month is not in range between 1 and 12")
        if not (0 <= day <= 31):
            raise ValueError("Common.setTime parameter day is not in range between 1 and 31")
        if not (0 <= hour <= 23):
            raise ValueError("Common.setTime parameter hour is not in range between 0 and 23")
        if not (0 <= minute <= 59):
            raise ValueError("Common.setTime parameter minute is not in range between 0 and 59")
        if not (0 <= second <= 59):
            raise ValueError("Common.setTime parameter second is not in range between 0 and 59")

        data = bytearray(
            [
                11,
                0,
                1,
                128,
                year % 100,
                month,
                day,
                datetime(year, month, day).weekday() + 1,
                hour,
                minute,
                second,
            ]
        )
        await self._send_bytes(data=data, response=True)

    async def set_joint(self, mode: int):
        """
        Currently no idea what this is doing.

        Args:
            mode (int): Set the joint mode.
        """
        data = bytearray(
            [
                5,
                0,
                12,
                128,
                mode,
            ]
        )
        await self._send_bytes(data=data)

    async def set_password(self, password: int):
        """
        Setting password: 6 digits in range 000000..999999. Reset device to clear.

        Args:
            password (int): Password.
        """
        pwd_high = (password // 10000) % 256
        pwd_mid = (password // 100) % 100 % 256
        pwd_low = password % 100 % 256
        data = bytearray(
            [
                8,
                0,
                4,
                2,
                1,
                pwd_high,
                pwd_mid,
                pwd_low,
            ]
        )
        await self._send_bytes(data=data)

    async def reset(self):
        """
        Sends a command that resets the device and its internals.
        Can fix issues that appear over time.

        Note:
            Credits to 8none1 for finding this method:
            https://github.com/8none1/idotmatrix/commit/1a08e1e9b82d78427ab1c896c24c2a7fb45bc2f0
        """
        reset_packets = [
            bytes(bytearray.fromhex("04 00 03 80")),
            bytes(bytearray.fromhex("05 00 04 80 50")),
        ]
        for data in reset_packets:
            await self._send_bytes(data=data, response=True)
