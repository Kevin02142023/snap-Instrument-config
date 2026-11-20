import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import config_store
from core.config_store import ConfigError
from instruments import discovery
from instruments import registry


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
        ttk.Button(buttons, text="确定", command=self._confirm).pack(
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


class AppWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("仪器配置快照工具 - InstrSnapConfig")
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
        self._scan_btn = ttk.Button(top, text="扫描", command=self._on_scan)
        self._scan_btn.pack(side="left")
        self._connect_btn = ttk.Button(top, text="连接", command=self._on_connect)
        self._connect_btn.pack(side="left", padx=(8, 0))
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
        for btn in (self._scan_btn, self._connect_btn, self._disconnect_btn,
                    self._save_btn, self._load_btn, self._apply_btn):
            btn.configure(state=state)

    # ---------- 事件处理 ----------

    def _on_scan(self):
        if self._busy:
            return
        self._set_busy(True)
        self._set_status("正在扫描仪器…", "gray")
        self._log("== 开始扫描可用仪器 ==")

        def work():
            try:
                resources = discovery.list_resources()
                self._queue.put(("done", "scan", resources, None))
            except Exception as exc:
                self._queue.put(("done", "scan", None, str(exc)))

        threading.Thread(target=work, daemon=True).start()

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
        if self._instrument is not None:
            self._instrument.disconnect()
            self._instrument = None
        instrument = item["cls"](
            log_callback=lambda msg: self._queue.put(("log", msg)))

        def work():
            try:
                instrument.connect(ip)
                self._queue.put(("done", "connect", None, None))
            except Exception as exc:
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
            except Exception as exc:
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

    def _show_param_dialog(self, params):
        dialog = _ParamSelectDialog(self, params)
        self.wait_window(dialog)
        return dialog.result

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
                               "apply": self._finish_apply,
                               "scan": self._finish_scan}[action]
                    try:
                        handler(data, error)
                    except Exception as exc:
                        self._log(f"[界面错误] {exc}")
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

    def _finish_scan(self, resources, error):
        self._set_busy(False)
        if error:
            self._set_status("扫描失败", "red")
            messagebox.showerror("扫描失败", error)
            return
        for resource in resources:
            self._log(f"[发现] {resource}")
        addresses = discovery.tcpip_ips(resources)
        if not addresses:
            self._set_status("未找到仪器", "orange")
            self._log("== 未发现可连接的 TCPIP 仪器 ==")
            return
        if len(addresses) == 1:
            self._fill_ip(addresses[0])
            return
        self._set_status(f"找到 {len(addresses)} 台仪器", "orange")
        self._choose_device(addresses)

    def _fill_ip(self, address):
        self._ip_var.set(address)
        self._set_status(f"扫描到仪器 {address}，可直接连接", "green")
        self._log(f"== 已填入地址 {address} ==")

    def _choose_device(self, addresses):
        win = tk.Toplevel(self)
        win.title("选择仪器")
        win.transient(self)
        win.resizable(False, False)
        ttk.Label(win, text="扫描到多台仪器，请选择：").pack(padx=12, pady=(12, 4))
        listbox = tk.Listbox(win, width=42, height=min(8, len(addresses)))
        listbox.pack(padx=12, pady=4)
        for address in addresses:
            listbox.insert("end", address)
        listbox.selection_set(0)
        listbox.focus_set()
        win.grab_set()

        def choose(_event=None):
            selection = listbox.curselection()
            if selection:
                self._fill_ip(addresses[selection[0]])
            win.destroy()

        listbox.bind("<Double-Button-1>", choose)
        ttk.Button(win, text="选择", command=choose).pack(pady=(4, 12))

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
        for line in result.equivalences:
            self._log(f"[等价] {line}")
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
