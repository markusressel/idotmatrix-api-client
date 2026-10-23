import asyncio
import binascii
import io
import logging
from collections.abc import Callable
from os import PathLike
from typing import List, Tuple

from PIL import Image as PILImage

from idotmatrix import protocol
from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.modules import IDotMatrixModule
from idotmatrix.protocol import build_command
from idotmatrix.screensize import ScreenSize
from idotmatrix.util import image_utils, color_utils
from idotmatrix.util.device_material import (
    DEFAULT_DISPLAY_TIME_SECONDS, INDEX_SHOW_NOW, convert_display_time, validate_display_time, validate_slot,
)
from idotmatrix.util.image_utils import ResizeMode, validate_colors
from idotmatrix.util.overlay import TextOverlay
from idotmatrix.util.quality import DEFAULT_MAX_COLOR_ERROR, color_error, color_score

# like browsers do, a frame without a delay or with one of 10 ms or less is shown for 100 ms
DEFAULT_DURATION_PER_FRAME_MS = 100
MIN_DURATION_PER_FRAME_MS = 16

AUTO_COLORS = "auto"
AUTO_COLOR_STEPS = (256, 128, 64, 32, 16)

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
        resize_mode: ResizeMode = ResizeMode.FIT,
        palletize: bool = True,
        background_color: Tuple[int, int, int] | int | str = (0, 0, 0),
        duration_per_frame_in_ms: int = None,
        slot: int | None = None,
        display_time: int = DEFAULT_DISPLAY_TIME_SECONDS,
        colors: int | str = 256,
        max_size_kb: int | None = None,
        overlay: TextOverlay | None = None,
        shared_palette: bool = False,
        max_color_error: float = DEFAULT_MAX_COLOR_ERROR,
        progress: Callable[[int, int], None] | None = None,
    ):
        """
        Uploads a GIF file to the device. It is shown right away, unless a slot is given.

        Args:
            file_path (str): path to the image file
            resize_mode (ResizeMode): The mode to resize the image.
            palletize (bool): Whether to convert the image to a color palette. Usually bad for images with
                high detail (like photos) but good for pixel-art or other content with high contrasts. Defaults to True.
            background_color (Tuple[int, int, int]): RGB color to fill transparent pixels. Defaults to black (0, 0, 0).
            duration_per_frame_in_ms (int, optional): Duration of each frame in milliseconds. If not provided, every frame keeps the duration it has in the GIF file (100 ms if it has none).
            slot (int, optional): If given (0 to 11), the GIF is stored in that slot of the device instead of being shown
                right away. The device cycles through the stored items by itself, see `MaterialsModule`.
            display_time (int): Seconds the stored item stays on screen in that cycle. Only used with a slot.
            colors (int | str): The number of colors of the palette (2 to 256), or "auto". Fewer colors make the
                upload smaller and
                faster (16 colors are about a third of the size of 256 for a photo-like animation), at the price of
                rougher colors. Less than 256 reduces the colors even if `palletize` is off.
            max_size_kb (int, optional): The most the converted GIF may have, which is what is transferred (a large
                one takes 10 s or more). If it is bigger, quality is given up until it fits, in this order: frames
                (every 2nd, 3rd, ... frame, the animation takes as long as before), then colors (down to 8). With
                colors="auto" this starts from the palette that `auto` chose. If it still does not fit the smallest
                version is used and a warning is logged.
            overlay (TextOverlay, optional): A text that is drawn on top of every frame, f.e. to label it.
            shared_palette (bool): One palette for all frames instead of one for each, which can flicker when the
                colors differ from frame to frame (it also changes the colors a little more). Not for "auto".
            max_color_error (float): With colors="auto": the GIF with the fewest bytes whose color error is at most
                this is used. The error is the mean color difference to the GIF with 256 colors (delta E) plus 8 times the
                flicker. On a 64x64 up to 5 looks good, up to 9 is still acceptable but duller, more looks broken
                (about 3 is nearly lossless). The palette sizes 256 to 16 are tried, with a palette for each frame
                and with a shared one.
            progress (Callable[[int, int], None], optional): Called with (chunks sent, chunks in total) while the GIF
                is transferred, each time the device has acknowledged a chunk of 4096 bytes. It is called after the
                conversion, which can take a few seconds for a long animation.
        """
        if colors != AUTO_COLORS:
            validate_colors(colors)
        if max_size_kb is not None and (isinstance(max_size_kb, bool) or not isinstance(max_size_kb, int)
                                        or max_size_kb < 1):
            raise ValueError(f"max_size_kb must be a positive number, got: {max_size_kb!r}")
        if slot is not None:
            validate_slot(slot)
            validate_display_time(display_time)
        screen_width = self.screen_size.value[0]  # assuming square canvas, so width == height
        background_color = color_utils.parse_color_rgb(background_color)

        # reading and converting the file takes a while, the event loop must not be blocked
        gif_data = await asyncio.to_thread(
            self._load_gif_and_adapt_to_canvas,
            file_path=file_path,
            canvas_size=screen_width,
            resize_mode=resize_mode,
            palletize=palletize,
            background_color=background_color,
            duration_per_frame_in_ms=duration_per_frame_in_ms,
            colors=colors,
            max_size_kb=max_size_kb,
            overlay=overlay,
            shared_palette=shared_palette,
            max_color_error=max_color_error,
        )

        # If the device already has the exact same GIF stored, it answers the first chunk with "finished"
        # and skips the rest of the upload, which is why uploading the same file twice is fast.

        packets = self.create_gif_data_packets(
            gif_data=gif_data,
            # TODO: figure out what this does
            #  this might be the index that this GIF will be stored within the device's memory :think:
            #  it doesn't seem to have an effect when sending a single GIF like it is done here though
            # shows the GIF right away, like the official app does
            gif_type=INDEX_SHOW_NOW if slot is None else slot,
            time_sign=0,
            display_time=None if slot is None else display_time,
        )
        await self._send_packets(packets=packets, response=True, wait_for_ack=True, progress=progress)

    async def clear_storage(self) -> None:
        """
        Deletes all materials that are stored on the device. This is the command the official app
        sends when the user deletes the materials on the device. Not verified on a real device yet.

        Uploading a GIF the device already has is fast, because the device skips the transfer.
        """
        data = build_command(protocol.DELETE_MATERIALS, 12, 0, *range(1, 12))
        await self._send_bytes(data=data, response=True)

    def _load_gif_and_adapt_to_canvas(
        self,
        file_path: PathLike | str,
        canvas_size: int,
        resize_mode: ResizeMode,
        palletize: bool = True,
        background_color: Tuple[int, int, int] = (0, 0, 0),
        duration_per_frame_in_ms: int = None,
        colors: int | str = 256,
        max_size_kb: int | None = None,
        overlay: TextOverlay | None = None,
        shared_palette: bool = False,
        max_color_error: float = DEFAULT_MAX_COLOR_ERROR,
    ) -> bytes:
        """
        Loads a GIF file and adapts it to the pixel size of the device's canvas.

        Args:
            file_path (PathLike): Path to the GIF file.
            canvas_size (int): Size of the pixel in the device's canvas.
            resize_mode (ResizeMode): The mode to resize the image. Options are:
                - ResizeMode.FIT: Resize to fit within the canvas while maintaining aspect ratio.
                - ResizeMode.FILL: Resize to fill the canvas, may crop the image.
                - ResizeMode.STRETCH: Stretch the image to fit the canvas, may distort the image.
                - ResizeMode.CROP: Crop the image to fit the canvas without resizing.
            palletize (bool): Whether to convert the image to a color palette. Defaults to True.
            background_color (Tuple[int, int, int]): Background color to fill transparent pixels.
            duration_per_frame_in_ms (int, optional): Duration of each frame in milliseconds. If not provided, every frame keeps the duration it has in the GIF file (100 ms if it has none).
            colors (int): The number of colors of the palette (2 to 256).
            max_size_kb (int, optional): The size the GIF may have at most, see `upload_gif_file`.
            overlay (TextOverlay, optional): A text that is drawn on top of every frame.
            shared_palette (bool): One palette for all frames.
            max_color_error (float): The limit for colors="auto", see `upload_gif_file`.
        Returns:
            bytes: A byte representation of the GIF file, adapted to fit the pixel size.
        """
        from PIL import GifImagePlugin
        GifImagePlugin.LOADING_STRATEGY = GifImagePlugin.LoadingStrategy.RGB_AFTER_DIFFERENT_PALETTE_ONLY

        with PILImage.open(file_path) as img:
            frames = []
            source_durations = []
            try:
                # The official app sends GIFs unchanged, with all frames and the delay of each frame, and the device
                # plays 128 frames in the original speed. How big the upload gets is up to `max_size_kb`.
                while True:
                    source_durations.append(img.info.get("duration"))
                    frame = img.copy()

                    if frame.size != (canvas_size, canvas_size):
                        # needs to use NEAREST to to avoid color distortion
                        resample_mode = PILImage.Resampling.NEAREST
                        frame = image_utils.resize_image(
                            image=frame,
                            canvas_size=canvas_size,
                            resize_mode=resize_mode,
                            resample_mode=resample_mode,
                            background_color=background_color,
                            mode="RGBA",
                        )
                    if overlay is not None:
                        frame = overlay.apply(frame)

                    frames.append(frame.copy())
                    img.seek(img.tell() + 1)
            except EOFError:
                pass


        durations = self._frame_durations(source_durations, duration_per_frame_in_ms)

        shared = shared_palette
        if colors == AUTO_COLORS:
            data, colors, shared = self._encode_gif_auto(frames, durations, max_color_error)
            if max_size_kb is None or len(data) <= max_size_kb * 1024:
                return data
            palletize = True
        if max_size_kb is None:
            return self._encode_gif(frames, durations, colors, palletize, shared)
        return self._encode_gif_within(frames, durations, colors, palletize, max_size_kb, shared)

    @staticmethod
    def _reduce_colors(
        frames: List[PILImage.Image], colors: int, palletize: bool, shared: bool = False
    ) -> List[PILImage.Image]:
        """Gives the frames a palette of `colors` colors, one for each frame or a shared one."""
        if shared:
            return image_utils.palettize_together(frames, colors=colors)
        if palletize or colors < 256:
            return [image_utils.palettize(frame, colors=colors) for frame in frames]
        return frames

    @staticmethod
    def _save_gif(frames: List[PILImage.Image], durations: List[int], colors: int) -> bytes:
        """Writes the frames as a GIF whose frames all have a color table of the same size."""
        # all frames need color tables of the same size, or the device garbles / drops frames
        table_size = image_utils.palette_table_size(colors)
        frames = [image_utils.pad_palette(frame, table_size) for frame in frames]

        gif_buffer = io.BytesIO()
        # take the first frame, append the rest as additional frames and save as GIF into gif_buffer
        frames[0].save(
            gif_buffer,
            format="GIF",
            save_all=True,
            optimize=False,  # True would shrink the color tables to the number of used colors again
            append_images=frames[1:],
            loop=0,  # loop forever
            duration=durations,
            disposal=2,  # Restore to background color after each frame
        )
        gif_buffer.seek(0)
        return gif_buffer.getvalue()

    def _encode_gif(
        self, frames: List[PILImage.Image], durations: List[int], colors: int, palletize: bool,
        shared: bool = False
    ) -> bytes:
        """Encodes the frames as a GIF whose frames all have a color table of the same size."""
        return self._save_gif(self._reduce_colors(frames, colors, palletize, shared), durations, colors)

    def _encode_gif_auto(
        self, frames: List[PILImage.Image], durations: List[int], max_color_error: float
    ) -> Tuple[bytes, int, bool]:
        """
        Finds the GIF with the fewest bytes whose color error (compared to the same GIF with 256 colors for each
        frame) is at most `max_color_error`, among palettes of 256 to 16 colors, for each frame or shared. If none is
        good enough the one with the lowest error is used.
        Returns the GIF, its number of colors and whether the palette is shared.
        """
        # compared to the GIF with all colors, which is what the limit was calibrated on
        reference = [frame.convert("RGB") for frame in self._reduce_colors(frames, 256, True)]
        best = None  # (size, data, colors, shared) of the smallest that is good enough
        closest = None  # (score, data, colors, shared)
        for colors in AUTO_COLOR_STEPS:
            for shared in (False, True):
                reduced = self._reduce_colors(frames, colors, True, shared)
                data = self._save_gif(reduced, durations, colors)
                score = color_score(*color_error(reference, [frame.convert("RGB") for frame in reduced]))
                if score <= max_color_error and (best is None or len(data) < best[0]):
                    best = (len(data), data, colors, shared)
                if closest is None or score < closest[0]:
                    closest = (score, data, colors, shared)
        if best is not None:
            _, data, colors, shared = best
        else:
            score, data, colors, shared = closest
            self.logging.warning(
                f"no palette is within the color error {max_color_error}, using the best ({score:.1f})")
        self.logging.info(f"{colors} colors{', shared palette' if shared else ''} ({len(data) / 1024:.0f} KB)")
        return data, colors, shared

    def _encode_gif_within(
        self,
        frames: List[PILImage.Image],
        durations: List[int],
        colors: int,
        palletize: bool,
        max_size_kb: int,
        shared: bool = False,
    ) -> bytes:
        """
        Encodes the frames as a GIF of at most `max_size_kb` KB if that is possible, by taking the first of
        `_size_reductions` that fits, and the smallest one otherwise.
        """
        limit = max_size_kb * 1024
        smallest = None
        for step_colors, every in self._size_reductions(colors, len(frames)):
            kept, kept_durations = self._thin_out(frames, durations, every)
            data = self._encode_gif(kept, kept_durations, step_colors, palletize, shared)
            if len(data) <= limit:
                if (step_colors, every) != (colors, 1):
                    self.logging.info(
                        f"GIF reduced to {step_colors} colors and every {every}. frame to fit {max_size_kb} KB "
                        f"({len(data) / 1024:.0f} KB)")
                return data
            if smallest is None or len(data) < len(smallest):
                smallest = data
        self.logging.warning(f"GIF does not fit {max_size_kb} KB, using the smallest version ({len(smallest) / 1024:.0f} KB)")
        return smallest

    @staticmethod
    def _size_reductions(colors: int, frame_count: int) -> List[Tuple[int, int]]:
        """
        What to give up to make a GIF smaller: first frames (every second, third, ... frame, the duration of the
        animation stays the same), and only when that does not suffice colors, down to 8, with the fewest frames
        (fewer colors are what looks worst). Returns (colors, keep every n-th frame), starting with what was asked for.
        """
        every_steps = [n for n in (2, 3, 4, 6, 8) if frame_count // n >= 2]
        steps = [(colors, n) for n in [1] + every_steps]
        fewest_frames = every_steps[-1] if every_steps else 1
        steps += [(fewer, fewest_frames) for fewer in (128, 64, 32, 16, 8) if fewer < colors]
        return steps

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
        ble_device_mtu_enabled: bool = True,
        display_time: int | None = None,
    ) -> list[list[bytearray]]:
        """
        Creates packets for sending GIF data, mirroring the Java GifAgreement logic.

        Args:
            gif_data: The raw byte array of the GIF data.
            gif_type: The type parameter (e.g., 12 or other values from sendImageData). Values up until 19 display an image on the device.
            time_sign: 0: "0", 1: "10", 2: "30", 3: "60", 4: "300", else: "5".
            display_time: The display time in seconds. If given it is used instead of the one `time_sign` stands for.
            ble_device_mtu_enabled: Boolean indicating if MTU is enabled on the BLE device.

        Returns:
            A list of lists of byte arrays. The outer list represents "4K chunks with headers",
            and the inner lists contain the actual BLE packets for each of those chunks.
        """
        send_data_3 = []

        if not gif_data:
            raise ValueError("gif_data cannot be empty or None.")

        # Calculate CRC32 for the entire GIF data
        # Ensure this CRC32 matches the Java CrcUtils.CRC32.CRC32 implementation
        crc32_val = self.calculate_crc32_java_equivalent(gif_data)
        crc32_bytes = self._int_to_bytes_le(crc32_val)  # Little-endian int (4 bytes)

        # Get the total length of the GIF data as bytes
        total_length_bytes = self._int_to_bytes_le(len(gif_data))  # Little-endian int (4 bytes)

        # 1. Chunk the gif_data into 4096-byte chunks
        chunks_4096 = self._chunk_data_by_size(gif_data, CHUNK_SIZE_4096)

        processed_large_packets_with_headers = []
        for i, current_chunk in enumerate(chunks_4096):
            packet_data_length = len(current_chunk) + HEADER_SIZE_GIF
            packet_data_length_bytes_be = bytearray(self._int_to_bytes_le(packet_data_length))

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
                # 'time_sign' passed to create_gif_data_packets is the input_key
                converted_time_value = display_time if display_time is not None else convert_display_time(time_sign)

                # little endian, like every other number of the header (the app does the same)
                header[13:15] = converted_time_value.to_bytes(2, byteorder='little')

            header[15] = gif_type & 0xFF  # Ensure it's a byte

            large_packet_with_header = bytes(header) + current_chunk
            processed_large_packets_with_headers.append(large_packet_with_header)

        # 3. Split each "large packet with header" into smaller BLE packets
        for i, large_packet in enumerate(processed_large_packets_with_headers):
            ble_packets_for_chunk = self._create_ble_packets(large_packet, ble_device_mtu_enabled)
            if ble_packets_for_chunk:
                send_data_3.append(ble_packets_for_chunk)

        return send_data_3

    @staticmethod
    def _create_ble_packets(data_packet: bytes, ble_device_mtu_enabled: bool = True) -> list[bytearray]:
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
    def _frame_durations(source_durations: List[int | None], override: int | None) -> List[int]:
        """The duration of every frame in ms: the given one for all frames, or the delay each frame has in the file."""
        if override is not None:
            return [override] * len(source_durations)
        durations = []
        for duration in source_durations:
            if not isinstance(duration, int) or duration <= 10:
                duration = DEFAULT_DURATION_PER_FRAME_MS
            durations.append(max(duration, MIN_DURATION_PER_FRAME_MS))
        return durations

    @staticmethod
    def _thin_out(
        frames: List[PILImage.Image], durations: List[int], every: int
    ) -> Tuple[List[PILImage.Image], List[int]]:
        """Keeps every n-th frame and adds the durations of the ones left out to it, so the loop takes as long as before."""
        if every == 1:
            return frames, durations
        return (
            frames[::every],
            [sum(durations[start:start + every]) for start in range(0, len(frames), every)],
        )
