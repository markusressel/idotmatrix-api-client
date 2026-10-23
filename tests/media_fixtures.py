"""
Synthetic pictures and animations that cover what real-world files do to the conversion: noise that does not
compress, flat colors, many frames, tiny and extreme sizes, transparency, odd frame durations.
They are generated, so no pictures need to be checked in.
"""
import random
from pathlib import Path
from typing import Callable

from PIL import Image

_RANDOM = random.Random(42)


def _noise(size: tuple[int, int], mode: str = "RGB") -> Image.Image:
    channels = len(mode)
    return Image.frombytes(mode, size, bytes(_RANDOM.randrange(256) for _ in range(size[0] * size[1] * channels)))


def _gradient(size: tuple[int, int], shift: int = 0) -> Image.Image:
    image = Image.new("RGB", size)
    pixels = image.load()
    for x in range(size[0]):
        for y in range(size[1]):
            pixels[x, y] = ((x * 255 // max(size[0] - 1, 1) + shift) % 256, y * 255 // max(size[1] - 1, 1), 128)
    return image


def _save_gif(path: Path, frames: list[Image.Image], **kwargs) -> Path:
    first, rest = frames[0], frames[1:]
    first.save(path, save_all=True, append_images=rest, loop=0, **kwargs)
    return path


def _noisy_gif(path: Path) -> Path:
    return _save_gif(path, [_noise((120, 90)).quantize(256) for _ in range(30)], duration=60)


def _flat_gif(path: Path) -> Path:
    return _save_gif(path, [Image.new("RGB", (80, 80), (i * 20, 0, 255 - i * 20)).quantize(256) for i in range(10)],
                     duration=100)


def _single_frame_gif(path: Path) -> Path:
    _gradient((50, 50)).quantize(256).save(path)
    return path


def _many_frames_gif(path: Path) -> Path:
    return _save_gif(path, [_gradient((48, 48), shift=i * 3).quantize(64) for i in range(200)], duration=20)


def _long_gif(path: Path) -> Path:
    """Few frames, but a long duration for each of them."""
    return _save_gif(path, [_gradient((64, 64), shift=i * 40).quantize(256) for i in range(6)], duration=1500)


def _no_duration_gif(path: Path) -> Path:
    return _save_gif(path, [_gradient((64, 64), shift=i * 30).quantize(256) for i in range(8)])


def _zero_duration_gif(path: Path) -> Path:
    return _save_gif(path, [_gradient((64, 64), shift=i * 30).quantize(256) for i in range(8)], duration=0)


def _huge_gif(path: Path) -> Path:
    return _save_gif(path, [_gradient((640, 360), shift=i * 20).quantize(256) for i in range(10)], duration=80)


def _transparent_gif(path: Path) -> Path:
    frames = []
    for i in range(6):
        frame = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        frame.paste((255, 0, 0, 255), (i * 8, i * 8, i * 8 + 16, i * 8 + 16))
        frames.append(frame)
    return _save_gif(path, frames, duration=100, disposal=2, transparency=0)


def _wide_gif(path: Path) -> Path:
    return _save_gif(path, [_gradient((600, 30), shift=i * 20).quantize(256) for i in range(5)], duration=100)


def _tall_gif(path: Path) -> Path:
    return _save_gif(path, [_gradient((30, 600), shift=i * 20).quantize(256) for i in range(5)], duration=100)


def _tiny_gif(path: Path) -> Path:
    return _save_gif(path, [Image.new("RGB", (1, 1), (i * 40, 0, 0)).quantize(256) for i in range(4)], duration=100)


def _pixel_art_gif(path: Path) -> Path:
    """Few colors and hard edges, like the art made for these displays."""
    frames = []
    for i in range(8):
        frame = Image.new("P", (64, 64), 0)
        frame.putpalette([0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * (252 * 3))
        for x in range(64):
            for y in range(64):
                frame.putpixel((x, y), 1 + ((x // 8 + y // 8 + i) % 3))
        frames.append(frame)
    return _save_gif(path, frames, duration=120)


def _noisy_png(path: Path) -> Path:
    _noise((200, 200)).save(path)
    return path


def _flat_png(path: Path) -> Path:
    Image.new("RGB", (64, 64), (10, 200, 30)).save(path)
    return path


def _transparent_png(path: Path) -> Path:
    image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    image.paste((0, 0, 255, 255), (10, 10, 30, 30))
    image.save(path)
    return path


def _wide_png(path: Path) -> Path:
    _gradient((900, 40)).save(path)
    return path


def _tall_png(path: Path) -> Path:
    _gradient((40, 900)).save(path)
    return path


def _tiny_png(path: Path) -> Path:
    Image.new("RGB", (1, 1), (255, 255, 255)).save(path)
    return path


def _huge_jpg(path: Path) -> Path:
    _gradient((1600, 1000)).save(path, quality=80)
    return path


def _grayscale_png(path: Path) -> Path:
    Image.linear_gradient("L").save(path)
    return path


GIFS: dict[str, Callable[[Path], Path]] = {
    "noisy": _noisy_gif,
    "flat": _flat_gif,
    "single_frame": _single_frame_gif,
    "many_frames": _many_frames_gif,
    "long_frames": _long_gif,
    "no_duration": _no_duration_gif,
    "zero_duration": _zero_duration_gif,
    "huge": _huge_gif,
    "transparent": _transparent_gif,
    "wide": _wide_gif,
    "tall": _tall_gif,
    "tiny": _tiny_gif,
    "pixel_art": _pixel_art_gif,
}

IMAGES: dict[str, Callable[[Path], Path]] = {
    "noisy": _noisy_png,
    "flat": _flat_png,
    "transparent": _transparent_png,
    "wide": _wide_png,
    "tall": _tall_png,
    "tiny": _tiny_png,
    "huge_jpg": _huge_jpg,
    "grayscale": _grayscale_png,
}
