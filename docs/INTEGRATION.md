# Embedding the library: Home Assistant and other Bluetooth stacks

The Home Assistant integration [ha-idotmatrix](https://github.com/markusressel/ha-idotmatrix) is built on this library.

By default the library connects with `bleak` itself. If something else owns the Bluetooth stack, like the scanner and
the Bluetooth proxies of Home Assistant, hand over what it found or how to connect:

```python
# a BLEDevice that a scanner found, instead of a MAC address
client = IDotMatrixClient(screen_size=ScreenSize.SIZE_64x64, ble_device=ble_device)

# or provide the whole connection, by implementing `idotmatrix.transport.Transport`
client = IDotMatrixClient(
    screen_size=ScreenSize.SIZE_64x64,
    mac_address="00:11:22:33:44:55",
    transport_factory=lambda address_or_device, on_disconnected: MyTransport(address_or_device, on_disconnected),
)
```

Turn off `install_signal_handlers` if your application handles SIGINT and SIGTERM itself, otherwise the client
replaces the handlers of the event loop to close the connection on exit. To connect with `bleak-retry-connector`
(Bluetooth proxies), create the transport yourself: `BleakTransport(address_or_device, on_disconnected, connector=...)`
where the connector is an async function that returns a connected `BleakClient`, like `establish_connection`.

`ConnectionManager.set_device(ble_device)` hands over a newer `BLEDevice` later. An established connection stays, the
new one is used for the next connection. A `Transport` has to write to the device, deliver its notifications and call
`on_disconnected` when the link is lost, see `idotmatrix/transport.py` and the `FakeTransport` in `tests/` for an example.
