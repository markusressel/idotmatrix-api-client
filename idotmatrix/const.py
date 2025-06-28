# Service: 000000fa-0000-1000-8000-00805f9b34fb (4)
#   Characteristic: 0000fa02-0000-1000-8000-00805f9b34fb (5): Vendor specific
#     Properties: ['write-without-response', 'write']
#     Max Write Without Response Size: 514
#   Characteristic: 0000fa03-0000-1000-8000-00805f9b34fb (8): Vendor specific
#     Properties: ['notify']
#     Max Write Without Response Size: 514
# Service: 00001800-0000-1000-8000-00805f9b34fb (1)
#   Characteristic: 00002a00-0000-1000-8000-00805f9b34fb (2): Device Name
#     Properties: ['read']
#     Max Write Without Response Size: 514
# Service: 0000ae00-0000-1000-8000-00805f9b34fb (128)
#   Characteristic: 0000ae01-0000-1000-8000-00805f9b34fb (129): Vendor specific
#     Properties: ['write-without-response']
#     Max Write Without Response Size: 514
#   Characteristic: 0000ae02-0000-1000-8000-00805f9b34fb (131): Vendor specific
#     Properties: ['notify']
#     Max Write Without Response Size: 514

UUID_CHARACTERISTIC_WRITE_DATA = "0000fa02-0000-1000-8000-00805f9b34fb"
UUID_READ_DATA = "0000fa03-0000-1000-8000-00805f9b34fb"
UUID_NOTIFY = "d44bc439-abfd-45a2-b575-925416129601"

UUID_SERVICE_DEVICE_PROPERTY = "00001800-0000-1000-8000-00805f9b34fb"
UUID_CHARACTERISTIC_DEVICE_PROPERTY = "00002a00-0000-1000-8000-00805f9b34fb"

UUID_READ_CHANNEL = "d44bc439-abfd-45a2-b575-925416129600"
UUID_WRITE_CHANNEL = UUID_READ_CHANNEL

BLUETOOTH_DEVICE_NAME = "IDM-"
