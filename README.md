<br/>
<p align="center">
  <a href="https://github.com/markusressel/idotmatrix-api-client">
    <img src="images/logo.png" alt="Logo" width="250" height="250">
  </a>

<h3 align="center">idotmatrix-api-client</h3>

  <p align="center">
    Control 16x16, 32x32 and 64x64 sized iDotMatrix Pixel Displays
  </p>

  <p align="center">
    <img src="https://img.shields.io/github/contributors/markusressel/idotmatrix-api-client?color=dark-green" alt="Contributors">
    <img src="https://img.shields.io/github/license/markusressel/idotmatrix-api-client" alt="License">
  </p>
</p>

## Features

This repository aims to reverse engineer
the [iDotMatrix](https://play.google.com/store/apps/details?id=com.tech.idotmatrix&pli=1) Android App for pixel screen
displays like the one below. The goal is to provide a library which can be used to
connect and control these displays without the need for the official app.

Looking for Home Assistant? The [ha-idotmatrix](https://github.com/markusressel/ha-idotmatrix) integration is built on
this library.

<p align="center">
  <img src="docs/images/device.png" alt="An iDotMatrix pixel display showing a pixel art picture" width="400">
</p>

* Show photos, animated GIFs and pixel art, with text on top, or store them in the slots of the device so that it
  cycles through them on its own
* Clock, countdown, chronograph, scoreboard, graffiti board, effects and a full screen color
* Scrolling text with the bundled pixel fonts
* Music sync with the microphone of the device
* Brightness, eco mode, power and time
* Digital picture frame for a folder of pictures
* Terminal UI to try all of it
* Works with the 16x16, 32x32 and 64x64 displays, with `bleak` or with the Bluetooth stack of Home Assistant

Open ends (alarm and buzzer, the cloud API, password protection, firmware update) are collected in the
[device protocol notes](docs/DEVICE-PROTOCOL.md#not-understood-yet).

## Getting Started

Requires Python 3.12 or newer. Windows may work but is untested.

```sh
pip install idotmatrix-api-client
```

The terminal UI needs an extra: `pip install 'idotmatrix-api-client[tui]'`.

To work on the library, clone the repo and install it with [Poetry](https://python-poetry.org/):

```sh
git clone https://github.com/markusressel/idotmatrix-api-client.git
cd idotmatrix-api-client/
poetry install --with test
```

## Usage

### Device API Client

```python
import asyncio

from idotmatrix import IDotMatrixClient, ScreenSize


async def main():
  # create a new IDotMatrixClient instance
  client = IDotMatrixClient(
    # (optional) the screen size of your device, ScreenSize.SIZE_64x64, SIZE_32x32 or SIZE_16x16.
    # If it is left out, the client asks the device when connecting (so call `connect` before using images or GIFs).
    screen_size=ScreenSize.SIZE_64x64,
    # mac_address="00:11:22:33:44:55",  # (optional) specify your device's Bluetooth address
  )
  # (optional) connect to first found iDotMatrix Pixel Display
  # If the device is not connected when issuing commands, an automatic connection attempt will be made.
  await client.connect()

  # do something with the device by using one of the toplevel functions or modules e.g. chronograph, clock, countdown, etc.
  await client.set_brightness(50)  # set brightness to 50%

  await client.text.show_text("Hello World!")  # display text on the screen


if __name__ == "__main__":
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    quit()
```

For more examples please check the [example.py](./example.py).

#### Images and GIFs

```python
from idotmatrix.util.image_utils import ResizeMode

# show a photo or any other image, scaled to the screen
await client.image.show_image_file("photo.jpg", resize_mode=ResizeMode.FILL)

# show an animated GIF
await client.gif.upload_gif_file("animation.gif")

# label a picture or every frame of a GIF (the text is drawn at the size of the screen, before the colors are reduced)
from idotmatrix.util.overlay import TextOverlay
await client.gif.upload_gif_file("animation.gif", overlay=TextOverlay("64c", position="top-right"))

# store files in the slots of the device, which then cycles through them on its own (no uploads during the show)
await client.materials.store(["a.gif", "b.png", "c.gif"], slots=[1, 2, 3], display_time=30)
# the module remembers what is in which slot: storing again only transfers what is new, in any order
```

Both can be mixed freely, no mode switching is needed in between. They work like the official app, which waits
for the device to acknowledge each chunk of data. An `UploadError` is raised if the device rejects an upload or does
not answer.

`client.image.upload_image_file` uses the DIY mode instead (see `client.image.set_mode`), which is meant for drawing
pixel by pixel and has to be left again before a GIF can be shown.

#### Home Assistant and other Bluetooth stacks

A Home Assistant integration that is built on this library is in development: [ha-idotmatrix](https://github.com/markusressel/ha-idotmatrix).

By default the library connects with `bleak` itself. If something else owns the Bluetooth stack, like the scanner and
the Bluetooth proxies of Home Assistant, hand over what it found or how to connect:

```python
# a BLEDevice that a scanner found, instead of a MAC address
client = IDotMatrixClient(screen_size=ScreenSize.SIZE_64x64, ble_device=ble_device)

# or provide the whole connection, by implementing `idotmatrix.transport.Transport`
client = IDotMatrixClient(
    screen_size=ScreenSize.SIZE_64x64,
    mac_address="00:11:22:33:44:55",
    transport_factory=lambda address_or_device, on_disconnected: MyTransport(address_or_device, on_disconnected),
)
```

Turn off `install_signal_handlers` if your application handles SIGINT and SIGTERM itself, otherwise the client
replaces the handlers of the event loop to close the connection on exit. To connect with `bleak-retry-connector`
(Bluetooth proxies), create the transport yourself: `BleakTransport(address_or_device, on_disconnected, connector=...)`
where the connector is an async function that returns a connected `BleakClient`, like `establish_connection`.

`ConnectionManager.set_device(ble_device)` hands over a newer `BLEDevice` later. An established connection stays, the
new one is used for the next connection. A `Transport` has to write to the device, deliver its notifications and call
`on_disconnected` when the link is lost, see `idotmatrix/transport.py` and the `FakeTransport` in `tests/` for an example.

### Digital Picture Frame

Besides the `IDotMatrixClient`, this repository also contains a `DigitalPictureFrame` class which can be used
to display images and GIFs in a slideshow fashion.
See [example_digital_picture_frame.py](./example_digital_picture_frame.py)
for more details on how to use it.

The `DigitalPictureFrame` can

* display a static list of images and/or GIFs
* watch one or more directories for images and GIFs
* automatically reconnect to the device in case of an error or connection loss

### Terminal UI

![The terminal UI: the files of a folder, the preview as it looks on the display and the details](docs/images/tui.png)

A terminal UI to browse a folder, see what a picture or animation will look like on the display (with your color,
size and label options, and how long the upload takes) and send it:

```shell
pip install 'idotmatrix-api-client[tui]'
idotmatrix-tui /path/to/pictures
```

It works without any argument: it connects to the display it used last, and opens the list of displays (`d`) if there is
none or it cannot connect. The list searches while it is open and shows every display it knows with its state
(connected, online with the signal strength, offline); Enter connects, `a` takes an address, `f` forgets a display.
`--address AA:BB:CC:DD:EE:FF` connects to that one, `--choose` opens the list at the start.

`Enter` shows the file on the display, `Space` marks files and `s` stores the marked ones (or the whole folder) in the
slots of the display, which then cycles through them on its own. `o` sets the colors (auto), the largest GIF, the
scale and a label, `b` the brightness, `c` shows the clock, `x` clears the slots, `/` filters, `Esc` cancels an upload
and `:` lists all commands (and the themes). The folder, the displays, the options and the theme are remembered
(`~/.config/idotmatrix-tui/session.json`).

The pages are switched with `F1` (files), `F2` and `F3`. `F2` has the controls of the display, one form per feature:
clock (style, date, 12/24 hours, color), text, a color, effects, the screen (brightness, rotation, on/off), countdown,
stopwatch, scoreboard, eco mode, music mode and the device (time, info, reset). The values you enter are remembered.
`F3` is a pixel editor for the DIY mode: the arrows move, `Space` paints, `Enter` puts the pen down (moving paints),
`f` fills, `l` and `b` draw lines and boxes, `1` to `0` pick a color (`c` takes any), `u` and `y` undo and redo, `a`
toggles sending every change to the display at once, `s` sends everything, `v` shows the drawing as a picture, `o` opens
and `w` saves a picture. The mouse paints too (left, right erases, middle picks). The drawing is kept between runs.
`o` on the first page sets how pictures are processed and sent: colors, the largest GIF, scale, PNG or raw RGB, the
palette, one palette for all frames, the color error, and the background.

The preview draws real pixels, exactly square and sharp, in terminals that support the Kitty graphics protocol or
Sixel (kitty, WezTerm, foot, Ghostty, iTerm2, ...). Elsewhere it uses half blocks, which are only exact if a cell is
twice as high as wide. A warning under the preview says when it is too small to show every pixel.
`IDOTMATRIX_TUI_PIXELS=off` always uses half blocks, `IDOTMATRIX_TUI_CELL_ASPECT` (cell height / width) tells the half
block preview the shape of your cells if the terminal does not report it.

## Fonts

`text.display_text()` (and `TextModule.show_text()`) rasterize each character directly to on/off
pixels (1-bit, no anti-aliasing) and send it to the device using one of two fixed per-character
cell sizes:

* a compact **8x16** cell, used automatically whenever every character of the string fits within
  8px wide / 16px tall
* the full **16x32** cell, used as a fallback for wider/taller glyphs (to avoid clipping)

Because there's no anti-aliasing step, regular vector fonts (the kind designed for print/screen
text with serifs, thin strokes, or fine curves) often render with broken strokes, gaps, or lopsided
shapes at these tiny sizes - especially once a font's fine details get thresholded straight to
black/white. This shows up as visual "artifacts": jagged edges, disconnected letterforms, or an
uneven look between different characters of the same font.

**Pixel/bitmap-style fonts** avoid this problem entirely, since they are designed on a fixed pixel
grid to begin with (no fine detail to lose) and render cleanly at any size that's a clean multiple
of their native grid.

### `font_size` doesn't grow the per-character cell

The 8x16/16x32 cell picked above is **fixed in pixel width** (8px or 16px) regardless of the
`font_size` you pass in - `font_size` only changes how big the glyph is drawn *within* that fixed
cell, it never widens the cell itself. Each character's cell bitmap is then sent back-to-back with
no extra spacing added between characters.

This means a font that isn't specifically designed to stay narrow at the `font_size` you're using
will render a glyph that fills (or even overflows) the entire 8px/16px cell width, leaving no blank
margin to act as letter-spacing - so consecutive characters end up touching or overlapping. This is
why the same font can look perfectly fine at one `font_size` and become illegible at a larger one:
a font's glyph width generally scales with `font_size`, but the cell width doesn't.

The bundled default (`Rain-DRM3.otf`) works around this by being intentionally narrow relative to
its point size, so it still leaves a gap even at larger sizes. Most other fonts need a specific,
manually-verified `font_size` to look right - see the naming convention below.

### Bundled fonts

The [`idotmatrix/fonts/`](idotmatrix/fonts/) directory is part of the installed package and ships a selection of pixel/bitmap fonts (with their respective
license files) that have been verified to render cleanly. Each filename (other than the default) is
prefixed with the `font_size` value(s) it has been manually tested and confirmed to render with
legible spacing between characters - always pass a matching `font_size`, since (per above) using a
larger one than the font was designed for will make characters touch/overlap:

| Font file(s) | Recommended `font_size` | Notes |
| --- | --- | --- |
| `16-PressStart2P-Regular.ttf` | 16 | Classic 8x8 arcade-style pixel font. Most reliable default at size 16. |
| `16-dogica.ttf`, `16-dogicabold.ttf`, `16-dogicapixel.ttf`, `16-dogicapixelbold.ttf` | 16 | Small pixel-grid font family, regular/bold/"pixel" variants. |
| `16-PixelOperator8.ttf`, `16-PixelOperator8-Bold.ttf` | 16 | 8px-grid pixel font family. |
| `16-MinecraftStandard.otf`, `16-MinecraftStandardBoldOblique.otf` | 16 | Blocky pixel-grid font, good legibility at small sizes. |
| `16-ErbosDraco1StOpenNbpRegular-l5wX.ttf` | 16 | Narrow pixel-style font (fits the compact 8x16 cell at size 16). |
| `16-PixelifySans-Regular.ttf` | 16 | Rounded pixel-grid font. |
| `16_32-HomeVideo-BLG6G.ttf`, `16_32-HomeVideoBold-R90Dv.ttf` | 16 or 32 | Wider retro/VHS-style font, verified to keep readable spacing at both sizes. |
| `16_32-MayfairNbpBold-gAA4.ttf` | 16 or 32 | Bold pixel-style display font, verified to keep readable spacing at both sizes. |
| `32-Jersey10-Regular.ttf` | 32 | Retro digital/LCD-style font, verified at size 32. |
| `Rain-DRM3.otf` | any | Default font, used when no `font_path` is given. Narrow enough to stay legible across sizes. |

Pick whichever fits your desired look, but stick to the recommended `font_size`(s) listed above (or
your own tested size) for that font - otherwise characters may run into each other. Narrower fonts
(that fit within 8px wide per character at the size used) will also get tighter, more compact text
since they qualify for the 8x16 cell instead of the 16x32 one.

### Font licenses

Each font keeps its own license, shipped next to it in `idotmatrix/fonts/`. They do not change the
license of this library's code.

| Font(s) | License |
| --- | --- |
| Rain-DRM3, Dogica, Press Start 2P, Pixelify Sans, Jersey 10 | [SIL Open Font License 1.1](https://openfontlicense.org) |
| Pixel Operator | CC0 1.0 |
| Home Video, Minecraft Standard | Public Domain |
| Erbos Draco 1st Open NBP ([source](https://www.fontspace.com/erbos-draco-monospaced-nbp-font-f14579)) | [CC BY-SA](idotmatrix/fonts/CC-BY-SA-4.0-License.txt) |
| Mayfair NBP Bold ([source](https://www.fontspace.com/mayfair-nbp-font-f15853)) | [CC BY-SA](idotmatrix/fonts/CC-BY-SA-4.0-License.txt) |

The two CC BY-SA fonts are redistributed unmodified. Copies of derived fonts must be shared under the
same license, with attribution to the original authors (see the links above).

### Finding more fonts

When looking for additional fonts, search for:

* `pixel font` / `bitmap font`
* `8x8 font`, `5x7 font`, `dot matrix font`
* `LED font` / `LCD font`
* `retro pixel font` / `monospace pixel font`

Good sources: [dafont.com/bitmap.php](https://www.dafont.com/bitmap.php),
[fontspace.com's pixel-fonts tag](https://www.fontspace.com/pixel-fonts)

Always test a new font at the font size you intend to use before committing to it - some
pixel-style fonts are only pixel-perfect at their native design size and look uneven at others.
Check each font's license before bundling/redistributing it (see the existing `*-License.txt`
files next to each font in [`idotmatrix/fonts/`](idotmatrix/fonts/) for examples).

## Helpful Links

* Create Images or GIFs
  * [pixilart](https://www.pixilart.com/draw)
    * Create a new drawing and select a preset for the size of your display (e.g. 64x64)

## Other Hardware
This software is specifically built for devices which are supported by the iDotMatrix app. There are other devices
being sold which have a similar form factor and claim to be compatible, but which are not.  Below is a list of known
non-iDotMatrix-compatible hardware and associated software.
- For hardware supported by the "LOY SPACE" app: https://github.com/eskibars/popledder/

## Contributing

GitHub is for social coding: if you want to write code, I encourage contributions through pull requests from forks
of this repository. Create GitHub tickets for bugs and new features and comment on the ones that you are interested in.

## License

Distributed under the GNU GENERAL PUBLIC License.
See [LICENSE](https://github.com/markusressel/idotmatrix-api-client/blob/main/LICENSE) for more information.

## Differences From The Original Project

This is a fork of [derkalle4/python3-idotmatrix-library](https://github.com/derkalle4/python3-idotmatrix-library),
which is no longer maintained. The fork continues its development and maintenance.

The API is not compatible with the original: the structure was reworked for usability and maintainability, so code
written for the original needs some adjustments to run with this library. Returning the raw bytearray data of commands
was dropped to keep the library simple.

## Acknowledgements

Original project by [derkalle4](https://github.com/derkalle4) and [jmgraeffe](https://github.com/jmgraeffe).

* [Othneil Drew](https://github.com/othneildrew/Best-README-Template) - *README Template*
* [LordRippon](https://github.com/LordRippon) - *Reverse Engineering for the Displays*
* [8none1](https://github.com/8none1) - *Reverse Engineering for the Displays*
* [schorsch3000](https://github.com/schorsch3000) - *smaller fixes*
* [tekka007](https://github.com/tekka007) - *code refactoring and reverse engineering*
* [inselberg](https://github.com/inselberg) - *Reverse Engineering for the Displays*
