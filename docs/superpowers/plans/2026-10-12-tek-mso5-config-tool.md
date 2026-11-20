# TekSnapConfig（泰克5系示波器配置快照工具）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一个 Python + Tkinter 桌面工具，通过 LAN 连接泰克 5 系示波器（MSO54/56/58），支持一键保存当前配置为 json、加载历史 json、把 json 配置应用回示波器。

**Architecture:** 三层结构：`instruments/`（pyvisa 通信 + 白名单 SCPI 命令表 + 保存/应用逻辑）、`core/`（json 存取）、`gui/`（Tkinter 界面，仪器 IO 走后台线程）。仪器抽象基类支持依赖注入（resource_factory）以便全部用 mock 测试。

**Tech Stack:** Python 3.14、pyvisa + pyvisa-py（LAN/VISA-TCPIP）、Tkinter、pytest。

**设计文档:** `docs/superpowers/specs/2026-10-12-tek-mso5-config-tool-design.md`（SCPI 命令已对照官方手册 077-1305-03 验证）

**多 agent 并行分组:**
- Phase 1（串行，必须先完成）: Task 1
- Phase 2（两个 agent 并行）: Agent A = Task 2；Agent B = Task 3 → Task 4 → Task 5（串行）
- Phase 3（Phase 2 全部完成后）: Agent C = Task 6 → Task 7

**环境注意:** Windows + Git Bash；测试命令统一用 `python -m pytest`；Python 位于 `C:\Python314\python.exe`（3.14.5，pyvisa/pytest 均未预装）。

---

### Task 1: 环境与项目骨架

**Files:**
- Create: `requirements.txt`
- Create: `instrument_config/__init__.py` 等空包文件（见步骤）

- [ ] **Step 1: 安装依赖**

Run: `pip install pyvisa pyvisa-py pytest`
Expected: 全部安装成功，无报错

- [ ] **Step 2: 验证 pyvisa 可用**

Run: `python -c "import pyvisa, pyvisa_py; print(pyvisa.__version__)"`
Expected: 输出版本号（如 1.7.x），无 ImportError

- [ ] **Step 3: 创建目录与包文件**

在项目根 `D:\WorkDisk\Ai\Pro\A_snap_instr_github项目` 下创建四个包：

```bash
mkdir -p instruments core gui tests
touch instruments/__init__.py core/__init__.py gui/__init__.py tests/__init__.py
```

- [ ] **Step 4: 创建 requirements.txt**

```
pyvisa>=1.6
pyvisa-py>=0.7
pytest>=8.0
```

- [ ] **Step 5: 验证 pytest 空跑**

Run: `python -m pytest tests/ -v`
Expected: `no tests ran`（collected 0 items），无 collection error

- [ ] **Step 6: Commit**

```bash
git add requirements.txt instruments/__init__.py core/__init__.py gui/__init__.py tests/__init__.py .gitignore
git commit -m "chore: 项目骨架与依赖清单"
```

---

### Task 2: core/config_store.py — json 存取（Agent A）

**Files:**
- Create: `core/config_store.py`
- Test: `tests/test_config_store.py`

- [ ] **Step 1: 写失败测试**

`tests/test_config_store.py`：

```python
import json

import pytest

from core import config_store


def test_save_load_roundtrip(tmp_path):
    config = {
        "仪器类型": "示波器",
        "型号": "泰克5系",
        "保存时间": "2026-10-12 15:30:00",
        "示波器": {"1通道参数": {"电压每格": "1.0E+00"}},
    }
    path = tmp_path / "cfg.json"
    config_store.save(path, config)
    assert config_store.load(path) == config


def test_save_writes_utf8_chinese(tmp_path):
    path = tmp_path / "cfg.json"
    config_store.save(path, {"仪器类型": "示波器"})
    text = path.read_text(encoding="utf-8")
    assert '"仪器类型": "示波器"' in text


def test_load_invalid_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(config_store.ConfigError):
        config_store.load(path)


def test_load_missing_keys_raises(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"仪器类型": "示波器"}), encoding="utf-8")
    with pytest.raises(config_store.ConfigError, match="型号"):
        config_store.load(path)


def test_load_non_object_raises(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(config_store.ConfigError):
        config_store.load(path)


def test_default_filename_format():
    name = config_store.default_filename("MSO54")
    assert name.startswith("MSO54_")
    assert name.endswith(".json")
    assert "_" in name[len("MSO54_"):-len(".json")]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_config_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.config_store'`

- [ ] **Step 3: 写实现**

`core/config_store.py`：

```python
import json
from datetime import datetime


class ConfigError(Exception):
    """配置文件读写或格式错误。"""


REQUIRED_KEYS = ("仪器类型", "型号", "保存时间")


def save(path, config):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
    except OSError as exc:
        raise ConfigError(f"写配置文件失败: {exc}") from exc


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"读配置文件失败: {exc}") from exc
    if not isinstance(config, dict):
        raise ConfigError("配置文件顶层必须是 JSON 对象")
    missing = [k for k in REQUIRED_KEYS if k not in config]
    if missing:
        raise ConfigError(f"配置文件缺少必需键: {', '.join(missing)}")
    return config


def default_filename(model):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{model}_{now}.json"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_config_store.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add core/config_store.py tests/test_config_store.py
git commit -m "feat: json 配置存取（UTF-8 中文键、必需键校验）"
```

---

### Task 3: instruments/base.py — 仪器抽象基类（Agent B）

**Files:**
- Create: `instruments/base.py`
- Test: `tests/test_base.py`

- [ ] **Step 1: 写失败测试**

`tests/test_base.py`：

```python
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


def test_disconnect_clears_state():
    inst = _connected()
    inst.disconnect()
    assert not inst.connected
    assert inst.idn == ""


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
```

注：`test_disconnect_clears_state` 里断言 `idn == ""` 需要实现里 disconnect 清空 `_idn`。

- [ ] **Step 2: 先建 mock（test_base 依赖它）**

`tests/mock_visa.py`：

```python
class StatefulMockVisaResource:
    """有状态的模拟示波器：write 设置参数值，query 返回当前值。

    write "HEADer VALUE" 存为 state["HEADER?"] = "VALUE"，
    query "HEADER?" 返回该值，使 保存→应用→回读 可以往返验证。
    未登记的命令 query 返回 "0"。
    """

    def __init__(self, state=None, fail_on=()):
        self.timeout = None
        self.read_termination = None
        self.write_termination = None
        self.written = []
        self.fail_on = tuple(cmd.upper() for cmd in fail_on)
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
        head, _, value = cmd.partition(" ")
        self.state[head.upper() + "?"] = value

    def query(self, cmd):
        cmd = cmd.strip()
        self.written.append(cmd)
        for bad in self.fail_on:
            if bad in cmd.upper():
                raise OSError(f"模拟IO错误: {cmd}")
        return self.state.get(cmd.upper(), "0") + "\n"

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
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python -m pytest tests/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'instruments.base'`

- [ ] **Step 4: 写实现**

`instruments/base.py`：

```python
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
            self._resource.write("HEADer 0")
            self._resource.query("*OPC?")
        except Exception as exc:
            self._resource = None
            raise InstrumentError(f"与仪器初始通信失败: {exc}") from exc

    def disconnect(self):
        if self._resource is not None:
            try:
                self._resource.close()
            except Exception:
                pass
            self._resource = None
            self._idn = ""

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

    @abstractmethod
    def save_config(self):
        ...

    @abstractmethod
    def apply_config(self, config):
        ...
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_base.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add instruments/base.py tests/test_base.py tests/mock_visa.py
git commit -m "feat: 仪器抽象基类（VISA 连接、SCPI 日志、依赖注入）"
```

---

### Task 4: instruments/tek_mso5.py — 泰克5系实现（Agent B）

**Files:**
- Create: `instruments/tek_mso5.py`
- Test: `tests/test_tek_mso5.py`

命令表来源：设计文档 §4.2（已对照官方手册 077-1305-03 验证）。表内顺序即应用顺序。

- [ ] **Step 1: 写失败测试（全部 8 个用例一次写全）**

`tests/test_tek_mso5.py`：

```python
import pytest

from instruments.base import InstrumentError
from instruments.tek_mso5 import TekMSO5
from tests.mock_visa import MockResourceFactory, StatefulMockVisaResource


def _connected(state=None, fail_on=(), idn="TEKTRONIX,MSO54,C000001,SCPY:1.0"):
    resource = StatefulMockVisaResource(state=state, fail_on=fail_on)
    if idn:
        resource.state["*IDN?"] = idn
    scope = TekMSO5(resource_factory=MockResourceFactory(resource))
    scope.connect("192.168.1.20")
    return scope, resource


def test_channel_count_from_idn():
    for idn, expected in [
        ("TEKTRONIX,MSO54,C1,SCPY:1.0", 4),
        ("TEKTRONIX,MSO56,C1,SCPY:1.0", 6),
        ("TEKTRONIX,MSO58,C1,SCPY:1.0", 8),
        ("TEKTRONIX,MSO58LP,C1,SCPY:1.0", 8),
        ("TEKTRONIX,UNKNOWN,C1,SCPY:1.0", 4),
    ]:
        scope, _ = _connected(idn=idn)
        assert scope.channel_count() == expected


def test_save_config_structure():
    scope, _ = _connected(state={
        "CH1:SCALE?": "1.0E+00",
        "HOR:SCALE?": "1.0E-3",
        "TRIG:A:TYPE?": "EDGE",
    })
    config = scope.save_config()
    assert config["仪器类型"] == "示波器"
    assert config["型号"] == "泰克5系"
    assert config["IP"] == "192.168.1.20"
    assert config["IDN"] == "TEKTRONIX,MSO54,C000001,SCPY:1.0"
    assert "保存时间" in config
    scope_data = config["示波器"]
    assert list(scope_data.keys()) == [
        "1通道参数", "2通道参数", "3通道参数", "4通道参数",
        "水平", "触发", "采集",
    ]
    assert scope_data["1通道参数"]["电压每格"] == "1.0E+00"
    assert scope_data["水平"]["时间每格"] == "1.0E-3"
    assert scope_data["触发"]["触发类型"] == "EDGE"
    assert scope_data["1通道参数"]["耦合"] == "0"  # mock 默认回应


def test_save_config_io_error_aborts():
    scope, _ = _connected(fail_on=("CH1:SCALE?",))
    with pytest.raises(InstrumentError):
        scope.save_config()


def test_apply_config_roundtrip():
    scope, _ = _connected(state={
        "CH1:SCALE?": "5.0E-01",
        "CH2:SCALE?": "1.0E+00",
        "HOR:MODE?": "MANUAL",
        "HOR:RECORDLENGTH?": "1.0E+06",
        "TRIG:A:TYPE?": "EDGE",
        "TRIG:A:LEVEL?": "1.6E+00",
    })
    config_before = scope.save_config()

    scope2, _ = _connected()  # 全新"仪器"（默认状态）
    result = scope2.apply_config(config_before)
    assert result.failed == 0
    assert result.mismatched == 0
    assert result.total > 0

    config_after = scope2.save_config()
    assert config_after["示波器"] == config_before["示波器"]


def test_apply_config_command_sequence():
    scope, _ = _connected()
    config = scope.save_config()
    scope2, resource2 = _connected()
    scope2.apply_config(config)
    written = resource2.written

    def first_index(prefix):
        return next(i for i, c in enumerate(written) if c.startswith(prefix))

    assert first_index("HOR:MODE ") < first_index("HOR:RECORDLENGTH ")
    assert first_index("TRIG:A:TYPE ") < first_index("TRIG:A:EDGE:SOURCE ")
    assert first_index("TRIG:A:EDGE:SOURCE ") < first_index("TRIG:A:LEVEL ")
    set_idx = first_index("HOR:SCALE ")
    assert written[set_idx + 1] == "*OPC?"  # 每条 set 后同步


def test_apply_config_skips_readonly_and_empty():
    scope, _ = _connected(state={"CH1:LABEL:NAME?": ""})
    config = scope.save_config()
    assert config["示波器"]["1通道参数"]["标注"] == ""

    scope2, resource2 = _connected()
    result = scope2.apply_config(config)
    assert not any(c.upper().startswith("CH1:PRO:GAIN ") for c in resource2.written)
    assert not any(c.upper().startswith("CH1:LABEL:NAME ") for c in resource2.written)
    assert any("只读" in s for s in result.skipped)
    assert any("空值" in s for s in result.skipped)
    assert result.total == result.ok + result.failed + result.mismatched


def test_apply_config_single_failure_continues():
    scope, _ = _connected()
    config = scope.save_config()
    # 只让 CH1 的 SCALE 写入失败（带尾空格避免匹配查询命令）
    scope2, _ = _connected(fail_on=("CH1:SCALE ",))
    result = scope2.apply_config(config)
    assert result.failed == 1
    assert result.total > 1
    assert result.ok > 0
    assert len(result.errors) == 1


def test_apply_config_missing_scope_raises():
    scope, _ = _connected()
    with pytest.raises(InstrumentError):
        scope.apply_config({"仪器类型": "示波器"})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_tek_mso5.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'instruments.tek_mso5'`

- [ ] **Step 3: 写实现**

`instruments/tek_mso5.py`：

```python
from datetime import datetime

from instruments.base import ApplyResult, Instrument, InstrumentError

# (中文键, query模板, set模板|None=只读) —— 表顺序即应用顺序
CHANNEL_PARAMS = [
    ("开关", "DISplay:GLObal:CH{ch}:STATE?", "DISplay:GLObal:CH{ch}:STATE {v}"),
    ("电压每格", "CH{ch}:SCALE?", "CH{ch}:SCALE {v}"),
    ("垂直位置", "CH{ch}:POSITION?", "CH{ch}:POSITION {v}"),
    ("偏移", "CH{ch}:OFFSET?", "CH{ch}:OFFSET {v}"),
    ("耦合", "CH{ch}:COUPLING?", "CH{ch}:COUPLING {v}"),
    ("带宽限制", "CH{ch}:BANDWIDTH?", "CH{ch}:BANDWIDTH {v}"),
    ("反相", "CH{ch}:INVERT?", "CH{ch}:INVERT {v}"),
    ("探头衰减", "CH{ch}:PRO:GAIN?", None),  # Query Only：由接入的物理探头决定
    ("标注", "CH{ch}:LABEL:NAME?", "CH{ch}:LABEL:NAME {v}"),
]

GLOBAL_PARAMS = {
    "水平": [
        # 手册要求：改记录长度前水平模式须为 MANUAL，故 MODE 在前
        ("水平模式", "HOR:MODE?", "HOR:MODE {v}"),
        ("时间每格", "HOR:SCALE?", "HOR:SCALE {v}"),
        ("水平位置", "HOR:POSITION?", "HOR:POSITION {v}"),
        ("记录长度", "HOR:RECORDLENGTH?", "HOR:RECORDLENGTH {v}"),
    ],
    "触发": [
        # 触发类型须先于源/斜率/电平设置
        ("触发类型", "TRIG:A:TYPE?", "TRIG:A:TYPE {v}"),
        ("触发源", "TRIG:A:EDGE:SOURCE?", "TRIG:A:EDGE:SOURCE {v}"),
        ("触发斜率", "TRIG:A:EDGE:SLOPE?", "TRIG:A:EDGE:SLOPE {v}"),
        ("触发电平", "TRIG:A:LEVEL?", "TRIG:A:LEVEL {v}"),
        ("触发模式", "TRIG:A:MODE?", "TRIG:A:MODE {v}"),
    ],
    "采集": [
        ("采集模式", "ACQ:MODE?", "ACQ:MODE {v}"),
        ("停止条件", "ACQ:STOPAFTER?", "ACQ:STOPAFTER {v}"),
    ],
}

MODEL_CHANNELS = {"MSO54": 4, "MSO56": 6, "MSO58": 8, "MSO58LP": 8}


class TekMSO5(Instrument):
    """泰克 5 系示波器（MSO54/56/58/58LP 等）。"""

    instrument_type = "示波器"
    model_name = "泰克5系"

    def channel_count(self):
        model = self._idn.split(",")[1].strip().upper() if "," in self._idn else ""
        for name, count in MODEL_CHANNELS.items():
            if model.startswith(name):
                return count
        return 4

    def save_config(self):
        self._require_connected()
        count = self.channel_count()
        scope = {}
        for ch in range(1, count + 1):
            group = {}
            for key, query_tpl, _ in CHANNEL_PARAMS:
                cmd = query_tpl.format(ch=ch)
                try:
                    group[key] = self._query(cmd)
                except Exception as exc:
                    raise InstrumentError(f"查询 {cmd} 失败: {exc}") from exc
            scope[f"{ch}通道参数"] = group
        for group_name, params in GLOBAL_PARAMS.items():
            group = {}
            for key, query_tpl, _ in params:
                try:
                    group[key] = self._query(query_tpl)
                except Exception as exc:
                    raise InstrumentError(f"查询 {query_tpl} 失败: {exc}") from exc
            scope[group_name] = group
        return {
            "仪器类型": self.instrument_type,
            "型号": self.model_name,
            "IDN": self._idn,
            "IP": self._ip,
            "保存时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "示波器": scope,
        }

    def apply_config(self, config):
        self._require_connected()
        scope = config.get("示波器")
        if not isinstance(scope, dict):
            raise InstrumentError("配置缺少 '示波器' 部分")

        # 按命令表顺序展开执行项: (中文路径, query模板, set模板, 值, 通道号|None)
        items = []
        for ch in range(1, self.channel_count() + 1):
            group = scope.get(f"{ch}通道参数", {})
            for key, query_tpl, set_tpl in CHANNEL_PARAMS:
                if key in group:
                    items.append((f"{ch}通道参数.{key}", query_tpl, set_tpl, group[key], ch))
        for group_name, params in GLOBAL_PARAMS.items():
            group = scope.get(group_name, {})
            for key, query_tpl, set_tpl in params:
                if key in group:
                    items.append((f"{group_name}.{key}", query_tpl, set_tpl, group[key], None))

        result = ApplyResult()
        written = []
        for path, query_tpl, set_tpl, value, ch in items:
            if set_tpl is None:
                result.skipped.append(f"{path}: 只读参数，跳过")
                continue
            if not value:
                result.skipped.append(f"{path}: 空值，跳过")
                continue
            result.total += 1
            cmd = set_tpl.format(ch=ch, v=value)
            try:
                self._write(cmd)
                self._query("*OPC?")
            except Exception as exc:
                result.failed += 1
                result.errors.append(f"{path}: 写入 {cmd} 失败: {exc}")
                continue
            written.append((path, query_tpl, value, ch))

        for path, query_tpl, value, ch in written:
            try:
                actual = self._query(query_tpl.format(ch=ch))
            except Exception as exc:
                result.mismatched += 1
                result.mismatches.append(f"{path}: 回读失败: {exc}")
                continue
            if actual != value:
                result.mismatched += 1
                result.mismatches.append(f"{path}: 期望 {value!r}，实际 {actual!r}")
            else:
                result.ok += 1
        return result
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_tek_mso5.py -v`
Expected: 8 passed

- [ ] **Step 5: 全量回归**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（含 test_base、test_config_store）

- [ ] **Step 6: Commit**

```bash
git add instruments/tek_mso5.py tests/test_tek_mso5.py
git commit -m "feat: 泰克5系示波器白名单命令表与保存/应用/回读校验"
```

---

### Task 5: instruments/registry.py — 仪器注册表（Agent B）

**Files:**
- Create: `instruments/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: 写失败测试**

`tests/test_registry.py`：

```python
import pytest

from instruments import registry
from instruments.tek_mso5 import TekMSO5

SCOPE_NAME = "示波器 - 泰克 5 系 (MSO54/56/58)"


def test_registry_lists_many_instrument_types():
    names = [item["名称"] for item in registry.INSTRUMENTS]
    assert len(names) >= 5
    assert any("示波器" in n for n in names)
    assert any("信号发生器" in n for n in names)
    assert any("源表" in n for n in names)


def test_exactly_one_available_and_it_is_tek_mso5():
    available = [i for i in registry.INSTRUMENTS if i["可用"]]
    assert len(available) == 1
    assert available[0]["名称"] == SCOPE_NAME
    assert available[0]["cls"] is TekMSO5


def test_get_by_name():
    item = registry.get_by_name(SCOPE_NAME)
    assert item["可用"] is True


def test_get_by_name_unknown_raises():
    with pytest.raises(KeyError):
        registry.get_by_name("不存在的仪器")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'instruments.registry'`

- [ ] **Step 3: 写实现**

`instruments/registry.py`：

```python
from instruments.tek_mso5 import TekMSO5

INSTRUMENTS = [
    {"名称": "示波器 - 泰克 5 系 (MSO54/56/58)", "类别": "示波器", "可用": True, "cls": TekMSO5},
    {"名称": "信号发生器 - 泰克 AFG (开发中)", "类别": "信号发生器", "可用": False, "cls": None},
    {"名称": "源表 - 吉时利 2400/2450 (开发中)", "类别": "源表", "可用": False, "cls": None},
    {"名称": "万用表 - 吉时利 DMM6500 (开发中)", "类别": "万用表", "可用": False, "cls": None},
    {"名称": "频谱分析仪 - (开发中)", "类别": "频谱分析仪", "可用": False, "cls": None},
    {"名称": "逻辑分析仪 - (开发中)", "类别": "逻辑分析仪", "可用": False, "cls": None},
]


def get_by_name(name):
    for item in INSTRUMENTS:
        if item["名称"] == name:
            return item
    raise KeyError(f"未知仪器: {name}")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_registry.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add instruments/registry.py tests/test_registry.py
git commit -m "feat: 仪器注册表（下拉列表数据源，仅泰克5系可用）"
```

---

### Task 6: gui/app.py — Tkinter 主窗口（Agent C）

**Files:**
- Create: `gui/app.py`
- Test: `tests/test_gui.py`

GUI 不做逐控件单测（Tkinter 事件循环难以单测），用冒烟测试：实例化窗口、验证初始状态、销毁。逻辑正确性由 instruments/core 层测试保证。

- [ ] **Step 1: 写失败冒烟测试**

`tests/test_gui.py`：

```python
def test_app_window_smoke():
    from gui.app import AppWindow

    app = AppWindow()
    app.withdraw()  # 不显示窗口
    try:
        assert "TekSnapConfig" in app.title()
        assert app._instrument is None
        assert app._loaded_config is None
        assert app._instrument_box["values"]  # 下拉列表非空
        app.update()  # 处理一轮事件循环
    finally:
        app.destroy()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_gui.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gui.app'`

- [ ] **Step 3: 写实现**

`gui/app.py`：

```python
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import config_store
from core.config_store import ConfigError
from instruments import registry
from instruments.base import InstrumentError


class AppWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("仪器配置快照工具 - TekSnapConfig")
        self.geometry("900x640")
        self._instrument = None
        self._loaded_config = None
        self._busy = False
        self._queue = queue.Queue()
        self._build_widgets()
        self.after(100, self._poll_queue)

    # ---------- 界面 ----------

    def _build_widgets(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="仪器:").pack(side="left")
        self._instrument_var = tk.StringVar(value=registry.INSTRUMENTS[0]["名称"])
        self._instrument_box = ttk.Combobox(
            top, textvariable=self._instrument_var, state="readonly",
            values=[item["名称"] for item in registry.INSTRUMENTS], width=34)
        self._instrument_box.pack(side="left", padx=(4, 12))
        ttk.Label(top, text="IP地址:").pack(side="left")
        self._ip_var = tk.StringVar(value="192.168.1.20")
        ttk.Entry(top, textvariable=self._ip_var, width=16).pack(side="left", padx=(4, 12))
        self._connect_btn = ttk.Button(top, text="连接", command=self._on_connect)
        self._connect_btn.pack(side="left")
        self._disconnect_btn = ttk.Button(top, text="断开", command=self._on_disconnect)
        self._disconnect_btn.pack(side="left", padx=(8, 0))

        info = ttk.Frame(self, padding=(8, 2))
        info.pack(fill="x")
        self._id_label = ttk.Label(info, text="设备ID: 未连接")
        self._id_label.pack(side="left")
        self._status_label = ttk.Label(info, text="状态: 未连接", foreground="gray")
        self._status_label.pack(side="left", padx=16)

        actions = ttk.Frame(self, padding=8)
        actions.pack(fill="x")
        self._save_btn = ttk.Button(actions, text="一键保存配置", command=self._on_save)
        self._save_btn.pack(side="left")
        self._load_btn = ttk.Button(actions, text="加载配置文件", command=self._on_load)
        self._load_btn.pack(side="left", padx=(8, 0))
        self._apply_btn = ttk.Button(actions, text="应用配置到仪器", command=self._on_apply)
        self._apply_btn.pack(side="left", padx=(8, 0))

        preview = ttk.LabelFrame(self, text="配置预览", padding=4)
        preview.pack(fill="both", expand=True, padx=8, pady=4)
        self._tree = ttk.Treeview(preview, columns=("值",), show="tree headings")
        self._tree.heading("#0", text="参数")
        self._tree.heading("值", text="值")
        self._tree.column("#0", width=280)
        self._tree.column("值", width=340)
        tree_scroll = ttk.Scrollbar(preview, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        log_frame = ttk.LabelFrame(self, text="日志", padding=4)
        log_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self._log_text = tk.Text(log_frame, height=10, state="disabled",
                                 font=("Consolas", 9))
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_scroll.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    # ---------- 日志与状态 ----------

    def _log(self, message):
        self._log_text.configure(state="normal")
        self._log_text.insert("end", message + "\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _set_status(self, text, color="black"):
        self._status_label.configure(text=f"状态: {text}", foreground=color)

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for btn in (self._connect_btn, self._disconnect_btn,
                    self._save_btn, self._load_btn, self._apply_btn):
            btn.configure(state=state)

    # ---------- 事件处理 ----------

    def _on_connect(self):
        if self._busy:
            return
        item = registry.get_by_name(self._instrument_var.get())
        if not item["可用"]:
            messagebox.showinfo("提示", "该仪器正在开发中，暂不可用")
            return
        ip = self._ip_var.get().strip()
        if not ip:
            messagebox.showwarning("提示", "请输入仪器 IP 地址")
            return
        instrument = item["cls"](
            log_callback=lambda msg: self._queue.put(("log", msg)))

        def work():
            try:
                instrument.connect(ip)
                self._queue.put(("done", "connect", None, None))
            except InstrumentError as exc:
                self._queue.put(("done", "connect", None, str(exc)))

        self._instrument = instrument
        self._set_busy(True)
        self._set_status("连接中…", "gray")
        self._log(f"== 连接 {ip} ==")
        threading.Thread(target=work, daemon=True).start()

    def _on_disconnect(self):
        if self._busy or self._instrument is None:
            return
        self._instrument.disconnect()
        self._instrument = None
        self._id_label.configure(text="设备ID: 未连接")
        self._set_status("未连接", "gray")
        self._log("== 已断开 ==")

    def _on_save(self):
        if self._busy:
            return
        if self._instrument is None or not self._instrument.connected:
            messagebox.showwarning("提示", "请先连接仪器")
            return

        def work():
            try:
                config = self._instrument.save_config()
                self._queue.put(("done", "save", config, None))
            except InstrumentError as exc:
                self._queue.put(("done", "save", None, str(exc)))

        self._set_busy(True)
        self._set_status("正在读取仪器配置…", "gray")
        threading.Thread(target=work, daemon=True).start()

    def _on_load(self):
        if self._busy:
            return
        path = filedialog.askopenfilename(
            title="选择配置文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            config = config_store.load(path)
        except ConfigError as exc:
            messagebox.showerror("加载失败", str(exc))
            return
        self._loaded_config = config
        self._show_config(config)
        self._set_status(f"已加载 {path}", "green")
        self._log(f"== 已加载配置 {path} ==")

    def _on_apply(self):
        if self._busy:
            return
        if self._instrument is None or not self._instrument.connected:
            messagebox.showwarning("提示", "请先连接仪器")
            return
        if self._loaded_config is None:
            messagebox.showwarning("提示", "请先加载配置文件")
            return

        def work():
            try:
                result = self._instrument.apply_config(self._loaded_config)
                self._queue.put(("done", "apply", result, None))
            except InstrumentError as exc:
                self._queue.put(("done", "apply", None, str(exc)))

        self._set_busy(True)
        self._set_status("正在应用配置…", "gray")
        self._log("== 开始应用配置 ==")
        threading.Thread(target=work, daemon=True).start()

    # ---------- 后台结果处理（主线程） ----------

    def _poll_queue(self):
        try:
            while True:
                message = self._queue.get_nowait()
                if message[0] == "log":
                    self._log(message[1])
                else:
                    _, action, data, error = message
                    handler = {"connect": self._finish_connect,
                               "save": self._finish_save,
                               "apply": self._finish_apply}[action]
                    handler(data, error)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _finish_connect(self, _, error):
        self._set_busy(False)
        if error:
            self._instrument = None
            self._set_status("连接失败", "red")
            messagebox.showerror("连接失败", error)
            return
        self._id_label.configure(text=f"设备ID: {self._instrument.idn}")
        self._set_status("已连接", "green")
        self._log(f"== 已连接: {self._instrument.idn} ==")

    def _finish_save(self, config, error):
        self._set_busy(False)
        if error:
            self._set_status("保存失败", "red")
            messagebox.showerror("保存失败", error)
            return
        model = "SCOPE"
        if self._instrument and "," in self._instrument.idn:
            model = self._instrument.idn.split(",")[1].strip()
        path = filedialog.asksaveasfilename(
            title="保存配置文件", defaultextension=".json",
            initialfile=config_store.default_filename(model),
            filetypes=[("JSON 文件", "*.json")])
        if not path:
            self._set_status("已取消保存", "gray")
            return
        try:
            config_store.save(path, config)
        except ConfigError as exc:
            self._set_status("保存失败", "red")
            messagebox.showerror("保存失败", str(exc))
            return
        self._loaded_config = config
        self._show_config(config)
        self._set_status(f"已保存 {path}", "green")
        self._log(f"== 配置已保存到 {path} ==")

    def _finish_apply(self, result, error):
        self._set_busy(False)
        if error:
            self._set_status("应用失败", "red")
            messagebox.showerror("应用失败", error)
            return
        for line in result.skipped:
            self._log(f"[跳过] {line}")
        for line in result.errors:
            self._log(f"[失败] {line}")
        for line in result.mismatches:
            self._log(f"[不一致] {line}")
        clean = result.failed == 0 and result.mismatched == 0
        self._set_status("应用完成", "green" if clean else "orange")
        self._log(f"== 应用完成: {result.summary()} ==")
        messagebox.showinfo("应用完成", result.summary())

    # ---------- 配置预览 ----------

    def _show_config(self, config):
        self._tree.delete(*self._tree.get_children())
        for key in ("仪器类型", "型号", "IDN", "IP", "保存时间"):
            if key in config:
                self._tree.insert("", "end", text=key, values=(config[key],))
        scope = config.get("示波器", {})
        root = self._tree.insert("", "end", text="示波器", open=True)
        for group_name, group in scope.items():
            gid = self._tree.insert(root, "end", text=group_name, open=True)
            for key, value in group.items():
                self._tree.insert(gid, "end", text=key, values=(value,))
```

- [ ] **Step 4: 跑冒烟测试确认通过**

Run: `python -m pytest tests/test_gui.py -v`
Expected: 1 passed

- [ ] **Step 5: 全量回归**

Run: `python -m pytest tests/ -v`
Expected: 全部通过

- [ ] **Step 6: Commit**

```bash
git add gui/app.py tests/test_gui.py
git commit -m "feat: Tkinter 主界面（后台线程仪器IO、树形预览、SCPI 日志）"
```

---

### Task 7: main.py 入口与集成验收（Agent C）

**Files:**
- Create: `main.py`

- [ ] **Step 1: 写入口**

`main.py`：

```python
import ctypes
import sys

from gui.app import AppWindow


def main():
    try:  # Windows 高分屏下避免界面模糊
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = AppWindow()
    app.mainloop()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 导入冒烟**

Run: `python -c "import main; print('import OK')"`
Expected: 输出 `import OK`（mainloop 不触发）

- [ ] **Step 3: 启动冒烟（自动运行 5 秒后由 timeout 结束）**

Run: `timeout 5 python main.py; echo "exit=$?"`
Expected: `exit=124`（被 timeout 杀掉 = 窗口正常存活 5 秒，无崩溃）。若 exit=1 且有 traceback，修复后再继续。

- [ ] **Step 4: 全量测试最终回归**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（约 19 项）

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: 程序入口与高分屏适配"
```

- [ ] **Step 6: 手动验收清单（需真实 MSO54/56/58，交付用户执行）**

1. `python main.py` 启动，界面中文无乱码
2. 选"示波器 - 泰克 5 系"，输入仪器 IP，点连接 → 设备 ID 显示 TEKTRONIX,MSO5x
3. 在仪器面板上随意改一些配置（垂直刻度、触发等）
4. 点"一键保存配置" → 选保存位置 → 生成 `MSO5x_日期_时间.json`，预览树显示全部参数
5. 打开 json 文件确认中文键、可读格式
6. 仪器上按 *RST 或恢复默认（或手工改乱配置）
7. 点"加载配置文件"选刚才的 json → 点"应用配置到仪器" → 弹出汇总"成功 N / 失败 0 / 回读不一致 0"
8. 核对示波器屏幕配置已恢复（刻度/触发/通道开关等）
9. 拔网线后点任意操作 → 界面红字报错，不崩溃

---

## 验收标准（整体）

- `python -m pytest tests/ -v` 全绿
- `timeout 5 python main.py` 窗口正常存活
- 真实仪器手动验收清单（Task 7 Step 6）全部通过
