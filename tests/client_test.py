from unittest.mock import AsyncMock, MagicMock, patch

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

    def test_ble_device_is_passed_to_the_connection_manager(self):
        device = MagicMock(address=ADDRESS)

        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32, ble_device=device)

        self.manager.set_device.assert_called_once_with(device)
        self.assertEqual(ADDRESS, client.mac_address)

    def test_transport_factory_is_passed_to_the_connection_manager(self):
        factory = MagicMock()

        IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32, mac_address=ADDRESS, transport_factory=factory)

        self.assertIs(factory, self.manager_cls.call_args.kwargs["transport_factory"])

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

    def test_modules_are_created_once(self):
        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32)
        for attr in ("chronograph", "clock", "common", "countdown", "eco", "effect", "color", "gif", "graffiti",
                     "image", "music_sync", "scoreboard", "system", "text"):
            with self.subTest(module=attr):
                self.assertIs(getattr(client, attr), getattr(client, attr))

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

    def _device_answers(self, screen_type=4):
        self.manager.request = AsyncMock(return_value=bytes([9, 0, 1, 128, 5, 9, 1, screen_type, 0]))

    async def test_connect_detects_the_screen_size_if_it_was_not_given(self):
        self._device_answers(screen_type=3)
        client = IDotMatrixClient(mac_address=ADDRESS)

        await client.connect()

        self.assertEqual(ScreenSize.SIZE_32x32, client.screen_size)
        self.assertEqual(ScreenSize.SIZE_32x32, client.image.screen_size)
        self.assertEqual(ScreenSize.SIZE_32x32, client.gif.screen_size)

    async def test_connect_does_not_ask_if_the_screen_size_was_given(self):
        self._device_answers(screen_type=3)
        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_64x64, mac_address=ADDRESS)

        await client.connect()

        self.manager.request.assert_not_awaited()
        self.assertEqual(ScreenSize.SIZE_64x64, client.screen_size)

    async def test_screen_size_is_not_known_before_connecting(self):
        client = IDotMatrixClient(mac_address=ADDRESS)

        with self.assertRaisesRegex(RuntimeError, "screen size is not known"):
            client.image

    async def test_other_modules_work_without_a_screen_size(self):
        client = IDotMatrixClient(mac_address=ADDRESS)

        self.assertIsInstance(client.clock, ClockModule)

    async def test_detecting_without_an_answer_fails(self):
        self.manager.request = AsyncMock(return_value=None)
        client = IDotMatrixClient(mac_address=ADDRESS)

        with self.assertRaisesRegex(RuntimeError, "did not tell"):
            await client.connect()

    async def test_detecting_an_unsupported_screen_fails(self):
        self._device_answers(screen_type=11)
        client = IDotMatrixClient(mac_address=ADDRESS)

        with self.assertRaisesRegex(RuntimeError, "screen type 11"):
            await client.connect()

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

    def test_heartbeat_delegates(self):
        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32)

        client.set_heartbeat(30)

        self.manager.set_heartbeat.assert_called_once_with(interval_seconds=30)

    def test_listener_and_auto_reconnect_delegate(self):
        client = IDotMatrixClient(screen_size=ScreenSize.SIZE_32x32)
        listener = ConnectionListener(on_connected=None, on_disconnected=None)
        client.add_connection_listener(listener)
        client.set_auto_reconnect(True)
        self.manager.add_connection_listener.assert_called_once_with(listener)
        self.manager.set_auto_reconnect.assert_called_once_with(auto_reconnect=True)
