import asyncio
import binascii
import io
import logging
import struct
from enum import Enum
from os import PathLike
from typing import List, Tuple

from PIL import Image as PILImage, ImageOps

from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.modules import IDotMatrixModule
from idotmatrix.screensize import ScreenSize
from idotmatrix.util import image_utils, color_utils
from idotmatrix.util.device_material import (
    DEFAULT_DISPLAY_TIME_SECONDS, INDEX_SHOW_NOW, convert_display_time, validate_display_time, validate_slot,
)
from idotmatrix.util.image_utils import validate_colors

MTU_SIZE_IF_ENABLED = 509
MTU_SIZE_IF_DISABLED = 18
CHUNK_SIZE_4096 = 4096
HEADER_SIZE_STATIC_IMAGE = 16
TYPE_STATIC_IMAGE = 2


class ImageMode(Enum):
    """Enum for image modes."""
    DisableDIY = 0  # Disable DIY mode
    EnableDIY = 1  # Enable DIY mode
    Unknown2 = 2  # Unknown mode 2
    Unknown3 = 3  # Unknown mode 3


class ImageModule(IDotMatrixModule):
    logging = logging.getLogger(__name__)

    def __init__(
        self,
        connection_manager: ConnectionManager,
        screen_size: ScreenSize,
    ):
        super().__init__(connection_manager=connection_manager)
        self.screen_size = screen_size

    async def set_mode(
        self,
        mode: ImageMode | int = ImageMode.EnableDIY,
    ):
        """
        Enter the DIY draw mode of the iDotMatrix device.

        Args:
            mode (int): 0 = disable DIY, 1 = enable DIY, 2 = ?, 3 = ?. Defaults to 1.
        """
        if isinstance(mode, ImageMode):
            mode = mode.value

        data = bytearray([5, 0, 4, 1, mode % 256])
        await self._send_bytes(data=data, response=True)

    async def upload_image_file(
        self,
        file_path: PathLike | str,
        resize_mode: image_utils.ResizeMode = image_utils.ResizeMode.FIT,
        palletize: bool = False,
        background_color: Tuple[int, int, int] | int | str = (0, 0, 0),  # default to black background
    ) -> None:
        """
        Uploads a file processed and makes sure everything is correct before uploading to the device.

        Args:
            file_path (str): path-like object to the image file
            resize_mode (image_utils.ResizeMode): The mode to use for resizing the image (ResizeMode.FIT, ResizeMode.FILL, ResizeMode.STRETCH).
            palletize (bool): If True, the image will be converted to a palette-based image. Usually bad for images with
                high detail (like photos) but good for pixel-art or other content with high contrasts. Defaults to False.
            background_color (Tuple[int, int, int]): RGB color for the background, which is only visible if the input
                image doesn't match the devices aspect ratio. Defaults to black (0, 0, 0).
        """
        background_color = color_utils.parse_color_rgb(background_color)
        # reading and converting the file takes a while, the event loop must not be blocked
        pixel_data = await asyncio.to_thread(
            self._load_image_and_adapt_to_canvas,
            file_path=file_path,
            canvas_size=self.screen_size.value[0],  # assuming square canvas, so width == height
            resize_mode=resize_mode,
            palletize=palletize,
            background_color=background_color,
        )
        await self._send_diy_image_data(pixel_data)

    @staticmethod
    def _load_image_and_adapt_to_canvas(
        file_path: PathLike | str,
        canvas_size: int,
        resize_mode: image_utils.ResizeMode,
        palletize: bool,
        background_color: Tuple[int, int, int],
        colors: int = 256,
    ) -> bytearray:
        """
        Loads an image from a file, resizes it to fit within a square canvas of pixel_size x pixel_size,
        and applies a black background if the image is smaller than the canvas size.
        Args:
            file_path (str): Path to the image file.
            canvas_size (int): Size of the square canvas in pixels.
            palletize (bool): If True, the image will be converted to a palette-based image.
            background_color (Tuple[int, int, int]): RGB color for the background, which is only visible if the input
            colors (int): The number of colors of the palette that `palletize` reduces the image to.
        Returns:
            bytearray: A bytearray containing the raw pixel data of the processed image in RGB format.
        """
        if background_color is None or len(background_color) != 3:
            raise ValueError("background_color must be a tuple of three integers (R, G, B)")

        with PILImage.open(file_path) as img:
            # rotate image based on EXIF data if available
            img = ImageOps.exif_transpose(img)

            # LANCZOS leads to a more pleasing result for images with high detail,
            # NEAREST is better for pixel-art images, as it preserves the pixel structure.
            resample_mode = PILImage.Resampling.NEAREST if palletize else PILImage.Resampling.LANCZOS
            img = image_utils.resize_image(
                image=img,
                canvas_size=canvas_size,
                resize_mode=resize_mode,
                resample_mode=resample_mode,
                background_color=background_color,
                mode="RGB",  # ensure the image is in RGB mode
            )

            if palletize:
                img = image_utils.palettize(img, colors=colors)

            # Convert to RGB if not already in that mode, to get the pixel data in RGB format
            mode = "RGB"
            if img.mode != mode:
                img = img.convert(mode)

            png_buffer = bytearray(img.tobytes())
            return png_buffer

    async def show_image_file(
        self,
        file_path: PathLike | str,
        resize_mode: image_utils.ResizeMode = image_utils.ResizeMode.FIT,
        palletize: bool = False,
        background_color: Tuple[int, int, int] | int | str = (0, 0, 0),
        png: bool = False,
        slot: int | None = None,
        display_time: int = DEFAULT_DISPLAY_TIME_SECONDS,
        colors: int = 256,
    ) -> None:
        """
        Shows an image file on the device, the way the official app does it for photos. It is shown right away, unless
        a slot is given.

        In contrast to `upload_image_file` this does not need `set_mode`, and it can be mixed with
        GIF uploads without any mode switching in between.

        Args:
            file_path (str): path-like object to the image file
            resize_mode (image_utils.ResizeMode): The mode to use for resizing the image.
            palletize (bool): If True, the image will be converted to a palette-based image. Usually bad for images with
                high detail (like photos) but good for pixel-art or other content with high contrasts. Defaults to False.
            background_color (Tuple[int, int, int]): RGB color for the background, which is only visible if the input
                image doesn't match the devices aspect ratio. Defaults to black (0, 0, 0).
            png (bool): If True, the image is sent as a PNG file instead of raw RGB data. That is smaller (about 25-45%
                for photos, more for pixel-art, and a palette PNG with `palletize`), which saves a little upload time.
                Experimental: tested on a 64x64 device only, the official app sends raw RGB. Defaults to False.
            slot (int, optional): If given (0 to 11), the image is stored in that slot of the device instead of being
                shown right away. The device cycles through the stored items by itself, see `MaterialsModule`.
            display_time (int): Seconds the stored item stays on screen in that cycle. Only used with a slot.
            colors (int): The number of colors of the palette (2 to 256) that `palletize` reduces the image to. The
                raw upload has the same size either way, with `png` fewer colors make it smaller. Less than 256 reduces
                the colors even if `palletize` is off.
        """
        validate_colors(colors)
        palletize = palletize or colors < 256
        if slot is not None:
            validate_slot(slot)
            validate_display_time(display_time)
        background_color = color_utils.parse_color_rgb(background_color)
        # reading and converting the file takes a while, the event loop must not be blocked
        pixel_data = await asyncio.to_thread(
            self._load_image_and_adapt_to_canvas,
            file_path=file_path,
            canvas_size=self.screen_size.value[0],  # assuming square canvas, so width == height
            resize_mode=resize_mode,
            palletize=palletize,
            background_color=background_color,
            colors=colors,
        )
        await self._send_static_image_data(
            pixel_data, png=png, palette=palletize, slot=slot, display_time=display_time, colors=colors)

    async def show_image_pixeldata(
        self,
        pixel_colors: List[Tuple[int, int, int] | int | str],
        png: bool = False,
    ) -> None:
        """
        Shows pixel data on the device, the way the official app does it for photos. See `show_image_file`.
        Args:
            pixel_colors: One color for each pixel of the screen, row by row.
            png (bool): If True, the pixels are sent as a PNG file. See `show_image_file`.
        """
        await self._send_static_image_data(self._pixel_colors_to_bytes(pixel_colors), png=png)

    def _encode_png(self, pixel_data: bytearray, palette: bool = False, colors: int = 256) -> bytearray:
        """
        Encodes raw RGB pixel data of the whole screen as a PNG file.

        Args:
            pixel_data: RGB bytes, row by row.
            palette: If True, the PNG uses a palette of up to 256 colors, which is smaller, but changes the colors of
                images with more than 256 of them.
        """
        size = self.screen_size.value[0]
        img = PILImage.frombytes("RGB", (size, size), bytes(pixel_data))
        if palette:
            img = img.quantize(colors, dither=PILImage.Dither.NONE)
        buffer = io.BytesIO()
        img.save(buffer, "PNG", optimize=True)
        return bytearray(buffer.getvalue())

    async def _send_static_image_data(
        self,
        pixel_data: bytearray,
        png: bool = False,
        palette: bool = False,
        slot: int | None = None,
        display_time: int = DEFAULT_DISPLAY_TIME_SECONDS,
        colors: int = 256,
    ) -> None:
        if png:
            pixel_data = self._encode_png(pixel_data, palette=palette, colors=colors)
        packets = self._create_static_image_data_packets(
            pixel_data,
            index=INDEX_SHOW_NOW if slot is None else slot,
            display_time=None if slot is None else display_time,
        )
        await self._send_packets(packets, response=True, wait_for_ack=True)

    def _create_static_image_data_packets(
        self,
        image_data: bytearray,
        index: int = INDEX_SHOW_NOW,
        time_sign: int = 0,
        display_time: int | None = None,
    ) -> List[List[bytearray]]:
        """
        Creates the packets of a static image upload. This corresponds to `sendImageData` of the official app,
        which looks like `sendDIYImageData` with a longer header, that contains a CRC32 and the index of the image.

        Returns:
            A list of lists of byte arrays. The outer list represents the "4K chunks"
            and the inner lists contain the actual BLE packets for each 4K chunk.
        """
        total_length = len(image_data).to_bytes(4, "little")
        crc32 = (binascii.crc32(image_data) & 0xFFFFFFFF).to_bytes(4, "little")

        packets = []
        for i, chunk in enumerate(self.chunk_data_by_size(image_data, CHUNK_SIZE_4096)):
            header = bytearray(HEADER_SIZE_STATIC_IMAGE)
            header[0:2] = (len(chunk) + HEADER_SIZE_STATIC_IMAGE).to_bytes(2, "little")
            header[2] = TYPE_STATIC_IMAGE
            header[3] = 0
            header[4] = 2 if i > 0 else 0  # continuation / first chunk
            header[5:9] = total_length
            header[9:13] = crc32
            header[13:15] = (
                display_time if display_time is not None else convert_display_time(time_sign)
            ).to_bytes(2, "little")
            header[15] = index

            packets.append(self._create_ble_packets(bytes(header) + chunk))
        return packets

    async def upload_image_pixeldata(
        self,
        pixel_colors: List[Tuple[int, int, int] | int | str],
    ) -> None:
        """
        Uploads pixel data to the iDotMatrix device.
        Args:
            pixel_colors (List[Tuple[int, int, int]]): List of tuples representing RGB pixel values.
                Each tuple should contain three integers (R, G, B) in the range 0-255.
                The length of this list must match the square of the screen size (pixel_size * pixel_size).
        """
        pixel_data = self._pixel_colors_to_bytes(pixel_colors)

        return await self._send_diy_image_data(pixel_data)

    def _pixel_colors_to_bytes(self, pixel_colors: List[Tuple[int, int, int] | int | str]) -> bytearray:
        pixel_size = self.screen_size.value[0]  # assuming square canvas, so width == height
        if len(pixel_colors) != pixel_size * pixel_size:
            raise ValueError(
                f"pixel_data must contain exactly {pixel_size * pixel_size} pixels (quared pixel_size), got: {len(pixel_colors)}"
            )

        # parse the pixel_colors to ensure they are in RGB format
        pixel_colors = color_utils.parse_color_rgb_list(pixel_colors)

        # Convert pixel_data to a bytearray in RGB format
        pixel_data = bytearray()
        for r, g, b in pixel_colors:
            if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
                raise ValueError(f"Invalid RGB value: ({r}, {g}, {b}). Values must be between 0 and 255.")
            pixel_data.extend([r, g, b])
        return pixel_data

    async def _send_diy_image_data(
        self, pixel_data: bytearray,
    ) -> None:
        packets = self._create_diy_image_data_packets(pixel_data)
        await self._send_packets(packets, response=True, wait_for_ack=True)

    @staticmethod
    def _short_to_bytes_le(value: int) -> bytes:
        """Converts a short (2 bytes) to little-endian bytes."""
        return struct.pack('<h', value)

    @staticmethod
    def _int_to_bytes_le(value: int) -> bytes:
        """Converts an int (4 bytes) to little-endian bytes."""
        return struct.pack('<i', value)

    @staticmethod
    def chunk_data_by_size(data: bytearray | bytes, chunk_size: int) -> List[bytearray]:
        """
        Chunks the input data into smaller pieces of a specified size.

        Args:
            data: The byte array to be chunked.
            chunk_size: The maximum size of each chunk.

        Returns:
            A list of byte arrays, where each is a chunk of the original data.
        """
        chunks = []
        for i in range(0, len(data), chunk_size):
            chunks.append(data[i:i + chunk_size])
        return chunks

    def _create_ble_packets(self, data_chunk, ble_device_mtu_enabled=True):
        """
        Splits a data chunk into smaller BLE packets based on MTU size.
        This corresponds to the inner chunking logic in `getSendData`.

        Args:
            data_chunk: A byte array representing a single "large" chunk (e.g., 4K).
            ble_device_mtu_enabled: Boolean indicating if MTU is enabled on the BLE device.

        Returns:
            A list of byte arrays, where each is a BLE packet.
        """
        mtu = MTU_SIZE_IF_ENABLED if ble_device_mtu_enabled else MTU_SIZE_IF_DISABLED
        return self.chunk_data_by_size(data_chunk, mtu)

    def _create_diy_image_data_packets(
        self,
        image_data: bytearray,
        ble_device_mtu_enabled=True
    ) -> List[List[bytearray]]:
        """
        Recreates the sendData3 structure for DIY image data.
        This corresponds to the logic in `sendDIYImageData`.

        Args:
            image_data: The raw byte array of the RGB image data.
            ble_device_mtu_enabled: Boolean indicating if MTU is enabled on the BLE device.

        Returns:
            A list of lists of byte arrays. The outer list represents the "4K chunks"
            and the inner lists contain the actual BLE packets for each 4K chunk.
        """
        send_data_3 = []

        image_data_len_bytes = self._int_to_bytes_le(len(image_data))

        # 1. Chunk the image_data into 4096-byte chunks (or smaller for the last one)
        # This corresponds to `getSendData4096`
        chunks_4096 = self.chunk_data_by_size(image_data, CHUNK_SIZE_4096)

        # 2. Process each 4096-byte chunk to create the "large packet" structure
        # This corresponds to the loop creating `arrayList` in `sendDIYImageData`
        processed_large_packets = []
        for i, chunk in enumerate(chunks_4096):
            packet_length = len(chunk) + 9  # 9 bytes for the header
            packet_length_bytes = self._short_to_bytes_le(packet_length)

            # Construct the header for this large packet
            header = bytearray(9)
            header[0] = packet_length_bytes[0]  # Little-endian short
            header[1] = packet_length_bytes[1]
            header[2] = 0  # Command or type
            header[3] = 0  # Sub-command or subtype

            if i > 0:
                header[4] = 2  # Continuation packet
            else:
                header[4] = 0  # First packet

            header[5] = image_data_len_bytes[0]  # Total image data length (little-endian int)
            header[6] = image_data_len_bytes[1]
            header[7] = image_data_len_bytes[2]
            header[8] = image_data_len_bytes[3]

            # Combine header and the current 4096B chunk data
            large_packet_data = bytes(header) + chunk
            processed_large_packets.append(large_packet_data)

        # 3. Split each "large packet" into smaller BLE packets
        # This corresponds to the loop calling `getSendData` and adding to `sendData3`
        for i, large_packet in enumerate(processed_large_packets):
            ble_packets_for_chunk = self._create_ble_packets(large_packet, ble_device_mtu_enabled)
            send_data_3.append(ble_packets_for_chunk)

        return send_data_3
