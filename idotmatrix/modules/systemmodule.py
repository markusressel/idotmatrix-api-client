import logging
from typing import Union

from cryptography.fernet import Fernet

from idotmatrix.modules import IDotMatrixModule


class SystemModule(IDotMatrixModule):
    """This class contains system calls for the iDotMatrix device."""

    logging = logging.getLogger(__name__)

    async def delete_device_data(self):
        """Deletes the device data and resets it to defaults.
        """
        data = bytearray(
            [
                17,
                0,
                2,
                1,
                12,
                0,
                1,
                2,
                3,
                4,
                5,
                6,
                7,
                8,
                9,
                10,
                11,
            ]
        )
        await self.send_bytes(data=data)

    @staticmethod
    def _encrypt_aes(data: bytes, key: bytes) -> bytes:
        """Encrypts data using AES encryption with the given key.

        Args:
            data (bytes): Data to be encrypted.
            key (bytes): Encryption key.

        Returns:
            bytes: Encrypted data.
        """
        f = Fernet(key)
        encrypted_data = f.encrypt(data)
        return encrypted_data

    async def get_device_location(self):
        """Gets the device location (untested yet). Missing some AES encryption stuff of iDotMatrix to work.
        """
        # TODO: implement Aes encryption according to iDotMatrix Android App
        command = bytearray(
            [
                6,
                76,
                79,
                67,
                65,
                84,
                69,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ]
        )
        key = Fernet.generate_key()
        data = self._encrypt_aes(bytes(command), key)
        await self.send_bytes(data=data)
