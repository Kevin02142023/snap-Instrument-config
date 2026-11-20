import re

from instruments.base import InstrumentError

# 形如 TCPIP0::169.254.1.100::inst0::INSTR，可直连的 LXI/VXI-11 仪器
_TCPIP_RE = re.compile(r"^TCPIP\d*::([^:]+)::inst0::INSTR$", re.IGNORECASE)


def _make_manager():
    import pyvisa

    try:
        return pyvisa.ResourceManager()
    except Exception:
        return pyvisa.ResourceManager("@py")


def list_resources():
    """扫描本机可见的 VISA 资源，返回资源字符串元组。"""
    try:
        manager = _make_manager()
    except Exception as exc:
        raise InstrumentError(f"VISA 资源管理器初始化失败: {exc}") from exc
    try:
        return tuple(manager.list_resources())
    except Exception as exc:
        raise InstrumentError(f"扫描设备失败: {exc}") from exc
    finally:
        try:
            manager.close()
        except Exception:
            pass


def tcpip_ips(resources):
    """从资源字符串中提取可通过 inst0 连接的 TCPIP 地址（IP 或主机名）。"""
    addresses = []
    for resource in resources:
        match = _TCPIP_RE.match(resource.strip())
        if match:
            addresses.append(match.group(1))
    return addresses
