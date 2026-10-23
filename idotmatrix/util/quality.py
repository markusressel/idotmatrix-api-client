import math
from typing import List, Sequence, Tuple

from PIL import Image, ImageChops, ImageCms, ImageStat

# Calibrated by eye on a 64x64 display with 6 real animations. Every version that looked acceptable scored up to
# 8.3 (one that "flickers but is ok" 9.7), every one that looked broken or muted scored 11 or more: 9 is the limit of
# what is still fine. What was preferred when there was a choice scored 0 to 4 (for 8351169 the preferred version
# had 128 colors with a score of 0, the one with a shared 64 color palette that scored 7.5 looked as smooth, but
# duller), so the default favors that.
DEFAULT_MAX_COLOR_ERROR = 5.0
# a color that jumps between frames is much more noticeable than a constant error
FLICKER_WEIGHT = 8.0

_SRGB = ImageCms.createProfile("sRGB")
_LAB = ImageCms.createProfile("LAB")
_TO_LAB = ImageCms.buildTransform(_SRGB, _LAB, "RGB", "LAB")


def color_difference(a: Image.Image, b: Image.Image) -> float:
    """
    The root mean square of the color difference between two pictures of the same size, in CIE76 delta E (the
    distance of two colors as the eye sees it: below 2 is hardly noticeable, 5 clearly visible).
    """
    diff = ImageChops.difference(
        ImageCms.applyTransform(a.convert("RGB"), _TO_LAB), ImageCms.applyTransform(b.convert("RGB"), _TO_LAB))
    lightness, green_red, blue_yellow = ImageStat.Stat(diff).rms
    return math.sqrt((lightness * 100 / 255) ** 2 + green_red ** 2 + blue_yellow ** 2)


def color_error(reference: Sequence[Image.Image], reduced: Sequence[Image.Image]) -> Tuple[float, float]:
    """
    How far an animation with fewer colors is from the original: (the mean color difference of the frames, the
    flicker). The flicker is how much more the colors jump from one frame to the next than in the original, which
    happens when every frame gets its own palette.
    """
    errors: List[float] = [color_difference(a, b) for a, b in zip(reference, reduced)]
    mean = sum(errors) / len(errors)
    if len(reference) < 2:
        return mean, 0.0
    jumps = [
        abs(color_difference(reduced[i], reduced[i + 1]) - color_difference(reference[i], reference[i + 1]))
        for i in range(len(reference) - 1)
    ]
    return mean, sum(jumps) / len(jumps)


def color_score(mean: float, flicker: float) -> float:
    """One number for how much worse an animation looks: the lower the better, `DEFAULT_MAX_COLOR_ERROR` is still fine."""
    return mean + FLICKER_WEIGHT * flicker
