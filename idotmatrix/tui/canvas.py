from PIL import Image as PILImage

Color = tuple[int, int, int]
BLACK: Color = (0, 0, 0)
MAX_UNDO = 100


class PixelCanvas:
    """A square picture to draw on, with undo, and a record of what changed since it was last sent to the display."""

    def __init__(self, size: int):
        self.size = size
        self._pixels: list[list[Color]] = [[BLACK] * size for _ in range(size)]
        self._undo: list[list[list[Color]]] = []
        self._redo: list[list[list[Color]]] = []
        self._dirty: set[tuple[int, int]] = set()
        self._touched: set[int] = set()

    def get(self, x: int, y: int) -> Color:
        return self._pixels[y][x]

    def inside(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    # changing

    def begin(self) -> None:
        """Remembers the state for undo. Call it once before a stroke, not for every pixel of it."""
        self._undo.append([row[:] for row in self._pixels])
        del self._undo[:-MAX_UNDO]
        self._redo.clear()

    def set(self, x: int, y: int, color: Color) -> bool:
        if not self.inside(x, y) or self._pixels[y][x] == color:
            return False
        self._pixels[y][x] = color
        self._dirty.add((x, y))
        self._touched.add(y)
        return True

    def line(self, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
        """Bresenham."""
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        step_x, step_y = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        error = dx + dy
        while True:
            self.set(x0, y0, color)
            if (x0, y0) == (x1, y1):
                return
            doubled = 2 * error
            if doubled >= dy:
                error += dy
                x0 += step_x
            if doubled <= dx:
                error += dx
                y0 += step_y

    def rectangle(self, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
        """The outline of the rectangle with these corners."""
        left, right, top, bottom = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
        self.line(left, top, right, top, color)
        self.line(left, bottom, right, bottom, color)
        self.line(left, top, left, bottom, color)
        self.line(right, top, right, bottom, color)

    def fill(self, x: int, y: int, color: Color) -> None:
        """Replaces the area of one color around a pixel."""
        if not self.inside(x, y):
            return
        target = self._pixels[y][x]
        if target == color:
            return
        stack = [(x, y)]
        while stack:
            px, py = stack.pop()
            if not self.inside(px, py) or self._pixels[py][px] != target:
                continue
            self.set(px, py, color)
            stack.extend(((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)))

    def clear(self) -> None:
        for y in range(self.size):
            for x in range(self.size):
                self.set(x, y, BLACK)

    def load(self, image: PILImage.Image) -> None:
        """Replaces the picture, scaled to the canvas without smoothing, so pixel art stays sharp."""
        rgb = image.convert("RGB")
        if rgb.size != (self.size, self.size):
            rgb = rgb.resize((self.size, self.size), PILImage.Resampling.NEAREST)
        for y in range(self.size):
            for x in range(self.size):
                self.set(x, y, rgb.getpixel((x, y)))

    # undo

    def undo(self) -> bool:
        return self._swap(self._undo, self._redo)

    def redo(self) -> bool:
        return self._swap(self._redo, self._undo)

    def _swap(self, source: list, target: list) -> bool:
        if not source:
            return False
        target.append([row[:] for row in self._pixels])
        state = source.pop()
        for y in range(self.size):
            for x in range(self.size):
                self.set(x, y, state[y][x])
        return True

    # sending

    def take_dirty(self) -> dict[tuple[int, int], Color]:
        """The pixels that changed since the last call, with their colors."""
        changed = {(x, y): self._pixels[y][x] for x, y in self._dirty}
        self._dirty.clear()
        return changed

    def take_touched(self) -> "set[int]":  # a string: the method set of this class hides the builtin
        """The rows of pixels that changed since the last call, to draw only those again."""
        touched = self._touched
        self._touched = set()
        return touched

    def everything(self) -> dict[tuple[int, int], Color]:
        self._dirty.clear()
        return {(x, y): self._pixels[y][x] for y in range(self.size) for x in range(self.size)}

    # as a picture

    def to_image(self) -> PILImage.Image:
        image = PILImage.new("RGB", (self.size, self.size))
        image.putdata([pixel for row in self._pixels for pixel in row])
        return image

    def colors(self) -> list[Color]:
        """All pixels, row by row."""
        return [pixel for row in self._pixels for pixel in row]
