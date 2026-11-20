import re

_LEVEL_SET_RE = re.compile(r"^TRIG:A:LEVEL:CH(\d+)\s+(\S+)$", re.IGNORECASE)
_LEVEL_QUERY_RE = re.compile(r"^TRIG:A:LEVEL:CH(\d+)\?$", re.IGNORECASE)
_BARE_LEVEL_SET_RE = re.compile(r"^TRIG:A:LEVEL\s", re.IGNORECASE)


class StatefulMockVisaResource:
    """有状态的模拟示波器：write 设置参数值，query 返回当前值。

    write "HEADer VALUE" 存为 state["HEADER?"] = "VALUE"，
    query "HEADER?" 返回该值，使 保存→应用→回读 可以往返验证。
    未登记的命令 query 返回 "0"。
    readback_map：{命令头: 替换值}，query 命中（不区分大小写）时优先返回
    替换值而非 state 中的值，用于模拟"仪器回读值与写入值格式不同"。

    触发电平（2026-10-12 MSO58B 实测语义）：
    - query "TRIG:A:LEVEL?" 返回各通道电平的分号列表
    - write "TRIG:A:LEVEL:CHn v" 对任意通道有效
    - 不带通道号的 "TRIG:A:LEVEL v"（含整串分号列表）被仪器静默忽略
    """

    def __init__(self, state=None, fail_on=(), readback_map=None):
        self.timeout = None
        self.read_termination = None
        self.write_termination = None
        self.written = []
        self.fail_on = tuple(cmd.upper() for cmd in fail_on)
        self.readback_map = {k.upper(): v for k, v in (readback_map or {}).items()}
        self.trig_levels = ["1.0E+00"] * 8
        self.state = {
            "*IDN?": "TEKTRONIX,MSO54,C000001,SCPY:1.0",
            "*OPC?": "1",
        }
        if state:
            self.state.update({k.upper(): v for k, v in state.items()})

    def write(self, cmd):
        cmd = cmd.strip()
        self.written.append(cmd)
        for bad in self.fail_on:
            if bad in cmd.upper():
                raise OSError(f"模拟IO错误: {cmd}")
        if _BARE_LEVEL_SET_RE.match(cmd):
            return  # 真机忽略不带通道号的电平写入
        match = _LEVEL_SET_RE.match(cmd)
        if match:
            channel = int(match.group(1))
            if 1 <= channel <= len(self.trig_levels):
                self.trig_levels[channel - 1] = match.group(2)
            return
        head, _, value = cmd.partition(" ")
        self.state[head.upper() + "?"] = value

    def query(self, cmd):
        cmd = cmd.strip()
        self.written.append(cmd)
        for bad in self.fail_on:
            if bad in cmd.upper():
                raise OSError(f"模拟IO错误: {cmd}")
        key = cmd.upper()
        if key in self.readback_map:
            return self.readback_map[key] + "\n"
        if key == "TRIG:A:LEVEL?":
            return ";".join(self.trig_levels) + "\n"
        match = _LEVEL_QUERY_RE.match(cmd)
        if match:
            channel = int(match.group(1))
            if 1 <= channel <= len(self.trig_levels):
                return self.trig_levels[channel - 1] + "\n"
        return self.state.get(key, "0") + "\n"

    def close(self):
        pass


class MockResourceFactory:
    """把固定 resource 返回给 Instrument 的工厂，记录传入的 VISA 地址。"""

    def __init__(self, resource):
        self.resource = resource
        self.addresses = []

    def __call__(self, address):
        self.addresses.append(address)
        return self.resource
