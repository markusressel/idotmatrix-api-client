import binascii
import io
import logging
import zlib
from os import PathLike
from typing import List, Tuple

from PIL import Image as PilImage

from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.modules import IDotMatrixModule
from idotmatrix.screensize import ScreenSize
from idotmatrix.util import image_utils, color_utils

ANIMATION_MAX_FRAME_COUNT = 64  # Maximum number of frames in a GIF animation
DEFAULT_DURATION_PER_FRAME_MS = 200  # Default duration per frame in milliseconds if not specified in the GIF file
ANIMATION_TOTAL_DURATION_LIMIT_MS = 2000
DEFAULT_ANIMATION_TOTAL_DURATION_MS = ANIMATION_TOTAL_DURATION_LIMIT_MS

# --- Constants based on the Java code ---
CHUNK_SIZE_4096 = 4096
HEADER_SIZE_GIF = 16  # As per sendImageData logic in GifAgreement.java

class GifModule(IDotMatrixModule):
    """
    This class handles GIF file uploads to the iDotMatrix device.
    """
    logging = logging.getLogger(__name__)

    def __init__(
        self,
        connection_manager: ConnectionManager,
        screen_size: ScreenSize,
    ) -> None:
        super().__init__(connection_manager=connection_manager)
        self.screen_size = screen_size

    async def upload_gif_file(
        self,
        file_path: PathLike | str,
        palletize: bool = True,
        background_color: Tuple[int, int, int] or int or str = (0, 0, 0),
        duration_per_frame_in_ms: int = None,
    ):
        """
        Uploads a GIF file to the device.

        Args:
            file_path (str): path to the image file
            palletize (bool): Whether to convert the image to a color palette. Usually bad for images with
                high detail (like photos) but good for pixel-art or other content with high contrasts. Defaults to True.
            background_color (Tuple[int, int, int]): RGB color to fill transparent pixels. Defaults to black (0, 0, 0).
            duration_per_frame_in_ms (int, optional): Duration of each frame in milliseconds. If not provided, defaults to the duration specified in the GIF file, or 200ms if not set.
        """
        pixel_size = self.screen_size.value[0]  # assuming square canvas, so width == height
        background_color = color_utils.parse_color_rgb(background_color)

        gif_data = self._load_gif_and_adapt_to_canvas(
            file_path=file_path,
            canvas_size=pixel_size,
            palletize=palletize,
            background_color=background_color,
            duration_per_frame_in_ms=duration_per_frame_in_ms,
        )

        # TODO: recreate this logic by analyzing the APK, similar to what is done in the ImageModule,
        # because the although the current implementation seems to _mostly_ work,
        # some GIFs stop animating during the upload, and often times the second upload fails completely.
        # So there is probably some edge case that is not handled correctly.
        data = self._create_payloads(gif_data)
        for chunk in data:
            await self._send_bytes(data=chunk, response=True, chunk_size=514)

    def _load_gif_and_adapt_to_canvas(
        self,
        file_path: PathLike | str,
        canvas_size: int,
        palletize: bool = True,
        background_color: Tuple[int, int, int] = (0, 0, 0),
        duration_per_frame_in_ms: int = None,
    ) -> bytes:
        """
        Loads a GIF file and adapts it to the pixel size of the device's canvas.

        Args:
            file_path (PathLike): Path to the GIF file.
            canvas_size (int): Size of the pixel in the device's canvas.
            palletize (bool): Whether to convert the image to a color palette. Defaults to True.
            background_color (Tuple[int, int, int]): Background color to fill transparent pixels.
            duration_per_frame_in_ms (int, optional): Duration of each frame in milliseconds. If not provided, defaults to the duration specified in the GIF file, or 200ms if not set.
        Returns:
            bytes: A byte representation of the GIF file, adapted to fit the pixel size.
        """
        with PilImage.open(file_path) as img:
            frames = []
            try:
                # There doesn't seem to be a frame limit in the app, but too many frames cause problems.
                # To be on the safe side, we limit it to 64 frames.
                while True:
                    frame = img.copy()
                    # if the dimensions of the frame are not equal to the pixel size, resize it while maintaining the aspect ratio
                    # and adding a black background if necessary.
                    if frame.size != (canvas_size, canvas_size):
                        frame.thumbnail(
                            size=(canvas_size, canvas_size),
                            # needs to use NEAREST to stay within color palette limits
                            resample=PilImage.Resampling.NEAREST,
                        )
                    # convert transparent pixels to the background color
                    new_image = PilImage.new(
                        mode="RGBA",
                        size=(canvas_size, canvas_size),
                        color=background_color
                    )
                    new_image.paste(
                        im=frame,
                        box=((canvas_size - frame.width) // 2, (canvas_size - frame.height) // 2),
                        mask=frame.convert("RGBA")
                    )
                    if palletize:
                        new_image = image_utils.palettize(new_image)
                    frame = new_image

                    frames.append(frame.copy())
                    img.seek(img.tell() + 1)
            except EOFError:
                pass

            frames, duration_per_frame_in_ms = self._ensure_reasonable_frame_count(
                img, frames, duration_per_frame_in_ms
            )

            # TODO: there are still some cases where
            #  - the GIF is not animating all frames

            gif_buffer = io.BytesIO()
            # take the first frame, append the rest as additional frames and save as GIF into gif_buffer
            frames[0].save(
                gif_buffer,
                format="GIF",
                save_all=True,
                optimize=True,  # setting this to False fails the transfer for some reason
                append_images=frames[1:],
                loop=0,  # loop forever
                duration=duration_per_frame_in_ms,
                disposal=2,  # Restore to background color after each frame
            )
            gif_buffer.seek(0)
            return gif_buffer.getvalue()

    def _create_payloads(
        self, gif_data: bytearray | bytes, chunk_size: int = 4096
    ) -> List[bytearray]:
        """
        Creates payloads from a GIF file.

        Args:
            gif_data (bytearray): data of the gif file
            chunk_size (int): size of a chunk

        Returns:
            bytearray: returns bytearray payload
        """
        # chunk header
        header = bytearray(
            [
                255,
                255,
                1,
                0,
                0,
                255,
                255,
                255,
                255,
                255,
                255,
                255,
                255,
                5,
                0,
                13,
            ]
        )
        # split gif into chunks
        chunks = []
        gif_chunks = self._split_into_chunks(gif_data, chunk_size)
        # set gif length
        header[5:9] = int(len(gif_data)).to_bytes(4, byteorder="little")
        # set crc of gif
        crc = zlib.crc32(gif_data)
        header[9:13] = crc.to_bytes(4, byteorder="little")
        # iterate over chunks
        for i, chunk in enumerate(gif_chunks):
            # starting from the second chunk, set the header to 2
            header[4] = 2 if i > 0 else 0
            # set chunk length in header
            chunk_len = len(chunk) + len(header)
            header[0:2] = chunk_len.to_bytes(2, byteorder="little")
            # append chunk to chunk list
            chunks.append(header + chunk)
        return chunks

    def _int_to_bytes_le(self, value: int, length: int = 4) -> bytearray:
        """Converts an integer to a little-endian bytearray of specified length."""
        return bytearray(value.to_bytes(length, byteorder='little'))

    def _short_to_bytes_le(self, value: int) -> bytearray:
        """Converts a short (2 bytes) to a little-endian bytearray."""
        return bytearray(value.to_bytes(2, byteorder='little'))

    def _chunk_data_by_size(self, data: bytes, chunk_size: int) -> list[bytearray]:
        """
        Chunks data into smaller pieces of a specified size.
        Corresponds to getSendData4096.
        """
        if not data:
            return []

        chunks = []
        num_chunks = (len(data) + chunk_size - 1) // chunk_size  # Ceiling division

        for i in range(num_chunks):
            start = i * chunk_size
            end = min((i + 1) * chunk_size, len(data))
            chunks.append(bytearray(data[start:end]))
        return chunks

    def create_gif_data_packets(
        self,
        gif_data: bytes,
        gif_type: int,
        time_sign: int,  # Assuming this is the raw time signature before DeviceMaterialTimeConvert.ConvertTime
        ble_device_mtu_enabled: bool = True
    ) -> list[list[bytearray]]:
        """
        Creates packets for sending GIF data, mirroring the Java GifAgreement logic.

        Args:
            gif_data: The raw byte array of the GIF data.
            gif_type: The type parameter (e.g., 12 or other values from sendImageData).
            time_sign: The time signature (e.g., from AppData.getInstance().getTimeSign()).
                       This will be processed similar to DeviceMaterialTimeConvert.ConvertTime.
            ble_device_mtu_enabled: Boolean indicating if MTU is enabled on the BLE device.

        Returns:
            A list of lists of byte arrays. The outer list represents "4K chunks with headers",
            and the inner lists contain the actual BLE packets for each of those chunks.
        """
        send_data_3 = []

        if not gif_data:
            print("DEBUG: GIF data is null or empty. Cannot create packets.")
            return send_data_3

        print(f"DEBUG: ====Creating GIF packets=== gifData.size:{len(gif_data)}")

        try:
            # Calculate CRC32 for the entire GIF data
            # Ensure this CRC32 matches the Java CrcUtils.CRC32.CRC32 implementation
            crc32_val = self.calculate_crc32_java_equivalent(gif_data)
            crc32_bytes = self._int_to_bytes_le(crc32_val)  # Little-endian int (4 bytes)

            # Get the total length of the GIF data as bytes
            total_length_bytes = self._int_to_bytes_le(len(gif_data))  # Little-endian int (4 bytes)

            print(f"DEBUG: ==========GIF data total length：{len(gif_data)}, CRC32: {crc32_val:08X}")

            # 1. Chunk the gif_data into 4096-byte chunks
            chunks_4096 = self._chunk_data_by_size(gif_data, CHUNK_SIZE_4096)
            print(f"DEBUG: ===dataList4096 (GIF) length: {len(chunks_4096)}")

            processed_large_packets_with_headers = []
            for i, current_chunk in enumerate(chunks_4096):
                packet_data_length = len(current_chunk) + HEADER_SIZE_GIF
                # Java: byte[] short2Bytes = ByteUtils.short2Bytes((short) length);
                # bArr2[0] = short2Bytes[1]; bArr2[1] = short2Bytes[0];
                # This indicates that ByteUtils.short2Bytes might be big-endian,
                # OR it's little-endian and they are swapping.
                # Assuming ByteUtils.short2Bytes(value) returns [LSB, MSB] (little-endian)
                # and then bArr2[0]=MSB, bArr2[1]=LSB is effectively writing it as big-endian.
                # However, the Python code uses _short_to_bytes_le for the DIY image data,
                # implying the packet length itself *should* be little-endian in the header.
                # Let's stick to little-endian for packet_length_bytes based on your Python _create_diy_image_data_packets
                # and assume the Java snippet `bArr2[0] = short2Bytes[1]; bArr2[1] = short2Bytes[0];`
                # was specific to how that `ByteUtils.short2Bytes` worked or a specific requirement.
                # If the device expects big-endian length, change this.
                # The Java code `bArr2[0] = short2Bytes[1]; bArr2[1] = short2Bytes[0];` effectively writes a short in Big Endian.
                # So we will use big-endian for packet_data_length_bytes.
                packet_data_length_bytes_be = bytearray(packet_data_length.to_bytes(2, byteorder='big'))

                header = bytearray(HEADER_SIZE_GIF)

                header[0] = packet_data_length_bytes_be[0]  # Packet Length (Big Endian short)
                header[1] = packet_data_length_bytes_be[1]
                header[2] = 1  # Command or type (fixed value from sendImageData)
                header[3] = 0  # Sub-command or subtype (fixed value)

                if i > 0:
                    header[4] = 2  # Continuation packet
                else:
                    header[4] = 0  # First packet

                # Total GIF data length (Little Endian int)
                header[5:9] = total_length_bytes[0:4]

                # CRC32 of GIF data (Little Endian int)
                header[9:13] = crc32_bytes[0:4]

                # Time signature or fixed bytes based on 'gif_type'
                if gif_type == 12:  # Assuming 12 is a special type
                    header[13] = 0
                    header[14] = 0
                else:
                    # Java: DeviceMaterialTimeConvert.ConvertTime(AppData.getInstance().getTimeSign())
                    # Assuming ConvertTime returns a short value.
                    # And then ByteUtils.short2Bytes is used, and bytes swapped (effectively Big Endian short)
                    # Python equivalent:
                    converted_time_short = (time_sign // 1000) % 65536  # Placeholder for ConvertTime, ensure it's a short value
                    time_sign_bytes_be = bytearray(converted_time_short.to_bytes(2, byteorder='big'))
                    header[13] = time_sign_bytes_be[0]
                    header[14] = time_sign_bytes_be[1]

                header[15] = gif_type & 0xFF  # Ensure it's a byte

                large_packet_with_header = bytes(header) + current_chunk
                processed_large_packets_with_headers.append(large_packet_with_header)

            print(f"DEBUG: ======(GIF) Total large packets (4K chunks with headers): {len(processed_large_packets_with_headers)}")

            # 3. Split each "large packet with header" into smaller BLE packets
            for i, large_packet in enumerate(processed_large_packets_with_headers):
                print(f"DEBUG: Processing large GIF packet {i} data length: {len(large_packet)}")
                ble_packets_for_chunk = self._create_ble_packets(large_packet, ble_device_mtu_enabled)
                if ble_packets_for_chunk:
                    send_data_3.append(ble_packets_for_chunk)

        except Exception as e:
            print(f"ERROR: Error creating GIF packets: {e}")
            import traceback
            traceback.print_exc()
            send_data_3 = []  # Clear on error

        return send_data_3

    def _create_ble_packets(self, data_packet: bytes, ble_device_mtu_enabled: bool = True) -> list[bytearray]:
        """
        Splits a single data packet into smaller packets suitable for BLE transmission.
        Corresponds to getSendData.
        MTU values (509, 18) are from GifAgreement.java.
        """
        if not data_packet:
            return []

        ble_packets = []
        mtu_packet_size = 509 if ble_device_mtu_enabled else 18

        num_ble_packets = (len(data_packet) + mtu_packet_size - 1) // mtu_packet_size

        for i in range(num_ble_packets):
            start = i * mtu_packet_size
            end = min((i + 1) * mtu_packet_size, len(data_packet))
            ble_packets.append(bytearray(data_packet[start:end]))
        return ble_packets

    # --- Placeholder for a CRC32 function ---
    # The Java code uses CrcUtils.CRC32.CRC32. Python's built-in binascii.crc32
    # might behave differently (e.g., signed vs. unsigned, initial value, polynomial).
    # For a direct equivalent, you might need a specific library or to implement
    # the exact CRC32 variant used in your Java code.
    # For this example, we'll use binascii.crc32 and note the potential difference.
    def calculate_crc32_java_equivalent(self, data: bytes) -> int:
        """
        Calculates CRC32. Note: binascii.crc32 might differ from Java's specific CRC32.
        The Java CrcUtils.CRC32.CRC32(bArr, 0, bArr.length) implies a standard CRC32.
        binascii.crc32 returns a signed 32-bit integer on some Python versions/platforms,
        Java usually deals with it as unsigned when converting to bytes.
        """
        # Initialize with 0xFFFFFFFF, XOR output with 0xFFFFFFFF
        # This is a common CRC32/MPEG-2 variant.
        # Python's binascii.crc32(data) is equivalent to binascii.crc32(data, 0)
        # The result should be masked to get an unsigned 32-bit value.
        crc = binascii.crc32(data) & 0xFFFFFFFF
        return crc

    @staticmethod
    def _split_into_chunks(data: bytearray, chunk_size: int) -> List[bytearray]:
        """
        Split the data into chunks of specified size.

        Args:
            data (bytearray): data to split into chunks
            chunk_size (int): size of the chunks

        Returns:
            List[bytearray]: returns list with chunks of given data input
        """
        return [data[i: i + chunk_size] for i in range(0, len(data), chunk_size)]

    @staticmethod
    def _ensure_reasonable_frame_count(
        img: PilImage.Image,
        frames: List[PilImage.Image],
        duration_per_frame_in_ms: int = None,
        default_total_duration: int = DEFAULT_ANIMATION_TOTAL_DURATION_MS,
        default_duration_per_frame: int = DEFAULT_DURATION_PER_FRAME_MS,
        total_duration_limit_ms: int = ANIMATION_TOTAL_DURATION_LIMIT_MS,
        max_total_frame_count: int = ANIMATION_MAX_FRAME_COUNT,
    ) -> Tuple[List[PilImage.Image], int]:
        """
        The device can only handle a limited number of frames in a GIF animation, due to limited processing power and memory.
        This function ensures that the number of frames does not exceed the maximum allowed frames (64) and adjusts the duration per frame if necessary.

        Args:
            img (PilImage.Image): The image object of the GIF.
            frames (List[PilImage.Image]): List of frames in the GIF.
            duration_per_frame_in_ms (int, optional): Duration of each frame in milliseconds. If not provided, defaults to the duration specified in the GIF file, or 200ms if not set.
        Returns:
            Tuple[List[PilImage.Image], int]: A tuple containing the list of frames and the duration per frame in milliseconds.
        """
        # determine the optimal duration per frame if not provided
        if duration_per_frame_in_ms is None:
            duration_per_frame_in_ms = img.info.get("duration", default_duration_per_frame)
            # if the value we get is not reasonable, compute alternative value
            if (
                not isinstance(duration_per_frame_in_ms, int)
                or not duration_per_frame_in_ms
                or duration_per_frame_in_ms <= 0
            ):
                if len(frames) > max_total_frame_count:
                    # if the number of frames exceeds the maximum allowed frames, set the duration so that exactly max_total_frame_count frames fit into the total duration limit
                    duration_per_frame_in_ms = total_duration_limit_ms / max_total_frame_count
                else:
                    # compute the duration per frame based on the number of frames and the default total duration
                    duration_per_frame_in_ms = default_total_duration / len(frames)

            if duration_per_frame_in_ms < 16:
                # make sure the duration is at least 16ms (60fps), otherwise the device might not be able to handle it
                duration_per_frame_in_ms = 16

        # make sure the duration of the full animation doesn't exceed (duration_per_frame_in_ms * 64)
        # because otherwise the upload takes a very long time. If using the given duration_per_frame_in_ms exceeds the limit,
        # intermediate frames are skipped to keep the total count of frames below max_total_frame_count.
        original_frame_count = len(frames)
        original_duration = original_frame_count * duration_per_frame_in_ms
        if original_duration > total_duration_limit_ms:
            # if the total duration limit is exceeded, skip frames (except for the first and last one) to stay within the limit
            result_frames = [frames[0], frames[-1]]  # always keep the first and last frame

            number_of_frames_to_keep = int(
                total_duration_limit_ms / duration_per_frame_in_ms) - 2  # -2 because we keep the first and last frame
            number_of_frames_to_keep = min(max_total_frame_count - 2, number_of_frames_to_keep)

            if number_of_frames_to_keep >= original_frame_count:
                # if the number of frames to keep is greater than or equal to the available frames, do nothing
                return frames, duration_per_frame_in_ms

            frames_excluding_first_and_last = frames[1:-1]
            # evenly select number_of_frames_to_keep frames from frames_excluding_first_and_last and insert them into result_frames between the first and last frame
            step = len(frames_excluding_first_and_last) // number_of_frames_to_keep
            for i in range(0, len(frames_excluding_first_and_last), step):
                if len(result_frames) < max_total_frame_count - 1:
                    result_frames.insert(-1, frames_excluding_first_and_last[i])
            frames = result_frames

        # print(f"GIF original frame count: {original_frame_count}")
        # print(f"GIF adjusted frame count: {len(frames)}")
        # print(f"GIF duration per frame: {duration_per_frame_in_ms} ms")
        # print(f"GIF total duration: {len(frames) * duration_per_frame_in_ms} ms")

        return frames, duration_per_frame_in_ms
