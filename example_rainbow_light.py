import asyncio
import time
from typing import List, Tuple

from idotmatrix.client import IDotMatrixClient
from idotmatrix.screensize import ScreenSize


def create_rainbow_colors_with_smooth_transition() -> List[Tuple[int, int, int]]:
    """
    Create a list of RGB tuples representing rainbow colors with a smooth transition effect.
    """
    colors = []
    for i in range(256):
        r = int((i * 6) % 256)
        g = int((i * 6 + 85) % 256)
        b = int((i * 6 + 170) % 256)
        colors.append((r, g, b))
    return colors


async def main():
    client = IDotMatrixClient(
        screen_size=ScreenSize.SIZE_64x64,  # or use ScreenSize.SIZE_32x32 or ScreenSize.SIZE_16x16
        # mac_address="00:11:22:33:44:55",  # (optional) specify your device's Bluetooth address
    )

    color_list = create_rainbow_colors_with_smooth_transition()
    while True:
        for color in color_list:
            await client.color.show_color(color)
            time.sleep(0.02)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        quit()
