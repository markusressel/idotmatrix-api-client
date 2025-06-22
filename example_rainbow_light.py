import asyncio
from typing import List, Tuple

from idotmatrix.client import IDotMatrixClient
from idotmatrix.screensize import ScreenSize


def create_rainbow_colors_with_smooth_transition() -> List[Tuple[int, int, int]]:
    """
    Create a list of RGB tuples representing rainbow colors with a smooth transition effect.
    """
    colors = []
    steps = 100  # Number of steps for smooth transition
    for i in range(steps):
        # Calculate the transition between red, green, and blue
        if i < steps / 3:
            # Transition from red to green
            r = int(255 * (1 - (i / (steps / 3))))
            g = int(255 * (i / (steps / 3)))
            b = 0
        elif i < 2 * steps / 3:
            # Transition from green to blue
            r = 0
            g = int(255 * (1 - ((i - steps / 3) / (steps / 3))))
            b = int(255 * ((i - steps / 3) / (steps / 3)))
        else:
            # Transition from blue to red
            r = int(255 * ((i - 2 * steps / 3) / (steps / 3)))
            g = 0
            b = int(255 * (1 - ((i - 2 * steps / 3) / (steps / 3))))

        colors.append((r, g, b))
    return colors


async def main():
    client = IDotMatrixClient(
        screen_size=ScreenSize.SIZE_64x64,  # or use ScreenSize.SIZE_32x32 or ScreenSize.SIZE_16x16
        mac_address="69:36:4C:4C:B6:B7",  # (optional) specify your device's Bluetooth address
    )

    color_list = create_rainbow_colors_with_smooth_transition()
    while True:
        for color in color_list:
            await client.color.show_color(color)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        quit()
