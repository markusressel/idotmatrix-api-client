import asyncio
import logging
from asyncio import sleep, Task
from os import PathLike
from typing import List

from idotmatrix.client import IDotMatrixClient
from idotmatrix.modules.image import ImageMode


class PictureFrameGif:
    def __init__(self, file_path: PathLike | str):
        self.file_path = file_path
        self.duration_per_frame_in_ms = None


class PictureFrameImage:
    def __init__(self, file_path: PathLike | str):
        self.file_path = file_path


DEFAULT_INTERVAL_SECONDS = 30


class DigitalPictureFrame:
    """
    A class to manage a digital picture frame that can display images and GIFs in a slideshow format.
    """
    logging = logging.getLogger(__name__)

    def __init__(
        self,
        device_client: IDotMatrixClient,
        images: List[PictureFrameImage | PictureFrameGif | PathLike | str],
    ):
        self.device_client = device_client
        self.images = images
        self.interval = DEFAULT_INTERVAL_SECONDS

        self._current_image: PictureFrameImage | PictureFrameGif | PathLike | str | None = None

        self._slideshow_task: Task | None = None

        self._is_in_diy_mode: bool = False

    def set_interval(self, interval: int):
        """
        Sets the interval between two images/GIFs for the slideshow.
        """
        self.interval = interval

    async def start_slideshow(self, interval: int = None) -> Task:
        """
        Starts a slideshow of images on the digital picture frame.

        Args:
            interval (int): Time in seconds between image changes. Defaults to 5 seconds.
        """
        self.logging.info(f"Starting slideshow with interval: {interval} seconds")
        if interval is not None:
            self.set_interval(interval)
        self._slideshow_task = self._start_slideshow_task()
        return self._slideshow_task

    async def stop_slideshow(self):
        """
        Stops the slideshow.
        """
        if self._slideshow_task:
            self.logging.info("Stopping slideshow")
            self._slideshow_task.cancel()
            self._slideshow_task = None

        await self.device_client.clock.show()

    def _start_slideshow_task(self) -> Task:
        """
        Starts the slideshow task that uploads images to the device at specified intervals.
        """
        return asyncio.create_task(self._slideshow_loop())

    async def _slideshow_loop(self):
        """
        Internal method to handle the slideshow loop.
        """
        await self.device_client.color.show_color(0, 0, 0)
        await self.device_client.reset()
        while True:
            for image in self.images:
                if image != self._current_image:
                    await self._switch_to_next(image)
                else:
                    self.logging.info(f"Skipping image '{image}' as it is already being displayed currently.")
                await sleep(self.interval)

    async def _switch_to_next(self, image: PictureFrameImage | PictureFrameGif | PathLike | str):
        if isinstance(image, PictureFrameImage):
            image_path = image.file_path
            await self._set_image(image_path)
        elif isinstance(image, PictureFrameGif):
            image_path = image.file_path
            await self._set_gif(
                file_path=image_path,
                duration_per_frame_in_ms=image.duration_per_frame_in_ms
            )
        elif isinstance(image, (PathLike, str)):
            # If it's a string or PathLike, treat it as a file path
            if isinstance(image, PathLike):
                image_path = image.__fspath__()
            else:
                image_path = image
            if image_path.lower().endswith('.gif'):
                await self._set_gif(image_path)
            else:
                await self._set_image(image_path)
        else:
            raise ValueError(
                f"Unsupported image type: {type(image)}. Must be PictureFrameImage, PictureFrameGif, or a file path."
            )

        self._current_image = image
        self.logging.info(f"Displaying image '{image_path}' for {self.interval} seconds.")

    async def _set_image(
        self,
        file_path: PathLike | str
    ):
        self.logging.info(f"Setting image file: {file_path}")
        # await self.device_client.reset()
        await self._switch_device_to_image_mode()
        await self.device_client.image.upload_image_file(
            file_path=file_path
        )

    async def _set_gif(
        self,
        file_path: PathLike | str,
        duration_per_frame_in_ms: int = None
    ):
        self.logging.info(f"Setting GIF file: {file_path} ({duration_per_frame_in_ms} ms per frame)")
        await self._switch_device_to_gif_mode()
        await self.device_client.gif.upload_gif_file(
            file_path=file_path,
            duration_per_frame_in_ms=duration_per_frame_in_ms,
        )
        # give the device some time to process the GIF
        await sleep(3)

    async def _switch_device_to_image_mode(self):
        if self._is_in_diy_mode:
            return
        self.logging.info("Switching device to image mode")
        await self.device_client.image.set_mode(ImageMode.EnableDIY)
        self._is_in_diy_mode = True

    async def _switch_device_to_gif_mode(self):
        if not self._is_in_diy_mode:
            return
        self.logging.info("Switching device to GIF mode")
        await self.device_client.image.set_mode(ImageMode.DisableDIY)
        await self.device_client.color.show_color(0, 0, 0)
        await self.device_client.reset()
        self._is_in_diy_mode = False
