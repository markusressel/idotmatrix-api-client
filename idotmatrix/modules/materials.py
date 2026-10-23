import asyncio
import logging
from os import PathLike
from typing import Iterable, Sequence, Tuple

from PIL import Image as PILImage

from idotmatrix import protocol
from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.modules import IDotMatrixModule
from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.protocol import build_command
from idotmatrix.util import image_utils
from idotmatrix.util.device_material import (
    DEFAULT_DISPLAY_TIME_SECONDS, SLOTS, validate_display_time, validate_slot,
)


class MaterialsModule(IDotMatrixModule):
    """
    The slots of the device ("device materials" in the official app). The device keeps the items in its slots and
    cycles through them by itself, in the order of the slots, so after the upload no Bluetooth traffic is needed and the
    animation is not interrupted by an upload, which takes seconds for a GIF. Based on `DeviceMaterialChildFragment` of
    the official app, which deletes the slots and then sends the items one after another.
    """
    logging = logging.getLogger(__name__)

    def __init__(self, connection_manager: ConnectionManager, gif: GifModule, image: ImageModule) -> None:
        super().__init__(connection_manager=connection_manager)
        self._gif = gif
        self._image = image

    async def clear(self, slots: Iterable[int] | None = None) -> None:
        """
        Deletes the items in the given slots.

        Args:
            slots: The slots to empty (0 to 11). All of them if not given.
        """
        slots = self._validate_slots(slots)
        # `11 00 02 01 <number of slots> <slot>...`, acknowledged with `05 00 02 01 01` (verified on a 64x64)
        await self._send_bytes(data=build_command(protocol.DELETE_MATERIALS, len(slots), *slots), response=True)

    async def store(
        self,
        files: Sequence[PathLike | str],
        slots: Iterable[int] | None = None,
        display_time: int = DEFAULT_DISPLAY_TIME_SECONDS,
        resize_mode: image_utils.ResizeMode = image_utils.ResizeMode.FIT,
        palletize: bool | None = None,
        background_color: Tuple[int, int, int] | int | str = (0, 0, 0),
        clear_unused: bool = True,
    ) -> list[int]:
        """
        Stores image and GIF files in the slots of the device, one file per slot, and ends up with the device cycling
        through them. Other slots are not touched, so a list of slots protects the others.

        The slots are not deleted before they are filled (the official app does that): an item the device already
        holds, with the same display time, is not transferred again, whatever slot it is in, which takes about 0.8 s
        instead of seconds. So storing the same files again, or in another order, is fast. (verified on a 64x64)

        Args:
            files: The files, in the order they should be shown in. Animated GIFs are stored as GIFs, the rest as images.
            slots: The slots the device may use (0 to 11), all of them if not given. The files go into them in the order
                of the slot numbers, which is the order of the cycle.
            display_time: Seconds each item stays on screen.
            resize_mode: How the files are scaled to the screen.
            palletize: Reduce the colors to a palette. The default is on for GIFs and off for images.
            background_color: Color of the bars if a file does not have the shape of the screen.
            clear_unused: Delete the slots that are allowed but get no file, so that nothing stale keeps cycling.

        Returns:
            The slots that were used, one for each file.

        Raises:
            ValueError: If there are more files than slots, or a slot or the display time is invalid.
        """
        slots = self._validate_slots(slots)
        validate_display_time(display_time)
        if len(files) > len(slots):
            raise ValueError(f"{len(files)} files do not fit into {len(slots)} slots")
        used = slots[:len(files)]
        if not used:
            return []

        unused = slots[len(files):]
        if clear_unused and unused:
            await self.clear(unused)
        for slot, file in zip(used, files):
            if await asyncio.to_thread(self._is_animated, file):
                await self._gif.upload_gif_file(
                    file_path=file,
                    resize_mode=resize_mode,
                    palletize=True if palletize is None else palletize,
                    background_color=background_color,
                    slot=slot,
                    display_time=display_time,
                )
            else:
                await self._image.show_image_file(
                    file_path=file,
                    resize_mode=resize_mode,
                    palletize=bool(palletize),
                    background_color=background_color,
                    slot=slot,
                    display_time=display_time,
                )
        return used

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

    @staticmethod
    def _is_animated(file: PathLike | str) -> bool:
        with PILImage.open(file) as img:
            return getattr(img, "n_frames", 1) > 1
