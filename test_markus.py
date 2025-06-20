import asyncio
from datetime import datetime
from typing import List, Tuple

from PIL import Image as PILImage
from PIL.GifImagePlugin import GifImageFile

from idotmatrix import ConnectionManager, Common, Graffiti, Gif, Image



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


async def draw_shuffled(pixel_data):
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

    graffiti_client = Graffiti()

    for x, y in shuffled_coordinate_pairs:
        color = pixel_data[y][x]
        if color == (0, 0, 0):
            continue
        # scatter the pixel indices
        red = color[0]
        green = color[1]
        blue = color[2]
        await graffiti_client.setPixel(
            r=red, g=green, b=blue,
            x=x, y=y
        )
        await asyncio.sleep(0.02)

async def main():
    # connect
    conn = ConnectionManager()
    await conn.connectByAddress("69:36:4C:4C:B6:B7")

    screen_size = 64

    common_client = Common()
    # await common_client.flipScreen(False)
    now = datetime.now()
    await common_client.setTime(
        year=now.year,
        month=now.month,
        day=now.day,
        hour=now.hour,
        minute=now.minute,
        second=now.second,
    )
    await common_client.setBrightness(10)
    await asyncio.sleep(0.1)
    #
    image_client = Image()
    await image_client.setMode(1)
    await asyncio.sleep(0.5)
    await image_client.uploadProcessed(
       pixel_size=64,
       file_path="./images/demo_64.png",
    )

    # gif_mode = Gif()
    # await gif_mode.uploadProcessed(
    #     pixel_size=screen_size,
    #     # file_path="./images/demo_512.png",
    #     file_path="/home/markus/Downloads/1624051-square-zoomed.jpg"
    # )

    # await common_client.setBrightness(95)
    # await asyncio.sleep(0.02)

    graffiti_client = Graffiti()


    # pixel_data = convert_image_to_pixel_array(
    #     pixel_size=screen_size,
    #     # file_path="./images/demo_512.png",
    #     file_path="/home/markus/Downloads/1624051-square-zoomed.jpg"
    # )
    #
    # await draw_shuffled(pixel_data)

    # Upload the pixel data to the iDotMatrix display
    # for y, column in enumerate(pixel_data):
    #     for x, color in enumerate(column):
    #         if color == (0, 0, 0):
    #             continue
    #         await graffiti_client.setPixel(
    #             r=color[0], g=color[1], b=color[2], x=x, y=y
    #         )
    #         await asyncio.sleep(0.02)



    # # draw a right angle with three pixels in all four corners of the 64x64 pixel screen to different colours
    # await test.setPixel(255, 255, 255, 0, 0)  # top left corner
    # await test.setPixel(255, 0, 0, 0, 63)  # top right corner
    # await test.setPixel(0, 255, 0, 63, 0)  # bottom left corner
    # await test.setPixel(0, 0, 255, 63, 63)  # bottom right corner

    # test = Text()
    # await test.setMode(
    #     text="Hello World!",
    #     font_size=16,
    #     text_mode=3,
    #     speed=95,
    #     text_color_mode=1,
    #     text_color=(255, 0, 0),
    #     text_bg_mode=0,
    #     text_bg_color=(0, 255, 0),
    #     # font_path="./fonts/RobotoMono-Regular.ttf",
    # )

    # await asyncio.sleep(1000)

    # colours = [(255, 0, 0), (255, 162, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255), (255, 255, 255)]  # default colours used in the app.
    #
    # # Effect
    # test = Effect()
    # for i in range(0, 7):
    #     for j in range(2, 7):
    #         await test.setMode(i, colours[:j])
    #         await asyncio.sleep(1000)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        quit()
