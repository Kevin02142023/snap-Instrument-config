import pytest

from instruments import discovery
from instruments.base import InstrumentError


def test_tcpip_ips_extracts_inst0_addresses():
    resources = (
        "TCPIP0::169.254.1.100::inst0::INSTR",
        "ASRL25::INSTR",
        "USB0::0x0699::0x040C::C000001::INSTR",
        "TCPIP0::192.168.1.20::5000::SOCKET",
    )
    assert discovery.tcpip_ips(resources) == ["169.254.1.100"]


def test_tcpip_ips_keeps_multiple_and_hostnames():
    resources = (
        "TCPIP0::192.168.1.20::inst0::INSTR",
        "TCPIP1::TEK_MSO58.local::inst0::INSTR",
    )
    assert discovery.tcpip_ips(resources) == ["192.168.1.20", "TEK_MSO58.local"]


def test_tcpip_ips_empty_inputs():
    assert discovery.tcpip_ips(()) == []
    assert discovery.tcpip_ips(("ASRL25::INSTR",)) == []


class _FakeManager:
    def __init__(self, resources=(), fail=False):
        self.resources = resources
        self.fail = fail
        self.closed = False

    def list_resources(self):
        if self.fail:
            raise OSError("VISA 扫描错误")
        return self.resources

    def close(self):
        self.closed = True


def test_list_resources_returns_tuple_and_closes_manager(monkeypatch):
    manager = _FakeManager(resources=["TCPIP0::192.168.1.20::inst0::INSTR"])
    monkeypatch.setattr(discovery, "_make_manager", lambda: manager)
    assert discovery.list_resources() == ("TCPIP0::192.168.1.20::inst0::INSTR",)
    assert manager.closed


def test_list_resources_wraps_scan_failure(monkeypatch):
    monkeypatch.setattr(
        discovery, "_make_manager", lambda: _FakeManager(fail=True))
    with pytest.raises(InstrumentError):
        discovery.list_resources()


def test_list_resources_wraps_backend_failure(monkeypatch):
    def boom():
        raise OSError("无可用 VISA 后端")

    monkeypatch.setattr(discovery, "_make_manager", boom)
    with pytest.raises(InstrumentError):
        discovery.list_resources()
