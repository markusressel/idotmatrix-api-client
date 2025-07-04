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

MTU_SIZE_IF_ENABLED = 509
MTU_SIZE_IF_DISABLED = 18
CHUNK_SIZE_4096 = 4096


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
        background_color: Tuple[int, int, int] or int or str = (0, 0, 0),  # default to black background
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
        pixel_data = self._load_image_and_adapt_to_canvas(
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
    ) -> bytearray:
        """
        Loads an image from a file, resizes it to fit within a square canvas of pixel_size x pixel_size,
        and applies a black background if the image is smaller than the canvas size.
        Args:
            file_path (str): Path to the image file.
            canvas_size (int): Size of the square canvas in pixels.
            palletize (bool): If True, the image will be converted to a palette-based image.
            background_color (Tuple[int, int, int]): RGB color for the background, which is only visible if the input
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
                mode="RGB",  # ensure the image is in RGB mode
            )

            if palletize:
                img = image_utils.palettize(img)

            # Convert to RGB if not already in that mode, to get the pixel data in RGB format
            mode = "RGB"
            if img.mode != mode:
                img = img.convert(mode)

            png_buffer = bytearray(img.tobytes())
            return png_buffer

    async def upload_image_pixeldata(
        self,
        pixel_colors: List[Tuple[int, int, int] or int or str],
    ) -> None:
        """
        Uploads pixel data to the iDotMatrix device.
        Args:
            pixel_colors (List[Tuple[int, int, int]]): List of tuples representing RGB pixel values.
                Each tuple should contain three integers (R, G, B) in the range 0-255.
                The length of this list must match the square of the screen size (pixel_size * pixel_size).
        """
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

        return await self._send_diy_image_data(pixel_data)

    async def _send_diy_image_data(
        self, pixel_data: bytearray,
    ) -> None:
        packets = self._create_diy_image_data_packets(pixel_data)
        await self._send_packets(packets)

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
