> [!NOTE]  
> This is a fork of the original
> project [derkalle4/python3-idotmatrix-library](https://github.com/derkalle4/python3-idotmatrix-library) which is no
> longer maintained due to the
> author's health condition. This fork aims to continue the development and maintenance of the library, ensuring it
> remains functional and up-to-date for users who rely on it for
> controlling iDotMatrix pixel displays.

> [!CAUTION]
> **Not compatible with the original project!**  
> While the featureset should be identical (or better), the structure of the original project has been significantly
> altered to improve usability and maintainability. This means it is not possible to switch between the original and
> this fork without manually adjusting the code.
>
> In addition to that, the support for returning the raw bytearray data for specific commands **has been dropped**
> to simplify maintenance and usability of the library.

<br/>
<p align="center">
  <a href="https://github.com/derkamarkusressel/python3-idotmatrix-library">
    <img src="images/logo.png" alt="Logo" width="250" height="250">
  </a>

<h3 align="center">Pixel Display Library</h3>

  <p align="center">
    Control all your 16x16 or 32x32 or 64x64 iDotMatrix Pixel Displays
    <br/>
    <br/>
    <a href="https://github.com/markusressel/python3-idotmatrix-library/issues">Report Bug</a>
    or
    <a href="https://github.com/markusressel/python3-idotmatrix-library/issues">Request Feature</a>
  </p>
</p>

![Contributors](https://img.shields.io/github/contributors/markusressel/python3-idotmatrix-library?color=dark-green) ![License](https://img.shields.io/github/license/markusressel/python3-idotmatrix-library)

## Table Of Contents

* [About the Project](#about-the-project)
* [Getting Started](#getting-started)
  * [Prerequisites](#prerequisites)
  * [Installation](#installation)
* [Usage](#usage)
* [Fonts](#fonts)
* [Roadmap](#roadmap)
* [Contributing](#contributing)
* [License](#license)
* [Authors](#authors)
* [Acknowledgements](#acknowledgements)

## About The Project

This repository aims to reverse engineer
the [iDotMatrix](https://play.google.com/store/apps/details?id=com.tech.idotmatrix&pli=1) Android App for pixel screen
displays like [this one on Aliexpress](https://de.aliexpress.com/item/1005006105517779.html). The goal is to provide a
library which can be used to
connect and control these displays without the need for the official app.

## Getting Started

### Prerequisites

Please install the following for your distribution (Windows may work but it is untested):

* latest Python3
* Python3 Virtual Env

### Installation

#### use latest github source code

1. Clone the repo

```sh
git clone https://github.com/markusressel/python3-idotmatrix-library.git
```

2. Install the latest version locally

```sh
cd python3-idotmatrix-library/
python3 -m venv venv
source venv/bin/activate  # on Windows use `venv\Scripts\activate`
pip install --upgrade pip poetry
poetry install
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

## Roadmap

If you want to contribute please focus on the reverse-engineering part because my personal skills are not that good.
Many thanks for all contributions! If you want to dive deep
into other issues please check for "#TODO" comments in the source code as well.

* [ ] Reverse Engineering
    * [X] Chronograph
    * [X] Clock
    * [X] Countdown
    * [x] Graffiti Board
    * [X] DIY-Mode
    * [X] Animated Images
    * [X] Display Text
    * [ ] Alarm & Buzzer (available according to issue #18)
    * [ ] Cloud-API to download images
    * [ ] Cloud-API to upload images to device
    * [ ] Cloud-Firmware Update possible?
    * [X] Eco-Mode
    * [X] Fullscreen Color
    * [X] MusicSync (with the microphone of the device)
    * [X] Scoreboard
    * [ ] bluetooth password protection
    * [ ] understand the returned byte arrays of the device for better error logs (done for the upload acknowledgements,
      see the protocol notes in [AGENTS.md](./AGENTS.md))

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

Contributions are what make the open source community such an amazing place to be learn, inspire, and create. Any
contributions you make are **greatly appreciated**.

* If you have suggestions for adding or removing projects, feel free
  to [open an issue](https://github.com/markusressel/python3-idotmatrix-library/issues/new) to discuss it, or
  directly create a pull request after you edit the *README.md* file with necessary changes.
* Please make sure you check your spelling and grammar.
* Create individual PR for each suggestion.
* Please also read through
  the [Code Of Conduct](https://github.com/markusressel/python3-idotmatrix-library/blob/main/CODE_OF_CONDUCT.md) before
  posting your first idea as well.

### Creating A Pull Request

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

Distributed under the GNU GENERAL PUBLIC License.
See [LICENSE](https://github.com/markusressel/python3-idotmatrix-library/blob/main/LICENSE) for more information.

## Acknowledgements

Original project by [derkalle4](https://github.com/derkalle4) and [jmgraeffe](https://github.com/jmgraeffe).

* [Othneil Drew](https://github.com/othneildrew/Best-README-Template) - *README Template*
* [LordRippon](https://github.com/LordRippon) - *Reverse Engineering for the Displays*
* [8none1](https://github.com/8none1) - *Reverse Engineering for the Displays*
* [schorsch3000](https://github.com/schorsch3000) - *smaller fixes*
* [tekka007](https://github.com/tekka007) - *code refactoring and reverse engineering*
* [inselberg](https://github.com/inselberg) - *Reverse Engineering for the Displays*
