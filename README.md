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

A library to control displays like the one below without the official
[iDotMatrix](https://play.google.com/store/apps/details?id=com.tech.idotmatrix&pli=1) app, based on its reverse engineered
Bluetooth protocol.

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

To work on the library, see the [development notes](docs/DEVELOPMENT.md).

## Usage

### Device API Client

The [examples](./examples) show how to connect to a device, show text, images and GIFs, and how to store files in the
slots of the device.

#### Home Assistant and other Bluetooth stacks

If something else owns the Bluetooth stack, like Home Assistant with its scanner and Bluetooth proxies, see the
[integration notes](docs/INTEGRATION.md).

### Digital Picture Frame

Besides the `IDotMatrixClient`, this repository also contains a `DigitalPictureFrame` class which can be used
to display images and GIFs in a slideshow fashion.
See [examples/example_digital_picture_frame.py](./examples/example_digital_picture_frame.py)
for more details on how to use it.

The `DigitalPictureFrame` can

* display a static list of images and/or GIFs
* watch one or more directories for images and GIFs
* automatically reconnect to the device in case of an error or connection loss

### Terminal UI

![The terminal UI: the files of a folder, the preview as it looks on the display and the details](docs/images/tui.png)

A terminal UI to browse a folder, preview how pictures and animations look on the display, send them, and control the
features of the display, with a pixel editor. Install it with the `tui` extra and run `idotmatrix-tui /path/to/pictures`,
see the [TUI notes](docs/TUI.md) for the keys and options.

## Fonts

Text is drawn in 1-bit cells without anti-aliasing, so pixel fonts work best. The package bundles a selection that was
tested at fixed `font_size` values. See the [font notes](docs/FONTS.md) for the sizes, licenses and how to add more.

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
