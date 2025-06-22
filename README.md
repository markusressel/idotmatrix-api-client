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
pip -m venv venv
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
  # create a new IDotMatrixClient instance with the screen size of your device
  client = IDotMatrixClient(
    screen_size=ScreenSize.SIZE_64x64
  )
  # (optional) connect to first found iDotMatrix Pixel Display
  # If the device is not connected when issuing commands, an automatic connection attempt will be made.
  await client.connect()

  # do something with the device by using one of the toplevel functions or modules e.g. chronograph, clock, countdown, etc.
  await client.set_brightness(50)  # set brightness to 50%

  await client.text.display_text("Hello World!")  # display text on the screen


if __name__ == "__main__":
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    quit()
```

For more examples please check the [example.py](./example.py).

### Digital Picture Frame

Besides the `IDotMatrixClient`, this repository also contains a `DigitalPictureFrame` class which can be used
to display images and GIFs in a slideshow fashion. See [digital_picture_frame.py](./idotmatrix/digital_picture_frame.py)
for more details on how to use it.

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
    * [ ] MusicSync
    * [X] Scoreboard
    * [ ] bluetooth password protection
    * [ ] understand the returned byte arrays of the device for better error logs

## Helpful Links

* Create Images or GIFs
  * [pixilart](https://www.pixilart.com/draw)
    * Create a new drawing and select a preset for the size of your display (e.g. 64x64)

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
