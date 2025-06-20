import io
import logging
import struct
from typing import Union, List

from PIL import Image as PilImage, ExifTags

from ..connectionManager import ConnectionManager

###

# Constants (mirrored from Java, adjust if necessary)
MTU_SIZE_IF_ENABLED = 509  # Corresponds to bleDevice.isMtuStatus() ? 509
MTU_SIZE_IF_DISABLED = 18  # Corresponds to : 18
CHUNK_SIZE_4096 = 4096


###


class Image:
    logging = logging.getLogger(__name__)

    def __init__(self) -> None:
        self.conn: ConnectionManager = ConnectionManager()

    async def setMode(self, mode: int = 1) -> Union[bool, bytearray]:
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

    def _loadPNG(self, file_path: str) -> bytes:
        """Load a PNG file into a byte buffer.

        Args:
            file_path (str): path to file

        Returns:
            bytes: returns the file contents
        """
        with open(file_path, "rb") as file:
            return file.read()

    def _splitIntoChunks(self, data: bytearray, chunk_size: int) -> List[bytearray]:
        """Split the data into chunks of specified size.

        Args:
            data (bytearray): data to split into chunks
            chunk_size (int): size of the chunks

        Returns:
            List[bytearray]: returns list with chunks of given data input
        """
        return [data[i: i + chunk_size] for i in range(0, len(data), chunk_size)]

    def _createPayloads(self, rgb_data: bytearray) -> List[bytearray]:
        chunks = self._splitIntoChunks(rgb_data, 4096)
        total_length_bytes = struct.pack(">I", len(rgb_data))  # 4 bytes big-endian

        packets = []

        for i, chunk in enumerate(chunks):
            packet_length = len(chunk) + 9  # total packet length including header

            # Pack as little-endian short (2 bytes)
            packet_length_le = struct.pack("<H", packet_length)

            # Java swaps bytes: bArr3[0] = short2Bytes[1], bArr3[1] = short2Bytes[0]
            # So swap bytes here to match Java exactly:
            packet_length_bytes = bytearray([packet_length_le[1], packet_length_le[0]])

            header = bytearray()
            header += packet_length_bytes  # [0-1] length in swapped little-endian
            header += b'\x00\x00'  # [2-3] reserved zero bytes
            header += b'\x00' if i <= 0 else b'\x02'  # [4] flag: 0 first packet else 2
            header += total_length_bytes  # [5-8] total length big-endian

            packet = header + chunk
            packets.append(packet)

        # Debug prints (optional)
        if packets:
            print("First packet header+data:", packets[0][:20].hex())
        print("Total packets created:", len(packets))

        return packets

    def _short_to_bytes_le(self, value):
        """Converts a short (2 bytes) to little-endian bytes."""
        return struct.pack('<h', value)

    def _int_to_bytes_le(self, value):
        """Converts an int (4 bytes) to little-endian bytes."""
        return struct.pack('<i', value)

    def chunk_data_by_size(self, data, chunk_size):
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

    def create_ble_packets(self, data_chunk, ble_device_mtu_enabled=True):
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

    def create_diy_image_data_packets(self, image_data, ble_device_mtu_enabled=True):
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

        print(f"====== Total number of large packets (before BLE splitting): {len(processed_large_packets)}")

        # 3. Split each "large packet" into smaller BLE packets
        # This corresponds to the loop calling `getSendData` and adding to `sendData3`
        for i, large_packet in enumerate(processed_large_packets):
            print(f"Processing large packet {i} with length: {len(large_packet)}")
            ble_packets_for_chunk = self.create_ble_packets(large_packet, ble_device_mtu_enabled)
            send_data_3.append(ble_packets_for_chunk)

        return send_data_3

    def send_diy_image_data(self, image_bytes: bytes) -> List[bytes]:
        send_data3 = []

        int2byte = image_bytes.__len__().to_bytes(4, byteorder='little')
        print(f"==========动画文件数据的长度: {len(image_bytes)}")

        send_data_4096 = self._splitIntoChunks(image_bytes, 4096)
        print(f"===dataList4096长度: {len(send_data_4096)}")

        packet_list = []

        for i, chunk in enumerate(send_data_4096):
            length = len(chunk) + 9
            short2bytes = length.to_bytes(2, byteorder='little')

            packet = bytearray(length)
            packet[0] = short2bytes[1]
            packet[1] = short2bytes[0]
            packet[2] = 0
            packet[3] = 0
            packet[4] = 2 if i > 0 else 0
            packet[5:9] = int2byte
            packet[9:] = chunk

            packet_list.append(packet)

        print(f"======每包4K数据的长度分包总数: {len(packet_list)}")

        for i, packet in enumerate(packet_list):
            print(f"发送第 {i} 大包数据: {len(packet)}")
            send_data3.extend(self.get_send_data(packet))

        return send_data3

    @staticmethod
    def get_send_data_4096(data: bytes) -> list[bytes]:
        chunk_size = 4096
        chunks = []

        total_chunks = (len(data) + chunk_size - 1) // chunk_size  # ceil division
        index = 0

        for i in range(total_chunks):
            if i == total_chunks - 1:
                # Last chunk: may be less than 4096 bytes
                chunk = data[index:]
            else:
                chunk = data[index:index + chunk_size]
                index += chunk_size
            chunks.append(chunk)

        return chunks

    @staticmethod
    def get_send_data(data: bytes) -> list[bytes] | None:
        # mtu_enabled = ble_device.is_mtu_status()
        mtu_enabled = True
        print(f"MTU setting status: {mtu_enabled}")

        chunk_size = 509 if mtu_enabled else 18
        chunks = []

        total_chunks = (len(data) + chunk_size - 1) // chunk_size  # ceil division
        index = 0

        for i in range(total_chunks):
            if i == total_chunks - 1:
                # Last chunk may be smaller
                chunk = data[index:]
            else:
                chunk = data[index:index + chunk_size]
                index += chunk_size
            chunks.append(chunk)

        return chunks

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

    def _createPayloadByColor(self, color_rgb: tuple[int, int, int]) -> List[bytearray]:
        IMAGE_WIDTH = 64
        IMAGE_HEIGHT = 64
        TOTAL_PIXELS = IMAGE_WIDTH * IMAGE_HEIGHT  # 4096
        BYTES_PER_IMAGE = TOTAL_PIXELS * 3  # 3 bytes per pixel = 12288
        MAX_CHUNK_SIZE = 4096

        # RGB triplet for the color (same value for R, G, B)
        r, g, b = color_rgb
        pixel = bytes([r, g, b])
        image_data = pixel * TOTAL_PIXELS  # Full frame of solid color

        total_length_bytes = struct.pack(">I", BYTES_PER_IMAGE)  # Big-endian 4 bytes
        chunks = self._splitIntoChunks(bytearray(image_data), MAX_CHUNK_SIZE)

        packets = []

        for i, chunk in enumerate(chunks):
            packet_length = len(chunk) + 9  # 9-byte header
            packet_length_le = struct.pack("<H", packet_length)
            packet_length_bytes = bytearray([packet_length_le[1], packet_length_le[0]])

            header = bytearray()
            header += packet_length_bytes  # [0-1] swapped LE length
            header += b'\x00\x00'  # [2-3] reserved
            header += b'\x00' if i == 0 else b'\x02'  # [4] flag
            header += total_length_bytes  # [5-8] total length

            packets.append(header + chunk)

        return packets

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

    async def uploadProcessed(
        self, file_path: str, pixel_size: int = 64
    ) -> Union[bool, bytearray]:
        """Uploads a file processed and makes sure everything is correct before uploading to the device.

        Args:
            file_path (str): path to the image file
            pixel_size (int, optional): amount of pixels (either 16 or 32 makes sense). Defaults to 32.

        Returns:
            Union[bool, bytearray]: False if there's an error, otherwise returns bytearray payload
        """
        try:
            with PilImage.open(file_path) as img:
                # Resize first (thumbnail)
                img.resize((pixel_size, pixel_size), PilImage.Resampling.LANCZOS)

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
                # png_buffer = bytearray(png_buffer.getvalue())

                # data_png = self._createPayloads(png_buffer)

                # data = data_color
                # packets = self.send_diy_image_data(data_color)

                data_color = self.create_uniform_color_rgb_byte_array(64, 64, (255, 255, 255))
                packets = self.create_diy_image_data_packets(png_buffer)

                if self.conn:
                    await self.conn.connect()
                    # flatten chunks
                    await self.conn.send_packets(data=packets)
                #return data
        except BaseException as error:
            raise error
            return False
