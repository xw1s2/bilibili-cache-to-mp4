"""Double-click GUI entry point; --input enables a scriptable batch interface."""
import argparse
from pathlib import Path
import sys
import threading

from cachemp4.core import Cancelled, convert, scan


def main() -> int:
    # Windows redirected output may otherwise use GBK and fail on video titles.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="B站缓存音视频无损合并为 MP4")
    parser.add_argument("--input", type=Path, help="缓存目录；不传则打开图形界面")
    parser.add_argument("--output", type=Path, help="MP4 输出目录")
    parser.add_argument("--list", action="store_true", help="只扫描，不转换")
    args = parser.parse_args()
    if args.input is None:
        from cachemp4.gui import main as gui_main
        gui_main()
        return 0
    cancel = threading.Event()
    jobs, warnings = scan(args.input, cancel)
    for warning in warnings:
        print("提示：" + warning)
    print(f"找到 {len(jobs)} 个可合并视频")
    if args.list:
        for job in jobs:
            print(job.filename)
        return 0 if jobs else 1
    output = args.output or args.input.resolve().parent / "bilibili_mp4"
    failures = 0
    for job in jobs:
        try:
            print(f"{convert(job, output, cancel)}：{job.filename}")
        except (KeyboardInterrupt, Cancelled):
            cancel.set()
            print("已停止")
            return 130
        except Exception as exc:
            failures += 1
            print(f"失败：{job.title}：{exc}", file=sys.stderr)
    return 1 if failures or not jobs else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        if getattr(sys, "frozen", False) and sys.stderr is None:
            import tkinter.messagebox
            tkinter.messagebox.showerror("启动失败", str(error))
        else:
            raise
