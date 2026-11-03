import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

from cachemp4.core import Cancelled, convert, inspect_media, probe, run_process, safe_name, scan, tool_path


class ConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix="bili-mp4-test-fixture-")
        cls.base = Path(cls.fixture.name)
        ffmpeg = str(tool_path("ffmpeg"))
        cancel = threading.Event()
        run_process([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=10",
                     "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                     "-movflags", "+frag_keyframe+empty_moov", "-f", "mp4", str(cls.base / "video.m4s")], cancel)
        run_process([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                     "-t", "1", "-c:a", "aac", "-vn", "-movflags", "+frag_keyframe+empty_moov",
                     "-f", "mp4", str(cls.base / "audio.m4s")], cancel)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bili-mp4-test-")
        self.root = Path(self.temporary.name)
        self.cache = self.root / "缓存 中文 空格"
        self.cache.mkdir()
        self.output = self.root / "输出 中文 空格"
        self.cancel = threading.Event()

    def tearDown(self):
        self.temporary.cleanup()

    def pair(self, folder=None, prefix=False, numbered=False):
        folder = folder or self.cache
        folder.mkdir(parents=True, exist_ok=True)
        for kind, code in (("video", "30016"), ("audio", "30280")):
            name = f"123-1-{code}.m4s" if numbered else f"{kind}.m4s"
            data = (self.base / f"{kind}.m4s").read_bytes()
            (folder / name).write_bytes((b"000000000" if prefix else b"") + data)

    def test_numbered_prefixed_real_conversion_and_no_overwrite(self):
        self.pair(prefix=True, numbered=True)
        (self.cache / "videoInfo.json").write_text(json.dumps({"title": "标题:你好/世界?", "status": "completed"}), encoding="utf-8")
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.cache.iterdir()}
        jobs, warnings = scan(self.cache)
        self.assertEqual(len(jobs), 1)
        self.assertFalse(warnings)
        self.assertEqual(jobs[0].video.prefix, 9)
        self.assertEqual(convert(jobs[0], self.output, self.cancel), "完成")
        output = self.output / jobs[0].filename
        info = probe(output, self.cancel)
        self.assertEqual({s["codec_type"] for s in info["streams"]}, {"video", "audio"})
        self.assertGreater(float(info["format"]["duration"]), 0.9)
        # Decode both streams, not only the container headers.
        run_process([str(tool_path("ffmpeg")), "-v", "error", "-xerror", "-i", str(output), "-f", "null", "-"], self.cancel)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        self.assertEqual(convert(jobs[0], self.output, self.cancel), "已存在，跳过")
        self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), digest)
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.cache.iterdir()})
        self.assertFalse(list(self.output.glob(".bili-mp4-*")))

    def test_standard_names_and_android_parent_metadata(self):
        folder = self.cache / "123" / "80"
        self.pair(folder)
        (folder.parent / "entry.json").write_text(json.dumps({"title": "主标题", "is_completed": True, "page_data": {"part": "第二集"}}), encoding="utf-8")
        jobs, warnings = scan(self.cache)
        self.assertEqual(jobs[0].title, "主标题 - 第二集")
        self.assertFalse(warnings)
        self.assertEqual(jobs[0].video.prefix, 0)
        self.assertEqual(convert(jobs[0], self.output, self.cancel), "完成")

    def test_missing_audio_and_incomplete_download(self):
        shutil.copyfile(self.base / "video.m4s", self.cache / "video.m4s")
        jobs, warnings = scan(self.cache)
        self.assertFalse(jobs)
        self.assertTrue(any("缺少音频" in text for text in warnings))
        self.pair()
        (self.cache / "videoInfo.json").write_text('{"status":"loading","progress":50}')
        jobs, warnings = scan(self.cache)
        self.assertFalse(jobs)
        self.assertTrue(any("尚未完成" in text for text in warnings))

    def test_same_title_has_distinct_output_names(self):
        for name in ("a", "b"):
            self.pair(self.cache / name)
            (self.cache / name / "videoInfo.json").write_text('{"title":"same"}')
        jobs, warnings = scan(self.cache)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(len({j.filename for j in jobs}), 2)
        self.assertFalse(warnings)

    def test_numbered_groups_never_cross_pair(self):
        self.pair(numbered=True)
        (self.cache / "123-1-30280.m4s").rename(self.cache / "456-1-30280.m4s")
        jobs, warnings = scan(self.cache)
        self.assertFalse(jobs)
        self.assertEqual(len(warnings), 2)

    def test_cancel_cleans_temporary_files(self):
        self.pair(prefix=True)
        jobs, _ = scan(self.cache)
        def stop(_):
            self.cancel.set()
        with self.assertRaises(Cancelled):
            convert(jobs[0], self.output, self.cancel, stop)
        self.assertFalse(list(self.output.iterdir()))

    def test_changed_cache_refused_without_partial_output(self):
        self.pair()
        jobs, _ = scan(self.cache)
        with jobs[0].audio.path.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(ValueError, "发生变化"):
            convert(jobs[0], self.output, self.cancel)
        self.assertFalse(list(self.output.iterdir()))

    def test_invalid_file_and_reserved_names(self):
        path = self.cache / "broken.m4s"
        path.write_bytes(b"not an mp4")
        with self.assertRaises(ValueError):
            inspect_media(path)
        jobs, warnings = scan(self.cache)
        self.assertFalse(jobs)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(safe_name("CON"), "_CON")
        self.assertNotIn("/", safe_name("中/文"))

    def test_cli_unicode_titles_with_redirected_legacy_console(self):
        self.pair()
        title = "中文标题 ´▽｀ 😀"
        (self.cache / "videoInfo.json").write_text(json.dumps({"title": title}), encoding="utf-8")
        env = dict(os.environ, PYTHONIOENCODING="ascii")
        result = subprocess.run([sys.executable, "app.py", "--input", str(self.cache), "--list"],
                                capture_output=True, env=env, encoding="utf-8", check=True)
        self.assertIn(title, result.stdout)


if __name__ == "__main__":
    unittest.main()
