# AGENTS.md — InstrSnapConfig 仪器配置快照工具

面向 AI 编码助手的项目说明。人类可读的项目介绍见 `README.md`。

## 项目是什么

保存 / 加载 / 一键恢复仪器配置的 Windows 桌面工具（Python + Tkinter + pyvisa）。
当前仅实现泰克 5 系示波器（MSO54/56/58/58LP），其他仪器在 `instruments/registry.py` 占位待开发。

## 常用命令

```bash
pip install -r requirements.txt        # pyvisa, pyvisa-py, pytest
python main.py                         # 运行 GUI（开发用）
python -m pytest tests/ -v             # 全部测试（纯 mock，无需真机）
python -m PyInstaller --noconfirm --onefile --windowed --name InstrSnapConfig_V0.1 \
    --collect-all pyvisa --collect-all pyvisa_py main_v0.1.py    # 打包 exe
```

- 打包发布用 `main_v0.1.py`（版本固化入口）；`main.py` 是持续更新的主入口，两者逻辑保持一致。
- 真机调试需示波器与电脑同局域网，VISA 地址 `TCPIP0::<IP>::inst0::INSTR`。

## 架构

```
main.py / main_v0.1.py    入口（含 Windows 高分屏 DPI 适配）
core/config_store.py      json 存取：UTF-8、中文键、必需键校验（仪器类型/型号/保存时间）
instruments/base.py       Instrument 抽象基类：VISA 连接、SCPI 日志、resource_factory 依赖注入
instruments/tek_mso5.py   泰克 5 系实现：白名单命令表 + save_config/apply_config/回读校验
instruments/discovery.py  局域网仪器扫描（list_resources + TCPIP inst0 正则提取）
instruments/registry.py   仪器注册表（GUI 下拉列表数据源）
gui/app.py                Tkinter 主窗口：后台线程做仪器 IO，queue + after(100) 轮询回主线程
tests/mock_visa.py        有状态模拟示波器（write/query 往返语义）
docs/superpowers/         设计文档与实施计划
```

## 关键约定

**代码与 UI 全中文**：注释、docstring、异常消息、GUI 文案、commit message 均用中文；commit message 前缀用英文 conventional 风格（`feat:` / `fix:` / `docs:` / `chore:`）。

**配置 json 为中文键字典**：顶层含 仪器类型/型号/IDN/IP/保存时间，`"示波器"` 下按 `"1通道参数"…"N通道参数"`、`"水平"`、`"触发"`、`"采集"` 分组。用户会手工编辑这些文件，格式不可随意变更。

**白名单命令表模式**（`instruments/tek_mso5.py`）：每行 `(中文键, query模板, set模板|None|callable)`，`None` 表示只读参数（如探头衰减），表顺序即应用顺序（有依赖的命令必须保持先后，如水平模式先于记录长度）。新增仪器型号 = 新建 Instrument 子类 + 命令表 + 注册表登记。探头相关参数（`_PROBE_DEPENDENT`，如带宽限制）在 `restorable_params()` 清单中默认不勾选；`apply_config(config, selected)` 的 `selected` 为参数名集合，`None` 表示全恢复。

**测试不碰真机**：通过 `resource_factory` 注入 `tests/mock_visa.py` 的 `StatefulMockVisaResource`，模拟 write→query 往返、`fail_on` 注入 IO 错误、`readback_map` 模拟回读格式漂移。行为改动必须带 mock 回归测试。

**GUI 线程模型**：仪器 IO 一律在 daemon 线程执行，结果经 `self._queue.put(...)` 回传，主线程 `_poll_queue`（`after(100)` 轮询）消费；按钮有 `_busy` 防重入。禁止在后台线程直接操作 Tkinter 控件。

## 真机验证过的 SCPI 陷阱（MSO58B 实测，改动前先读注释）

这些行为与手册直觉相悖，代码内注释标注了 `真机实测`，不要"顺手优化"掉：

- `TRIG:A:LEVEL?` 返回全通道分号列表，但不带通道号的写入（含整串列表）被仪器**静默忽略**——必须逐通道 `TRIG:A:LEVEL:CHn v` 写入。
- `ACQ:STOPAFTER` 等会启动采集的命令，写后**不能**跟 `*OPC?`（单次采集 + NORM 触发无信号时永不返回）；生效性由回读校验兜底。见 `_ASYNC_WRITE_PREFIXES`。
- `apply_config` 开头先发 `ACQ:STATE STOP` 解除已武装的单次采集，否则后续 `*OPC?` 全部挂起。
- 连接后发 `HEADer 0`（关响应头），且**不用** `*OPC?` 同步（同上原因）。
- 仪器返回值的长短格式由 `VERBose` 决定（工具不控制它，重启/复位会变）：同一查询两次会话可能返回 `EDG` 或 `EDGE`，均为合法等价形式（2026-10-13 Debug1 实测）。

## 回读校验语义

`apply_config` 逐项写入后 query 回读比对，经 `_values_equivalent`（`instruments/tek_mso5.py`）语义比较：精确一致或等价（缩写/全称前缀、数值相等、分号列表逐元素）计入**成功**，等价但非精确一致的项记入 `ApplyResult.equivalences`，GUI 以 `[等价]` 行输出；仅值真正不同才计"不一致"，IO 异常计"失败"。带引号的自由文本（通道标注）必须精确一致，不做前缀等价。

## 文件说明

- `MSO58B_20261013_185925.json`：配置快照示例（序列号已脱敏），可加载预览格式。
- `build/`、`dist/`、`.qoder/` 等为本地开发产物，已在 `.gitignore` 中，勿提交。
