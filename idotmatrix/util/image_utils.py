from enum import Enum

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

    # Ensure the image is in RGB mode before palettizing to avoid quantization,
    # see: https://github.com/python-pillow/Pillow/issues/6832#issuecomment-1366276887
    # see: https://github.com/python-pillow/Pillow/blob/2755e0ffaadc8b29c3e67e223c333c50e197a733/src/PIL/Image.py#L964-L965
    # TODO: not sure if this actually makes a difference
    # image = image.convert(mode="RGB")

    return image.convert(
        mode="P",
        dither=dither,
        palette=PILImage.Palette.ADAPTIVE,
        colors=colors
    )


class ResizeMode(Enum):
    """
    Enum for resize modes.
    """
    FIT = "fit"  # Resize to fit within the canvas while maintaining aspect ratio
    FILL = "fill"  # Resize to fill the canvas, may crop the image, but maintains aspect ratio
    STRETCH = "stretch"  # Stretch the image to fit the canvas, may distort the image


def resize_image(
    image: PILImage.Image,
    canvas_size: int,
    resize_mode: ResizeMode,
    resample_mode: PILImage.Resampling,
    background_color: tuple[int, int, int] = (0, 0, 0),
    mode: str = "RGB",
) -> PILImage.Image:
    """
    Resize an image to a specific size.

    :param image: The input image to be resized.
    :param canvas_size: The (square) size of the canvas to fit the image into.
    :param resize_mode: The mode to use for resizing the image (ResizeMode.FIT, ResizeMode.FILL, ResizeMode.STRETCH).
    :param resample_mode: The resampling mode to use for resizing (e.g., PILImage.Resampling.LANCZOS).
    :param background_color: The color to fill the background with if the image does not fill the whole canvas.
    :param mode: The mode to use for the new image (default is "RGB").
    :return: The resized image.
    """
    if resize_mode == ResizeMode.FIT:
        # if the dimensions of the frame are not equal to the pixel size, resize it while maintaining the aspect ratio
        # and adding a black background if necessary.
        ratio = min(canvas_size / image.width, canvas_size / image.height)
        new_size = (int(image.width * ratio), int(image.height * ratio))
        image = image.resize(
            size=new_size,
            resample=resample_mode,
        )
    elif resize_mode == ResizeMode.FILL:
        # if the dimensions of the frame are not equal to the pixel size, resize it to fill the canvas
        # this might crop the image, but maintains aspect ratio
        ratio = max(canvas_size / image.width, canvas_size / image.height)
        new_size = (int(image.width * ratio), int(image.height * ratio))
        image = image.resize(
            size=new_size,
            resample=resample_mode,
        )
        # crop anything that is outside the canvas size
        box = (
            (image.width - canvas_size) // 2,
            (image.height - canvas_size) // 2,
            (image.width + canvas_size) // 2,
            (image.height + canvas_size) // 2,
        )
        image = image.crop(box)
    elif resize_mode == ResizeMode.STRETCH:
        # if the dimensions of the frame are not equal to the pixel size, stretch it to fit the canvas
        # and add a black background if necessary.
        image = image.resize(
            size=(canvas_size, canvas_size),
            resample=resample_mode,
        )

    # convert transparent pixels to the background color
    new_image = PILImage.new(
        mode="RGBA",
        size=(canvas_size, canvas_size),
        color=background_color
    )
    new_image.paste(
        im=image,
        box=((canvas_size - image.width) // 2, (canvas_size - image.height) // 2),
        mask=image.convert("RGBA")
    )
    image = new_image

    # ensure exact image dimensions
    # ensure the image is always exactly canvas_size x canvas_size pixels and
    # fill the background behind the image with background_color, if the image doesn't fill the whole canvas
    new_img = PILImage.new(mode, (canvas_size, canvas_size), background_color)
    new_img.paste(
        im=image,
        box=((canvas_size - image.width) // 2, (canvas_size - image.height) // 2)
    )
    image = new_img

    return image
