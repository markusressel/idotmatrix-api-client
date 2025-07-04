import asyncio
import logging
from asyncio import sleep
from pathlib import Path
from typing import List, Tuple

from PIL import Image as PILImage

from idotmatrix.client import IDotMatrixClient
from idotmatrix.modules.clock import ClockStyle
from idotmatrix.screensize import ScreenSize
from idotmatrix.util.image_utils import ResizeMode

# set basic logging
logging.basicConfig(
    level=logging.DEBUG,
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

    # now = datetime.now()
    # await client.common.set_time(now)

    # await client.common.set_screen_flipped(False)

    # await client.set_brightness(100)
    await client.clock.show(
        style=ClockStyle.RGBSwipeOutline,
        show_date=False,
    )
    await client.reset()
    # exit(0)

    # await sleep(1)

    # folder = Path("/home/markus/pictures/Pixel Art GIF/unknown")
    # folder = Path("/home/markus/pictures/Pixel Art GIF/dont work")
    # folder = Path("/home/markus/pictures/Pixel Art GIF/not repeating")
    # folder = Path("/home/markus/pictures/Pixel Art GIF/no animation")
    folder = Path("/home/markus/pictures/Pixel Art GIF/work")
    gif_file_paths: List[Path] = []
    gif_file_paths += list(folder.glob(pattern="*.gif", case_sensitive=False))
    # gif_file_paths = list(filter(lambda x: "beautiful" in x.name, gif_file_paths))

    for idx, gif_file in enumerate(gif_file_paths):
        if not gif_file.exists():
            print(f"File {gif_file} does not exist, skipping.")
            continue
        print(f"Uploading GIF: {gif_file.name}")
        await client.reset()
        await client.gif.upload_gif_file(
            file_path=gif_file,
            resize_mode=ResizeMode.FILL,
            duration_per_frame_in_ms=100,
        )
        if idx < len(gif_file_paths) - 1:
            print(f"Waiting...")
            await sleep(10)

    # exit(0)

    # image_file_paths: List[Path] = []
    # # example_images_folder = Path("/home/markus/pictures/Abi Buch Collage")
    # example_images_folder = Path("/home/markus/pictures/DPF")
    # image_file_paths += list(example_images_folder.glob(pattern="*.jpg", case_sensitive=False))
    # # image_file_paths = list(filter(lambda x: "Foto0127" in x.name, image_file_paths))
    #
    # await client.image.set_mode(ImageMode.EnableDIY)
    # for file in image_file_paths:
    #     if not file.exists():
    #         print(f"File {file} does not exist, skipping.")
    #         continue
    #     await client.image.upload_image_file(
    #         file_path=file,
    #         palletize=False,
    #     )
    #     await sleep(5)

    # await client.gif.upload_processed(
    #     # file_path="./images/demo_512.png",
    #     file_path="/home/markus/pictures/Peek 2024-10-13 10-43.gif"
    # )
    #
    # await client.common.set_brightness(95)
    #
    # pixel_data = convert_image_to_pixel_array(
    #     pixel_size=client.screen_size.value[0],  # assuming square canvas, so width == height
    #     # file_path="./images/demo_512.png",
    #     file_path="/home/markus/Downloads/1624051-square-zoomed.jpg"
    # )
    #
    # await draw_shuffled(client, pixel_data)

    # await client.text.show_text(
    #     text="HELLO WORLD!",
    #     # font_size=16,
    #     # text_mode=TextMode.MARQUEE,
    #     # speed=95,
    #     # text_color_mode=TextColorMode.WHITE,
    #     # text_color=(255, 0, 0),
    #     # text_bg_color=(0, 20, 0),
    #     # font_path="./fonts/Rain-DRM3.otf",
    # )

    # colours = [(255, 0, 0), (255, 162, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255), (255, 255, 255)]  # default colours used in the app.
    #
    # # Effect
    # for i in range(0, 7):
    #     for j in range(2, 7):
    #         await client.effect.set_mode(i, colours[:j])
    #         await sleep(1000)


def convert_image_to_pixel_array(
    pixel_size: int = 64,
    file_path: str = "./images/demo_64.png"
) -> List[List[Tuple[int, int, int]]]:
    """
    Converts an image to a pixel array suitable for the iDotMatrix display.
    Args:
        pixel_size (int): Size (squared) of the pixels in the display (default is 64).
        file_path (str): Path to the image file to be converted.
    Returns:
        List[List[Tuple[int, int, int]]]: A 2D list representing the pixel data of the image.
        Each pixel is represented as a tuple of (R, G, B) values.
        The indexing of the list corresponds to the pixel coordinates on the display,
        where the first index is the x-coordinate and the second index is the y-coordinate.
    """

    with PILImage.open(file_path) as img:
        if img.size != (pixel_size, pixel_size):
            img = img.resize(
                (pixel_size, pixel_size), PILImage.Resampling.LANCZOS
            )
        img = img.convert("RGB")  # Ensure the image is in RGB format
        pixel_data = img.load()
        pixel_array = [
            [
                (pixel_data[x, y][0], pixel_data[x, y][1], pixel_data[x, y][2])
                for x in range(pixel_size)
            ]
            for y in range(pixel_size)
        ]
        return pixel_array


async def draw_shuffled(client: IDotMatrixClient, pixel_data: List[List[Tuple[int, int, int]]]) -> None:
    """
    Draws the pixel data on the iDotMatrix display in a shuffled manner.
    Args:
        pixel_data (List[List[Tuple[int, int, int]]]): The pixel data to be drawn.
    """
    # draw the same image, scatter the pixel indices, so the image is recognizable before it is fully drawn
    column_indices = [index for index, _ in enumerate(pixel_data)]
    row_indices = [index for index, _ in enumerate(pixel_data[0])]

    coordinate_pairs = [
        (x, y) for x in column_indices for y in row_indices
    ]
    shuffled_coordinate_pairs = coordinate_pairs.copy()
    import random
    random.shuffle(shuffled_coordinate_pairs)

    for x, y in shuffled_coordinate_pairs:
        color = pixel_data[y][x]
        if color == (0, 0, 0):
            continue
        # scatter the pixel indices
        red = color[0]
        green = color[1]
        blue = color[2]
        await client.graffiti.set_pixel(
            color=(red, green, blue),
            xy=(x, y)
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        quit()
