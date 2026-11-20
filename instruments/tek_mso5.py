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

def _trigger_level_commands(value):
    """真机（MSO58B 实测）：TRIG:A:LEVEL? 返回各通道电平的分号列表，
    但不带通道号的写入（含整串列表）会被仪器静默忽略，须逐通道写入。"""
    return [f"TRIG:A:LEVEL:CH{index} {part}"
            for index, part in enumerate(str(value).split(";"), 1)]


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
        ("触发电平", "TRIG:A:LEVEL?", _trigger_level_commands),
        ("触发模式", "TRIG:A:MODE?", "TRIG:A:MODE {v}"),
    ],
    "采集": [
        ("采集模式", "ACQ:MODE?", "ACQ:MODE {v}"),
        ("停止条件", "ACQ:STOPAFTER?", "ACQ:STOPAFTER {v}"),
    ],
}

MODEL_CHANNELS = {"MSO54": 4, "MSO56": 6, "MSO58": 8, "MSO58LP": 8}

# 探头相关参数：可设范围受物理接入的探头制约（2026-10-13 Debug2 真机实测：
# 换探头后带宽上限 250→200 MHz，恢复必"不一致"），参数选择对话框中默认不勾选。
_PROBE_DEPENDENT = {"带宽限制"}


def _values_equivalent(expected, actual):
    """SCPI 等价值判断（2026-10-13 Debug1，MSO58B 实测）：

    保存与回读会话之间，仪器的响应格式状态（HEADer/VERBose）可能不同，
    同一设置会以缩写/全称（EDG/EDGE）、不同数值格式（1.0/1.0000E+00）
    返回。写入本身已成功，这些等价形式不应计为回读不一致：
    - 带引号的自由文本（如通道标注）必须精确一致，不做前缀等价
    - 分号列表（如触发电平）逐元素比较
    - 数值按数值相等比较
    - 其余按 SCPI 助记符规则：缩写为全称的前缀（不区分大小写）
    """
    if expected == actual:
        return True
    if expected.startswith('"') or actual.startswith('"'):
        return False
    if ";" in expected or ";" in actual:
        parts_e = expected.split(";")
        parts_a = actual.split(";")
        return len(parts_e) == len(parts_a) and all(
            _values_equivalent(e.strip(), a.strip())
            for e, a in zip(parts_e, parts_a))
    try:
        return float(expected) == float(actual)
    except ValueError:
        pass
    e, a = expected.strip().upper(), actual.strip().upper()
    return bool(e) and bool(a) and (e.startswith(a) or a.startswith(e))

# 这些命令会启动/重启采集（如 STOPAFTER SEQ 单次采集），随后的 *OPC? 会
# 等待采集完成——NORM 触发且无信号时永不返回，故写入后不做同步（真机实测）。
# 取值是否生效由回读校验兜底。
_ASYNC_WRITE_PREFIXES = ("ACQ:STOPAFTER",)


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

    def restorable_params(self):
        """可恢复参数清单（供 GUI 参数选择对话框）：
        (分组, 参数名, 默认勾选)。只读参数（探头衰减）不列入；
        探头相关参数默认不勾选，可由用户手动勾上。"""
        params = [
            ("通道参数（全部通道）", key, key not in _PROBE_DEPENDENT)
            for key, _, set_tpl in CHANNEL_PARAMS if set_tpl is not None]
        for group_name, rows in GLOBAL_PARAMS.items():
            params.extend(
                (group_name, key, key not in _PROBE_DEPENDENT)
                for key, _, set_tpl in rows if set_tpl is not None)
        return params

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

    def apply_config(self, config, selected=None):
        self._require_connected()
        scope = config.get("示波器")
        if not isinstance(scope, dict):
            raise InstrumentError("配置缺少 '示波器' 部分")

        # 仪器可能停在已武装的单次采集（如上次应用残留的 SEQ 停止条件），
        # 此时任何 *OPC? 同步都会挂起——先停采集再恢复参数（真机实测立即生效）
        self._write("ACQ:STATE STOP")

        # 按命令表顺序展开执行项: (中文路径, query模板, 写入命令列表|None, 期望值, 通道号|None)
        # 展开时按选择过滤：selected=None 全恢复；只读参数（set 模板为 None，
        # 如探头衰减）不受选择影响，执行时仍提示"只读参数，跳过"
        items = []
        unselected_paths = []
        for ch in range(1, self.channel_count() + 1):
            group = scope.get(f"{ch}通道参数", {})
            for key, query_tpl, set_tpl in CHANNEL_PARAMS:
                if key not in group:
                    continue
                if set_tpl is not None and selected is not None and key not in selected:
                    unselected_paths.append(f"{ch}通道参数.{key}")
                    continue
                commands = None if set_tpl is None else [set_tpl.format(ch=ch, v=group[key])]
                items.append((f"{ch}通道参数.{key}", query_tpl, commands, group[key], ch))
        for group_name, params in GLOBAL_PARAMS.items():
            group = scope.get(group_name, {})
            for key, query_tpl, set_tpl in params:
                if key not in group:
                    continue
                if set_tpl is not None and selected is not None and key not in selected:
                    unselected_paths.append(f"{group_name}.{key}")
                    continue
                if callable(set_tpl):
                    commands = set_tpl(group[key])
                else:
                    commands = None if set_tpl is None else [set_tpl.format(v=group[key])]
                items.append((f"{group_name}.{key}", query_tpl, commands, group[key], None))

        result = ApplyResult()
        result.skipped.extend(f"{path}: 未选择，跳过" for path in unselected_paths)
        written = []
        for path, query_tpl, commands, value, ch in items:
            if commands is None:
                result.skipped.append(f"{path}: 只读参数，跳过")
                continue
            if not value:
                result.skipped.append(f"{path}: 空值，跳过")
                continue
            result.total += 1
            try:
                for cmd in commands:
                    try:
                        self._write(cmd)
                    except Exception as exc:
                        raise InstrumentError(f"写入 {cmd} 失败: {exc}") from exc
                if not any(cmd.upper().startswith(prefix)
                           for cmd in commands
                           for prefix in _ASYNC_WRITE_PREFIXES):
                    self._query("*OPC?")
            except Exception as exc:
                result.failed += 1
                result.errors.append(f"{path}: {exc}")
                continue
            written.append((path, query_tpl, value, ch))

        for path, query_tpl, value, ch in written:
            try:
                actual = self._query(query_tpl.format(ch=ch))
            except Exception as exc:
                result.mismatched += 1
                result.mismatches.append(f"{path}: 回读失败: {exc}")
                continue
            if actual == value:
                result.ok += 1
            elif _values_equivalent(value, actual):
                result.ok += 1
                result.equivalences.append(
                    f"{path}: 期望 {value!r}，实际 {actual!r}（等价格式，视为成功）")
            else:
                result.mismatched += 1
                result.mismatches.append(f"{path}: 期望 {value!r}，实际 {actual!r}")
        return result
