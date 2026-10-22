from unittest.mock import AsyncMock, patch

from idotmatrix.client import IDotMatrixClient
from idotmatrix.connection_manager import ConnectionListener
from idotmatrix.modules.chronograph import ChronographModule
from idotmatrix.modules.clock import ClockModule
from idotmatrix.modules.common import CommonModule
from idotmatrix.modules.countdown import CountdownModule
from idotmatrix.modules.eco import EcoModule
from idotmatrix.modules.effect import EffectModule
from idotmatrix.modules.fullscreen_color import FullscreenColorModule
from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.graffiti import GraffitiModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.modules.music_sync import MusicSyncModule
from idotmatrix.modules.scoreboard import ScoreboardModule
from idotmatrix.modules.system import SystemModule
from idotmatrix.modules.text import TextModule
from idotmatrix.screensize import ScreenSize
from tests import TestBase

ADDRESS = "00:11:22:33:44:55"


class TestPackageExports(TestBase):

    def test_readme_imports_work(self):
        # README: from idotmatrix import IDotMatrixClient, ScreenSize
        from idotmatrix import IDotMatrixClient as exported_client, ScreenSize as exported_size
        self.assertIs(IDotMatrixClient, exported_client)
        self.assertIs(ScreenSize, exported_size)


class TestIDotMatrixClient(TestBase):

    def setUp(self):
        patcher = patch("idotmatrix.client.ConnectionManager")
        self.manager_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.manager = self.manager_cls.return_value
        for name in ("connect_by_address", "connect_by_discovery", "disconnect"):
            setattr(self.manager, name, AsyncMock())
        self.manager.send_bytes = AsyncMock()
        self.manager.send_packets = AsyncMock()

    def test_max_ble_packet_size_is_passed_to_the_connection_manager(self):
        IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32, mac_address=ADDRESS, max_ble_packet_size=101)

        self.assertEqual(101, self.manager_cls.call_args.kwargs["max_ble_packet_size"])

    def test_max_ble_packet_size_defaults_to_detection(self):
        IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32, mac_address=ADDRESS)

        self.assertIsNone(self.manager_cls.call_args.kwargs["max_ble_packet_size"])

    def test_modules_are_wired_to_the_connection_manager(self):
        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32, mac_address=ADDRESS)
        expected = {
            "chronograph": ChronographModule,
            "clock": ClockModule,
            "common": CommonModule,
            "countdown": CountdownModule,
            "eco": EcoModule,
            "effect": EffectModule,
            "color": FullscreenColorModule,
            "gif": GifModule,
            "graffiti": GraffitiModule,
            "image": ImageModule,
            "music_sync": MusicSyncModule,
            "scoreboard": ScoreboardModule,
            "system": SystemModule,
            "text": TextModule,
        }
        for attr, module_cls in expected.items():
            with self.subTest(module=attr):
                module = getattr(client, attr)
                self.assertIsInstance(module, module_cls)
                self.assertIs(self.manager, module._connection_manager)

    def test_screen_size_is_passed_to_sized_modules(self):
        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_16x16)
        self.assertEqual(ScreenSize.SIZE_16x16, client.gif.screen_size)
        self.assertEqual(ScreenSize.SIZE_16x16, client.image.screen_size)

    async def test_connect_with_address(self):
        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32, mac_address=ADDRESS)
        await client.connect()
        self.manager.connect_by_address.assert_awaited_once_with(ADDRESS)
        self.manager.connect_by_discovery.assert_not_awaited()

    async def test_connect_without_address_discovers(self):
        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32)
        await client.connect()
        self.manager.connect_by_discovery.assert_awaited_once()
        self.manager.connect_by_address.assert_not_awaited()

    async def test_disconnect(self):
        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32)
        await client.disconnect()
        self.manager.disconnect.assert_awaited_once()

    @patch("idotmatrix.modules.sleep", new=AsyncMock())
    async def test_top_level_commands_delegate_to_common_module(self):
        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32)
        await client.turn_on()
        await client.turn_off()
        await client.set_brightness(50)
        await client.reset()
        sent = [c.kwargs.get("data", c.kwargs.get("packets")) for c in
                self.manager.send_bytes.await_args_list + self.manager.send_packets.await_args_list]
        self.assertIn(bytearray([5, 0, 7, 1, 1]), sent)
        self.assertIn(bytearray([5, 0, 7, 1, 0]), sent)
        self.assertIn(bytearray([5, 0, 4, 128, 50]), sent)
        self.assertIn([[bytes([4, 0, 3, 128])]], sent)

    def test_listener_and_auto_reconnect_delegate(self):
        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32)
        listener = ConnectionListener(on_connected=None, on_disconnected=None)
        client.add_connection_listener(listener)
        client.set_auto_reconnect(True)
        self.manager.add_connection_listener.assert_called_once_with(listener)
        self.manager.set_auto_reconnect.assert_called_once_with(auto_reconnect=True)
