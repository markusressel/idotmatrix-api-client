from typing import List


class IDotMatrixModule:

    def __init__(
        self,
        connection_manager: 'ConnectionManager',
    ):
        self._connection_manager: 'ConnectionManager' = connection_manager

    async def connect(self):
        """Connects to the IDotMatrix device."""
        await self._connection_manager.connect()

    async def send_bytes(self, data: bytearray | bytes, response=False):
        """Sends data to the IDotMatrix device."""
        await self.connect()
        await self._connection_manager.send_bytes(data=data, response=response)

    async def send_packets(self, packets: List[List[bytearray | bytes]], response=False):
        """Sends multiple packets to the IDotMatrix device."""
        await self.connect()
        self._connection_manager.send_packets(packets=packets, response=response)
