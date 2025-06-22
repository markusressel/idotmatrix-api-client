import asyncio
import logging
from datetime import datetime
from pathlib import Path
from random import shuffle
from typing import List

from idotmatrix.client import IDotMatrixClient
from idotmatrix.digital_picture_frame import DigitalPictureFrame
from idotmatrix.modules.clock import ClockStyle
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

    now = datetime.now()
    await client.common.set_time(now)

    await client.set_brightness(100)
    await client.clock.show(
        style=ClockStyle.RGBSwipeOutline,
        show_date=False,
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
        images=all_file_paths
    )
    slideshow_task = await digital_picture_frame.start_slideshow(interval=5)

    await asyncio.gather(slideshow_task)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        quit()
