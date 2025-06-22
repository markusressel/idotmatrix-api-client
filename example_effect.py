import asyncio
import logging
import time

from idotmatrix.client import IDotMatrixClient
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
    )
    await client.connect()

    # default colours used in the app.
    colours = [
        (255, 0, 0),
        (255, 162, 0),
        (255, 255, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 0, 255),
        (255, 255, 255)
    ]

    # Effect
    for i in range(0, 7):
        for j in range(2, 8):
            await client.effect.show(i, colours[:j])
            time.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        quit()
