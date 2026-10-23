# iDotMatrix device protocol

Everything we know about how the iDotMatrix BLE displays work. This document is the place for findings, so that they
are not lost in commit messages or chat logs. **Update it whenever you learn something new or find that something here
is wrong**, and say how sure you are (see the legend).

## Legend and sources

| Mark | Meaning |
|---|---|
| **verified** | Tried on a real device, with the result described |
| **app** | Read in the decompiled official Android app (`com.tech.idotmatrix`), not tried on a device |
| **claim** | Said by a third party (see "Third-party sources"), not checked by us |
| **guess** | Our interpretation of an observation |

Devices used so far: a 64x64 panel on Linux/BlueZ (verified), a 32x32 panel on macOS Catalina (issue #11, reported by
its owner).

## Bluetooth basics

- Devices advertise as `IDM-<6 hex characters>`, no pairing is needed. (**verified**)
- Service `000000fa-0000-1000-8000-00805f9b34fb` is used for everything we do:
  - `fa02` accepts commands, as write or write-without-response.
  - `fa03` only supports notifications. Reading it always fails with `READ_NOT_PERMITTED`; the library used to read it
    after every write for that reason, which only produced errors. (**verified**)
- Service `0000ae00-...` (`ae01` write-without-response, `ae02` notify) is the firmware update (OTA) channel of the
  Jieli Bluetooth chip, encrypted. (**claim**, plausible because the app references the Jieli OTA SDK)
- The size of a write-without-response depends on the negotiated MTU: 514 bytes on the 64x64 under BlueZ (20 before the
  MTU exchange completed), 101 on macOS Catalina (MTU 104). Writes above the limit are silently truncated by the OS.
  `ConnectionManager` detects the limit on every connect and splits the writes accordingly. (**verified**)
- The ATT MTU is not part of the protocol: the device reassembles the byte stream, so the size of the BLE writes can
  be chosen freely. (**verified**)

## Commands

A command is a byte string `[length, 0, command, subcommand, ...arguments]`. The implemented ones are in
`idotmatrix/modules/`, each module documents the source of its bytes. Writes are always sent to `fa02`.

Known quirks:

- `reset()` writes `04 00 03 80` and `05 00 04 80 50`. The display goes back to its defaults and replays the boot
  animation. (**verified**) The boot beep is said to be the only way to make the device beep. (**claim**)
- Brightness below 5 % is not accepted. (**claim**)
- The device does not resize anything it is sent. Data for a larger screen is cropped to the top-left corner, so
  the host has to scale to the exact screen size. (**verified**)

## Acknowledgements on `fa03`

### During uploads (**verified** on the 64x64)

Each 4096 byte chunk of an image or GIF upload is answered with a notification `05 00 <type> 00 <status>`:

| Type | Upload | `status` |
|---|---|---|
| `00` | DIY image | `02` = send the next chunk, `01` (or `00`) = finished |
| `01` | GIF | `01` = send the next chunk, `03` = finished, `00` = rejected (see below) |
| `02` | static image | like GIF (**app**) |

Rules:

- The next chunk must not be sent before the acknowledgement of the previous one. The official app does the same
  (it also paces the BLE writes 20 ms apart and gives up after 5 s without an answer, counted from the first write of
  the chunk; any notification stops that timer). If chunks are sent too early,
  the device answers `status 00`, drops data, and the animation stutters, loses frames or never changes. In the app,
  `02` for a GIF means "not enough space" (**app**). `00` is the "not ready" answer we saw in practice.
- The last chunk is answered with "finished". If the device already has the exact same data (probably compared by the
  CRC), it answers "finished" to the first chunk and skips the rest. Uploading the same GIF twice therefore takes well
  under a second. (**verified**)
- The app writes the 509 byte BLE packets of a chunk 20 ms apart, and with response (Android's default write type;
  nothing in the app sets write-without-response). We used to write all but the last packet of a chunk back-to-back
  without response. Pacing them 20 ms apart (0.2.2) did not help behind an ESPHome Bluetooth proxy: in a debug log the
  device acknowledged chunk 1 of a GIF only 3.4 s after the last write (normally milliseconds), never acknowledged
  chunk 2 and rebooted. The same file went through without problems from a PC with BlueZ (132 image and 40 GIF
  uploads). A proxy takes write-without-response packets without real flow control, so packets get lost and the
  firmware chokes on the gap (**guess**, based on one log). Uploads now write every packet with response like the app,
  which the device answers one by one, and do not need the pause anymore. Writes without response (only when
  `response=False` is asked for) are still paced.
- Implemented in `ConnectionManager.send_packets(wait_for_ack=True)` and `util/upload_ack.py`. A device that does
  not answer leads to an `UploadError` after 5 s.

### For other commands (**verified** on the 64x64)

Most commands are answered within a few milliseconds with `05 00 <command> <subcommand> <status>`, where the status
is `01` if the command was accepted and `00` if the device rejected its arguments. The device accepts a command whose
arguments are out of range silently, the acknowledgement is the only way to notice.

| Command | Sent | Acknowledgement |
|---|---|---|
| brightness 50 | `05 00 04 80 32` | `05 00 04 80 01` |
| brightness 200 or 0 (invalid) | `05 00 04 80 c8` | `05 00 04 80 00` |
| flip | `05 00 06 80 00` | `05 00 06 80 01` |
| clock | `08 00 06 01 ...` | `05 00 06 01 01` |
| clock with style 99 (invalid) | `08 00 06 01 63 ...` | `05 00 06 01 00` |
| fullscreen color | `07 00 02 02 ...` | `05 00 02 02 01` |
| effect | `... 03 02 ...` | `05 00 03 02 01` |
| countdown | `07 00 08 80 ...` | `05 00 08 80 01` |
| chronograph | `05 00 09 80 ...` | `05 00 09 80 01` |
| scoreboard | `08 00 0a 80 ...` | `05 00 0a 80 01` |
| microphone mode | `06 00 0b 80 ...` | `05 00 0b 80 01` |
| screen on | `05 00 07 01 01` | `05 00 07 01 01` |
| freeze (it toggles) | `04 00 03 00` | `05 00 03 00 00`, then `05 00 03 00 01` for the second call (**guess**: the new state) |
| text | upload | `05 00 03 00 03` (the upload acknowledgement, type 3 finished) |
| set time | `0b 00 01 80 ...` | `09 00 01 80 05 09 01 04 00`, the device info, see below |
| countdown off after the countdown has ended | `07 00 08 80 00 ...` | `05 00 04 80 01` once, the acknowledgement of a brightness command (**guess**: the device restores the brightness when a countdown ends). Stopping a running countdown is acknowledged normally, `05 00 08 80 01` |

No acknowledgement came for `set_speed`, `set_joint`, an unknown command (`05 00 63 80 01`) and a command whose length
byte does not match (`09 00 04 80 32`). Knocking on the display or other events do not produce notifications either.

`send_bytes` waits for the acknowledgement of commands that are known to be acknowledged (the list is
`ACKNOWLEDGED_COMMANDS` in `util/command_ack.py`, matched by command and subcommand, other notifications are skipped) and
raises `CommandRejectedError` for status `00`. A missing acknowledgement is only logged. `wait_for_ack=True/False`
forces or disables it. The list holds the commands that were verified: brightness, flip, screen on and off, clock,
fullscreen color, effects, countdown, chronograph, scoreboard and the microphone mode. These take 25-45 ms on the 64x64
(the clock 125 ms), and the modules skip the 0.5 s pause they used to make after a command. `set_speed` and
`set_joint` are never acknowledged, freeze, text and `set_time` are answered differently, so they are not in the list.
Add a command to the list once its acknowledgement was verified on a device.

### Device info (reply to set time)

The device answers the set time command (`0b 00 01 80 ...`) with `09 00 01 80 <major> <minor> <?> <type> <password>`.
The official app reads it right after connecting (`MainActivity`, **app**), the library as `CommonModule.get_device_info`.
On the 64x64 it is `09 00 01 80 05 09 01 04 00`:

| Byte | Example | Meaning |
|---|---|---|
| 4, 5 | `05 09` | firmware version 5.09 (**app**, **verified** that it is the same for every call) |
| 6 | `01` | "switch status", the app treats 0 as off and anything else as on, and updates a switch with it. It does **not** follow the screen: it stayed `01` while the screen was off (**verified**). Meaning unknown |
| 7 | `04` | screen type: 1 = 16x16, 2 = 8x32, 3 = 32x32, 4 = 64x64 (**verified**), 11 = 16x64 (**app**). The app uses it to choose the screen size, types containing an 8 in hex (splicing displays) open a dialog |
| 8 | `00` | password flag, 1 = the device is protected (**app**) |

The reply was identical with the screen on and off, and for repeated calls (**verified**).

A protected device is unlocked with `07 00 05 02 <p1> <p2> <p3>` (the password as three two-digit numbers), answered
with `05 00 05 02 01` if the password was right (**app**, not tried). The app does this when the password flag is set.

### Heartbeat

`ConnectionManager.set_heartbeat(seconds)` detects a link that died silently. After the device has been silent for the
given time it is sent `05 00 04 80 ff`, a brightness that is out of range. The device rejects it with `05 00 04 80 00`
and changes nothing (**verified**: the display stayed dimmed through values 200, 255, 0 and 101), which is all that is
needed to know that it is alive. Any notification also counts. Without an answer within 3 s the link is closed and
restored by the reconnect logic. Verified on the 64x64 with the power cut: BlueZ reported the lost connection itself
after about 5 s, so the heartbeat's own detection was not needed there, and the reconnect worked once the device had power
again. Where the Bluetooth stack takes long to notice a vanished device the heartbeat is the faster way.

A third party reports the upload acknowledgements of a 32x32 as `01 00 03 00 01` and `01 00 03 00 03`, which
does not match the 64x64 or the app. (**claim**, probably a transcription error, to be checked on a 32x32)

## Image and GIF uploads

All uploads split the data into chunks of at most 4096 bytes, put a header in front of each and then split the result
into BLE writes. All numbers are little endian unless noted.

### Header of GIF (type 1) and static image (type 2) uploads, 16 bytes (**app**, GIF **verified**)

| Byte | Content |
|---|---|
| 0-1 | size of this chunk including the header |
| 2 | type: 1 = GIF, 2 = static image |
| 3 | 0 |
| 4 | 0 for the first chunk, 2 for the following |
| 5-8 | size of all data |
| 9-12 | CRC32 of all data |
| 13-14 | display time of the item in a cycle of stored items, little endian, see below |
| 15 | index |

The index selects where the item goes: 0 to 11 are slots the device keeps and cycles through (**app**, the app calls
them "device materials"), 13 shows the item right away, 12 is the one the app uses for text. The official app uses 13
for showing a photo or GIF, and so do we. The display time is the time the item stays on screen in a cycle of stored
items; the app takes it from a setting (default 5 s). We sent the value big endian until 0.2.3, which the device
read as 1280: items in slots 1 to 3 changed in under a second. With the bytes in the order of the app (little endian,
`1e 00` for 30 s) items in slots 4 to 6 stayed on screen for about 30 s while the old ones still flashed by.
(**verified** on a 64x64, by eye; the unit is probably seconds, 5, 10, 30, 60 and 300 are the app's options.)
Whether the value matters for index 13 (show now) is not known (**guess**: no).

### Header of DIY image uploads (type 0), 9 bytes (**verified**)

`[size(2), 0, 0, first/continue(1), total size(4)]` followed by raw RGB data, 3 bytes per pixel, row by row. Used by
the drawing mode of the app. The DIY mode has to be entered first (`05 00 04 01 01`) and left again
(`05 00 04 01 00`) before other content can be shown. (**verified**)

### Photos

The official app shows photos with a static image upload (type 2, index 13) containing raw RGB, no mode switch needed.
(**verified**: photos and GIFs can follow each other freely without delays) `ImageModule.show_image_file` does this.

### PNG payload

The data of a static image (type 2) and of a DIY image (type 0) can also be a PNG file instead of raw RGB, the device
decodes it. The header is the same, the length and CRC32 refer to the PNG bytes. (**verified** on a 64x64 for RGB and
palette PNGs; the original Python library and the Homey app do this for DIY images, the official app sends raw RGB.)
Not tested on 16x16 and 32x32 devices. `show_image_file(png=True)` does this, and it is the default since a raw upload
leaves a stray dark red pixel at the second LED of the first row on a 64x64 (**verified**: on black and gray images and
on photos, with any header time or index, with a single chunk or several; a PNG of the same picture, DIY mode and GIFs
do not do it; the app sends raw RGB with the same header, so it probably shows it too: **guess**). The pixel is drawn by
the device, the data has the right color there.

Measured on a 64x64 (raw RGB is 12288 bytes, 3 chunks): photos shrink to 6.6-10 KB as RGB PNG and 4.6-4.8 KB as palette
PNG, pixel-art to 4.7 KB / 1.8 KB. Upload time dropped from 0.8-1.1 s (raw) to 0.7-0.85 s (RGB PNG) and 0.5-0.6 s
(palette PNG), so the gain is small: the time is mostly one acknowledgement round trip per 4096 byte chunk, and PNG only
saves chunks when it crosses a chunk boundary. RGB PNGs are lossless, palette PNGs lose colors beyond 256. Nobody could
see a difference on the display. (**verified**)

Do not use the DIY mode for slideshows. Switching between DIY and GIFs needed `DisableDIY`, a black screen and `reset()`
in between, a GIF that started right after the reset was rejected (`status 00`), the device briefly showed its default
rainbow effect, and once it rebooted. (**verified**)

### GIFs

- All frames need color tables of the same size. PIL writes tables that are only as large as the number of colors a
  frame uses, so they differ in size from frame to frame. The device then garbles or drops frames: a GIF with a flat
  background showed frame 1 and 11 of 12, another one played 6 of its 12 frames, a third stuttered. With all tables
  padded to 256 entries all of them played completely and smoothly. (**verified**, `image_utils.pad_palette`)
- Frames have to be written without optimization, or PIL trims the tables again. Frames are full size, disposal
  method 2. (**verified**)
- The official app sends a GIF file unchanged: all frames, the delay of every frame, no limit on frames, duration or
  size that I could find in the decompiled code (`GifAgreement.sendImageData`, `MyMaterialActivity`). Only the
  app's own animation editor writes GIFs (`GIFUtils.makeGif2`), with one delay for all frames. (**app**)
- The device plays 128 frames (184 KB) and 336 frames (564 KB, an 11 s loop, uploaded in 66 s) at the original speed
  without errors, and it honors the delay of every frame: a test animation with delays alternating 100 and 400 ms
  stepped unevenly, one with 250 ms evenly. (**verified**) The library used to cut a GIF to 64 frames and 2 s per
  loop by dropping frames and keeping the delay, which played long animations up to 8 times too fast: that limit
  was only meant to shorten uploads and is gone, `max_size_kb` does that now.
- Large GIFs (60+ frames, 50-70 KB) work, a 70 KB upload takes about 5 s. (**verified**)
- Upload time on a local BlueZ adapter, 64x64, 3 to 125 KB: about 0.1 to 0.15 s per KB, so 120 KB takes 12 to 14 s and
  25 KB about 3 s. (**verified**)
- What to give up for `max_size_kb`, rated by eye on two 64x64 animations (120 KB, 63 and 51 frames): keeping every 2nd
  frame (half the size, same duration) looks as good as all frames, one of them looked less "nervous". Every 3rd frame
  looks like slow motion, every 4th to 6th very much so, but it is acceptable when size matters most. Fewer colors
  than `colors="auto"` chose (32 instead of 64 or 128) already looked clearly worse, so frames go first.
  (**verified**, by eye)

### Storage

- The device has 12 slots (0 to 11, the index byte of the upload header). Items uploaded into a slot stay on the device,
  also over a power cycle (**guess**, not tried), and the device cycles through the stored items by itself, in the order
  of the slots, each for the display time of its header. No Bluetooth traffic is needed for that. (**verified** on a
  64x64: GIFs and images in slots 1 to 6 cycled with 10 s and 30 s) The official app deletes the slots it is about to
  fill and then sends its items one after another (`DeviceMaterialChildFragment`). `MaterialsModule` does the same.
- Deleting slots: `<length> 00 02 01 <number of slots> <slot>...` (the length is 5 plus the number of slots, so
  `11 00 02 01 0c 00 01 02 03 04 05 06 07 08 09 0a 0b` for all of them), answered with `05 00 02 01 01`.
  (**verified**) Other slots are not touched.
- The device skips an upload of an item it already holds: same data and same display time (a different display time
  is transferred in full). The check is not per slot: the same item sent to another slot is answered "finished" at
  the first chunk too (0.8 s instead of 2 to 10 s), and the device then has it in that slot as well (the item showed
  up twice in the cycle). With `show now` (index 13) that is only the last item. (**verified**)
- An upload into an occupied slot replaces what was in it, no delete needed. (**verified**) So `MaterialsModule.store`
  does not delete the slots it fills (as the app does): unchanged items cost 0.8 s, and reordering is cheap.
- We never got a "no space" answer. The rejections we saw were all status `00` ("not ready"). The size of the storage
  is not known, the app does not ask for it. (**verified**)

## Text

The device has no fonts: the host draws every character with PIL and sends bitmaps. (**verified**)

Packet: a 16 byte header (total length at 0-1, payload length at 5-8, CRC32 at 9-12), 14 bytes of metadata (number of
characters (2), `00`, `01`, mode, speed, color mode, RGB, background mode, background RGB), then one bitmap per character.

The speed is a percentage: the slider of the app goes from 5 to 100 (`activity_text.xml`: `android:min="5"`,
`android:max="100"`, shown as `n%`) and `TextAgreement` sends its value as it is. The device was not tried with other
values, and which direction is faster is not verified (the percentage suggests: higher is faster). (**app**)

Two cell sizes exist, chosen for the whole string:

| Cell | Separator | Bitmap | Per character |
|---|---|---|---|
| compact 8x16 | `02 ff ff ff` | 16 bytes | 20 bytes |
| full 16x32 | `05 ff ff ff` | 64 bytes | 68 bytes |

The number of characters in the metadata must be the real number of characters. Counting separators found 0 in compact
mode because the bytes of a bitmap can contain anything, and the device then showed 4 characters of "Hello 123".
(**verified**)

## Music sync

Two different mechanisms exist in the official app.

1. **Microphone of the device** (**verified** on the 64x64): `06 00 0b 80 <mode> <sensitivity>` with the mode starting
   at 1 and the sensitivity from 0 to 100 (the app default is 50). The device then reacts to sound and knocks on its
   own, no audio is sent. Modes 1 to 5 each show a different scene (a figure, a heart, two frog-like faces, ...).
   `MusicSyncModule.set_mic_type` sends it. The library used to send it without the sensitivity and with a wrong length
   byte, which is why it never worked.
2. **Microphone of the phone** (**app**): the app records sound, and about every 60 ms it sends the device the
   loudness as `06 00 00 02 <level 1-7> <variant>` (the "image" scenes), or an array of 28 frequency levels for the
   bar scenes (`VisualizerUtil.getSendWave`). Sent once, `06 00 00 02 <level> 01` just shows a still frame of the animation
   (**verified**: 1 shows a sitting figure, 2 a frog-like face). `send_image_rythm` sends one such packet. The bar scenes are
   not implemented.

Effect styles (looked at on a 64x64): `GRADIENT_HORIZONTAL_RAINBOW` (0) draws smooth horizontal stripes that move down,
`VERTICAL_RAINBOW` (3) hard vertical stripes (4 pixels wide) that move to the right, `DIAGONAL_RIGHT_RAINBOW` (4) hard stripes without
blending from the bottom left to the top right. (**verified**) The names of the members are fine. The other styles
were not looked at.

There is no command that leaves the music sync again: `06 00 00 02 00 00` (`stop_rythm`) had no effect. Showing
something else, f.e. the clock, does. (**verified**)

## Not understood yet

- `set_joint` (`05 00 0c 80 <mode>`), `set_mic_type` (`06 00 0b 80 <type>`): not used by the app.
- `get_device_location` needs an AES step that the app does in a native library (`csh.tiro.cc.aes`).
- The password flow: `set_password` exists (`08 00 04 02 01 <3 bytes>`). A protected device is unlocked with a verify
  command according to the app (see Device info), nobody tried it.
- Firmware update (OTA) over `ae00`: encrypted, not a goal for now.
- What byte 6 of the device info stands for, and whether any command produces other notifications.

## Third-party sources

- [fbnlrz/homeyidotmatrix](https://github.com/fbnlrz/homeyidotmatrix) (`docs/idm.md`, `docs/AE-SERVICE.md`): notes
  from a Homey integration, tested on a 32x32 and written with the help of an AI, so treat them as claims. Source of
  the acknowledgements for other commands, the music sync bytes, the buzzer remark and the OTA findings.
- [derkalle4/python3-idotmatrix-library](https://github.com/derkalle4/python3-idotmatrix-library) and
  [8none1/idotmatrix](https://github.com/8none1/idotmatrix): the origin of this library and further notes.
- The decompiled Android app (`com.tech.idotmatrix`): `ImageAgreement`, `GifAgreement` and `Agreement` contain the
  upload protocol.
