import asyncio
import logging
from pathlib import Path
from random import shuffle
from typing import List

from idotmatrix.client import IDotMatrixClient
from idotmatrix.digital_picture_frame import DigitalPictureFrame
from idotmatrix.screensize import ScreenSize

# set basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s :: %(levelname)s :: %(name)s :: %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
    handlers=[logging.StreamHandler()],
)
# set log level of bleak
logging.getLogger("bleak").setLevel(logging.WARNING)


async def main():
    client = IDotMatrixClient(
        screen_size=ScreenSize.SIZE_64x64,
        mac_address="69:36:4C:4C:B6:B7"
    )

    # GIFs
    gif_file_paths: List[Path] = []
    gif_folder = Path("/home/markus/pictures/Pixel Art GIF/work")
    gif_file_paths += list(gif_folder.glob(pattern="*.gif", case_sensitive=False))

    # Images
    image_file_paths: List[Path] = []
    image_folder = Path("/home/markus/pictures/DPF")
    image_file_paths += list(image_folder.glob(pattern="*.jpg", case_sensitive=False))

    # Combine all file paths
    all_file_paths = gif_file_paths + image_file_paths
    # shuffle them around
    shuffle(all_file_paths)

    digital_picture_frame = DigitalPictureFrame(
        device_client=client,
        # either input a static list of images or use a folder to watch (see below)
        # images=all_file_paths
    )

    digital_picture_frame.watch_folders(
        folders=[gif_folder, image_folder]
    )

    await digital_picture_frame.start_slideshow(interval=5)

    logging.info("Digital Picture Frame started. Press Ctrl+C to exit.")


if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        tasks = asyncio.gather(main())
        loop.run_until_complete(tasks)
        loop.run_forever()
    except KeyboardInterrupt:
        quit()
