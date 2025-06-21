import logging
from typing import Union

from idotmatrix.modules import IDotMatrixModule


class MusicSyncModule(IDotMatrixModule):
    logging = logging.getLogger(__name__)

    async def set_mic_type(self, type: int):
        """Set the microphone type. Not referenced anywhere in the iDotMatrix Android App. So not used atm.

        Args:
            type (int): type of the Microphone. Unknown what values can be used.

        Returns:
            Union[bool, bytearray]: False if there's an error, otherwise byte array of the command which needs to be sent to the device.
        """
        data = bytearray(
            [
                6,
                0,
                11,
                128,
                type % 256,
            ]
        )
        await self.send_bytes(data=data)

    async def send_image_rythm(self, value1: int):
        """Set the image rhythm. Not referenced anywhere in the iDotMatrix Android App. When used (tested with values up to 10)
        it displays a stick figure which dances if the value1 gets changed often enough to a different one.

        Args:
            value1 (int): type of the rhythm? Unknown what values can be used.
        """
        data = bytearray(
            [
                6,
                0,
                0,
                2,
                value1 % 256,
                1,
            ]
        )
        await self.send_bytes(data=data)

    async def send_rhythm(
        self, mode: int, byteArray: bytearray
    ):
        """Used to send synchronized Microphone sound data to the device and visualizing it. Is handled in MicrophoneActivity.java of the
        iDotMatrix Android App. Will not be implemented here because there are no plans to support the computer microphone. The device
        has an integrated microphone which is able to react to sound.

        Args:
            mode (int): mode of the rhythm.
            byteArray (bytearray): actual microphone sound data for the visualization.
        """
        # Assuming `mode` is intended to be used in future or within `byteArray` preparation.
        data = byteArray
        await self.send_bytes(data=data)

    async def stop_rythm(self):
        """Stops the Microphone Rhythm on the iDotMatrix device.

        Returns:
            bytearray: Byte array of the command which needs to be sent to the device.
        """
        data = bytearray(
            [
                6,
                0,
                0,
                2,
                0,
                0,
            ]
        )
        await self.send_bytes(data=data)
