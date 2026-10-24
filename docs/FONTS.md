# Fonts

## How text is drawn

`text.show_text()` rasterizes each character to on/off pixels (1-bit, no anti-aliasing) and sends it in one of two
fixed cell sizes:

* a compact **8x16** cell, used automatically when every character of the string fits into 8 px width and 16 px height
* the full **16x32** cell, the fallback for wider or taller glyphs

Regular vector fonts (serifs, thin strokes, fine curves) break apart at these sizes: strokes get gaps and letters look
uneven. **Pixel or bitmap fonts** are designed on a pixel grid and render cleanly.

### `font_size` does not grow the cell

The cell is fixed at 8 or 16 px width, whatever `font_size` is. `font_size` only changes the size of the glyph inside
the cell, and the cells are sent back to back without spacing. A font whose glyphs fill or overflow the cell at the
chosen size has no gap between characters, so they touch or overlap. The same font can look fine at one size and be
illegible at a larger one, because the glyph width grows with `font_size` and the cell does not.

The default font (`Rain-DRM3.otf`) is narrow for its size and keeps a gap at larger sizes. Other fonts need a tested
`font_size`, which is why the bundled files carry it in their name.

## Bundled fonts

[`idotmatrix/fonts/`](../idotmatrix/fonts/) is part of the installed package. A file name starts with the
`font_size` the font was tested with (`16_32-` means both 16 and 32). Pass that size, or your own tested one. Narrow
fonts that fit 8 px per character also get the compact 8x16 cell and tighter text.

| Font file(s) | `font_size` | License | Notes |
| --- | --- | --- | --- |
| `16-PressStart2P-Regular.ttf` | 16 | [OFL 1.1](https://openfontlicense.org) | Classic 8x8 arcade font, the most reliable at 16 |
| `16-dogica.ttf`, `16-dogicabold.ttf`, `16-dogicapixel.ttf`, `16-dogicapixelbold.ttf` | 16 | OFL 1.1 | Small pixel font family |
| `16-PixelOperator8.ttf`, `16-PixelOperator8-Bold.ttf` | 16 | CC0 1.0 | 8 px grid |
| `16-MinecraftStandard.otf`, `16-MinecraftStandardBoldOblique.otf` | 16 | Public Domain | Blocky, legible when small |
| `16-ErbosDraco1StOpenNbpRegular-l5wX.ttf` | 16 | [CC BY-SA](../idotmatrix/fonts/CC-BY-SA-4.0-License.txt), [source](https://www.fontspace.com/erbos-draco-monospaced-nbp-font-f14579) | Narrow, fits the 8x16 cell |
| `16-PixelifySans-Regular.ttf` | 16 | OFL 1.1 | Rounded pixel grid |
| `16_32-HomeVideo-BLG6G.ttf`, `16_32-HomeVideoBold-R90Dv.ttf` | 16 or 32 | Public Domain | Wide retro/VHS style |
| `16_32-MayfairNbpBold-gAA4.ttf` | 16 or 32 | [CC BY-SA](../idotmatrix/fonts/CC-BY-SA-4.0-License.txt), [source](https://www.fontspace.com/mayfair-nbp-font-f15853) | Bold display font |
| `32-Jersey10-Regular.ttf` | 32 | OFL 1.1 | Digital/LCD style |
| `Rain-DRM3.otf` | any | OFL 1.1 | Default, used without `font_path` |

Every font keeps its own license file next to it in `idotmatrix/fonts/`. The licenses do not change the license of
this library's code. The two CC BY-SA fonts are redistributed unmodified; copies of derived fonts must be shared under
the same license, with attribution to the authors.

## Adding fonts

Search for `pixel font`, `bitmap font`, `8x8 font`, `5x7 font`, `dot matrix font`, `LED font` or `LCD font`. Good
sources are [dafont.com/bitmap.php](https://www.dafont.com/bitmap.php) and the
[pixel-fonts tag of fontspace.com](https://www.fontspace.com/pixel-fonts).

Test a new font at the size you plan to use: some are only pixel-perfect at their native size. Check its license before
bundling it, and ship the license file next to it (see the existing `*-License.txt` files).
