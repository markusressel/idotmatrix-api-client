import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock


class FakeTransport:
    """
    A device that is simulated in memory, which implements `idotmatrix.transport.Transport`.

    The methods are `AsyncMock`s with a working behavior, so tests can assert on them or replace their `side_effect`.
    The device answers writes with the notifications in `replies`, or with whatever `auto_reply` returns.
    """

    def __init__(
        self,
        address: str = "00:11:22:33:44:55",
        on_disconnected: Callable[[], None] | None = None,
        max_write_without_response_size: int = 514,
    ) -> None:
        self.address = address
        self.on_disconnected = on_disconnected
        self.is_connected = False
        self.max_size = max_write_without_response_size

        self.events: list[tuple[str, bytes]] = []  # everything that was written, in order
        self.replies: list[bytes] = []  # notifications for the next writes (with response)
        self.reply_to_any_write = False  # also answer writes without response
        self.auto_reply: Callable[[bytes], bytes | None] | None = None  # called with the written data
        self.callback: Callable[[bytes], None] | None = None

        self.connect = AsyncMock(side_effect=self._connect)
        self.disconnect = AsyncMock(side_effect=self._disconnect)
        self.write = AsyncMock(side_effect=self._write)
        self.read = AsyncMock(return_value=b"ok")
        self.start_notify = AsyncMock(side_effect=self._start_notify)
        self.max_write_without_response_size = AsyncMock(side_effect=lambda: self.max_size)

    def notify(self, data: bytes | bytearray) -> None:
        """The device sends a notification."""
        self.callback(bytes(data))

    def lose_connection(self) -> None:
        """The device vanishes, and the stack tells about it."""
        self.is_connected = False
        if self.on_disconnected:
            self.on_disconnected()

    async def _connect(self) -> None:
        self.is_connected = True

    async def _disconnect(self) -> None:
        self.is_connected = False

    async def _start_notify(self, callback: Callable[[bytes], None]) -> None:
        self.callback = callback

    async def _write(self, data: bytes | bytearray, response: bool) -> None:
        self.events.append(("write", bytes(data)))
        await asyncio.sleep(0)  # let other tasks run, like a real BLE write does
        # the device answers once a full protocol packet has been received
        if (response or self.reply_to_any_write) and self.replies:
            self.notify(self.replies.pop(0))
        elif self.auto_reply is not None:
            reply = self.auto_reply(bytes(data))
            if reply is not None:
                self.notify(reply)
