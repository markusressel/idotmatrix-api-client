from typing import Tuple


def parse_color_rgb(color: Tuple[int, int, int] | int | str) -> Tuple[int, int, int]:
    """
    Parses a color input and returns it as an RGB tuple.
    Args:
        color (tuple, int, str): Color in RGB format as a tuple of three integers (r, g, b),
                                 an integer (0 to 16777215), or a string in hex format (#RRGGBB or 0xRRGGBB)
                                 or a named color.
    """
    if color is None:
        return None
    if isinstance(color, int):
        if not (0 <= color < 16777216):
            raise ValueError("Color integer must be between 0 and 16777215 (0xFFFFFF)")
        # Convert integer to RGB tuple
        r = (color >> 16) & 0xFF
        g = (color >> 8) & 0xFF
        b = color & 0xFF
        color = (r, g, b)
    elif isinstance(color, str):
        if color.startswith("#"):
            # Convert hex color to RGB
            color = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        elif color.startswith("0x"):
            # Convert hex color with '0x' prefix to RGB
            color = tuple(int(color[i:i + 2], 16) for i in (2, 4, 6))
        else:
            try:
                from matplotlib import colors
                color = colors.to_rgb(color)
                # convert to integer values
                color = tuple(int(c * 255) for c in color)
            except:
                raise ValueError(
                    "Invalid color string. Use hex format (#RRGGBB), '0xRRGGBB', or a named color."
                )
    elif isinstance(color, tuple):
        if len(color) != 3:
            raise ValueError("Color tuple must contain three integers (r, g, b)")
        if not all(isinstance(c, int) for c in color):
            raise ValueError("Color tuple must contain three integers (r, g, b)")
        if not all(0 <= c < 256 for c in color):
            raise ValueError("Color values must be between 0 and 255")
    else:
        raise ValueError("Color must be an integer, a string, or a tuple of three integers (r, g, b)")

    return color


def parse_color_rgb_list(colors: list[Tuple[int, int, int] | int | str]) -> list[Tuple[int, int, int]]:
    """
    Parses a list of color inputs and returns them as a list of RGB tuples.
    Args:
        colors (list): List of colors in RGB format as tuples of three integers (r, g, b),
                       integers (0 to 16777215), or strings in hex format (#RRGGBB or 0xRRGGBB)
                       or named colors.
    """
    return [parse_color_rgb(color) for color in colors]
