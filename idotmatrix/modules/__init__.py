from asyncio import sleep
from typing import List

from idotmatrix.connectionManager import ConnectionManager


class IDotMatrixModule:

    def __init__(
        self,
        connection_manager: ConnectionManager,
    ):
        self._connection_manager: ConnectionManager = connection_manager

    async def connect(self):
        """Connects to the IDotMatrix device."""
        await self._connection_manager.connect()

    async def send_bytes(
        self,
        data: bytearray | bytes,
        response: bool = False,
        sleep_after: float = 0.5
    ):
        """
        Sends raw data to the IDotMatrix device.
        Args:
            data (bytearray | bytes): The data to send.
            response (bool, optional): Whether to expect a response from the device. Defaults to False.
            sleep_after (float, optional): Time to wait after sending the data. Defaults to 0.5 seconds.
        """
        await self._connection_manager.send_bytes(data=data, response=response)
        if sleep_after > 0:
            # sometimes the device needs a moment to process the command before it is able to receive the next one
            await sleep(sleep_after)

    async def send_packets(
        self,
        packets: List[List[bytearray | bytes]],
        response: bool = False,
        sleep_after: float = 0.5
    ):
        """
        Sends multiple packets to the IDotMatrix device.
        Args:
            packets (List[List[bytearray | bytes]]): The packets to send.
            response (bool, optional): Whether to expect a response from the device. Defaults to False.
            sleep_after (float, optional): Time to wait after sending the packets. Defaults to 0.5 seconds.
        """
        await self._connection_manager.send_packets(packets=packets, response=response)
        if sleep_after > 0:
            # sometimes the device needs a moment to process the command before it is able to receive the next one
            await sleep(sleep_after)
