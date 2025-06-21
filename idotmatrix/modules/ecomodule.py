import logging

from idotmatrix.modules import IDotMatrixModule


class EcoModule(IDotMatrixModule):
    """
    This class contains code for the eco mode of the iDotMatrix device.
    With this class you can enable or disable the screen and change the brightness automatically depending on the time.
    Based on the BleProtocolN.java file of the iDotMatrix Android App.
    """

    logging = logging.getLogger(__name__)

    async def set_mode(
        self,
        flag: int,
        start_hour: int,
        start_minute: int,
        end_hour: int,
        end_minute: int,
        light: int,
    ):
        """
        Sets the eco mode of the device (e.g. turning on or off the device, set the color, ....)

        Args:
            flag (int): currently unknown, seems to be either 1 or 0
            start_hour (int): hour to start
            start_minute (int): minute to start
            end_hour (int): hour to end
            end_minute (int): minute to end
            light (int): the brightness of the screen
        """
        # TODO: input validation
        data = self._compute_payload(
            flag=flag,
            start_hour=start_hour,
            start_minute=start_minute,
            end_hour=end_hour,
            end_minute=end_minute,
            light=light,
        )
        await self.send_bytes(data=data)

    def _compute_payload(self, flag, start_hour, start_minute, end_hour, end_minute, light) -> bytearray:
        data = bytearray(
            [
                10,
                0,
                2,
                128,
                int(flag) % 256,
                int(start_hour) % 256,
                int(start_minute) % 256,
                int(end_hour) % 256,
                int(end_minute) % 256,
                int(light) % 256,
            ]
        )
        return data
