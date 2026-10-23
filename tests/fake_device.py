from idotmatrix.connection_manager import ConnectionManager
from tests import TestBase
from tests.fake_transport import FakeTransport

ADDRESS = "00:11:22:33:44:55"


class FakeDeviceTestBase(TestBase):
    """Tests a `ConnectionManager` against a simulated device (`self.transport`)."""

    def setUp(self):
        self.transport = FakeTransport(address=ADDRESS)
        self.transports = []

        def factory(address, on_disconnected):
            self.transport.address = address
            self.transport.on_disconnected = on_disconnected
            self.transports.append(self.transport)
            return self.transport

        self.transport_factory = factory
        self.under_test = ConnectionManager(address=ADDRESS, transport_factory=factory)

    @property
    def events(self):
        return self.transport.events

    @property
    def replies(self):
        return self.transport.replies

    @replies.setter
    def replies(self, value):
        self.transport.replies = value
