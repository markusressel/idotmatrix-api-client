import asyncio
import hashlib
import logging
from os import PathLike
from typing import Callable, Iterable, Sequence, Tuple

from PIL import Image as PILImage

from idotmatrix import protocol
from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.modules import IDotMatrixModule
from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.protocol import build_command
from idotmatrix.util import image_utils
from idotmatrix.util.image_utils import validate_colors
from idotmatrix.util.overlay import TextOverlay
from idotmatrix.util.device_material import (
    DEFAULT_DISPLAY_TIME_SECONDS, SLOTS, validate_display_time, validate_slot,
)


class MaterialsModule(IDotMatrixModule):
    """
    The slots of the device ("device materials" in the official app). The device keeps the items in its slots and
    cycles through them by itself, in the order of the slots, so after the upload no Bluetooth traffic is needed and the
    animation is not interrupted by an upload, which takes seconds for a GIF. Based on `DeviceMaterialChildFragment` of
    the official app, which deletes the slots and then sends its items one after another.

    The module remembers what it stored in which slot (as long as it lives), so storing again only transfers what is new.
    """
    logging = logging.getLogger(__name__)

    def __init__(self, connection_manager: ConnectionManager, gif: GifModule, image: ImageModule) -> None:
        super().__init__(connection_manager=connection_manager)
        self._gif = gif
        self._image = image
        # slot -> what is in it: None for empty, a fingerprint of the stored item, or missing if it is not known
        self._contents: dict[int, tuple | None] = {}

    async def clear(self, slots: Iterable[int] | None = None) -> None:
        """
        Deletes the items in the given slots.

        Args:
            slots: The slots to empty (0 to 11). All of them if not given.
        """
        slots = self._validate_slots(slots)
        for slot in slots:
            self._contents.pop(slot, None)
        # `11 00 02 01 <number of slots> <slot>...`, acknowledged with `05 00 02 01 01` (verified on a 64x64)
        await self._send_bytes(data=build_command(protocol.DELETE_MATERIALS, len(slots), *slots), response=True)
        for slot in slots:
            self._contents[slot] = None

    async def store(
        self,
        files: Sequence[PathLike | str],
        slots: Iterable[int] | None = None,
        display_time: int = DEFAULT_DISPLAY_TIME_SECONDS,
        resize_mode: image_utils.ResizeMode = image_utils.ResizeMode.FIT,
        palletize: bool | None = None,
        background_color: Tuple[int, int, int] | int | str = (0, 0, 0),
        clear_unused: bool = True,
        keep_order: bool = False,
        verify: bool = False,
        colors: int = 256,
        max_size_kb: int | None = None,
        overlay: TextOverlay | Callable[[str], TextOverlay | None] | None = None,
    ) -> list[int]:
        """
        Stores image and GIF files in the slots of the device, one file per slot, and ends up with the device cycling
        through them. Other slots are not touched, so a list of slots protects the others.

        Only what is new is transferred: a file that this module stored in one of the allowed slots earlier (same
        content, options and display time) stays where it is and costs nothing. The rest goes into the other allowed
        slots, which are overwritten, no delete is needed. A transfer of an item the device holds anyway takes about
        0.8 s instead of seconds, also in another slot, so reordering is cheap, too. (verified on a 64x64)

        Args:
            files: The files. Animated GIFs are stored as GIFs, the rest as images.
            slots: The slots the device may use (0 to 11), all of them if not given.
            display_time: Seconds each item stays on screen.
            resize_mode: How the files are scaled to the screen.
            palletize: Reduce the colors to a palette. The default is on for GIFs and off for images.
            background_color: Color of the bars if a file does not have the shape of the screen.
            colors: The number of colors of the palette (2 to 256), fewer make GIFs smaller and faster to upload.
            max_size_kb: The most a converted GIF may have, quality is given up until it fits, see
                `GifModule.upload_gif_file`. Keeps the upload of each GIF short.
            overlay: A text that is drawn on top of every file, or a function that gets the path of a file and returns
                the text for it (or None), f.e. to label each file with its name.
            clear_unused: Delete the allowed slots that get no file, so that nothing stale keeps cycling.
            keep_order: Put the files into the slots in the order of the slot numbers, which is the order of the cycle,
                instead of keeping what is stored where it is. That can transfer many files again, because writing a
                slot destroys the item that is in it.
            verify: Do not trust what this module remembers about the slots, send all files again (which takes about
                0.8 s for each item the device holds). Use it if something else (the app) may have changed the slots.

        Returns:
            The slot of each file, in the order of the files. The device cycles in the order of the slots.

        Raises:
            ValueError: If there are more files than slots, or a slot or the display time is invalid.
        """
        slots = self._validate_slots(slots)
        validate_display_time(display_time)
        validate_colors(colors)
        if len(files) > len(slots):
            raise ValueError(f"{len(files)} files do not fit into {len(slots)} slots")
        if not files:
            return []

        overlays = [overlay(str(file)) if callable(overlay) else overlay for file in files]
        items = [
            await asyncio.to_thread(
                self._fingerprint, file, display_time, resize_mode, palletize, background_color, colors, max_size_kb,
                file_overlay)
            for file, file_overlay in zip(files, overlays)
        ]
        keys = [key for key, _ in items]
        stored = {} if verify else self._contents
        assignment = self._plan(keys, slots, stored, keep_order)

        unused = [slot for slot in slots if slot not in assignment.values()]
        if clear_unused:
            unused = [slot for slot in unused if self._contents.get(slot, False) is not None]
            if unused:
                await self.clear(unused)

        for index, file in enumerate(files):
            slot = assignment[index]
            if stored.get(slot) == keys[index]:
                continue
            self._contents.pop(slot, None)  # not known anymore, in case the upload fails
            if items[index][1]:
                await self._gif.upload_gif_file(
                    file_path=file,
                    resize_mode=resize_mode,
                    palletize=True if palletize is None else palletize,
                    background_color=background_color,
                    slot=slot,
                    display_time=display_time,
                    colors=colors,
                    max_size_kb=max_size_kb,
                    overlay=overlays[index],
                )
            else:
                await self._image.show_image_file(
                    file_path=file,
                    resize_mode=resize_mode,
                    palletize=bool(palletize),
                    background_color=background_color,
                    slot=slot,
                    display_time=display_time,
                    colors=colors,
                    overlay=overlays[index],
                )
            self._contents[slot] = keys[index]
        return [assignment[index] for index in range(len(files))]

    @staticmethod
    def _plan(keys: list[tuple], slots: list[int], stored: dict[int, tuple | None], keep_order: bool) -> dict[int, int]:
        """Decides which file goes into which slot: the index of each file -> its slot."""
        if keep_order:
            return dict(enumerate(slots[:len(keys)]))
        free = list(slots)
        assignment: dict[int, int] = {}
        for index, key in enumerate(keys):
            for slot in free:
                if stored.get(slot) == key:
                    assignment[index] = slot
                    free.remove(slot)
                    break
        for index in range(len(keys)):
            if index not in assignment:
                assignment[index] = free.pop(0)
        return assignment

    @staticmethod
    def _fingerprint(
        file: PathLike | str, display_time: int, resize_mode, palletize, background_color, colors: int,
        max_size_kb: int | None,
        overlay: TextOverlay | None,
    ) -> tuple:
        """What identifies an item: the content of the file and everything that changes what is sent."""
        with open(file, "rb") as handle:
            digest = hashlib.sha1(handle.read()).hexdigest()
        with PILImage.open(file) as img:
            animated = getattr(img, "n_frames", 1) > 1
        options = (display_time, resize_mode, palletize, str(background_color), colors, max_size_kb, overlay)
        return (digest, animated, *options), animated

    @staticmethod
    def _validate_slots(slots: Iterable[int] | None) -> list[int]:
        if slots is None:
            return list(SLOTS)
        slots = sorted(validate_slot(slot) for slot in slots)
        if len(set(slots)) != len(slots):
            raise ValueError(f"slots must not contain duplicates, got: {slots}")
        if not slots:
            raise ValueError("slots must not be empty")
        return slots
