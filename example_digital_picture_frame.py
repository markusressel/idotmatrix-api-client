import asyncio
import logging
from pathlib import Path

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

    gif_folder = Path("/home/markus/pictures/Pixel Art GIF")
    image_folder = Path("/home/markus/pictures/DPF")

    digital_picture_frame = DigitalPictureFrame(
        device_client=client,
        # either input a static list of images or use a folder to watch (see below)
        # images=all_file_paths
        shuffle_images=True,
    )

    digital_picture_frame.watch_folder(
        folder=gif_folder,
    )

    digital_picture_frame.watch_folders(
        folders=[image_folder],
        recursive=True,
    )

    await digital_picture_frame.start_slideshow(interval=5)

    logging.info("Digital Picture Frame started. Press Ctrl+C to exit.")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        asyncio.gather(main())
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received, stopping...")
        quit()
    except Exception as e:
        quit()
