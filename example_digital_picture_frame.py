import asyncio
import logging
from pathlib import Path

from idotmatrix.client import IDotMatrixClient
from idotmatrix.digital_picture_frame import DigitalPictureFrame
from idotmatrix.screensize import ScreenSize

# set basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s :: %(levelname)s :: %(name)s :: %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
    handlers=[logging.StreamHandler()],
)
# set log level of bleak
logging.getLogger("bleak").setLevel(logging.WARNING)


def _setup_signal_handlers(client: IDotMatrixClient):
    """
    Sets up signal handlers for graceful shutdown.
    This is useful to ensure that the connection is properly closed when the application is terminated.
    """
    import signal
    async def async_signal_handler():
        """
        Handles the signal to stop the slideshow gracefully.
        """
        await client.disconnect()

    def done_callback(future):
        """
        Callback to handle the completion of the signal handler.
        """
        try:
            future.result()
            logging.info("Signal handler completed, exiting...")
        except Exception as e:
            logging.error(f"Error in signal handler: {e}")
        raise SystemExit(0)

    def signal_handler(signum):
        signame = signal.Signals(signum).name
        logging.info(f'Signal handler called with signal {signame} ({signum})')
        asyncio.ensure_future(async_signal_handler()).add_done_callback(done_callback)

    asyncio.get_event_loop().add_signal_handler(signal.SIGINT, lambda: signal_handler(signal.SIGINT))
    asyncio.get_event_loop().add_signal_handler(signal.SIGTERM, lambda: signal_handler(signal.SIGTERM))


async def main():
    client = IDotMatrixClient(
        screen_size=ScreenSize.SIZE_64x64,
        mac_address="69:36:4C:4C:B6:B7"
    )

    _setup_signal_handlers(client)

    image_folder = Path("/home/markus/pictures/DPF")

    digital_picture_frame = DigitalPictureFrame(
        device_client=client,
        # either input a static list of images or use a folder to watch (see below)
        # images=all_file_paths
        shuffle_images=True,
    )

    digital_picture_frame.watch_folders(
        folders=[image_folder],
        recursive=True,
    )

    await digital_picture_frame.start_slideshow(interval=5)

    logging.info("Digital Picture Frame started. Press Ctrl+C to exit.")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        asyncio.gather(main())
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received, stopping...")
        quit()
    except Exception as e:
        quit()
