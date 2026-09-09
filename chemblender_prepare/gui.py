"""Small desktop front end; all scientific work runs through the CLI process."""

from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import time
from tempfile import TemporaryDirectory

from cbq_core.worker_protocol import read_result
from .core.import_pipeline.request import ValidationMode


COMMANDS = ("convert", "inspect", "derive", "validate", "upgrade", "export",
            "formats", "capabilities", "doctor")


def command_arguments(values):
    """Build argv without a shell, preserving spaces and literal parameter text."""
    command = values["command"]
    if command not in COMMANDS:
        raise ValueError("Choose a supported operation")
    argv = [command, "--json"]
    sources = [line.strip() for line in values.get("sources", "").splitlines() if line.strip()]
    inline = command == "convert" and values.get("source_kind", "files") in {"smiles", "pubchem"}
    if inline:
        name = "smiles_text" if values["source_kind"] == "smiles" else "pubchem"
        text = values.get(name, "").strip()
        if not text:
            raise ValueError("Enter SMILES text or PubChem CID/name")
        argv.extend(("--" + name.replace("_", "-"), text))
    elif command not in {"formats", "capabilities", "doctor"}:
        if not sources or (command != "convert" and len(sources) != 1):
            raise ValueError("Choose input files; this operation requires one input except convert")
        argv.extend(sources)
    if command in {"convert", "derive", "upgrade", "export"}:
        output = values.get("output", "").strip()
        if not output:
            raise ValueError("Choose a new output path")
        argv.extend(("--output", output))
    if command == "convert":
        mode = values.get("validation-mode", "balanced")
        if mode not in {item.value for item in ValidationMode}:
            raise ValueError("Choose a supported validation mode")
        argv.extend(("--validation-mode", mode))
    scalar = {
        "convert": ("reader", "project", "entity", "preset", "unit"),
        "inspect": ("reader",),
        "derive": ("operation",),
        "export": ("entity", "format", "cif-mode", "missing-value-token", "poscar-comment",
                   "poscar-coordinate-mode", "poscar-scale-policy", "poscar-target-volume",
                   "poscar-source-scale", "poscar-velocity-mode"),
    }
    for name in scalar.get(command, ()):
        if inline and name != "project":
            continue
        if command == "export" and (
            (name.startswith("poscar-") and values.get("format") != "poscar")
            or (name == "cif-mode" and values.get("format") != "cif")
            or (name == "missing-value-token" and values.get("format") != "extxyz")
        ):
            continue
        value = values.get(name, "").strip()
        if value:
            argv.extend(("--" + name, value))
    if not inline and command in {"convert", "export"} and values.get("dataset_index", "").strip():
        argv.extend(("--dataset-index", values["dataset_index"].strip()))
    if command == "derive":
        parameters = values.get("parameters", "{}").strip() or "{}"
        if not isinstance(json.loads(parameters), dict):
            raise ValueError("Parameters must be a JSON object")
        argv.extend(("--parameters", parameters))
        for entity in values.get("inputs", "").split():
            argv.extend(("--input", entity))
    list_fields = {"convert": (("params", "param"), ("companions", "companion")),
                   "derive": (("companions", "artifact"),)}
    for name, flag in list_fields.get(command, ()):
        if inline:
            continue
        for line in values.get(name, "").splitlines():
            if line.strip():
                argv.extend(("--" + flag, line.strip()))
    if command == "export":
        selective = values.get("poscar-include-selective-dynamics", "")
        if selective and values.get("format") == "poscar":
            if selective not in {"true", "false"}:
                raise ValueError("Selective dynamics must be true or false")
            argv.append("--poscar-include-selective-dynamics" if selective == "true"
                        else "--no-poscar-include-selective-dynamics")
        if values.get("confirm_loss"):
            argv.append("--confirm-loss")
        if values.get("preview"):
            argv.append("--preview")
    if command == "convert" and values.get("infer_bonds"):
        argv.append("--infer-bonds")
    return argv


class CliProcess:
    """One owned CLI process, using the existing result/progress/cancel files."""

    def __init__(self, arguments, *, python_executable=sys.executable):
        with ExitStack() as resources:
            self.temporary = TemporaryDirectory(prefix="cbq-gui-")
            resources.enter_context(self.temporary)
            self.root = Path(self.temporary.name)
            self.task = self.root / "task"
            self.cancel_path = self.root / "cancel"
            self.cancel_started = None
            self.terminated = False
            self.diagnostic = arguments[0] in {"capabilities", "doctor"}
            self.stdout = resources.enter_context((self.root / "stdout.log").open("wb"))
            self.stderr = resources.enter_context((self.root / "stderr.log").open("wb"))
            argv = [str(python_executable), "-m", "chemblender_prepare", *arguments]
            if not self.diagnostic:
                argv.extend(("--task-directory", str(self.task),
                             "--cancel-file", str(self.cancel_path)))
            self.process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                stdout=self.stdout, stderr=self.stderr,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            # Construction succeeded; close() owns these resources after process exit.
            resources.pop_all()

    def cancel(self):
        if self.cancel_started is None:
            self.cancel_started = time.monotonic()
        self.cancel_path.touch(exist_ok=True)

    def progress(self):
        try:
            path = self.task / "progress.json"
            candidates = [candidate for candidate in (path, *self.task.glob("reader-*/progress.json")) if candidate.is_file()]
            if candidates:
                path = max(candidates, key=lambda candidate: candidate.stat().st_mtime_ns)
            document = json.loads(path.read_text(encoding="utf-8"))
            completed, total = document["completed"], document["total"]
            if type(completed) is int and type(total) is int and 0 <= completed <= total and total > 0:
                return completed / total
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def poll(self):
        if self.process.poll() is None:
            if (self.cancel_started is not None and not self.terminated
                    and time.monotonic() - self.cancel_started >= 2.0):
                self.process.terminate()
                self.terminated = True
            return None
        self.stdout.close()
        self.stderr.close()
        if self.diagnostic:
            try:
                return json.loads((self.root / "stdout.log").read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise RuntimeError("CLI returned an invalid diagnostic document") from error
        result_path = self.task / "result.json"
        if result_path.is_file():
            return read_result(result_path)
        if self.terminated:
            raise RuntimeError("CLI did not acknowledge cancellation within two seconds and was terminated; "
                               "no final result was received. Verify any output before using it.")
        message = (self.root / "stderr.log").read_text(encoding="utf-8", errors="replace")
        raise RuntimeError(message.strip() or f"CLI exited with code {self.process.returncode} without a result")

    def close(self):
        if self.process.poll() is None:
            raise RuntimeError("Cancel and wait for the owned process before closing it")
        self.stdout.close()
        self.stderr.close()
        self.temporary.cleanup()


class PrepareWindow:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk

        self.root, self.job, self.closing = root, None, False
        root.title("ChemBlender Prepare — 计算结果准备")
        root.geometry("900x850")
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        self.values, self.field_widgets = {}, {}
        row = 0

        def entry(name, label, default="", choices=None):
            nonlocal row
            caption = ttk.Label(frame, text=label)
            caption.grid(row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            value = tk.StringVar(value=default)
            widget = ttk.Combobox(frame, textvariable=value, values=choices, state="readonly") if choices else ttk.Entry(frame, textvariable=value)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            self.values[name] = value
            self.field_widgets[name] = (caption, widget)
            row += 1
            return widget

        entry("command", "操作", "convert", COMMANDS)
        entry("python", "运行环境 Python", sys.executable)
        source_label = ttk.Label(frame, text="输入文件／CBQ：每行一个路径")
        source_label.grid(row=row, column=0, sticky="nw", pady=3)
        self.sources = tk.Text(frame, height=3, wrap="none")
        self.sources.grid(row=row, column=1, sticky="ew", pady=3)
        row += 1
        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=1, sticky="w")
        ttk.Button(buttons, text="选择输入文件", command=self.choose_sources).pack(side="left")
        ttk.Button(buttons, text="选择 CBQ 目录", command=self.choose_project).pack(side="left", padx=6)
        self.source_widgets = (source_label, self.sources, buttons)
        row += 1
        entry("output", "新输出文件／CBQ 路径")
        self.output_button = ttk.Button(frame, text="选择输出位置", command=self.choose_output)
        self.output_button.grid(row=row, column=1, sticky="w")
        row += 1
        self.advanced = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="显示高级选项", variable=self.advanced, command=self.update_fields).grid(row=row, column=1, sticky="w")
        row += 1
        entry("source_kind", "输入类型", "files", ("files", "smiles", "pubchem"))
        from cbq_core.element_data import preset_smiles
        preset = entry("smiles_preset", "历史 SMILES 片段（选择后核对文本）", "", ("", *preset_smiles))
        preset.bind("<<ComboboxSelected>>", self.select_smiles_preset)
        entry("smiles_text", "SMILES（生成二维坐标；三维需另行计算）")
        entry("pubchem", "PubChem CID／名称（执行时联网下载）")
        entry("reader", "Reader ID（留空自动识别）")
        entry("validation-mode", "校验模式", "balanced", tuple(mode.value for mode in ValidationMode))
        entry("project", "已有 CBQ（可选，保留原包）")
        entry("entity", "结构／导出实体 UUID")
        entry("preset", "Cube 物理量 preset（可选）")
        entry("unit", "Cube 数值单位（与 preset 成对）")
        entry("dataset_index", "Cube dataset index（从 0 开始，留空不选择）")
        entry("operation", "派生操作", "wavefunction.mo_grid")
        entry("inputs", "派生输入 UUID（按顺序，空格分隔）")
        entry("parameters", "派生参数 JSON", "{}")
        entry("format", "导出格式", "xyz", ("xyz", "extxyz", "cube", "mol", "mol2", "pdb", "pqr", "sdf", "smiles", "cif", "poscar", "cjson", "qcschema"))
        entry("cif-mode", "CIF 模式", "", ("", "preserve", "normalized"))
        entry("missing-value-token", "缺失值标记（可选）")
        entry("poscar-comment", "POSCAR 注释")
        entry("poscar-coordinate-mode", "POSCAR 坐标", "", ("", "direct", "cartesian"))
        entry("poscar-scale-policy", "POSCAR 缩放", "", ("", "unit", "preserve_source", "target_volume"))
        entry("poscar-target-volume", "目标体积（Å³）")
        entry("poscar-source-scale", "保留的源比例值")
        entry("poscar-include-selective-dynamics", "保留约束", "", ("", "true", "false"))
        entry("poscar-velocity-mode", "速度坐标", "", ("", "direct", "cartesian"))
        self.text_values = {}
        for name, label in (("params", "Reader 参数 KEY=VALUE（每行一个）"),
                            ("companions", "配套文件 ROLE=PATH（每行一个）")):
            caption = ttk.Label(frame, text=label)
            caption.grid(row=row, column=0, sticky="nw", pady=3)
            widget = tk.Text(frame, height=2, wrap="none")
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            self.text_values[name] = widget
            self.field_widgets[name] = (caption, widget)
            row += 1
        self.preview = tk.BooleanVar(value=True)
        self.confirm_loss = tk.BooleanVar(value=False)
        self.infer_bonds = tk.BooleanVar(value=False)
        checks = ttk.Frame(frame)
        checks.grid(row=row, column=1, sticky="w")
        ttk.Checkbutton(checks, text="导出先预览", variable=self.preview).pack(side="left")
        ttk.Checkbutton(checks, text="已阅读并确认导出损失", variable=self.confirm_loss).pack(side="left", padx=10)
        ttk.Checkbutton(checks, text="转换时推断缺失的键", variable=self.infer_bonds).pack(side="left")
        row += 1
        actions = ttk.Frame(frame)
        actions.grid(row=row, column=1, sticky="ew", pady=8)
        self.run_button = ttk.Button(actions, text="执行", command=self.start)
        self.run_button.pack(side="left")
        ttk.Button(actions, text="取消任务", command=self.cancel).pack(side="left", padx=8)
        ttk.Button(actions, text="复核构象候选", command=self.review_conformers).pack(side="left", padx=8)
        self.status = tk.StringVar(value="输入文件在外部准备；Blender 读取生成的 CBQ。")
        ttk.Label(actions, textvariable=self.status).pack(side="left")
        row += 1
        self.bar = ttk.Progressbar(frame, maximum=1.0)
        self.bar.grid(row=row, column=0, columnspan=2, sticky="ew")
        row += 1
        self.report = tk.Text(frame, height=9, wrap="word")
        self.report.grid(row=row, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        frame.rowconfigure(row, weight=1)
        for value in self.values.values():
            value.trace_add("write", self.invalidate_export_confirmation)
        for widget in (self.sources, *self.text_values.values()):
            widget.edit_modified(False)
            widget.bind("<<Modified>>", self.input_text_changed)
        self.values["source_kind"].trace_add("write", lambda *_: self.update_fields())
        self.values["command"].trace_add("write", lambda *_: self.update_fields())
        self.values["format"].trace_add("write", lambda *_: self.update_fields())
        self.update_fields()
        root.protocol("WM_DELETE_WINDOW", self.request_close)

    def select_smiles_preset(self, _event=None):
        from cbq_core.element_data import preset_smiles
        key = self.values["smiles_preset"].get()
        if key in preset_smiles:
            self.values["smiles_text"].set(preset_smiles[key][1])
            self.status.set("预设文本已填入；请核对立体化学与端基后执行。")

    def review_conformers(self):
        import tkinter as tk
        from tkinter import ttk, messagebox
        if self.job is not None:
            return
        try:
            document = json.loads(self.report.get("1.0", "end"))
            metadata = document["metadata"]
            groups = metadata["conformer_suggestions"]
            if document["status"] != "success" or metadata["command"] != "inspect" or not groups:
                raise ValueError("请先检查包含构象候选的 CBQ")
            source = metadata["cbq_path"]
            if not isinstance(source, str) or not source or not isinstance(groups, list) or len(groups) > 100:
                raise ValueError("无效的构象检查结果")
            # The report is editable; reject malformed evidence before creating a dialog.
            for group in groups:
                if not isinstance(group, dict) or not isinstance(group.get("evidence"), list):
                    raise ValueError("无效的构象映射依据")
                for key in ("id", "snapshot"):
                    if not isinstance(group.get(key), str) or not group[key]:
                        raise ValueError("缺少构象身份或快照")
                if type(group.get("record_count")) is not int or group["record_count"] < 2:
                    raise ValueError("无效的构象记录数")
                if any(type(group.get(key)) is not bool for key in ("requires_review", "evidence_truncated")):
                    raise ValueError("无效的复核状态")
                for item in group["evidence"]:
                    if (not isinstance(item, dict) or not isinstance(item.get("record_id"), str)
                            or type(item.get("mapping_truncated")) is not bool):
                        raise ValueError("无效的原子映射记录")
        except (ValueError, KeyError, TypeError) as error:
            messagebox.showerror("无法复核", str(error), parent=self.root)
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("复核 CBQ 构象候选")
        dialog.transient(self.root)
        ttk.Label(dialog, text="选择候选并阅读映射依据；填入后还需选择新输出位置并点击执行。").pack(padx=12, pady=8)
        choice = ttk.Combobox(dialog, name="candidate", state="readonly",
            values=[f"{index + 1}: {group['record_count']} records — {group['id']}" for index, group in enumerate(groups)])
        choice.pack(fill="x", padx=12)
        details = tk.Text(dialog, name="evidence", width=95, height=20, wrap="word", state="disabled")
        details.pack(fill="both", expand=True, padx=12, pady=8)
        reviewed = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, name="reviewed", text="我已复核该候选的完整原子映射及歧义", variable=reviewed).pack()
        def select(_event=None):
            reviewed.set(False)
            index = choice.current()
            details.configure(state="normal")
            details.delete("1.0", "end")
            if index >= 0:
                details.insert("1.0", json.dumps(groups[index], ensure_ascii=False, indent=2))
            details.configure(state="disabled")
        def apply():
            index = choice.current()
            if index < 0:
                return
            group = groups[index]
            if group["evidence_truncated"] or any(item["mapping_truncated"] for item in group["evidence"]):
                messagebox.showerror("无法接受", "映射依据被截断，不能据此接受分组。", parent=dialog)
                return
            if group["requires_review"] and not reviewed.get():
                messagebox.showerror("需要复核", "请先复核该候选的原子映射与歧义。", parent=dialog)
                return
            self.values["command"].set("derive")
            self.sources.delete("1.0", "end")
            self.sources.insert("1.0", source)
            self.values["operation"].set("molecule.group_conformers")
            self.values["inputs"].set(" ".join(item["record_id"] for item in group["evidence"]))
            self.values["parameters"].set(json.dumps({"suggestion_id": group["id"],
                "snapshot": group["snapshot"], "review_confirmed": reviewed.get()}))
            self.values["output"].set("")
            self.text_values["companions"].delete("1.0", "end")
            self.status.set("构象分组已填入；选择新输出位置后点击执行。")
            dialog.destroy()
        choice.bind("<<ComboboxSelected>>", select)
        ttk.Button(dialog, name="apply", text="填入派生任务", command=apply).pack(pady=8)
        dialog.grab_set()

    def invalidate_export_confirmation(self, *_):
        # Approval belongs to the current inputs, never to the next export.
        self.confirm_loss.set(False)
        self.preview.set(True)

    def input_text_changed(self, event):
        if event.widget.edit_modified():
            event.widget.edit_modified(False)
            self.invalidate_export_confirmation()

    def update_fields(self):
        command = self.values["command"].get()
        visible = {"command", "python"}
        if command in {"convert", "derive", "upgrade", "export"}:
            visible.add("output")
        visible.update({"convert": {"reader", "validation-mode", "preset", "unit", "dataset_index"},
                        "inspect": {"reader"}, "derive": {"operation", "inputs", "parameters", "companions"},
                        "export": {"entity", "format", "dataset_index"}}.get(command, set()))
        if command == "convert":
            visible.add("source_kind")
            if self.values["source_kind"].get() in {"smiles", "pubchem"}:
                visible.update({"smiles_text", "smiles_preset"} if self.values["source_kind"].get() == "smiles" else {"pubchem"})
                visible.difference_update({"reader", "preset", "unit", "dataset_index"})
        if command == "convert" and self.advanced.get():
            visible.update({"project"} if self.values["source_kind"].get() in {"smiles", "pubchem"}
                           else {"project", "entity", "params", "companions"})
        if command == "export":
            target = self.values["format"].get()
            if target == "cif":
                visible.add("cif-mode")
            if target == "extxyz":
                visible.add("missing-value-token")
            if target == "poscar":
                visible.update(name for name in self.field_widgets if name.startswith("poscar-"))
        for name, widgets in self.field_widgets.items():
            for widget in widgets:
                widget.grid() if name in visible else widget.grid_remove()
        needs_input = command not in {"formats", "capabilities", "doctor"}
        for widget in self.source_widgets:
            widget.grid() if needs_input else widget.grid_remove()
        self.output_button.grid() if "output" in visible else self.output_button.grid_remove()

    def choose_sources(self):
        from tkinter import filedialog
        paths = filedialog.askopenfilenames(parent=self.root)
        if paths:
            self.sources.delete("1.0", "end")
            self.sources.insert("1.0", "\n".join(paths))

    def choose_project(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.root, title="选择 .cbq 目录")
        if path:
            self.sources.delete("1.0", "end")
            self.sources.insert("1.0", path)

    def choose_output(self):
        from tkinter import filedialog
        suffix = "" if self.values["command"].get() == "export" else ".cbq"
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=suffix, title="选择尚不存在的新输出路径")
        if path:
            self.values["output"].set(path)

    def start(self):
        from tkinter import messagebox
        if self.job is not None:
            return
        values = {name: value.get() for name, value in self.values.items()}
        values.update({name: widget.get("1.0", "end") for name, widget in self.text_values.items()})
        values.update(sources=self.sources.get("1.0", "end"), preview=self.preview.get(), confirm_loss=self.confirm_loss.get(), infer_bonds=self.infer_bonds.get())
        try:
            arguments = command_arguments(values)
            self.run_button.state(["disabled"])
            self.status.set("处理中…")
            self.bar.configure(mode="indeterminate")
            self.bar.start(30)
            # Tk callbacks run after this handler returns. A failed launch leaves a harmless stale poll.
            self.root.after(100, self.poll)
            self.job = CliProcess(arguments, python_executable=values["python"])
        except BaseException as error:
            try:
                self.bar.stop()
                self.run_button.state(["!disabled"])
            except BaseException as cleanup_error:
                if ((not isinstance(cleanup_error, Exception) or isinstance(cleanup_error, MemoryError))
                        and isinstance(error, Exception) and not isinstance(error, MemoryError)):
                    raise
                error.add_note(f"UI cleanup failed: {type(cleanup_error).__name__}")
            if (not isinstance(error, Exception) or isinstance(error, MemoryError)):
                raise
            messagebox.showerror("无法开始", str(error), parent=self.root)

    def cancel(self):
        if self.job is not None:
            self.job.cancel()
            self.status.set("已请求取消，等待当前计算块结束…")

    def poll(self):
        from cbq_core.worker_protocol import result_document
        job = self.job
        if job is None:
            return
        failure = None
        terminal = False
        try:
            result = job.poll()
            terminal = result is not None
            if result is None:
                fraction = job.progress()
                if fraction is not None:
                    self.bar.stop()
                    self.bar.configure(mode="determinate", value=fraction)
                self.root.after(100, self.poll)
                return
            if isinstance(result, dict):
                text = json.dumps(result, ensure_ascii=False, indent=2)
                self.status.set("诊断完成" if result.get("status") != "failed"
                                else "诊断失败；查看下方详情")
            else:
                text = json.dumps(result_document(result), ensure_ascii=False, indent=2)
                self.status.set({"success": "完成", "cancelled": "已取消", "error": "失败；查看下方诊断"}[result.status.value])
        except BaseException as error:
            failure = error
            terminal = job.process.poll() is not None
            if not terminal:
                # Keep ownership and polling even if cancellation itself fails.
                try:
                    job.cancel()
                finally:
                    self.root.after(100, self.poll)
                if (not isinstance(error, Exception) or isinstance(error, MemoryError)):
                    raise
                self.status.set("失败；等待任务退出后清理")
                self.report.delete("1.0", "end")
                self.report.insert("1.0", str(error))
                return
            if (not isinstance(error, Exception) or isinstance(error, MemoryError)):
                raise
            text = str(error)
            self.status.set("失败；查看下方诊断")
        finally:
            if terminal:
                try:
                    job.close()
                except BaseException as cleanup_error:
                    self.root.after(100, self.poll)
                    cleanup_fatal = not isinstance(cleanup_error, Exception) or isinstance(cleanup_error, MemoryError)
                    failure_fatal = not isinstance(failure, Exception) or isinstance(failure, MemoryError)
                    if failure is not None and (failure_fatal or not cleanup_fatal):
                        failure.add_note(f"Task cleanup failed: {type(cleanup_error).__name__}")
                        raise failure
                    raise
                self.job = None
        self.bar.stop()
        self.run_button.state(["!disabled"])
        self.report.delete("1.0", "end")
        self.report.insert("1.0", text)
        if self.closing:
            self.root.destroy()

    def request_close(self):
        if self.job is None:
            self.root.destroy()
        else:
            self.closing = True
            self.cancel()


def main():
    import tkinter as tk
    root = tk.Tk()
    PrepareWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
