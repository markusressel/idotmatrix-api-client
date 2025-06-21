import asyncio
import logging
from asyncio import sleep, Task
from os import PathLike
from typing import List

from idotmatrix.client import IDotMatrixClient


class PictureFrameGif:
    def __init__(self, file_path: PathLike | str):
        self.file_path = file_path
        self.duration_per_frame_in_ms = None


class PictureFrameImage:
    def __init__(self, file_path: PathLike | str):
        self.file_path = file_path


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

        self._slideshow_task: Task | None = None

    async def start_slideshow(self, interval: int = 30):
        """
        Starts a slideshow of images on the digital picture frame.

        Args:
            interval (int): Time in seconds between image changes. Defaults to 5 seconds.
        """
        self.logging.info(f"Starting slideshow with interval: {interval} seconds")
        self._slideshow_task = await self._start_slideshow_task(interval)

    async def stop_slideshow(self):
        """
        Stops the slideshow.
        """
        if self._slideshow_task:
            self.logging.info("Stopping slideshow")
            self._slideshow_task.cancel()
            self._slideshow_task = None

    async def _start_slideshow_task(self, interval) -> Task:
        """
        Starts the slideshow task that uploads images to the device at specified intervals.
        """
        return asyncio.create_task(self._slideshow_loop(interval))

    async def _slideshow_loop(self, interval: int):
        """
        Internal method to handle the slideshow loop.
        """
        while True:
            for image in self.images:
                if isinstance(image, PictureFrameImage):
                    await self._set_image(image.file_path)
                elif isinstance(image, PictureFrameGif):
                    await self._set_gif(
                        file_path=image.file_path,
                        duration_per_frame_in_ms=image.duration_per_frame_in_ms
                    )
                elif isinstance(image, (PathLike, str)):
                    # If it's a string or PathLike, treat it as a file path
                    if isinstance(image, PathLike):
                        image = image.__fspath__()
                    if image.lower().endswith('.gif'):
                        await self.device_client.gif.upload_gif_file(image)
                    else:
                        await self.device_client.image.upload_image_file(image)
                self.logging.info(f"Displaying image '{image}' for {interval} seconds.")
                await sleep(interval)

    async def _set_image(
        self,
        file_path: PathLike | str
    ):
        self.logging.info(f"Setting image file: {file_path}")
        await self.device_client.reset()
        await self.device_client.image.set_mode()
        await sleep(10)
        await self.device_client.image.upload_image_file(
            file_path=file_path
        )

    async def _set_gif(
        self,
        file_path: PathLike | str,
        duration_per_frame_in_ms: int = None
    ):
        self.logging.info(f"Setting GIF file: {file_path} with ({duration_per_frame_in_ms} ms per frame)")
        await self.device_client.gif.upload_gif_file(
            file_path=file_path,
            duration_per_frame_in_ms=duration_per_frame_in_ms,
        )
