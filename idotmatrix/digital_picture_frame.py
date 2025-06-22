import asyncio
import logging
from asyncio import sleep, Task
from enum import Enum
from os import PathLike
from pathlib import Path
from typing import List

from watchdog.observers.inotify import InotifyObserver
from watchdog.observers.polling import PollingObserver

from idotmatrix.client import IDotMatrixClient
from idotmatrix.connection_manager import ConnectionListener
from idotmatrix.modules.image import ImageMode
from idotmatrix.util.file_watch import EventHandler

FilesystemObserver = InotifyObserver | PollingObserver


class PictureFrameGif:
    def __init__(self, file_path: PathLike | str):
        self.file_path = file_path
        self.duration_per_frame_in_ms = None

    def __eq__(self, other):
        if isinstance(other, PictureFrameGif):
            return self.file_path == other.file_path
        if isinstance(other, (PathLike, str)):
            return self.file_path == other
        return False

    def __str__(self):
        return f"PictureFrameGif(file_path={self.file_path}, duration_per_frame_in_ms={self.duration_per_frame_in_ms})"


class PictureFrameImage:
    def __init__(self, file_path: PathLike | str):
        self.file_path = file_path

    def __eq__(self, other):
        if isinstance(other, PictureFrameImage):
            return self.file_path == other.file_path
        if isinstance(other, (PathLike, str)):
            return self.file_path == other
        return False

    def __str__(self):
        return f"PictureFrameImage(file_path={self.file_path})"


DEFAULT_INTERVAL_SECONDS = 30


class FileObserverType(Enum):
    INOTIFY = "inotify"
    POLLING = "polling"


class DigitalPictureFrame:
    """
    A class to manage a digital picture frame that can display images and GIFs in a slideshow format.
    """
    logging = logging.getLogger(__name__)

    def __init__(
        self,
        device_client: IDotMatrixClient,
        images: List[PictureFrameImage | PictureFrameGif | PathLike | str] = None,
    ):
        self.device_client: IDotMatrixClient = device_client
        self.device_client.set_auto_reconnect(True)
        self._setup_connection_listener()

        if not images:
            images = []
        self.images: List[PictureFrameImage | PictureFrameGif | PathLike | str] = images
        self.interval_seconds: int = DEFAULT_INTERVAL_SECONDS

        self._filesystem_observers: List[FilesystemObserver] = []

        self._current_slideshow_index: int = 0
        self._current_image: PictureFrameImage | PictureFrameGif | PathLike | str | None = ""

        self._slideshow_task: Task | None = None

        self._is_paused: bool = False
        self._is_in_diy_mode: bool = False

    def _setup_connection_listener(self):
        """
        Due to the device not beeing the most stable, and the connection also being lost sometimes,
        we need to ensure that the device is always in a valid state when the connection is re-established.
        """

        async def on_device_connected():
            self.logging.debug("Device connected, resetting state and resuming slideshow.")
            await self.resume_slideshow()

        async def on_device_disconnected():
            self.logging.debug("Device disconnected, resetting state and pausing slideshow.")
            self._current_image = None
            self._is_in_diy_mode = False
            await self.pause_slideshow()

        connection_listener = ConnectionListener(
            on_connected=on_device_connected,
            on_disconnected=on_device_disconnected,
        )

        self.device_client.add_connection_listener(connection_listener)

    def set_interval(self, interval: int):
        """
        Sets the interval between two images/GIFs for the slideshow.
        """
        self.logging.info(f"Setting slideshow interval to {interval} seconds")
        self.interval_seconds = interval

    def watch_folders(
        self,
        folders: List[PathLike | str],
        observer_type: FileObserverType = FileObserverType.INOTIFY
    ):
        """
        Adds the given folders to the watchlist and displays any image or GIF in them in the slideshow.

        Args:
            folders (List[PathLike | str]): The folders to watch.
            observer_type (FileObserverType): The type of file observer to use. Defaults to FileObserverType.INOTIFY.
        """
        if not isinstance(folders, list):
            raise ValueError("Folders must be a list of PathLike or str.")

        for folder in folders:
            self.add_folder(folder)
            self.watch_folder(folder, observer_type)

    def watch_folder(
        self,
        folder: PathLike | str,
        observer_type: FileObserverType = FileObserverType.INOTIFY
    ):
        """
        Adds the given folder to the watchlist and displays any image or GIF in them in the slideshow.

        Args:
            folder (PathLike | str): The folder to watch.
            observer_type (FileObserverType): The type of file observer to use. Defaults to FileObserverType.INOTIFY.
        """
        if not isinstance(folder, (PathLike, str)):
            raise ValueError("Folder must be of type PathLike or str.")

        self._add_folder_watch(
            folder=Path(folder),
            observer_type=observer_type,
        )

        self.logging.info(f"Watching folder: {folder}")

    def add_folder(self, folder: PathLike | str):
        """
        Adds all images and GIFs in the given folder to the slideshow.
        """
        if not isinstance(folder, (PathLike, str)):
            raise ValueError("Folder must be of type PathLike or str.")

        folder_path = Path(folder)
        if not folder_path.is_dir():
            raise ValueError(f"The provided path '{folder}' is not a directory.")

        self.logging.info(f"Adding images from folder: {folder_path}")
        for file in folder_path.glob("*"):
            if file.suffix.lower() in [".jpg", ".jpeg", ".png"]:
                self.add_image(PictureFrameImage(file))
            elif file.suffix.lower() == ".gif":
                self.add_image(PictureFrameGif(file))

    def add_image(self, image: PictureFrameImage | PictureFrameGif | PathLike | str):
        """
        Adds an image or GIF to the slideshow.

        Args:
            image (PictureFrameImage | PictureFrameGif | PathLike | str): The image or GIF to add.
        """
        if not isinstance(image, (PictureFrameImage, PictureFrameGif, PathLike, str)):
            raise ValueError("Image must be of type PictureFrameImage, PictureFrameGif, PathLike, or str.")

        self.images.append(image)
        self.logging.info(f"Added image: {image}")

    def remove_image(self, image: PictureFrameImage | PictureFrameGif | PathLike | str):
        """
        Removes an image or GIF from the slideshow.

        Args:
            image (PictureFrameImage | PictureFrameGif | PathLike | str): The image or GIF to remove.
        """
        if image in self.images:
            self.images.remove(image)
            self.logging.info(f"Removed image: {image}")
        else:
            self.logging.warning(f"Image not found in slideshow: {image}")

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
        await asyncio.sleep(0)
        return self._slideshow_task

    async def pause_slideshow(self):
        """
        Pauses the slideshow.
        """
        if self.is_slideshow_running():
            self.logging.info("Pausing slideshow")
        self._is_paused = True

    async def resume_slideshow(self):
        """
        Resumes the slideshow if it was paused.
        """
        if not self.is_slideshow_running():
            self.logging.info("Resuming slideshow")
            self._is_paused = False

    async def stop_slideshow(self):
        """
        Stops the slideshow.
        """
        if self._slideshow_task:
            self.logging.info("Stopping slideshow")
            self._slideshow_task.cancel()
            self._slideshow_task = None

        await self.device_client.clock.show()

    def is_slideshow_running(self) -> bool:
        """
        Checks if the slideshow is currently running.

        Returns:
            bool: True if the slideshow is running, False otherwise.
        """
        return self._slideshow_task is not None and not self._slideshow_task.done() and not self._is_paused

    def _start_slideshow_task(self) -> Task:
        """
        Starts the slideshow task that uploads images to the device at specified intervals.
        """
        return asyncio.create_task(self._slideshow_task_main_loop())

    async def _slideshow_task_main_loop(self):
        """
        Internal method to handle the slideshow loop.
        """
        while True:
            try:
                # initialize by connecting to the device and showing a black screen
                await self.device_client.connect()
                await self._show_black_screen()

                # start the slideshow loop
                await self._slideshow_task_inner_loop()
            except asyncio.CancelledError:
                self.logging.info("Slideshow loop cancelled.")
            except Exception as ex:
                self.logging.error(f"Unexpected error in slideshow loop: {ex}")
                # wait a bit before retrying to avoid rapid reconnection attempts
                await sleep(10)

    async def _slideshow_task_inner_loop(self):
        while True:
            try:
                if self._is_paused:
                    await sleep(1)
                    continue
                await self.next()
            except Exception as ex:
                self.logging.error(f"Error switching to next image in slideshow: {ex}")
                continue
            await sleep(self.interval_seconds)

    async def next(self):
        """
        Switches to the next image in the slideshow.

        This can be used to manually advance to the next image in the slideshow, but keep in mind
        that if a slideshow has been started, it will also automatically advance to the next image
        independently.
        """
        if not self.images:
            if self._current_image is not None:
                self.logging.warning("No images in slideshow to display.")
                await self._show_black_screen()
            return
        self._advance_slideshow_index()
        next_image = self.images[self._current_slideshow_index]
        if next_image != self._current_image:
            try:
                image_path = await self._switch_to(next_image)
            except:
                self.logging.error(f"Failed to switch to image: {next_image}. Skipping this image.")
                return
            if len(self.images) > 1:
                self.logging.info(f"Displaying image '{image_path}'.")
            else:
                self.logging.info(f"Displaying image '{image_path}' (only image in slideshow).")
        else:
            if len(self.images) > 1:
                self.logging.info(f"Skipping image '{next_image}' as it is already being displayed currently.")

    async def _switch_to(self, image: PictureFrameImage | PictureFrameGif | PathLike | str) -> str:
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
        return image_path

    async def _set_image(
        self,
        file_path: PathLike | str
    ):
        self.logging.debug(f"Setting image file: {file_path}")
        await self._switch_device_to_image_mode()
        await self.device_client.image.upload_image_file(
            file_path=file_path
        )

    async def _set_gif(
        self,
        file_path: PathLike | str,
        duration_per_frame_in_ms: int = None
    ):
        self.logging.debug(f"Setting GIF file: {file_path} ({duration_per_frame_in_ms} ms per frame)")
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
        self.logging.debug("Switching device to image mode")
        await self.device_client.image.set_mode(ImageMode.EnableDIY)
        self._is_in_diy_mode = True

    async def _switch_device_to_gif_mode(self):
        if not self._is_in_diy_mode:
            return
        self.logging.debug("Switching device to GIF mode")
        await self.device_client.image.set_mode(ImageMode.DisableDIY)
        await self._show_black_screen()

    def _add_folder_watch(self, folder: Path, observer_type: FileObserverType = FileObserverType.INOTIFY):
        """
        Adds a folder to the watchlist and sets up file observers to monitor changes in the folder.
        Args:
            folder (Path): The folder to watch.
            observer_type (FileObserverType): The type of file observer to use. Defaults to FileObserverType.INOTIFY.
        """
        observers = self._setup_file_observers(
            observer_type=observer_type,
            source_directories=[folder]
        )
        self._filesystem_observers.extend(observers)

        self.logging.info(f"Added folder to watchlist: {folder}")

    def _setup_file_observers(
        self,
        observer_type: FileObserverType,
        source_directories: List[Path]
    ) -> List[FilesystemObserver]:
        observers = []

        for directory in source_directories:
            if observer_type == FileObserverType.INOTIFY:
                observer = InotifyObserver()
            elif observer_type == FileObserverType.POLLING:
                observer = PollingObserver()
            else:
                raise ValueError(f"Unexpected file observer type {observer_type}")

            def on_file_moved(old, new):
                self.remove_image(old)
                self.add_image(new)

            event_handler = EventHandler(
                on_created=lambda x: self.add_image(x),
                on_deleted=lambda x: self.remove_image(x),
                on_moved=on_file_moved
            )

            observer.schedule(event_handler, str(directory), recursive=True)
            observer.start()
            observers.append(observer)

        return observers

    def _advance_slideshow_index(self):
        self._current_slideshow_index = (self._current_slideshow_index + 1) % len(self.images)

    async def _show_black_screen(self):
        self._current_image = None
        self._is_in_diy_mode = False
        await self.device_client.color.show_color(color="black")
        await self.device_client.reset()
