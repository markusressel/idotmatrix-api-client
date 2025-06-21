import io
import logging
import zlib
from os import PathLike
from typing import List, Tuple

from PIL import Image as PilImage

from idotmatrix.connectionManager import ConnectionManager
from idotmatrix.modules import IDotMatrixModule
from idotmatrix.screensize import ScreenSize


class GifModule(IDotMatrixModule):
    logging = logging.getLogger(__name__)

    def __init__(
        self,
        connection_manager: ConnectionManager,
        screen_size: ScreenSize,
    ) -> None:
        super().__init__(connection_manager=connection_manager)
        self.screen_size = screen_size

    async def upload_gif_file(
        self, file_path: PathLike | str
    ):
        """
        Uploads a GIF file to the device.

        Args:
            file_path (str): path to the image file
        """
        pixel_size = self.screen_size.value[0]  # assuming square canvas, so width == height

        gif_data = self._load_gig_and_adapt_to_canvas(
            file_path=file_path,
            pixel_size=pixel_size,
        )

        data = self._create_payloads(gif_data)
        for chunk in data:
            await self.send_bytes(data=chunk, response=True)

    @staticmethod
    def _load_gig_and_adapt_to_canvas(
        file_path: PathLike | str,
        pixel_size: int,
        background_color: Tuple[int, int, int] = (0, 0, 0),
    ) -> bytes:
        """
        Loads a GIF file and adapts it to the pixel size of the device's canvas.

        Args:
            file_path (PathLike): Path to the GIF file.
            pixel_size (int): Size of the pixel in the device's canvas.
        Returns:
            bytes: A byte representation of the GIF file, adapted to fit the pixel size.
        """
        with PilImage.open(file_path) as img:
            frames = []
            try:
                # there doesn't seem to be a frame limit, I have seen gifts with 34 frames in the "cloud material".
                # but to be on the safe side, we limit it to 34 frames.
                while True:
                    frame = img.copy()
                    # if the dimensions of the frame are not equal to the pixel size, resize it while maintaining the aspect ratio
                    # and adding a black background if necessary.
                    if frame.size != (pixel_size, pixel_size):
                        frame = frame.resize(
                            (pixel_size, pixel_size),
                            PilImage.Resampling.NEAREST,  # needs to use NEAREST to stay within color palette limits
                        )
                    # convert transparent pixels to the background color
                    new_image = PilImage.new("RGBA", frame.size, background_color)
                    new_image.paste(frame, (0, 0), frame.convert("RGBA"))
                    frame = new_image

                    frames.append(frame.copy())
                    img.seek(img.tell() + 1)
            except EOFError:
                pass

            gif_buffer = io.BytesIO()
            duration_per_frame_in_ms = img.info.get("duration", 200)  # default to 100ms if not set
            # take the first frame, append the rest as additional frames and save as GIF into gif_buffer
            frames[0].save(
                gif_buffer,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                loop=1,
                duration=duration_per_frame_in_ms,
                disposal=2,
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
