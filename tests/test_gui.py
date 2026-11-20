import time

import pytest


def test_app_window_smoke():
    from gui.app import AppWindow

    app = AppWindow()
    app.withdraw()  # 不显示窗口
    try:
        assert "InstrSnapConfig" in app.title()
        assert app._instrument is None
        assert app._loaded_config is None
        assert app._instrument_box["values"]  # 下拉列表非空
        app.update()  # 处理一轮事件循环
    finally:
        app.destroy()


def test_poll_queue_survives_handler_exception():
    from gui.app import AppWindow

    app = AppWindow()
    app.withdraw()
    try:
        # 注入一个会抛异常的 handler：绕过 action 映射直接测兜底逻辑
        original = app._finish_connect
        app._finish_connect = lambda data, error: (_ for _ in ()).throw(RuntimeError("boom"))
        app._queue.put(("done", "connect", None, None))
        app._poll_queue()  # 不应抛出
        app._queue.put(("log", "循环存活"))
        app._poll_queue()
        assert "循环存活" in app._log_text.get("1.0", "end")
        app._finish_connect = original
    finally:
        app.destroy()


def test_finish_scan_single_device_fills_ip():
    from gui.app import AppWindow

    app = AppWindow()
    app.withdraw()
    try:
        app._finish_scan(
            ("TCPIP0::169.254.1.100::inst0::INSTR", "ASRL25::INSTR"), None)
        assert app._ip_var.get() == "169.254.1.100"
        assert "扫描" in app._status_label.cget("text")
        assert "169.254.1.100" in app._log_text.get("1.0", "end")
    finally:
        app.destroy()


def test_finish_scan_multiple_devices_opens_chooser():
    from gui.app import AppWindow

    app = AppWindow()
    app.withdraw()
    try:
        chosen = []
        app._choose_device = lambda addresses: chosen.extend(addresses)
        app._finish_scan(
            ("TCPIP0::192.168.1.20::inst0::INSTR",
             "TCPIP0::169.254.1.100::inst0::INSTR"), None)
        assert chosen == ["192.168.1.20", "169.254.1.100"]
        assert app._ip_var.get() == "192.168.1.20"  # 未被改动
    finally:
        app.destroy()


def test_finish_scan_no_devices_reports_missing():
    from gui.app import AppWindow

    app = AppWindow()
    app.withdraw()
    try:
        app._finish_scan(("ASRL25::INSTR",), None)
        assert "未找到" in app._status_label.cget("text")
        assert app._ip_var.get() == "192.168.1.20"  # 未被改动
    finally:
        app.destroy()


def test_finish_scan_error_shows_and_resets(monkeypatch):
    from gui import app as app_module
    from gui.app import AppWindow

    shown = []
    monkeypatch.setattr(
        app_module.messagebox, "showerror",
        lambda title, message: shown.append((title, message)))
    app = AppWindow()
    app.withdraw()
    try:
        app._set_busy(True)
        app._finish_scan(None, "VISA 扫描错误")
        assert shown and shown[0][0] == "扫描失败"
        assert "扫描失败" in app._status_label.cget("text")
        assert app._connect_btn.instate(["disabled"]) is False  # busy 已复位
    finally:
        app.destroy()


def test_finish_apply_logs_equivalences(monkeypatch):
    from gui import app as app_module
    from gui.app import AppWindow
    from instruments.base import ApplyResult

    shown = []
    monkeypatch.setattr(
        app_module.messagebox, "showinfo",
        lambda title, message: shown.append((title, message)))
    app = AppWindow()
    app.withdraw()
    try:
        result = ApplyResult(total=1, ok=1)
        result.equivalences.append("触发.触发类型: 期望 'EDG'，实际 'EDGE'（等价格式）")
        app._finish_apply(result, None)
        log = app._log_text.get("1.0", "end")
        assert "[等价] 触发.触发类型" in log
        assert "应用完成" in app._status_label.cget("text")
    finally:
        app.destroy()


def test_on_scan_runs_in_background_and_reports():
    from gui import app as app_module
    from gui.app import AppWindow

    class _FakeDiscovery:
        def __init__(self):
            self.calls = 0

        def list_resources(self):
            self.calls += 1
            return ("TCPIP0::10.0.0.8::inst0::INSTR",)

    fake = _FakeDiscovery()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(app_module.discovery, "list_resources", fake.list_resources)
    app = AppWindow()
    app.withdraw()
    try:
        app._on_scan()
        for _ in range(200):  # 最多等 20 秒等后台线程完成
            app.update()
            if app._ip_var.get() == "10.0.0.8":
                break
            time.sleep(0.1)
        app.update()
        assert fake.calls == 1
        assert app._ip_var.get() == "10.0.0.8"
        assert "扫描" in app._status_label.cget("text")
        assert app._connect_btn.instate(["disabled"]) is False
    finally:
        app.destroy()
        monkeypatch.undo()


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
