# 参数选择恢复功能（应用前勾选）设计文档

- 日期：2026-10-13
- 状态：已获用户批准（方案 A，AskUserQuestion 确认）
- 背景：Debug2 —— 换探头后带宽上限不同（250→200 MHz），带宽限制恢复必然"不一致"；且该参数与物理探头绑定，类似探头衰减。用户要求做成参数级可配置恢复。

## 1. 需求（已确认）

1. 点"应用配置到仪器"时弹出参数选择对话框（多选框），确认后只恢复勾选项
2. 勾选粒度**按参数类型**：一个勾选项作用于全部通道（如勾"带宽限制"= CH1–8 全恢复）
3. 默认全勾选；**带宽限制默认不勾选**（探头相关，可手动勾上）；探头衰减（只读）不列入清单
4. 勾选状态**不跨会话保存**，每次按默认弹出
5. 取消则本次不执行任何写入

## 2. 交互流程

```
点[应用配置到仪器] → restorable_params() 取清单
  → 清单为 None（仪器未实现）→ 不弹窗，全恢复（兼容未来仪器）
  → 清单非空 → 弹模态对话框：
       标题"选择要恢复的参数"，提示"勾选的参数将恢复到配置文件保存的值"
       分组 LabelFrame：通道参数（全部通道）/ 水平 / 触发 / 采集，约 19 项，双列排布
       底部：[全选] [全不选] …… [取消] [恢复]，Enter=恢复、Esc=取消
  → 点[恢复] → selected = 勾选参数名集合 → 后台线程 apply_config(config, selected)
  → 点[取消] → 不执行
```

## 3. 模块设计

### instruments/base.py

- `restorable_params()` 基类默认返回 `None`：表示该仪器不提供选择清单，GUI 不弹窗、直接全恢复。未来新仪器型号可选择实现。
- `apply_config(config, selected=None)` 抽象签名增加 `selected`（中文名集合；`None` = 全恢复，向后兼容）。

### instruments/tek_mso5.py

- `_PROBE_DEPENDENT = {"带宽限制"}`：探头相关参数（恢复值受物理接入探头制约，Debug2 真机实测换探头后 250→200 MHz），默认不勾选。
- `restorable_params()`：由白名单命令表生成 `[(分组, 参数名, 默认勾选)]`；set 模板为 None（只读，如探头衰减）的行不列入；通道组标签为"通道参数（全部通道）"。
- `apply_config(config, selected=None)` 展开执行项时过滤：
  - 只读参数（commands 为 None）：**先于**选择判断，保持现有"[跳过] …只读参数，跳过"提示不变
  - 未选择参数：`[跳过] …: 未选择，跳过`，不计入 total
  - `total/ok/failed/mismatched` 只统计实际恢复项

### gui/app.py

- `_ParamSelectDialog(tk.Toplevel)`：模态（transient + grab_set + wait_window）；`result` 属性 = `None`（取消）或勾选参数名 `set`（确认，空集合法）。
- `AppWindow._show_param_dialog(params)`：创建对话框并 `wait_window`，返回 `result`。
- `_on_apply`：取 `self._instrument.restorable_params()`；非 None 则弹窗，取消即 return；`selected` 传入后台 `apply_config(config, selected=selected)`。其余防重入/线程/队列流程不变。

## 4. 测试计划（全部 mock，无需真机）

mock 级（tests/test_tek_mso5.py）：
1. `test_restorable_params_listing`：清单不含探头衰减；带宽限制默认 False；其余默认 True；含四组
2. `test_apply_config_selected_params_only`：selected={"电压每格"} → 仅写 CHn:SCALE，total=通道数，未选择与只读提示并存
3. `test_apply_config_bandwidth_default_off`：复刻 Debug2（保存 250 MHz、换探头回读 200 MHz），按默认勾选集恢复 → 0 不一致

GUI 级（tests/test_gui.py）：
4. `test_param_dialog_defaults_and_selection`：默认勾选状态与勾选取值/取消语义
5. `test_on_apply_e2e_passes_selection`：注入 fake 仪器，走真实对话框（after 回调操作勾选）→ apply_config 收到 selected
6. `test_on_apply_cancelled_does_nothing`：对话框取消 → 不调用 apply_config

既有测试不传 `selected`，天然覆盖 `None` 全恢复路径（向后兼容回归）。

## 5. 文档更新

- README：功能列表、使用步骤、常见问题（带宽限制默认不恢复的原因）、版本历史
- AGENTS.md：白名单命令表模式补充 `_PROBE_DEPENDENT` 与参数选择约定

## 6. 验收标准

- 全量 pytest 通过（51 既有 + 新增）
- Debug2 场景回放：带宽限制默认不恢复，0 不一致、0 失败
- 未实现 `restorable_params` 的仪器行为与现状完全一致
