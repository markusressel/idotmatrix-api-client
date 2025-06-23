import logging

from idotmatrix.modules import IDotMatrixModule


class EcoModule(IDotMatrixModule):
    """
    This class contains code for the eco-mode of the iDotMatrix device.
    With this class you can change the brightness automatically depending on the time.
    Based on the BleProtocolN.java file of the iDotMatrix Android App.
    """

    logging = logging.getLogger(__name__)

    async def set_mode(
        self,
        enabled: bool = True,
        start_hour: int = 18, start_minute: int = 0,
        end_hour: int = 6, end_minute: int = 0,
        eco_brightness: int = 30,
    ):
        """
        Sets the eco-mode settings of the device.
        eco-mode loweres the brightness of the display to the given amount
        between the given start and end time.

        Args:
            enabled (int): whether to enable the eco-mode feature or not
            start_hour (int): hour to start eco-mode
            start_minute (int): minute to start eco-mode
            end_hour (int): hour to end eco-mode
            end_minute (int): minute to end eco-mode
            eco_brightness (int): the brightness of the screen when in eco-mode. Set to 0 to disable eco-mode.
        """
        if not (0 <= start_hour < 24) or not (0 <= end_hour < 24):
            raise ValueError("start_hour and end_hour must be between 0 and 23")
        if not (0 <= start_minute < 60) or not (0 <= end_minute < 60):
            raise ValueError("start_minute and end_minute must be between 0 and 59")
        if not (0 <= eco_brightness < 256):
            raise ValueError("eco_brightness must be between 0 and 255")

        data = self._compute_payload(
            enabled=1 if enabled else 0,
            start_hour=start_hour,
            start_minute=start_minute,
            end_hour=end_hour,
            end_minute=end_minute,
            eco_brightness=eco_brightness,
        )
        await self._send_bytes(data=data)

    @staticmethod
    def _compute_payload(
        enabled: int,
        start_hour: int, start_minute: int,
        end_hour: int, end_minute: int,
        eco_brightness: int) -> bytearray:
        data = bytearray(
            [
                10,
                0,
                2,
                128,
                int(enabled) % 256,
                int(start_hour) % 256,
                int(start_minute) % 256,
                int(end_hour) % 256,
                int(end_minute) % 256,
                int(eco_brightness) % 256,
            ]
        )
        return data
