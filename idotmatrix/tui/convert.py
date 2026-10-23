import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image as PILImage

from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.screensize import ScreenSize
from idotmatrix.tui.settings import Options

# seconds of upload per KB, measured on a local BlueZ adapter (a Bluetooth proxy can be slower)
UPLOAD_SECONDS_PER_KB = 0.12


@dataclass
class Preview:
    """What a file looks like on the display, and what it costs to send."""
    frames: list[PILImage.Image]
    durations: list[int]
    size_bytes: int
    animated: bool

    @property
    def loop_seconds(self) -> float:
        return sum(self.durations) / 1000

    @property
    def upload_seconds(self) -> float:
        return self.size_bytes / 1024 * UPLOAD_SECONDS_PER_KB


def is_animated(path: Path) -> bool:
    with PILImage.open(path) as img:
        return getattr(img, "n_frames", 1) > 1


def convert(path: Path, canvas_size: int, options: Options) -> Preview:
    """
    Converts a file the way an upload does, with the options, and decodes the result. Slow for a long animation, so
    not for the UI thread.
    """
    if is_animated(path):
        screen = next((size for size in ScreenSize if size.value[0] == canvas_size), ScreenSize.SIZE_64x64)
        module = GifModule(connection_manager=None, screen_size=screen)
        data = module._load_gif_and_adapt_to_canvas(
            file_path=path, canvas_size=canvas_size, resize_mode=options.resize,
            colors=options.colors_value, max_size_kb=options.max_size_kb, overlay=options.overlay_for(path))
        with PILImage.open(io.BytesIO(data)) as gif:
            frames, durations = [], []
            for index in range(gif.n_frames):
                gif.seek(index)
                frames.append(gif.convert("RGB"))
                durations.append(gif.info.get("duration", 100))
        return Preview(frames, durations, len(data), animated=True)

    pixels = ImageModule._load_image_and_adapt_to_canvas(
        file_path=path, canvas_size=canvas_size, resize_mode=options.resize, palletize=False,
        background_color=(0, 0, 0), overlay=options.overlay_for(path))
    image = PILImage.frombytes("RGB", (canvas_size, canvas_size), bytes(pixels))
    png = io.BytesIO()
    image.save(png, "PNG", optimize=True)  # what is sent: images are sent as PNG
    return Preview([image], [1000], len(png.getvalue()), animated=False)
