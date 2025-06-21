import logging
import struct
from os import PathLike
from typing import Union, List, Tuple

from PIL import Image as PilImage, ExifTags

from ..connectionManager import ConnectionManager

MTU_SIZE_IF_ENABLED = 509
MTU_SIZE_IF_DISABLED = 18
CHUNK_SIZE_4096 = 4096


class Image:
    logging = logging.getLogger(__name__)

    def __init__(self) -> None:
        self.conn: ConnectionManager = ConnectionManager()

    async def set_mode(self, mode: int = 1) -> Union[bool, bytearray]:
        """Enter the DIY draw mode of the iDotMatrix device.

        Args:
            mode (int): 0 = disable DIY, 1 = enable DIY, 2 = ?, 3 = ?. Defaults to 1.

        Returns:
            Union[bool, bytearray]: False if there's an error, otherwise byte array of the command which needs to be sent to the device.
        """
        try:
            data = bytearray([5, 0, 4, 1, mode % 256])
            if self.conn:
                await self.conn.connect()
                await self.conn.send(data=data)
            return data
        except BaseException as error:
            self.logging.error(f"could not enter image mode due to {error}")
            return False

    @staticmethod
    def _split_into_chunks(data: bytearray | bytes, chunk_size: int) -> List[bytearray]:
        """Split the data into chunks of specified size.

        Args:
            data (bytearray): data to split into chunks
            chunk_size (int): size of the chunks

        Returns:
            List[bytearray]: returns list with chunks of given data input
        """
        return [data[i: i + chunk_size] for i in range(0, len(data), chunk_size)]

    @staticmethod
    def _short_to_bytes_le(value):
        """Converts a short (2 bytes) to little-endian bytes."""
        return struct.pack('<h', value)

    @staticmethod
    def _int_to_bytes_le(value):
        """Converts an int (4 bytes) to little-endian bytes."""
        return struct.pack('<i', value)

    @staticmethod
    def chunk_data_by_size(data, chunk_size):
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
            image_data: The raw byte array of the image data.
            ble_device_mtu_enabled: Boolean indicating if MTU is enabled on the BLE device.

        Returns:
            A list of lists of byte arrays. The outer list represents the "4K chunks"
            and the inner lists contain the actual BLE packets for each 4K chunk.
        """
        send_data_3 = []

        image_data_len_bytes = self._int_to_bytes_le(len(image_data))
        print(f"========== Image file data length: {len(image_data)}")

        # 1. Chunk the image_data into 4096-byte chunks (or smaller for the last one)
        # This corresponds to `getSendData4096`
        chunks_4096 = self.chunk_data_by_size(image_data, CHUNK_SIZE_4096)
        print(f"=== Number of 4096B (or smaller) chunks: {len(chunks_4096)}")

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

    @staticmethod
    def create_uniform_color_rgb_byte_array(width, height, color_rgb):
        """
        Creates a flat byte array in RGB format for an image of a uniform color.

        Args:
            width (int): The width of the image.
            height (int): The height of the image.
            color_rgb (tuple): An (R, G, B) tuple representing the color to be applied
                               to all pixels. Each R, G, B value should be an integer
                               between 0 and 255.

        Returns:
            bytearray: A bytearray containing the RGB data (R, G, B, R, G, B, ...),
                       or None if the input is invalid.
        """
        if width <= 0 or height <= 0:
            print("Error: Width and height must be positive integers.")
            return None

        if not (isinstance(color_rgb, tuple) and len(color_rgb) == 3):
            print("Error: color_rgb must be a tuple of 3 integers (R, G, B).")
            return None

        r, g, b = color_rgb
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            print(f"Error: Invalid RGB color value in color_rgb: ({r}, {g}, {b}). "
                  "Values must be between 0 and 255.")
            return None

        num_pixels = width * height
        # Each pixel is 3 bytes (R, G, B)
        rgb_byte_array = bytearray(num_pixels * 3)

        output_byte_index = 0
        for _ in range(num_pixels):
            rgb_byte_array[output_byte_index] = r
            output_byte_index += 1
            rgb_byte_array[output_byte_index] = g
            output_byte_index += 1
            rgb_byte_array[output_byte_index] = b
            output_byte_index += 1

        return rgb_byte_array

    # async def uploadUnprocessed(self, file_path: str) -> Union[bool, bytearray]:
    #     """Uploads an image without further checks and resizes.
    #
    #     Args:
    #         file_path (str): path to the image file
    #
    #     Returns:
    #         Union[bool, bytearray]: False if there's an error, otherwise returns bytearray payload
    #     """
    #     try:
    #         png_data = self._loadPNG(file_path)
    #         data = self._createPayloads(png_data)
    #         if self.conn:
    #             await self.conn.connect()
    #             await self.conn.send(data=data)
    #         return data
    #     except BaseException as error:
    #         self.logging.error(f"could not upload the unprocessed image: {error}")
    #         return False

    async def upload_image_file(
        self, file_path: PathLike, pixel_size: int = 64
    ) -> None:
        """Uploads a file processed and makes sure everything is correct before uploading to the device.

        Args:
            file_path (str): path-like object to the image file
            pixel_size (int, optional): number of pixels (one of 16, 32 or 64). Defaults to 64.
        """
        pixel_data = self._load_image_and_adapt_to_canvas(file_path, pixel_size)
        return await self._send_diy_image_data(pixel_data)

    async def upload_image_pixeldata(
        self, pixel_data: List[Tuple[int, int, int]], pixel_size: int = 64
    ) -> None:
        if pixel_size not in [16, 32, 64]:
            raise ValueError("pixel_size must be one of [16, 32, 64]")
        if len(pixel_data) != pixel_size * pixel_size:
            raise ValueError(
                f"pixel_data must contain exactly {pixel_size * pixel_size} pixels (quared pixel_size), got: {len(pixel_data)}"
            )

        # Convert pixel_data to a bytearray in RGB format
        pixel_data = bytearray()
        for r, g, b in pixel_data:
            if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
                raise ValueError(f"Invalid RGB value: ({r}, {g}, {b}). Values must be between 0 and 255.")
            pixel_data.extend([r, g, b])

        return await self._send_diy_image_data(pixel_data)

    async def _send_diy_image_data(
        self, pixel_data: bytearray,
    ) -> None:
        packets = self._create_diy_image_data_packets(pixel_data)
        if self.conn:
            await self.conn.connect()
            await self.conn.send_packets(data=packets)

    @staticmethod
    def _load_image_and_adapt_to_canvas(
        file_path: PathLike,
        pixel_size: int
    ) -> bytearray:
        """
        Loads an image from a file, resizes it to fit within a square canvas of pixel_size x pixel_size,
        and applies a black background if the image is smaller than the canvas size.
        Args:
            file_path (str): Path to the image file.
            pixel_size (int): Size of the square canvas in pixels.
        Returns:
            bytearray: A bytearray containing the raw pixel data of the processed image in RGB format.
        """
        with PilImage.open(file_path) as img:
            background_color = (0, 0, 0)  # black background
            # resize image to pixel_size x pixel_size, but keep aspect ratio, and fill with background_color if the image is smaller
            img.thumbnail((pixel_size, pixel_size), PilImage.Resampling.LANCZOS)
            new_img = PilImage.new("RGB", (pixel_size, pixel_size), background_color)
            new_img.paste(
                img, ((pixel_size - img.width) // 2, (pixel_size - img.height) // 2)
            )
            img = new_img

            # Read EXIF orientation tag if exists
            try:
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation] == 'Orientation':
                        break
                exif = img._getexif()
                if exif is not None:
                    orientation_value = exif.get(orientation, None)
                    if orientation_value == 3:
                        img = img.rotate(180, expand=True)
                    elif orientation_value == 6:
                        img = img.rotate(270, expand=True)  # rotate 270° == rotate right 90°
                    elif orientation_value == 8:
                        img = img.rotate(90, expand=True)  # rotate 90° == rotate left 90°
            except Exception:
                pass  # no exif or orientation tag, ignore
            # Convert to RGB if not already in that mode
            mode = "RGB"
            if img.mode != mode:
                img = img.convert(mode)

            # png_buffer = io.BytesIO()
            # img.save(png_buffer, format="PNG")
            # png_buffer.seek(0)
            png_buffer = bytearray(img.tobytes())
            return png_buffer
