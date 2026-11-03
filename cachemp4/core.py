from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from collections.abc import Callable


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class Media:
    path: Path
    kind: str
    prefix: int
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class Job:
    title: str
    video: Media
    audio: Media
    filename: str


def check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise Cancelled("任务已停止")


def inspect_media(path: Path) -> Media:
    """Read ISO BMFF box headers; never infer a stream type from its filename."""
    stat = path.stat()
    kinds: set[str] = set()
    with path.open("rb") as stream:
        head = stream.read(64)
        prefix = 9 if head[:9] == b"000000000" and head[13:17] in (b"ftyp", b"styp") else 0
        if head[prefix + 4:prefix + 8] not in (b"ftyp", b"styp", b"sidx", b"moof"):
            raise ValueError("无法识别文件头（可能未下载完整或属于其他缓存格式）")
        budget = 10000

        def boxes(start: int, end: int, depth: int = 0) -> None:
            nonlocal budget
            if depth > 5:
                return
            while start + 8 <= end and budget > 0:
                budget -= 1
                stream.seek(start)
                raw = stream.read(8)
                if len(raw) != 8:
                    return
                size, tag = struct.unpack(">I4s", raw)
                header = 8
                if size == 1:
                    extended = stream.read(8)
                    if len(extended) != 8:
                        return
                    size = struct.unpack(">Q", extended)[0]
                    header = 16
                elif size == 0:
                    size = end - start
                if size < header or start + size > end:
                    return
                if tag in (b"moov", b"trak", b"mdia"):
                    boxes(start + header, start + size, depth + 1)
                elif tag == b"hdlr" and size >= header + 12:
                    stream.seek(start + header + 8)
                    handler = stream.read(4)
                    if handler == b"vide":
                        kinds.add("video")
                    elif handler == b"soun":
                        kinds.add("audio")
                start += size

        boxes(prefix, stat.st_size)
    if len(kinds) != 1:
        raise ValueError("未找到单独的视频或音频轨道")
    return Media(path, kinds.pop(), prefix, stat.st_size, stat.st_mtime_ns)


def safe_name(value: str, limit: int = 90) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    value = value[:limit].rstrip(" .") or "未命名视频"
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", value, re.I):
        value = "_" + value
    return value


def metadata(folder: Path, root: Path) -> dict:
    current = folder
    while True:
        for name in ("videoInfo.json", "entry.json", ".videoInfo"):
            candidate = current / name
            try:
                if candidate.stat().st_size > 2 * 1024 * 1024:
                    continue
                value = json.loads(candidate.read_text(encoding="utf-8-sig"))
                if isinstance(value, dict):
                    return value
            except (OSError, ValueError, UnicodeError):
                pass
        if current == root or current.parent == current:
            return {}
        current = current.parent


def scan(root: Path, cancel: threading.Event | None = None) -> tuple[list[Job], list[str]]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("缓存目录不存在，请重新选择")
    cancel = cancel or threading.Event()
    jobs: list[Job] = []
    warnings: list[str] = []

    def walk_error(error: OSError) -> None:
        warnings.append(f"无法读取目录：{error.filename}（{error.strerror}）")

    for folder_text, directories, names in os.walk(root, followlinks=False, onerror=walk_error):
        check_cancel(cancel)
        directories[:] = sorted(d for d in directories if not d.startswith(".bili-mp4-"))
        folder = Path(folder_text)
        candidates = sorted(n for n in names if n.lower().endswith(".m4s"))
        if not candidates:
            continue
        info = metadata(folder, root)
        if info.get("is_completed") is False or (info.get("status") not in (None, "completed") and info.get("progress", 0) < 100):
            warnings.append(f"{folder.name}：下载尚未完成，已跳过")
            continue
        groups: dict[str, list[Media]] = {}
        for name in candidates:
            check_cancel(cancel)
            try:
                media = inspect_media(folder / name)
                match = re.fullmatch(r"(.+)-\d+", Path(name).stem)
                key = match[1] if match else "default"
                groups.setdefault(key, []).append(media)
            except (OSError, ValueError) as exc:
                warnings.append(f"{folder.name}/{name}：{exc}")
        for group, files in groups.items():
            video = sorted((m for m in files if m.kind == "video"), key=lambda m: (-m.size, m.path.name))
            audio = sorted((m for m in files if m.kind == "audio"), key=lambda m: (-m.size, m.path.name))
            if not video or not audio:
                warnings.append(f"{folder.name}/{group}：缺少{'视频' if not video else '音频'}，已跳过")
                continue
            if len(video) > 1 or len(audio) > 1:
                warnings.append(f"{folder.name}/{group}：存在多条同类轨道，选用文件最大的音视频组合")
            page = info.get("page_data") or info.get("ep") or {}
            if not isinstance(page, dict):
                page = {}
            title = str(info.get("title") or info.get("groupTitle") or folder.name)
            part = str(page.get("part") or page.get("index_title") or "")
            if part and part != title:
                title += " - " + part
            relative = folder.relative_to(root).as_posix()
            identity = hashlib.sha256(f"{relative}/{group}".encode("utf-8")).hexdigest()[:10]
            filename = f"{safe_name(title)} [{identity}].mp4"
            jobs.append(Job(title, video[0], audio[0], filename))
    return jobs, warnings


def tool_path(name: str) -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    executable = name + (".exe" if os.name == "nt" else "")
    for candidate in (base / "bin" / executable, base / executable):
        if candidate.is_file():
            return candidate
    found = shutil.which(name)
    if found:
        return Path(found)
    raise FileNotFoundError(f"找不到 {executable}，请保留程序旁的 bin 文件夹，或先运行 prepare_tools.ps1")


def run_process(args: list[str], cancel: threading.Event, timeout: float | None = None) -> str:
    import time
    check_cancel(cancel)
    started = time.monotonic()
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          encoding="utf-8", errors="replace", creationflags=flags) as process:
        try:
            while True:
                check_cancel(cancel)
                if timeout and time.monotonic() - started > timeout:
                    raise TimeoutError("读取媒体信息超时")
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
        except BaseException:
            process.kill()
            process.communicate()
            raise
        if process.returncode:
            raise RuntimeError((stderr.strip() or "FFmpeg 处理失败")[-2400:])
        return stdout


def probe(path: Path, cancel: threading.Event) -> dict:
    return json.loads(run_process([str(tool_path("ffprobe")), "-v", "error", "-show_entries",
                                  "stream=codec_type,codec_name,width,height,duration:format=duration",
                                  "-of", "json", str(path)], cancel, timeout=90))


def unchanged(media: Media) -> None:
    stat = media.path.stat()
    if stat.st_size != media.size or stat.st_mtime_ns != media.mtime_ns:
        raise ValueError(f"缓存文件已发生变化，请重新扫描：{media.path.name}")


def prepare_input(media: Media, temporary: Path, cancel: threading.Event) -> Path:
    unchanged(media)
    if not media.prefix:
        return media.path
    destination = temporary / (media.kind + ".m4s")
    with media.path.open("rb") as source, destination.open("xb") as target:
        source.seek(media.prefix)
        while True:
            check_cancel(cancel)
            block = source.read(1024 * 1024)
            if not block:
                break
            target.write(block)
    unchanged(media)
    return destination


def convert(job: Job, output: Path, cancel: threading.Event,
            report: Callable[[str], None] = lambda message: None) -> str:
    check_cancel(cancel)
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / job.filename
    if destination.exists():
        return "已存在，跳过"
    tool_path("ffmpeg")
    tool_path("ffprobe")
    # Temporary copies only remove the known nine-byte cache prefix. Sources are read-only.
    with tempfile.TemporaryDirectory(prefix=".bili-mp4-", dir=output) as temp_text:
        temporary = Path(temp_text)
        report("准备音视频")
        video = prepare_input(job.video, temporary, cancel)
        audio = prepare_input(job.audio, temporary, cancel)
        video_info = probe(video, cancel)
        audio_info = probe(audio, cancel)
        if not any(s.get("codec_type") == "video" for s in video_info.get("streams", [])):
            raise ValueError("视频轨道无效")
        if not any(s.get("codec_type") == "audio" for s in audio_info.get("streams", [])):
            raise ValueError("音频轨道无效")
        report("无损合并中")
        partial = temporary / "result.mp4"
        args = [str(tool_path("ffmpeg")), "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                "-xerror", "-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                "-c", "copy", "-movflags", "+faststart", "-metadata", f"title={job.title}"]
        if any(s.get("codec_name") == "hevc" for s in video_info.get("streams", [])):
            args += ["-tag:v", "hvc1"]
        run_process(args + [str(partial)], cancel)
        report("检查输出")
        result_info = probe(partial, cancel)
        kinds = {s.get("codec_type") for s in result_info.get("streams", [])}
        if not {"video", "audio"}.issubset(kinds) or float(result_info.get("format", {}).get("duration", 0)) <= 0:
            raise ValueError("输出校验失败：缺少音视频轨道或时长无效")
        unchanged(job.video)
        unchanged(job.audio)
        check_cancel(cancel)
        try:
            if os.name == "nt":
                os.rename(partial, destination)  # Windows rename refuses to replace an existing file.
            else:
                os.link(partial, destination)
                partial.unlink()
        except FileExistsError:
            return "已存在，跳过"
    return "完成"
