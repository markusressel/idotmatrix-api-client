import asyncio
import logging
import time

from idotmatrix.client import IDotMatrixClient
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
        screen_size=ScreenSize.SIZE_64x64,  # or use ScreenSize.SIZE_32x32 or ScreenSize.SIZE_16x16
        # mac_address="00:11:22:33:44:55",  # (optional) specify your device's Bluetooth address
    )
    # if mac_address is provided, this is optional.
    # if not, the first discovered device will be connected to.
    await client.connect()

    # Chronograph
    await client.chronograph.reset()
    time.sleep(5)
    await client.chronograph.start_from_zero()
    time.sleep(5)

    # Clock
    await client.clock.show(ClockStyle.RGBSwipeOutline)
    time.sleep(5)

    # Common
    await client.common.set_screen_flipped(True)
    time.sleep(5)
    await client.common.set_screen_flipped(False)

    # Countdown
    await client.countdown.start(minutes=10)
    time.sleep(5)

    # FullscreenColor
    await client.color.show_color("yellow")
    time.sleep(5)

    # GIF
    await client.gif.upload_gif_file(
        file_path="./images/demo.gif",
    )
    time.sleep(5)

    # Graffiti
    await client.graffiti.set_pixel(
        color=(255, 255, 255),
        xy=(10, 10),
    )
    await client.graffiti.set_pixels(
        color=(128, 192, 255),
        xys=[(x, y) for y in range(20, 30) for x in range(20, 30)]
    )
    time.sleep(5)

    # Image
    await client.image.set_mode()
    await client.image.upload_image_file(
        file_path="./images/demo_512.png",
        palletize=True,
    )
    time.sleep(5)

    # Scoreboard
    await client.scoreboard.show(10, 5)
    time.sleep(5)

    # Text
    await client.text.show_text(
        text="HELLO WORLD",
        font_path="./fonts/Rain-DRM3.otf",
    )
    time.sleep(5)

    # Effect
    await client.effect.show(
        style=1,
        colors=[(255, 0, 0), (255, 162, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255)]
    )
    time.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        quit()
