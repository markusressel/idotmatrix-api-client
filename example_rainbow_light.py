import asyncio
import logging
from typing import List, Tuple

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


def create_rainbow_colors_with_smooth_transition(
    steps: int = 500,
) -> List[Tuple[int, int, int]]:
    """
    Generates a list of RGB tuples representing a smooth rainbow color transition.
    The colors transition from red to green to blue and back to red, creating a smooth gradient effect.
    :param steps: Number of steps for the smooth transition. Default is 100.
    :return: A list of RGB tuples representing the rainbow colors.
    """
    result = []
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

        result.append((r, g, b))
    return result


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
