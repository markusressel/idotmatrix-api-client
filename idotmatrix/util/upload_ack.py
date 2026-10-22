from enum import Enum
from typing import Optional

# The device acknowledges every 4096 byte chunk of an image or GIF upload with a notification
# of the form 05 00 <type> 00 <status>. The official app does not send the next chunk before it
# received that acknowledgement.
TYPE_DIY_IMAGE = 0
TYPE_GIF = 1
TYPE_IMAGE = 2


class UploadStatus(Enum):
    NEXT = "next"  # chunk received, send the next one
    FINISHED = "finished"  # the upload is complete (or the device already has the same data stored)
    ERROR = "error"  # the device rejected the data (f.e. not enough space)


def parse_upload_notification(data: bytes | bytearray) -> Optional[UploadStatus]:
    """
    Interprets a notification of the device during an upload.
    Args:
        data: The raw notification.
    Returns:
        The status the notification stands for, or None if it is not related to uploads.
    """
    if len(data) < 5 or data[0] != 5 or data[1] != 0 or data[3] != 0:
        return None

    upload_type, status = data[2], data[4]
    if upload_type == TYPE_DIY_IMAGE:
        if status == 2:
            return UploadStatus.NEXT
        if status in (0, 1):
            return UploadStatus.FINISHED
    elif upload_type in (TYPE_GIF, TYPE_IMAGE):
        if status == 1:
            return UploadStatus.NEXT
        if status == 3:
            return UploadStatus.FINISHED
        if status in (0, 2):
            return UploadStatus.ERROR
    return None
