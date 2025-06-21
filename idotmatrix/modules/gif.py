import io
import logging
import zlib
from os import PathLike
from typing import List, Tuple

from PIL import Image as PilImage

from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.modules import IDotMatrixModule
from idotmatrix.screensize import ScreenSize

ANIMATION_MAX_FRAMES = 64  # Maximum number of frames in a GIF animation
DEFAULT_DURATION_PER_FRAME_MS = 200  # Default duration per frame in milliseconds if not specified in the GIF file
ANIMATION_TOTAL_DURATION_LIMIT_MS = 2000
DEFAULT_ANIMATION_TOTAL_DURATION = ANIMATION_TOTAL_DURATION_LIMIT_MS


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
        background_color: Tuple[int, int, int] = (0, 0, 0),
        duration_per_frame_in_ms: int = None,
    ):
        """
        Uploads a GIF file to the device.

        Args:
            file_path (str): path to the image file
            background_color (Tuple[int, int, int]): RGB color to fill transparent pixels. Defaults to black (0, 0, 0).
            duration_per_frame_in_ms (int, optional): Duration of each frame in milliseconds. If not provided, defaults to the duration specified in the GIF file, or 200ms if not set.
        """
        pixel_size = self.screen_size.value[0]  # assuming square canvas, so width == height

        gif_data = self._load_gif_and_adapt_to_canvas(
            file_path=file_path,
            pixel_size=pixel_size,
            background_color=background_color,
            duration_per_frame_in_ms=duration_per_frame_in_ms,
        )

        data = self._create_payloads(gif_data)
        for chunk in data:
            await self.send_bytes(data=chunk, response=True, chunk_size=514)

    def _load_gif_and_adapt_to_canvas(
        self,
        file_path: PathLike | str,
        pixel_size: int,
        background_color: Tuple[int, int, int] = (0, 0, 0),
        duration_per_frame_in_ms: int = None,
    ) -> bytes:
        """
        Loads a GIF file and adapts it to the pixel size of the device's canvas.

        Args:
            file_path (PathLike): Path to the GIF file.
            pixel_size (int): Size of the pixel in the device's canvas.
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
                    if frame.size != (pixel_size, pixel_size):
                        frame = frame.resize(
                            size=(pixel_size, pixel_size),
                            resample=PilImage.Resampling.NEAREST,
                            # needs to use NEAREST to stay within color palette limits
                        )
                    # convert transparent pixels to the background color
                    new_image = PilImage.new(
                        mode="RGBA",
                        size=(pixel_size, pixel_size),
                        color=background_color
                    )
                    new_image.paste(
                        im=frame,
                        box=(0, 0, pixel_size, pixel_size),
                        mask=frame.convert("RGBA")
                    )
                    frame = new_image

                    frames.append(frame.copy())
                    img.seek(img.tell() + 1)
            except EOFError:
                pass

            frames, duration_per_frame_in_ms = self._ensure_reasonable_frame_count(img, frames,
                                                                                   duration_per_frame_in_ms)

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
        duration_per_frame_in_ms: int = None
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
            duration_per_frame_in_ms = img.info.get("duration", DEFAULT_DURATION_PER_FRAME_MS)
            # if the value we get is not reasonable, compute alternative value
            if (
                not isinstance(duration_per_frame_in_ms, int)
                or not duration_per_frame_in_ms
                or duration_per_frame_in_ms <= 0
            ):
                # compute the duration per frame based on the number of frames and the default total duration
                duration_per_frame_in_ms = DEFAULT_ANIMATION_TOTAL_DURATION / len(frames)

            if duration_per_frame_in_ms < 16:
                # make sure the duration is at least 16ms, otherwise the device might not be able to handle it
                duration_per_frame_in_ms = 16

        # make sure the duration of the full animation doesn't exceed (duration_per_frame_in_ms * 64)
        # because otherwise the upload takes a very long time

        if len(frames) * duration_per_frame_in_ms > ANIMATION_TOTAL_DURATION_LIMIT_MS:
            # if the time limit is exceeded, skip frames (except for the first and last one) to stay within the time limit
            number_of_frames_to_keep = int(ANIMATION_TOTAL_DURATION_LIMIT_MS / duration_per_frame_in_ms)
            number_of_frames_to_keep = min(ANIMATION_MAX_FRAMES, number_of_frames_to_keep)
            available_frames = len(frames)

            if number_of_frames_to_keep >= available_frames:
                # if the number of frames to keep is greater than or equal to the available frames, do nothing
                return frames, duration_per_frame_in_ms
            # calculate the step size to skip frames
            step_size = max(1, available_frames // number_of_frames_to_keep)
            frames = [frames[i] for i in range(0, available_frames, step_size)]
            # if the number of frames exceeds the maximum allowed frames, truncate the list
            if len(frames) > ANIMATION_MAX_FRAMES:
                frames = frames[:ANIMATION_MAX_FRAMES]

        print(f"GIF frames: {len(frames)}")
        print(f"GIF duration per frame: {duration_per_frame_in_ms} ms")
        print(f"GIF total duration: {len(frames) * duration_per_frame_in_ms} ms")

        return frames, duration_per_frame_in_ms
