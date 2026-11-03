# B站缓存转 MP4

离线 Windows 工具，将 B 站缓存中的独立音视频轨道无损合并为 MP4。提供中文窗口和 Python 命令行入口。源码保存在专用 GitHub **私有仓库**，缓存视频不上传。

## 双击使用

1. 打开整个便携版文件夹，双击 `BiliCacheToMP4.exe`。无需安装 Python。
2. 选择「缓存目录」，可以选缓存总目录，也可以选某一个视频的目录。
3. 选择「输出目录」，点击「扫描缓存」。
4. 点击「合并全部」，或用 Ctrl / Shift 多选后点击「合并选中」。
5. 完成后点击「打开输出目录」。

请保留 EXE 同目录下的 `_internal` 和 `bin` 文件夹，移动工具时移动整个文件夹。

默认缓存目录为 `D:\user\Videos\bilibili`（存在时）；默认输出到同级的 `bilibili_mp4` 文件夹。程序只在开始合并时创建输出目录。扫描不会改动缓存。

## 支持的缓存

- 同目录中的 `video.m4s` 和 `audio.m4s`。
- Windows 客户端编号文件，例如 `41164541576-1-30016.m4s` 和 `41164541576-1-30280.m4s`。
- 自动移除部分客户端添加的 **9 个 ASCII 字符 0** 前缀，只处理临时副本，不修改原文件。
- 自动读取 `videoInfo.json`、`.videoInfo` 或 Android `entry.json` 中的标题及分 P 信息。
- 递归扫描子目录；通过 MP4 轨道结构识别音视频类型，不依赖文件名中的质量代码。
- 同组存在多个视频或音频版本时，选择各自文件最大的组合，并在日志中提示。

## 输出与保护

- 使用 FFmpeg `-c copy`，保留原视频和音频编码，不重新编码。画质、音质及分辨率保持不变。
- MP4 是容器；原编码为 HEVC / AV1 时，播放器仍需要支持该编码。工具不自动转为 H.264。
- 输出采用「标题 [目录标识].mp4」，过滤 Windows 不允许的文件名字符；同名不同目录视频会使用不同标识。
- 已存在的输出自动跳过，不覆盖；如需重新导出，可换一个输出目录。
- 缺少音频、缺少视频、明确标记未完成或格式不支持的缓存会被跳过并显示原因。
- 原缓存以只读方式打开。合并前后检查缓存大小及修改时间，缓存正在变化时会报错。
- 输出先写到独立临时目录，检查音视频轨道和有效时长后才发布正式 MP4。正常失败或停止会清理临时文件。
- 9 字节前缀文件需要临时复制，输出磁盘应预留约「音视频总大小的两倍」可用空间。无前缀文件直接读取。
- 「停止」会停止当前任务并清理未完成输出；此前已完成的视频保留。强制结束进程或断电可能留下 `.bili-mp4-*` 临时目录，请确认程序已退出后自行清理。
- 本工具不支持加密/DRM 文件、单纯网络分片或没有初始化信息的残缺缓存。
- 已存在文件的跳过判断基于输出文件名，不会重新验证该文件是否完整。

## 从源码运行

需要带 Tk 的 Python 3.11+（已用 Python 3.14.4 验证）及 Windows 10/11 64 位。

```powershell
powershell -ExecutionPolicy Bypass -File .\prepare_tools.ps1
python .\app.py
```

FFmpeg / FFprobe 由脚本下载到 `bin/`，使用固定版本及 SHA256 校验；也可自行安装并加入 PATH。程序运行和视频合并均不需要网络。

命令行批量处理：

```powershell
python .\app.py --input "D:\user\Videos\bilibili" --list
python .\app.py --input "D:\user\Videos\bilibili" --output "D:\user\Videos\bilibili_mp4"
```

## 验证与打包

```powershell
python -m unittest discover -s tests -v
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File .\build.ps1 -Python python
```

打包结果位于 `dist/BiliCacheToMP4/`。第三方组件来源和许可见 [THIRD_PARTY.md](THIRD_PARTY.md)，本版本验证记录见 [VALIDATION.md](VALIDATION.md)。Git 只跟踪源码、依赖声明、说明和构建脚本，不跟踪缓存视频、临时数据、下载包或生成的 EXE。
