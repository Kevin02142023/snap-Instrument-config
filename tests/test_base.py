import pytest

from instruments.base import Instrument, InstrumentError
from tests.mock_visa import MockResourceFactory, StatefulMockVisaResource


class _FakeInstrument(Instrument):
    def save_config(self):
        return {}

    def apply_config(self, config):
        return None


def _connected(resource=None):
    resource = resource or StatefulMockVisaResource()
    inst = _FakeInstrument(resource_factory=MockResourceFactory(resource))
    inst.connect("192.168.1.20")
    return inst


def test_connect_sets_idn_and_sends_header_off():
    resource = StatefulMockVisaResource()
    factory = MockResourceFactory(resource)
    inst = _FakeInstrument(resource_factory=factory)
    inst.connect("192.168.1.20")
    assert inst.connected
    assert inst.idn == "TEKTRONIX,MSO54,C000001,SCPY:1.0"
    assert factory.addresses == ["TCPIP0::192.168.1.20::inst0::INSTR"]
    assert "HEADer 0" in resource.written


def test_connect_failure_raises_instrument_error():
    class _FailingFactory:
        def __call__(self, address):
            raise OSError("无法访问")

    inst = _FakeInstrument(resource_factory=_FailingFactory())
    with pytest.raises(InstrumentError):
        inst.connect("1.2.3.4")
    assert not inst.connected


def test_connect_io_failure_closes_resource():
    class _HalfOpenResource:
        def __init__(self):
            self.closed = False

        def __getattr__(self, name):
            raise AttributeError(name)

        def query(self, cmd):
            raise OSError("仪器无响应")

        def close(self):
            self.closed = True

    resource = _HalfOpenResource()
    inst = _FakeInstrument(resource_factory=lambda address: resource)
    with pytest.raises(InstrumentError):
        inst.connect("1.2.3.4")
    assert resource.closed
    assert not inst.connected


def test_disconnect_clears_state():
    inst = _connected()
    inst.disconnect()
    assert not inst.connected
    assert inst.idn == ""
    assert inst.ip == ""


def test_query_write_logging():
    messages = []
    resource = StatefulMockVisaResource()
    inst = _FakeInstrument(
        resource_factory=MockResourceFactory(resource),
        log_callback=messages.append,
    )
    inst.connect("192.168.1.1")
    inst._write("CH1:SCALE 1.0")
    assert inst._query("CH1:SCALE?") == "1.0"
    assert any(">> CH1:SCALE 1.0" in m for m in messages)
    assert any("<< 1.0" in m for m in messages)


def test_io_without_connection_raises():
    with pytest.raises(InstrumentError):
        _FakeInstrument()._write("X")
    with pytest.raises(InstrumentError):
        _FakeInstrument()._query("X?")
