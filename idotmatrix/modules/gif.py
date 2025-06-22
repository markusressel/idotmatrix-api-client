import io
import logging
import zlib
from os import PathLike
from typing import List, Tuple

from PIL import Image as PilImage

from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.modules import IDotMatrixModule
from idotmatrix.screensize import ScreenSize

ANIMATION_MAX_FRAME_COUNT = 64  # Maximum number of frames in a GIF animation
DEFAULT_DURATION_PER_FRAME_MS = 200  # Default duration per frame in milliseconds if not specified in the GIF file
ANIMATION_TOTAL_DURATION_LIMIT_MS = 2000
DEFAULT_ANIMATION_TOTAL_DURATION_MS = ANIMATION_TOTAL_DURATION_LIMIT_MS


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
        background_color: Tuple[int, int, int] = (0, 0, 0),
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
            await self.send_bytes(data=chunk, response=True, chunk_size=514)

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
                            resample=PilImage.Resampling.NEAREST,
                            # needs to use NEAREST to stay within color palette limits
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
                        # use color palette to improve readability and compatibility
                        new_image = new_image.convert('P', palette=PilImage.Palette.ADAPTIVE)
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
