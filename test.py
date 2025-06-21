import asyncio
import time

from idotmatrix.client import IDotMatrixClient
from idotmatrix.screensize import ScreenSize


async def main():
    client = IDotMatrixClient(
        screen_size=ScreenSize.SIZE_64x64,
    )

    # connect
    await client.connect()
    # # chronograph
    # await client.chronograph.set_mode(1)
    # time.sleep(5)
    # # clock
    # await client.clock.set_mode(1)
    # time.sleep(5)
    # # Common
    # await client.common.set_screen_flipped(True)
    # time.sleep(5)
    # await client.common.set_screen_flipped(False)
    # # Countdown
    # await client.countdown.set_mode(1, 0, 5)
    # time.sleep(5)
    # # FullscreenColor
    # await client.color.set_mode(r=255, g=255, b=0)
    # time.sleep(5)
    # # show GIF
    # await client.gif.upload_processed(
    #     file_path="./images/demo.gif",
    # )
    # time.sleep(5)
    # # Graffiti
    # await client.graffiti.set_pixel(r=255, g=255, b=255, x=10, y=10)
    # time.sleep(5)
    # Image
    await client.image.upload_image_file(
        file_path="./images/demo_512.png",
    )
    time.sleep(5)
    # Scoreboard
    await client.scoreboard.set_mode(10, 5)
    time.sleep(5)
    # Text
    await client.text.set_mode(
        "HELLO WORLD",
        font_path="./fonts/Rain-DRM3.otf",
    )
    time.sleep(5)
    # Effect
    await client.effect.set_mode(1, [(255, 0, 0), (255, 162, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255)])
    time.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        quit()
