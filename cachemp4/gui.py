from __future__ import annotations

import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import __version__
from .core import Cancelled, Job, convert, scan, tool_path


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"B站缓存转 MP4  ·  {__version__}")
        root.geometry("1020x700")
        root.minsize(840, 580)
        root.configure(bg="#f2f5fa")
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.closing = False
        self.jobs: list[Job] = []
        self.controls: list[ttk.Widget] = []
        preferred = Path(r"D:\user\Videos\bilibili")
        default = preferred if preferred.is_dir() else Path.home() / "Videos" / "bilibili"
        self.source = tk.StringVar(value=str(default))
        self.output = tk.StringVar(value=str(default.parent / "bilibili_mp4"))
        self.status = tk.StringVar(value="选择缓存目录，点击「扫描缓存」开始。")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f2f5fa")
        style.configure("TLabel", background="#f2f5fa", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", padding=(12, 7), font=("Microsoft YaHei UI", 10))
        style.configure("Accent.TButton", background="#1963d1", foreground="white")
        style.map("Accent.TButton", background=[("active", "#164fa6"), ("disabled", "#9fb4cf")])
        style.configure("Treeview", rowheight=32, font=("Microsoft YaHei UI", 10))
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"), padding=7)
        main = ttk.Frame(root, padding=24)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="把缓存，变成可播放的视频", font=("Microsoft YaHei UI", 21, "bold")).pack(anchor="w")
        ttk.Label(main, text="自动配对音视频  ·  无损合并  ·  保留原始缓存", foreground="#52637b").pack(anchor="w", pady=(6, 20))
        paths = ttk.Frame(main)
        paths.pack(fill="x")
        paths.columnconfigure(1, weight=1)
        for row, (label, variable) in enumerate((("缓存目录", self.source), ("输出目录", self.output))):
            ttk.Label(paths, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
            entry = ttk.Entry(paths, textvariable=variable, font=("Microsoft YaHei UI", 10))
            entry.grid(row=row, column=1, sticky="ew", pady=6)
            browse = ttk.Button(paths, text="选择文件夹", command=lambda v=variable: self.browse(v))
            browse.grid(row=row, column=2, padx=(10, 0), pady=6)
            self.controls.extend((entry, browse))
        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(16, 12))
        for title, action, accent in (("扫描缓存", self.start_scan, False),
                                      ("合并全部", lambda: self.start_convert(False), True),
                                      ("合并选中", lambda: self.start_convert(True), False)):
            button = ttk.Button(buttons, text=title, command=action, style="Accent.TButton" if accent else "TButton")
            button.pack(side="left", padx=(0, 8))
            self.controls.append(button)
        self.stop_button = ttk.Button(buttons, text="停止", command=self.cancel.set, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Button(buttons, text="打开输出目录", command=self.open_output).pack(side="right")
        table = ttk.Frame(main)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("title", "size", "state"), show="headings", selectmode="extended")
        for column, title, width in (("title", "视频标题", 540), ("size", "缓存大小", 110), ("state", "状态", 150)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, minwidth=80, stretch=column == "title")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Control-a>", lambda event: self.select_all())
        ttk.Label(main, text="可用 Ctrl / Shift 多选；已存在的同名 MP4 会自动跳过。", foreground="#52637b").pack(anchor="w", pady=(7, 8))
        self.progress = ttk.Progressbar(main, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 8))
        ttk.Label(main, textvariable=self.status, wraplength=920).pack(anchor="w", pady=(0, 8))
        self.log = ScrolledText(main, height=6, font=("Microsoft YaHei UI", 9), relief="flat", bg="#e8edf5", state="disabled", wrap="word")
        self.log.pack(fill="x")
        self.append_log("就绪。支持 video.m4s + audio.m4s，以及编号形式的 .m4s 缓存。")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.pump)

    def append_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def browse(self, variable: tk.StringVar):
        result = filedialog.askdirectory(parent=self.root, initialdir=variable.get(), title="选择文件夹")
        if result:
            variable.set(result)

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())
        return "break"

    def set_busy(self, value: bool):
        self.busy = value
        for control in self.controls:
            control.configure(state="disabled" if value else "normal")
        self.stop_button.configure(state="normal" if value else "disabled")
        if not value:
            self.progress.stop()
            self.progress.configure(mode="determinate")

    def start_scan(self):
        if self.busy:
            return
        if not self.source.get().strip():
            messagebox.showinfo("选择目录", "请先选择缓存目录", parent=self.root)
            return
        source = Path(self.source.get().strip()).expanduser().resolve()
        self.source.set(str(source))
        self.jobs.clear()
        self.tree.delete(*self.tree.get_children())
        self.cancel.clear()
        self.set_busy(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start(15)
        self.status.set("正在扫描缓存…")

        def worker():
            try:
                self.events.put(("scan", *scan(source, self.cancel)))
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("idle",))
        threading.Thread(target=worker, daemon=True).start()

    def start_convert(self, selected: bool):
        if self.busy:
            return
        indices = [int(item) for item in self.tree.selection()] if selected else list(range(len(self.jobs)))
        if not indices:
            messagebox.showinfo("没有可合并的视频", "请先扫描缓存，并选择需要合并的视频。", parent=self.root)
            return
        if not self.output.get().strip():
            messagebox.showinfo("选择目录", "请先选择输出目录", parent=self.root)
            return
        try:
            tool_path("ffmpeg")
            tool_path("ffprobe")
        except FileNotFoundError as exc:
            messagebox.showerror("缺少组件", str(exc), parent=self.root)
            return
        output = Path(self.output.get().strip()).expanduser().resolve()
        self.output.set(str(output))
        self.cancel.clear()
        self.set_busy(True)
        self.progress.configure(maximum=len(indices), value=0)
        self.status.set(f"准备合并 {len(indices)} 个视频…")

        def worker():
            counts = {"完成": 0, "跳过": 0, "失败": 0}
            stopped = False
            for count, index in enumerate(indices, 1):
                if self.cancel.is_set():
                    stopped = True
                    break
                job = self.jobs[index]
                try:
                    result = convert(job, output, self.cancel, lambda message, i=index: self.events.put(("row", i, message)))
                    counts["完成" if result == "完成" else "跳过"] += 1
                    self.events.put(("row", index, result))
                    self.events.put(("log", f"{result}：{job.filename}"))
                except Cancelled:
                    self.events.put(("row", index, "已停止"))
                    stopped = True
                    break
                except Exception as exc:
                    counts["失败"] += 1
                    self.events.put(("row", index, "失败（见下方详情）"))
                    self.events.put(("log", f"失败：{job.title}\n{exc}"))
                self.events.put(("progress", count))
            summary = "已停止。" if stopped else "处理结束。"
            summary += "  ".join(f"{key} {value}" for key, value in counts.items())
            self.events.put(("summary", summary))
            self.events.put(("idle",))
        threading.Thread(target=worker, daemon=True).start()

    def pump(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "scan":
                    self.jobs, warnings = event[1:]
                    for index, job in enumerate(self.jobs):
                        size = (job.video.size + job.audio.size) / 1024 / 1024
                        self.tree.insert("", "end", iid=str(index), values=(job.title, f"{size:.1f} MB", "待合并"))
                    self.status.set(f"找到 {len(self.jobs)} 个可合并视频，提示 {len(warnings)} 条。")
                    self.append_log(self.status.get())
                    for warning in warnings:
                        self.append_log("提示：" + warning)
                    if not self.jobs:
                        self.append_log("未发现完整的音视频组合。请检查下载是否完成、目录是否正确。")
                elif event[0] == "row":
                    self.tree.set(str(event[1]), "state", event[2])
                    self.tree.see(str(event[1]))
                    self.status.set(f"{event[2]}：{self.jobs[event[1]].title}")
                elif event[0] == "log":
                    self.append_log(event[1])
                elif event[0] == "progress":
                    self.progress.configure(value=event[1])
                elif event[0] == "summary":
                    self.status.set(event[1])
                    self.append_log(event[1])
                elif event[0] == "error":
                    self.status.set(event[1])
                    self.append_log(event[1])
                elif event[0] == "idle":
                    self.set_busy(False)
                    if self.closing:
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def open_output(self):
        path = Path(self.output.get()).expanduser()
        if not path.is_dir():
            messagebox.showinfo("输出目录", "完成首次合并后，可在这里打开输出目录。", parent=self.root)
            return
        try:
            os.startfile(str(path.resolve()))
        except OSError as exc:
            messagebox.showerror("无法打开目录", str(exc), parent=self.root)

    def close(self):
        if self.busy:
            if not messagebox.askyesno("退出", "停止当前任务并退出？原缓存会保留。", parent=self.root):
                return
            self.closing = True
            self.cancel.set()
            self.status.set("正在停止并清理临时文件…")
        else:
            self.root.destroy()


def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()
