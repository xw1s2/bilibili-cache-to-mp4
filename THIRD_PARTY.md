# 第三方组件

- 本工具通过独立进程调用 FFmpeg / FFprobe 9.0.2，不链接 FFmpeg 库。
- Windows 构建来源：[GyanD/codexffmpeg 9.0.2](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2)。该构建采用 GPLv3，完整许可随便携版保存在 `bin/FFmpeg-LICENSE.txt`。
- 对应 FFmpeg 源码：[946fcce07b](https://github.com/FFmpeg/FFmpeg/commit/946fcce07b)。构建说明及配置：[Gyan 构建页](https://www.gyan.dev/ffmpeg/builds/)。
- 工具命令参考：[FFmpeg 文档](https://ffmpeg.org/ffmpeg.html)、[MP4 faststart 选项](https://ffmpeg.org/ffmpeg-formats.html)。
- Python 3.14 / Tcl/Tk 由 PyInstaller 打包；Python 采用 PSF 许可，Tcl/Tk 采用其各自开源许可。PyInstaller 采用 GPL 及引导程序分发例外，相关信息见 [PyInstaller](https://pyinstaller.org/en/stable/license.html)。
- 无在线转换服务、遥测或视频上传。运行已打包工具时不需要网络。
