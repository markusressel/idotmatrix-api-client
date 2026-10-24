# Examples

The scripts in this folder talk to a real device. Run them from the root of the repository, f.e.
`python examples/example.py`.

* [example.py](example.py): connect, show text, upload a GIF and an image
* [example_digital_picture_frame.py](example_digital_picture_frame.py): slideshow of a folder
* [example_effect.py](example_effect.py): show an effect
* [example_rainbow_light.py](example_rainbow_light.py): animate a full screen color
* [example_markus.py](example_markus.py): text, effects and single pixels, with the author's own files and paths

## Getting started with the client

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

## Images and GIFs

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
