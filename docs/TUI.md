# Terminal UI

![The terminal UI: the files of a folder, the preview as it looks on the display and the details](images/tui.png)

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
