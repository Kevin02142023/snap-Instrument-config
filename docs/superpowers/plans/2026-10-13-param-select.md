# 参数选择恢复功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 应用配置前弹出参数选择对话框，按参数类型勾选恢复范围（带宽限制等探头相关参数默认不勾选）。

**Architecture:** 仪器层提供 `restorable_params()` 清单与 `apply_config(config, selected)` 过滤；GUI 层新增模态 `_ParamSelectDialog`，在 `_on_apply` 里弹窗并把勾选集合传入后台应用线程。基类 `restorable_params()` 默认 `None`，未实现的仪器不弹窗、全恢复。

**Tech Stack:** Python 3.10+ / Tkinter / pytest（mock VISA，无需真机）。

**设计文档:** `docs/superpowers/specs/2026-10-13-param-select-design.md`

---

### Task 1: 仪器层——restorable_params 清单与 selected 过滤

**Files:**
- Modify: `instruments/base.py`（`Instrument` 类：`restorable_params` 默认实现 + `apply_config` 抽象签名）
- Modify: `instruments/tek_mso5.py`（`_PROBE_DEPENDENT` 常量 + `restorable_params` 方法 + `apply_config` 过滤逻辑）
- Test: `tests/test_tek_mso5.py`

- [ ] **Step 1: 写 3 个失败测试**

在 `tests/test_tek_mso5.py` 末尾（`test_connect_does_not_wait_opc_when_armed` 之后）追加：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tek_mso5.py -q`
Expected: 3 FAILED（`restorable_params` 不存在 / `apply_config() got an unexpected keyword argument 'selected'`）

- [ ] **Step 3: 实现 base.py**

`instruments/base.py` 的 `Instrument` 类：`save_config` 抽象方法之前加入默认方法，并把 `apply_config` 抽象签名改为带 `selected`：

```python
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
```

- [ ] **Step 4: 实现 tek_mso5.py**

`MODEL_CHANNELS` 之后加入：

```python
# 探头相关参数：可设范围受物理接入的探头制约（2026-10-13 Debug2 真机实测：
# 换探头后带宽上限 250→200 MHz，恢复必"不一致"），参数选择对话框中默认不勾选。
_PROBE_DEPENDENT = {"带宽限制"}
```

`TekMSO5` 类中 `channel_count` 之后加入：

```python
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
```

`apply_config` 签名改为 `def apply_config(self, config, selected=None):`，展开执行项的两段循环替换为（只读判断先于选择判断，保持探头衰减的"只读参数"提示不变；`ACQ:STATE STOP` 与后续执行/回读循环不动）：

```python
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
```

- [ ] **Step 5: 运行确认通过 + 全量回归**

Run: `python -m pytest tests/ -q`
Expected: 57 passed（51 既有 + 3 新增；既有测试不传 selected，覆盖 None 全恢复路径）

- [ ] **Step 6: Commit**

```bash
git add instruments/base.py instruments/tek_mso5.py tests/test_tek_mso5.py
git commit -m "feat: 参数级选择恢复——restorable_params 清单与 selected 过滤"
```

---

### Task 2: GUI 层——参数选择对话框

**Files:**
- Modify: `gui/app.py`（新增 `_ParamSelectDialog` 类、`_show_param_dialog` 方法、改造 `_on_apply`）
- Test: `tests/test_gui.py`

- [ ] **Step 1: 写 3 个失败测试**

`tests/test_gui.py` 顶部导入保持现状（已有 `import time`、`import pytest`），文件末尾追加：

```python
def test_param_dialog_defaults_and_selection():
    from gui.app import AppWindow, _ParamSelectDialog

    app = AppWindow()
    app.withdraw()
    try:
        params = [("通道参数（全部通道）", "带宽限制", False),
                  ("通道参数（全部通道）", "电压每格", True),
                  ("触发", "触发类型", True)]
        dialog = _ParamSelectDialog(app, params)
        try:
            assert dialog.result is None
            states = {key: var.get() for key, var in dialog._vars.items()}
            assert states == {"带宽限制": False, "电压每格": True,
                              "触发类型": True}
            dialog._vars["带宽限制"].set(True)   # 用户手动勾上带宽限制
            dialog._vars["触发类型"].set(False)
            dialog._confirm()
            assert dialog.result == {"带宽限制", "电压每格"}
        finally:
            if dialog.winfo_exists():
                dialog.destroy()
    finally:
        app.destroy()


def test_param_dialog_cancel_returns_none():
    from gui.app import AppWindow, _ParamSelectDialog

    app = AppWindow()
    app.withdraw()
    try:
        dialog = _ParamSelectDialog(
            app, [("通道参数（全部通道）", "电压每格", True)])
        try:
            dialog._cancel()
            assert dialog.result is None
        finally:
            if dialog.winfo_exists():
                dialog.destroy()
    finally:
        app.destroy()


def test_on_apply_e2e_passes_selection(monkeypatch):
    """端到端：_on_apply 弹出真实对话框（after 回调里代用户勾选/确认），
    selected 集合传入 apply_config；取消则不执行。"""
    from gui import app as app_module
    from gui.app import AppWindow, _ParamSelectDialog
    from instruments.base import ApplyResult

    monkeypatch.setattr(app_module.messagebox, "showinfo",
                        lambda title, message: None)

    class _FakeInstrument:
        connected = True
        idn = "TEKTRONIX,MSO54,C000001,SCPY:1.0"

        def __init__(self):
            self.calls = []

        def restorable_params(self):
            return [("通道参数（全部通道）", "带宽限制", False),
                    ("通道参数（全部通道）", "电压每格", True)]

        def apply_config(self, config, selected=None):
            self.calls.append((config, selected))
            return ApplyResult(total=1, ok=1)

    fake = _FakeInstrument()
    app = AppWindow()
    app.withdraw()
    try:
        app._instrument = fake
        app._loaded_config = {"示波器": {}}

        def drive_dialog():
            for child in app.winfo_children():
                if isinstance(child, _ParamSelectDialog):
                    child._vars["带宽限制"].set(True)  # 用户勾上带宽限制
                    child._confirm()
                    return
            raise AssertionError("对话框未弹出")

        app.after(300, drive_dialog)
        app._on_apply()

        for _ in range(200):
            app.update()
            if fake.calls:
                break
            time.sleep(0.05)
        app.update()
        assert fake.calls and fake.calls[0][1] == {"电压每格", "带宽限制"}

        # 取消路径：重新走一遍，对话框选取消，不应有任何调用
        fake.calls.clear()
        app._loaded_config = {"示波器": {}}

        def cancel_dialog():
            for child in app.winfo_children():
                if isinstance(child, _ParamSelectDialog):
                    child._cancel()
                    return

        app.after(300, cancel_dialog)
        app._on_apply()
        for _ in range(60):
            app.update()
            time.sleep(0.05)
        assert fake.calls == []
        assert app._apply_btn.instate(["disabled"]) is False
    finally:
        app.destroy()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_gui.py -q`
Expected: 3 FAILED（`cannot import name '_ParamSelectDialog'`）

- [ ] **Step 3: 实现 gui/app.py**

`gui/app.py` 的 `AppWindow` 类定义之前加入对话框类：

```python
class _ParamSelectDialog(tk.Toplevel):
    """参数选择对话框：result = None（取消）或勾选参数名集合（确认）。"""

    def __init__(self, master, params):
        super().__init__(master)
        self.title("选择要恢复的参数")
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        self._vars = {}
        ttk.Label(self, text="勾选的参数将恢复到配置文件保存的值；"
                             "通道参数勾选项作用于全部通道。"
           ).pack(padx=12, pady=(10, 4))
        groups = {}
        for group, key, default in params:
            groups.setdefault(group, []).append((key, default))
        for group, entries in groups.items():
            frame = ttk.LabelFrame(self, text=group, padding=8)
            frame.pack(fill="x", padx=10, pady=3)
            for index, (key, default) in enumerate(entries):
                var = tk.BooleanVar(value=default)
                self._vars[key] = var
                ttk.Checkbutton(frame, text=key, variable=var).grid(
                    row=index // 2, column=index % 2, sticky="w", padx=8, pady=1)
        buttons = ttk.Frame(self, padding=(10, 6))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="全选",
                   command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(buttons, text="全不选",
                   command=lambda: self._set_all(False)).pack(side="left", padx=(4, 0))
        ttk.Button(buttons, text="取消", command=self._cancel).pack(side="right")
        ttk.Button(buttons, text="恢复", command=self._confirm).pack(
            side="right", padx=(4, 0))
        self.bind("<Return>", lambda _event: self._confirm())
        self.bind("<Escape>", lambda _event: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grab_set()

    def _set_all(self, value):
        for var in self._vars.values():
            var.set(value)

    def _confirm(self):
        self.result = {key for key, var in self._vars.items() if var.get()}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
```

`AppWindow` 中 `_on_apply` 方法替换为（校验之后、启动线程之前插入弹窗）：

```python
    def _on_apply(self):
        if self._busy:
            return
        if self._instrument is None or not self._instrument.connected:
            messagebox.showwarning("提示", "请先连接仪器")
            return
        if self._loaded_config is None:
            messagebox.showwarning("提示", "请先加载配置文件")
            return
        params = self._instrument.restorable_params()
        selected = None
        if params:
            selected = self._show_param_dialog(params)
            if selected is None:
                return  # 用户取消，不执行任何写入
            self._log(f"== 恢复参数范围: {len(selected)} 类 ==")

        def work():
            try:
                result = self._instrument.apply_config(self._loaded_config,
                                                       selected=selected)
                self._queue.put(("done", "apply", result, None))
            except Exception as exc:
                self._queue.put(("done", "apply", None, str(exc)))

        self._set_busy(True)
        self._set_status("正在应用配置…", "gray")
        self._log("== 开始应用配置 ==")
        threading.Thread(target=work, daemon=True).start()
```

并在 `AppWindow` 中新增方法（放在 `_on_apply` 之后）：

```python
    def _show_param_dialog(self, params):
        dialog = _ParamSelectDialog(self, params)
        self.wait_window(dialog)
        return dialog.result
```

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `python -m pytest tests/ -q`
Expected: 60 passed（57 + 3）

- [ ] **Step 5: Commit**

```bash
git add gui/app.py tests/test_gui.py
git commit -m "feat: 应用配置前弹出参数选择对话框（按参数类型勾选）"
```

---

### Task 3: 文档更新与收尾

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: 更新 README.md**

功能列表追加一条（"应用配置到仪器"条目之后）：

```markdown
- **按需选择恢复参数**：应用前弹出勾选窗口，可去掉不想恢复的参数；带宽限制等探头相关项默认不勾选（换探头后可设范围不同）
```

使用步骤第 4 步改为：

```markdown
4. 下次实验时：连接仪器 → 点**加载配置文件**选当时的 json → 点**应用配置到仪器** → 在弹窗中勾选要恢复的参数（默认全选，带宽限制不选）→ 点**恢复**
```

常见问题追加：

```markdown
- **带宽限制默认不恢复**：带宽上限受物理接入的探头制约（换探头后如 250→200 MHz），恢复保存值必然不一致，故参数选择窗口中默认不勾选；用同一探头想恢复时手动勾上即可
```

版本历史表追加：

```markdown
| V0.1（2026-10-13 功能） | 2026-10-13 | 参数选择恢复：应用前弹出按参数类型勾选的对话框（默认全选，探头相关的带宽限制默认不勾选）；`apply_config` 支持 `selected` 过滤，未选择项日志记"未选择，跳过" |
```

- [ ] **Step 2: 更新 AGENTS.md**

"白名单命令表模式"段落末尾追加一句：

```markdown
探头相关参数（`_PROBE_DEPENDENT`，如带宽限制）在 `restorable_params()` 清单中默认不勾选；`apply_config(config, selected)` 的 `selected` 为参数名集合，`None` 表示全恢复。
```

- [ ] **Step 3: 全量回归**

Run: `python -m pytest tests/ -q`
Expected: 60 passed

- [ ] **Step 4: Commit**

```bash
git add README.md AGENTS.md
git commit -m "docs: 参数选择恢复功能说明（README/AGENTS.md）"
```

---

## Self-Review 记录

- **Spec 覆盖**：需求 1-5 → Task 2（对话框/取消）+ Task 1（selected 过滤/默认勾选）；交互流程 → Task 1/2；测试计划 6 项 → Task 1 Step 1（3 个）+ Task 2 Step 1（3 个，其中端到端合并了取消路径）；文档更新 → Task 3。✓
- **占位符**：无 TBD/TODO，所有步骤含完整代码。✓
- **类型一致性**：`restorable_params()` 返回 `(分组, 参数名, 默认勾选)` 三元组列表，Task 1 实现与 Task 2 测试/dialog 消费一致；`apply_config(config, selected=None)` 签名三处一致；`_ParamSelectDialog.result` 语义（None/set）在测试与实现一致。✓
