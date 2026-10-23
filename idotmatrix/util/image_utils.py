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

    # quantize from RGB: the quantizer for RGBA input is coarse and leaves a part of the colors unused
    return to_rgb(image).quantize(colors=colors, dither=dither)


def to_rgb(image: PILImage.Image) -> PILImage.Image:
    """The image as RGB, transparent areas shown on black like on the display."""
    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = PILImage.new("RGBA", rgba.size, (0, 0, 0, 255))
        return PILImage.alpha_composite(background, rgba).convert("RGB")
    return image.convert("RGB")


def validate_colors(colors: int) -> int:
    """Raises a ValueError for a number of palette colors that cannot be used (2 to 256)."""
    if isinstance(colors, bool) or not isinstance(colors, int) or not 2 <= colors <= 256:
        raise ValueError(f"colors must be between 2 and 256, got: {colors!r}")
    return colors


def palette_table_size(colors: int) -> int:
    """
    The size of the color table of a GIF for that many colors: a power of 2 entries, and PIL writes at least 4.
    """
    return max(4, 1 << (validate_colors(colors) - 1).bit_length())


def palettize_together(images: list[PILImage.Image], colors: int = 256) -> list[PILImage.Image]:
    """
    Converts the images to one common palette, built from all of them. In an animation that keeps a color the
    same from frame to frame, where a palette for each frame makes colors jump (flicker).
    """
    rgb = [to_rgb(image) for image in images]
    montage = PILImage.new("RGB", (rgb[0].width, rgb[0].height * len(rgb)))
    for index, image in enumerate(rgb):
        montage.paste(image, (0, index * image.height))
    palette = montage.quantize(colors=colors, dither=PILImage.Dither.NONE)
    return [image.quantize(palette=palette, dither=PILImage.Dither.NONE) for image in rgb]


def pad_palette(image: PILImage.Image, size: int = 256) -> PILImage.Image:
    """
    Makes sure an image is palettized and its palette has exactly `size` entries.

    PIL writes palettes that are only as large as the number of colors an image uses, so the
    color tables of the frames in an animation differ in size. The iDotMatrix device garbles
    or drops frames of GIFs like that.

    :param image: The input image, converted with `palettize` if it is not palettized yet.
    :param size: The number of palette entries (default is 256).
    :return: A palettized image with a palette of `size` entries.
    """
    if image.mode != "P":
        image = palettize(image.convert("RGB"), colors=size)
    else:
        image = image.copy()

    palette = image.getpalette()[:size * 3]
    palette += [0] * (size * 3 - len(palette))
    image.putpalette(palette)
    return image


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
        # at least one pixel, a very wide or tall picture would be 0 pixels high on a small screen
        new_size = (
            min(canvas_size, max(1, round(image.width * ratio))),
            min(canvas_size, max(1, round(image.height * ratio))),
        )
        image = image.resize(
            size=new_size,
            resample=resample_mode,
        )
    elif resize_mode == ResizeMode.FILL:
        # if the dimensions of the frame are not equal to the pixel size, resize it to fill the canvas
        # this might crop the image, but maintains aspect ratio
        ratio = max(canvas_size / image.width, canvas_size / image.height)
        # never smaller than the canvas, rounding down would leave a stripe of background
        new_size = (
            max(canvas_size, round(image.width * ratio)),
            max(canvas_size, round(image.height * ratio)),
        )
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
