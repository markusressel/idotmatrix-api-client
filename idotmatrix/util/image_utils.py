from PIL import Image as PILImage


def palettize(
    image: PILImage.Image,
    dither: PILImage.Dither = PILImage.Dither.NONE,
    colors: int = 256
) -> PILImage.Image:
    """
    Convert an image to use a specific palette.

    :param image: The input image to be palettized.
    :param dither: The dithering method to use (default is PILImage.Dither.NONE).
                   Other options include PILImage.Dither.FLOYDSTEINBERG, PILImage.Dither.ORDERED, etc.
    :param colors: The number of colors in the palette (default is 256).
    :return: The palettized image.
    """
    if not isinstance(image, PILImage.Image):
        raise TypeError("Input must be a PIL Image.")

    return image.convert(
        mode="P",
        dither=dither,
        palette=PILImage.Palette.ADAPTIVE,
        colors=colors
    )
