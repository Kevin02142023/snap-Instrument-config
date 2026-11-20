import pytest

from instruments.base import InstrumentError
from instruments.tek_mso5 import TekMSO5
from tests.mock_visa import MockResourceFactory, StatefulMockVisaResource


def _connected(state=None, fail_on=(), idn="TEKTRONIX,MSO54,C000001,SCPY:1.0",
               readback_map=None):
    resource = StatefulMockVisaResource(state=state, fail_on=fail_on,
                                        readback_map=readback_map)
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
    # 触发电平逐通道恢复：每个通道一条 TRIG:A:LEVEL:CHn
    for ch in range(1, 9):
        assert f"TRIG:A:LEVEL:CH{ch} 1.0E+00" in written
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


def test_apply_config_readback_mismatch_detected():
    scope, _ = _connected()
    config = scope.save_config()
    # 模拟仪器回读 CH1:SCALE? 时返回与写入值真正不同的值（"0" vs 1.0）
    scope2, _ = _connected(readback_map={"CH1:SCALE?": "1.0000E+00"})
    result = scope2.apply_config(config)
    assert result.mismatched >= 1
    assert any("CH1:SCALE" not in m and "电压每格" in m for m in result.mismatches)
    assert result.total == result.ok + result.failed + result.mismatched


def test_apply_config_abbreviation_forms_equivalent():
    """回归（2026-10-13 Debug1，MSO58B 实测）：保存与回读会话间仪器的响应
    格式状态（VERBose）可能不同——文件存缩写 EDG/EIT/NORM/SAM/SEQ，
    回读返回全称 EDGE/EITHER/NORMAL/SAMPLE/SEQUENCE。同一设置的两种
    写法等价（写入本身已成功），应计入成功并记录等价提示，而非误报不一致。"""
    scope, _ = _connected(state={
        "TRIG:A:TYPE?": "EDG",
        "TRIG:A:EDGE:SLOPE?": "EIT",
        "TRIG:A:MODE?": "NORM",
        "ACQ:MODE?": "SAM",
        "ACQ:STOPAFTER?": "SEQ",
    })
    config = scope.save_config()
    assert config["示波器"]["触发"]["触发类型"] == "EDG"

    scope2, _ = _connected(readback_map={
        "TRIG:A:TYPE?": "EDGE",
        "TRIG:A:EDGE:SLOPE?": "EITHER",
        "TRIG:A:MODE?": "NORMAL",
        "ACQ:MODE?": "SAMPLE",
        "ACQ:STOPAFTER?": "SEQUENCE",
    })
    result = scope2.apply_config(config)

    assert result.failed == 0
    assert result.mismatched == 0
    assert result.total == result.ok
    assert len(result.equivalences) == 5
    assert any("触发类型" in line for line in result.equivalences)
    assert any("停止条件" in line for line in result.equivalences)


def test_apply_config_numeric_formats_equivalent():
    """数值格式漂移（1.0E+00 vs 1.0000E+00）为同一数值，不应报不一致。"""
    scope, _ = _connected(state={"CH1:SCALE?": "1.0E+00"})
    config = scope.save_config()
    assert config["示波器"]["1通道参数"]["电压每格"] == "1.0E+00"

    scope2, _ = _connected(readback_map={"CH1:SCALE?": "1.0000E+00"})
    result = scope2.apply_config(config)

    assert result.failed == 0
    assert result.mismatched == 0
    assert any("电压每格" in line for line in result.equivalences)


def test_apply_config_quoted_label_requires_exact_match():
    """带引号的自由文本（通道标注）不做缩写前缀等价，必须精确一致，
    防止 '"ABC"' 与 '"ABCD"' 被误判为等价。"""
    scope, _ = _connected(state={"CH1:LABEL:NAME?": '"ABC"'})
    config = scope.save_config()

    scope2, _ = _connected(readback_map={"CH1:LABEL:NAME?": '"ABCD"'})
    result = scope2.apply_config(config)

    assert result.mismatched == 1
    assert result.ok == result.total - 1
    assert result.equivalences == []


def test_apply_config_level_list_formats_equivalent():
    """触发电平分号列表逐元素比较：各元素数值等价即视为成功。"""
    resource = StatefulMockVisaResource()
    resource.trig_levels = ["1.2", "5.6", "0.8", "3.0", "7.6", "0.0", "4.0", "0.0"]
    scope = TekMSO5(resource_factory=MockResourceFactory(resource))
    scope.connect("192.168.1.20")
    config = scope.save_config()
    assert config["示波器"]["触发"]["触发电平"] == "1.2;5.6;0.8;3.0;7.6;0.0;4.0;0.0"

    scope2, _ = _connected(readback_map={
        "TRIG:A:LEVEL?": "1.2000;5.6000;800.0000E-3;3.0000;7.6000;0.0E+0;4.0000;0.0E+0"})
    result = scope2.apply_config(config)

    assert result.mismatched == 0
    assert any("触发电平" in line for line in result.equivalences)


def test_apply_config_readback_io_failure_counted():
    scope, _ = _connected()
    config = scope.save_config()
    # 写入成功但回读查询失败（fail_on 只匹配查询形式：带 ? 后缀）
    scope2, _ = _connected(fail_on=("CH1:SCALE?",))
    result = scope2.apply_config(config)
    assert result.mismatched >= 1
    assert any("回读失败" in m for m in result.mismatches)


def test_apply_config_missing_scope_raises():
    scope, _ = _connected()
    with pytest.raises(InstrumentError):
        scope.apply_config({"仪器类型": "示波器"})


def test_mock_trigger_level_semantics():
    """mock 与真机一致性：电平逐通道可写，不带通道号的写入无效。"""
    resource = StatefulMockVisaResource()
    assert resource.query("TRIG:A:LEVEL?").strip() == ";".join(["1.0E+00"] * 8)
    resource.write("TRIG:A:LEVEL:CH4 3.0000")
    assert resource.query("TRIG:A:LEVEL:CH4?").strip() == "3.0000"
    resource.write("TRIG:A:LEVEL 1.2;5.6;0.8")  # 裸写无效
    assert resource.query("TRIG:A:LEVEL?").strip() == ";".join(
        ["1.0E+00"] * 3 + ["3.0000"] + ["1.0E+00"] * 4)


def test_apply_restores_per_channel_trigger_levels():
    """回归（2026-10-12 MSO58B 实测）：TRIG:A:LEVEL? 返回各通道电平列表，
    恢复必须逐通道写入 TRIG:A:LEVEL:CHn，整串裸写会被仪器静默忽略。"""
    scope, resource = _connected(idn="TEKTRONIX,MSO58,C000000,CF:1.0")
    resource.trig_levels = ["1.2000", "5.6000", "800.0000E-3", "3.0000",
                            "7.6000", "0.0E+0", "4.0000", "0.0E+0"]
    config = scope.save_config()
    assert config["示波器"]["触发"]["触发电平"] == (
        "1.2000;5.6000;800.0000E-3;3.0000;7.6000;0.0E+0;4.0000;0.0E+0")

    # 另一台同型号仪器：CH4 电平已漂移为 2.2（用户实测场景）
    scope2, resource2 = _connected(idn="TEKTRONIX,MSO58,C000000,CF:1.0")
    resource2.trig_levels = ["1.2000", "5.6000", "800.0000E-3", "2.2000",
                             "7.6000", "0.0E+0", "4.0000", "0.0E+0"]
    result = scope2.apply_config(config)

    assert result.failed == 0
    assert result.mismatched == 0
    assert resource2.trig_levels[3] == "3.0000"
    assert any(c == "TRIG:A:LEVEL:CH4 3.0000" for c in resource2.written)
    assert not any(c.startswith("TRIG:A:LEVEL ") for c in resource2.written)


class _StopAfterOpcHangResource(StatefulMockVisaResource):
    """模拟真机：ACQ:STOPAFTER SEQ 启动单次采集，紧随的 *OPC? 等待
    采集完成；NORM 触发且无信号时永不返回（超时）。"""

    def query(self, cmd):
        if (cmd.strip() == "*OPC?" and self.written
                and self.written[-1].upper().startswith("ACQ:STOPAFTER")):
            raise OSError("VI_ERROR_TMO: 模拟等待采集完成超时")
        return super().query(cmd)


class _ArmedOpcHangResource(StatefulMockVisaResource):
    """模拟真机：处于已武装的单次采集（SEQ+NORM+无信号）时，
    任何 *OPC? 都等待采集完成而挂起；ACQ:STATE STOP 解除武装。"""

    def __init__(self):
        super().__init__()
        self.armed = True

    def write(self, cmd):
        upper = cmd.upper()
        if upper.startswith("ACQ:STATE"):
            self.armed = "RUN" in upper or " 1" in upper
        elif upper.startswith("ACQ:STOPAFTER"):
            self.armed = "SEQ" in upper
        super().write(cmd)

    def query(self, cmd):
        if cmd.strip() == "*OPC?" and self.armed:
            raise OSError("VI_ERROR_TMO: 模拟已武装等待触发超时")
        return super().query(cmd)


def test_apply_does_not_wait_opc_after_stopafter():
    """回归（2026-10-12 MSO58B 实测）：STOPAFTER 写入后不应 *OPC? 同步，
    否则无触发信号时应用配置必超时失败（取值由回读校验兜底）。"""
    scope, _ = _connected()
    config = scope.save_config()

    resource2 = _StopAfterOpcHangResource()
    scope2 = TekMSO5(resource_factory=MockResourceFactory(resource2))
    scope2.connect("192.168.1.20")
    result = scope2.apply_config(config)

    assert result.failed == 0
    assert result.mismatched == 0


def test_apply_disarms_acquisition_first():
    """回归（2026-10-12 MSO58B 实测）：仪器停在已武装的单次采集
    （SEQ+NORM+无信号）时，任何 *OPC? 同步都会挂起——
    apply 开始应先 ACQ:STATE STOP 解除武装。"""
    scope, _ = _connected()
    config = scope.save_config()

    resource2 = _ArmedOpcHangResource()
    scope2 = TekMSO5(resource_factory=MockResourceFactory(resource2))
    scope2.connect("192.168.1.20")
    result = scope2.apply_config(config)

    written = resource2.written
    # 解除武装须是应用配置的第一条设置命令（紧随连接初始化的 HEADer 0）
    assert written[written.index("HEADer 0") + 1] == "ACQ:STATE STOP"
    assert result.failed == 0
    assert result.mismatched == 0


def test_connect_does_not_wait_opc_when_armed():
    """回归（2026-10-12 真机）：连接初始化不得用 *OPC? 同步——
    仪器停在已武装的单次采集时会挂起导致连接失败。"""
    resource = _ArmedOpcHangResource()
    scope = TekMSO5(resource_factory=MockResourceFactory(resource))
    scope.connect("192.168.1.20")
    assert scope.connected
    assert scope.idn == "TEKTRONIX,MSO54,C000001,SCPY:1.0"


def test_restorable_params_listing():
    """参数选择清单：只读参数（探头衰减）不列出，探头相关的带宽限制
    默认不勾选，其余默认勾选。"""
    scope, _ = _connected()
    params = scope.restorable_params()
    names = [key for _, key, _ in params]
    assert "探头衰减" not in names  # 只读，永远不参与恢复
    defaults = {key: default for _, key, default in params}
    assert defaults["带宽限制"] is False
    assert defaults["触发类型"] is True
    assert defaults["时间每格"] is True
    groups = {group for group, _, _ in params}
    assert "通道参数（全部通道）" in groups
    assert {"水平", "触发", "采集"} <= groups


def test_apply_config_selected_params_only():
    """按选择的参数类型恢复：只写勾选项，未选择项记 [跳过] 未选择，
    只读项照常提示，total 只计实际恢复项。"""
    scope, _ = _connected()
    config = scope.save_config()

    scope2, resource2 = _connected()
    result = scope2.apply_config(config, selected={"电压每格"})

    written = resource2.written
    assert any(c.startswith("CH1:SCALE ") for c in written)
    assert not any(c.startswith("CH1:COUPLING ") for c in written)
    assert not any(c.startswith("TRIG:A:TYPE ") for c in written)
    assert result.total == 4  # MSO54 共 4 通道的电压每格
    assert result.ok == 4
    assert result.failed == 0
    assert result.mismatched == 0
    assert any("未选择" in s for s in result.skipped)
    assert any("只读" in s for s in result.skipped)


def test_apply_config_bandwidth_default_off():
    """回归（2026-10-13 Debug2，MSO58B 实测）：换探头后带宽上限不同
    （250→200 MHz），带宽限制为探头相关参数、默认不在恢复范围，
    按默认勾选集恢复不再出现回读不一致。"""
    scope, _ = _connected(state={
        "CH3:BANDWIDTH?": "250.0000E+6", "CH4:BANDWIDTH?": "250.0000E+6"})
    config = scope.save_config()

    # 换探头后的仪器：CH3/CH4 带宽被限制为 200 MHz
    scope2, _ = _connected(readback_map={
        "CH3:BANDWIDTH?": "200.0000E+6", "CH4:BANDWIDTH?": "200.0000E+6"})
    selected = {key for _, key, default in scope2.restorable_params() if default}
    assert "带宽限制" not in selected
    result = scope2.apply_config(config, selected=selected)

    assert result.failed == 0
    assert result.mismatched == 0
    assert result.ok == result.total
