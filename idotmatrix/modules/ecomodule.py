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
        if flag not in (0, 1):
            raise ValueError("EcoModule.set_mode expects parameter flag to be either 0 or 1")
        if not (0 <= start_hour < 24) or not (0 <= end_hour < 24):
            raise ValueError("EcoModule.set_mode expects start_hour and end_hour to be between 0 and 23")
        if not (0 <= start_minute < 60) or not (0 <= end_minute < 60):
            raise ValueError("EcoModule.set_mode expects start_minute and end_minute to be between 0 and 59")
        if not (0 <= light < 256):
            raise ValueError("EcoModule.set_mode expects light to be between 0 and 255")
        if start_hour > end_hour or (start_hour == end_hour and start_minute >= end_minute):
            raise ValueError("EcoModule.set_mode expects start time to be before end time")

        data = self._compute_payload(
            flag=flag,
            start_hour=start_hour,
            start_minute=start_minute,
            end_hour=end_hour,
            end_minute=end_minute,
            light=light,
        )
        await self.send_bytes(data=data)

    @staticmethod
    def _compute_payload(flag, start_hour, start_minute, end_hour, end_minute, light) -> bytearray:
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
