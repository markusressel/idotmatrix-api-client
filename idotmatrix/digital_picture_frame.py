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

        self._is_in_diy_mode: bool = False

    async def start_slideshow(self, interval: int = 30):
        """
        Starts a slideshow of images on the digital picture frame.

        Args:
            interval (int): Time in seconds between image changes. Defaults to 5 seconds.
        """
        self.logging.info(f"Starting slideshow with interval: {interval} seconds")
        self._slideshow_task = self._start_slideshow_task(interval)
        return self._slideshow_task

    async def stop_slideshow(self):
        """
        Stops the slideshow.
        """
        if self._slideshow_task:
            self.logging.info("Stopping slideshow")
            self._slideshow_task.cancel()
            self._slideshow_task = None

    def _start_slideshow_task(self, interval) -> Task:
        """
        Starts the slideshow task that uploads images to the device at specified intervals.
        """
        return asyncio.create_task(self._slideshow_loop(interval))

    async def _slideshow_loop(self, interval: int):
        """
        Internal method to handle the slideshow loop.
        """
        await self.device_client.color.show_color(0, 0, 0)
        await self.device_client.reset()
        await self.device_client.text.show_text("Starting Slideshow...")
        await sleep(6)
        await self.device_client.color.show_color(0, 0, 0)
        await sleep(1)
        await self.device_client.reset()
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
                        await self._set_gif(image)
                    else:
                        await self._set_image(image)
                self.logging.info(f"Displaying image '{image}' for {interval} seconds.")
                await sleep(interval)

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
        self.logging.info(f"Setting GIF file: {file_path} with ({duration_per_frame_in_ms} ms per frame)")
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
        await self.device_client.reset()
        await self.device_client.color.show_color(0, 0, 0)
        self._is_in_diy_mode = False
