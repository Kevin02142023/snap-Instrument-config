from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class InstrumentError(Exception):
    """仪器通信或配置错误。"""


@dataclass
class ApplyResult:
    total: int = 0
    ok: int = 0
    failed: int = 0
    mismatched: int = 0
    skipped: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    mismatches: list = field(default_factory=list)
    equivalences: list = field(default_factory=list)

    def summary(self):
        return (f"共 {self.total} 项：成功 {self.ok}，"
                f"失败 {self.failed}，回读不一致 {self.mismatched}")


def _default_resource_factory(address):
    import pyvisa

    try:
        rm = pyvisa.ResourceManager()
    except Exception:
        rm = pyvisa.ResourceManager("@py")
    return rm.open_resource(address)


class Instrument(ABC):
    def __init__(self, resource_factory=None, log_callback=None):
        self._resource = None
        self._idn = ""
        self._ip = ""
        self._resource_factory = resource_factory or _default_resource_factory
        self._log_callback = log_callback or (lambda msg: None)

    @property
    def connected(self):
        return self._resource is not None

    @property
    def idn(self):
        return self._idn

    @property
    def ip(self):
        return self._ip

    def connect(self, ip):
        self._ip = ip
        address = f"TCPIP0::{ip}::inst0::INSTR"
        try:
            resource = self._resource_factory(address)
            resource.timeout = 10000
            resource.read_termination = "\n"
            resource.write_termination = "\n"
        except Exception as exc:
            raise InstrumentError(f"连接 {address} 失败: {exc}") from exc
        self._resource = resource
        try:
            self._idn = self._resource.query("*IDN?").strip()
            # 不能以 *OPC? 同步：仪器停在已武装的单次采集时会挂起（真机实测）
            self._resource.write("HEADer 0")
        except Exception as exc:
            self._resource = None
            try:
                resource.close()
            except Exception:
                pass
            raise InstrumentError(f"与仪器初始通信失败: {exc}") from exc

    def disconnect(self):
        if self._resource is not None:
            try:
                self._resource.close()
            except Exception:
                pass
            self._resource = None
            self._idn = ""
            self._ip = ""

    def _require_connected(self):
        if self._resource is None:
            raise InstrumentError("仪器未连接")

    def _log(self, message):
        self._log_callback(message)

    def _write(self, cmd):
        self._require_connected()
        self._log(f">> {cmd}")
        return self._resource.write(cmd)

    def _query(self, cmd):
        self._require_connected()
        self._log(f">> {cmd}")
        response = self._resource.query(cmd).strip()
        self._log(f"<< {response}")
        return response

    def restorable_params(self):
        """可恢复参数清单 [(分组, 参数名, 默认勾选)]。
        基类默认 None：不提供选择清单，GUI 不弹窗、直接全恢复。"""
        return None

    @abstractmethod
    def save_config(self):
        ...

    @abstractmethod
    def apply_config(self, config, selected=None):
        ...
