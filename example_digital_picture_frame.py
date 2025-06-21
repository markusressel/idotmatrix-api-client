import asyncio
from datetime import datetime
from pathlib import Path
from random import shuffle
from typing import List

from idotmatrix.client import IDotMatrixClient
from idotmatrix.digital_picture_frame import DigitalPictureFrame
from idotmatrix.modules.clock import ClockStyle
from idotmatrix.screensize import ScreenSize


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
    # gif_file_paths = list(filter(lambda x: "beautiful" in x.name, gif_file_paths))

    # Images
    image_file_paths: List[Path] = []
    image_folder = Path("/home/markus/pictures/Abi Buch Collage")
    image_file_paths += list(image_folder.glob(pattern="*.jpg", case_sensitive=False))

    all_file_paths = gif_file_paths + image_file_paths
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
