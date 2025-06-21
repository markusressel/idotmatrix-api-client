import asyncio
import time

from idotmatrix.client import IDotMatrixClient
from idotmatrix.screensize import ScreenSize


async def main():
    client = IDotMatrixClient(
        screen_size=ScreenSize.SIZE_64x64,
    )
    await client.connect()

    colours = [(255, 0, 0), (255, 162, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255), (255, 255, 255)]  # default colours used in the app.

    # Effect
    for i in range(0, 7):
        await client.effect.set_mode(i, colours[:2])
        time.sleep(5)
        await client.effect.set_mode(i, colours[:3])
        time.sleep(5)
        await client.effect.set_mode(i, colours[:4])
        time.sleep(5)
        await client.effect.set_mode(i, colours[:5])
        time.sleep(5)
        await client.effect.set_mode(i, colours[:6])
        time.sleep(5)
        await client.effect.set_mode(i, colours[:7])
        time.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        quit()
