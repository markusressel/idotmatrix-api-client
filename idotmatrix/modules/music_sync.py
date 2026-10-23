import logging

from idotmatrix import protocol
from idotmatrix.modules import IDotMatrixModule
from idotmatrix.protocol import build_command


class MusicSyncModule(IDotMatrixModule):
    logging = logging.getLogger(__name__)

    async def set_mic_type(self, type: int, sensitivity: int = 50):
        """
        Switches the device to music sync with its built-in microphone, which then reacts to sound on its own,
        without any audio data being sent. This is what the "microphone" screen of the iDotMatrix Android App does
        (`BleProtocolN.sendMicCommand1`, which sends the 1-based mode and the sensitivity).

        Tested on a 64x64: modes 1 to 5 show different scenes (a figure, a heart, two frog-like faces, ...) that move
        to sound and knocks. There is no command to leave the mode, show something else (f.e. the clock) instead.

        Args:
            type (int): The scene, starting at 1.
            sensitivity (int): How sensitive the microphone is, 0 to 100. Defaults to 50, like the app.
        """
        if not 0 <= sensitivity <= 100:
            raise ValueError("sensitivity must be between 0 and 100")
        data = build_command(protocol.MICROPHONE_MODE, type % 256, sensitivity)
        await self._send_bytes(data=data)

    async def send_image_rythm(self, value1: int):
        """
        Shows one frame of the "image rhythm" animation. The Android App sends this about every 60 ms with the loudness
        (1 to 7) of the sound its microphone records, so the animation only moves if it is sent over and over with
        changing values. Sent once it just shows a still frame. To let the device react to sound on its own use
        `set_mic_type`.

        Args:
            value1 (int): The loudness, 1 to 7 in the App. Larger values were tested up to 10 and show other frames.
        """
        data = build_command(protocol.IMAGE_RHYTHM, value1 % 256, 1)
        await self._send_bytes(data=data)

    async def send_rhythm(
        self, mode: int, byteArray: bytearray
    ):
        """
        Used to send synchronized Microphone sound data to the device and visualizing it. Is handled in MicrophoneActivity.java of the
        iDotMatrix Android App. Will not be implemented here because there are no plans to support the computer microphone. The device
        has an integrated microphone which is able to react to sound.

        Args:
            mode (int): mode of the rhythm.
            byteArray (bytearray): actual microphone sound data for the visualization.
        """
        # Assuming `mode` is intended to be used in future or within `byteArray` preparation.
        data = byteArray
        await self._send_bytes(data=data)

    async def stop_rythm(self):
        """
        Stops the Microphone Rhythm on the iDotMatrix device. Tested on a 64x64: this does not leave the animation that
        `set_mic_type` or `send_image_rythm` started, show something else (f.e. the clock) to leave it.

        Returns:
            bytearray: Byte array of the command which needs to be sent to the device.
        """
        data = build_command(protocol.IMAGE_RHYTHM, 0, 0)
        await self._send_bytes(data=data)
