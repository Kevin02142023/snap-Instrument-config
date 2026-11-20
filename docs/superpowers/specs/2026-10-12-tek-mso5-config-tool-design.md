# 仪器配置快照工具（TekSnapConfig）设计文档

- 日期：2026-10-12
- 状态：已获用户批准（口头确认）
- 范围：本次只实现泰克 5 系示波器（MSO54/56/58），其余仪器仅在下拉列表占位

## 1. 背景与目标

硬件工程师使用示波器、信号发生器、源表等仪器前，重复配置浪费时间。本工具提供：

1. **一键保存**：把当前示波器的配置读出并保存为 .json 文件
2. **加载配置**：选择以前保存的 .json 文件并预览
3. **应用配置**：把 json 内容写回示波器，使其恢复到保存时的状态

技术栈：Python 3.10+ / Tkinter / pyvisa（pyvisa-py 后端优先）。

## 2. 通信方案

- 连接方式：**LAN 网口**（VISA over TCPIP），VISA 地址 `TCPIP0::<IP>::inst0::INSTR`
- 后端选择：默认 `pyvisa-py`（纯 Python，无需安装 NI-VISA）；若检测到系统已装 NI-VISA 则自动改用默认后端。实现上：先尝试 `pyvisa.ResourceManager()`（系统 VISA），失败则回退 `pyvisa.ResourceManager("@py")`
- SCPI 交互规范（参照 Tektronix Programmatic-Control-Examples）：
  - 写命令后用 `*OPC?` 同步
  - `*IDN?` 识别型号，据此确定通道数（MSO54=4 / MSO56=6 / MSO58=8）
  - read/write 终止符 `\n`，timeout 10 s

## 3. 目录结构

```
instrument_config/
├── main.py                # 程序入口
├── requirements.txt       # pyvisa, pyvisa-py
├── instruments/
│   ├── __init__.py
│   ├── base.py            # 仪器抽象基类
│   ├── tek_mso5.py        # 泰克5系实现（白名单命令表 + 保存/加载/应用）
│   └── registry.py        # 仪器注册表（下拉列表数据源）
├── core/
│   ├── __init__.py
│   └── config_store.py    # json 读写
├── gui/
│   ├── __init__.py
│   └── app.py             # Tkinter 主窗口
└── tests/
    ├── test_config_store.py
    ├── test_tek_mso5.py
    └── mock_visa.py       # mock pyvisa resource
```

## 4. 模块设计

### 4.1 instruments/base.py — 仪器抽象基类

```python
class Instrument(ABC):
    def __init__(self, resource_factory=None, log_callback=None)
    def connect(self, ip: str) -> None          # 建立连接并查询 *IDN?，随后发送 HEADer 0
    def disconnect(self) -> None
    @property
    def idn(self) -> str
    @property
    def connected(self) -> bool
    def save_config(self) -> dict               # 读仪器当前配置 → 字典
    def apply_config(self, config: dict) -> ApplyResult  # 字典 → 写回仪器
```

- `resource_factory` 参数用于测试注入 mock（依赖注入）；默认实现先试系统 VISA，失败回退 `@py` 后端
- `log_callback(msg)` 把每条 SCPI 命令/回应转给 GUI 日志区（GUI 传入的回调只做队列 put，线程安全）
- `ApplyResult` dataclass：total / ok / failed / mismatched 计数 + skipped / errors / mismatches 明细列表
- `save_config` / `apply_config` 在子类用白名单命令表实现
- 所有 IO 异常向上抛 `InstrumentError`（自定义异常，携带仪器侧上下文）

### 4.2 instruments/tek_mso5.py — 泰克 5 系实现

核心是**白名单命令表**：每行一个参数项，含中文键名、query 命令、set 命令模板（None 表示只读）、所属分组。以下命令头均已对照《5 Series MSO Programmer Manual》(077-1305-03) 原文验证：

| 分组 | 中文键（示例） | query | set 模板 |
|---|---|---|---|
| 通道 | 开关 | `DISplay:GLObal:CH1:STATE?` | `DISplay:GLObal:CH{n}:STATE {v}` |
| 通道 | 电压每格 | `CH1:SCALE?` | `CH{n}:SCALE {v}` |
| 通道 | 垂直位置 | `CH1:POSITION?` | `CH{n}:POSITION {v}` |
| 通道 | 偏移 | `CH1:OFFSET?` | `CH{n}:OFFSET {v}` |
| 通道 | 耦合 | `CH1:COUPLING?` | `CH{n}:COUPLING {v}` |
| 通道 | 带宽限制 | `CH1:BANDWIDTH?` | `CH{n}:BANDWIDTH {v}` |
| 通道 | 反相 | `CH1:INVERT?` | `CH{n}:INVERT {v}` |
| 通道 | 探头衰减 | `CH1:PRO:GAIN?` | **只读**（Query Only，由接入探头决定，应用时跳过） |
| 通道 | 标注 | `CH1:LABEL:NAME?` | `CH{n}:LABEL:NAME {v}` |
| 水平 | 水平模式 | `HOR:MODE?` | `HOR:MODE {v}`（**须先于记录长度**，手册要求改记录长度前水平模式为 MANUAL） |
| 水平 | 时间每格 | `HOR:SCALE?` | `HOR:SCALE {v}` |
| 水平 | 水平位置 | `HOR:POSITION?` | `HOR:POSITION {v}` |
| 水平 | 记录长度 | `HOR:RECORDLENGTH?` | `HOR:RECORDLENGTH {v}` |
| 触发 | 触发类型 | `TRIG:A:TYPE?` | `TRIG:A:TYPE {v}`（**须先于源/斜率/电平**） |
| 触发 | 触发源 | `TRIG:A:EDGE:SOURCE?` | `TRIG:A:EDGE:SOURCE {v}` |
| 触发 | 触发斜率 | `TRIG:A:EDGE:SLOPE?` | `TRIG:A:EDGE:SLOPE {v}` |
| 触发 | 触发电平 | `TRIG:A:LEVEL?` | `TRIG:A:LEVEL {v}`（作用于当前触发源） |
| 触发 | 触发模式 | `TRIG:A:MODE?` | `TRIG:A:MODE {v}` |
| 采集 | 采集模式 | `ACQ:MODE?` | `ACQ:MODE {v}` |
| 采集 | 停止条件 | `ACQ:STOPAFTER?` | `ACQ:STOPAFTER {v}` |

连接后必须发送 `HEADer 0`，否则仪器回应带命令头前缀（如 `:CH1:SCALE 1.0E+00`），值解析会出错。命令表顺序即应用顺序（依赖约束已内建：水平模式→记录长度、触发类型→源/斜率/电平→模式）。

- 保存：逐项 query，值为仪器原始回应字符串（strip 后）；若某项查询返回空字符串（固件不支持该命令），存空字符串并继续
- 应用：逐项 write + `*OPC?`；只读项（探头衰减）与空值项跳过并记日志；某项失败记录并继续，最后回读校验
- 通道数由 IDN 型号字段解析（MSO54→4、MSO56→6、MSO58/MSO58LP→8、无法识别→4），只对存在的通道生成"1通道参数"…"N通道参数"

### 4.3 instruments/registry.py — 仪器注册表

```python
INSTRUMENTS = [
    {"类别": "示波器", "型号": "泰克 5 系 (MSO54/56/58)", "可用": True, "cls": TekMSO5},
    {"类别": "信号发生器", "型号": "泰克 AFG", "可用": False},
    {"类别": "源表", "型号": "吉时利 2400/2450", "可用": False},
    {"类别": "万用表", "型号": "吉时利 DMM6500", "可用": False},
    {"类别": "频谱分析仪", "型号": "待定", "可用": False},
    {"类别": "逻辑分析仪", "型号": "待定", "可用": False},
]
```

下拉列表显示全部条目，不可用项标注"（开发中）"且选中后禁用连接按钮。

### 4.4 core/config_store.py — json 存取

- `save(path, config)`：`json.dump(..., ensure_ascii=False, indent=4)`，UTF-8 编码
- `load(path)`：读 json 并校验必需顶层键（仪器类型/型号/保存时间/示波器），不合法抛 `ConfigError`
- 文件名建议（由 GUI 生成）：`MSO54_20261012_153000.json`（型号_日期_时间）

### 4.5 gui/app.py — Tkinter 主窗口

布局（中文）：

```
┌──────────────────────────────────────────────┐
│ 仪器下拉 | IP地址 [____] | 连接 | 断开        │
│ 设备ID: TEKTRONIX,MSO54,...   状态: 已连接    │
├──────────────────────────────────────────────┤
│  [一键保存配置]  [加载配置文件]  [应用配置到仪器] │
├──────────────────────────────────────────────┤
│ 配置预览 (Treeview 树形，中文键→值)           │
├──────────────────────────────────────────────┤
│ 日志区 (每条SCPI命令/回应/错误，滚动)          │
└──────────────────────────────────────────────┘
```

- 仪器 IO 一律在后台 `threading.Thread` 执行，界面不卡死；结果经 `queue.Queue` 由主线程 `after()` 轮询刷新
- 应用配置时按钮禁用，完成或失败后恢复
- 应用结束弹提示：成功 N 条 / 失败 M 条 / 回读不一致 K 条

## 5. json 文件格式

```json
{
    "仪器类型": "示波器",
    "型号": "泰克5系",
    "IDN": "TEKTRONIX,MSO54,Cxxxxxx,SCPY:1.0",
    "IP": "192.168.1.20",
    "保存时间": "2026-10-12 15:30:00",
    "示波器": {
        "1通道参数": {
            "开关": "1",
            "电压每格": "1.0E+00",
            "垂直位置": "0.0E+00",
            "偏移": "0.0E+00",
            "耦合": "DC",
            "带宽限制": "FULL",
            "探头衰减": "1.0E+00",
            "反相": "0",
            "标注": "CH1"
        },
        "2通道参数": { "...": "..." },
        "水平": {
            "时间每格": "1.0E-3",
            "水平位置": "0.0E+00",
            "记录长度": "1.0E+07",
            "水平模式": "AUTO"
        },
        "触发": {
            "触发类型": "EDGE",
            "触发源": "CH1",
            "触发斜率": "RISE",
            "触发电平": "1.6E+00",
            "触发模式": "AUTO"
        },
        "采集": {
            "采集模式": "SAMPLE",
            "停止条件": "RUNSTop"
        }
    }
}
```

- 值一律为字符串（仪器原始回应），不猜单位、不做数值转换，保证回读校验可比
- 应用时若 json 中某键在当前固件不支持：跳过并记日志，不中断

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| 连接失败/超时 | 状态栏红字提示，UI 可继续操作 |
| 保存中途 IO 错误 | 中止保存，弹窗提示，不写残缺文件 |
| 应用时单条命令失败 | 记日志继续，结束汇总 N/M/K |
| json 格式非法/键缺失 | 拒绝加载，明确指出缺什么 |
| 回读校验不一致 | 日志黄字列出该键的期望值/实际值 |
| 断开时仪器异常 | 静默清理本地状态 |

## 7. 测试策略（pytest，全部用 mock 仪器）

1. `test_config_store.py`：save→load 往返一致；非法 json 报错
2. `test_tek_mso5.py`：
   - mock resource 收到 query 时返回预设值，验证 save_config 生成的字典结构与键名
   - 验证 apply_config 发出的 SCPI 命令序列与 `*OPC?` 同步次序
   - IDN 解析通道数（MSO54/56/58）
   - 单条失败容错与回读校验
3. 手动验收（需真实仪器，交付后由用户执行）：连接→改配置→一键保存→*RST→加载→应用→核对波形显示一致

## 8. 实施方式

- 用 superpowers 的 writing-plans 技能产出实施计划
- 用 subagent-driven-development 技能派多个子 agent 实现（instruments 层 / core+tests 层 / gui 层），主会话审查集成
- 遵循 TDD：先写测试再实现

## 9. 明确不做（YAGNI）

- 不做信号发生器/源表等其它仪器的实际功能（仅下拉占位）
- 不做波形数据采集、截图、测量等测试功能
- 不做 USB/串口连接
- 不做配置文件管理库（历史列表、搜索）；仅文件对话框按需选择
- 不做打包 exe（后续可加 PyInstaller）
