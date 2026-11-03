param([string]$ToolsDirectory = (Join-Path $PSScriptRoot 'bin'))
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$url = 'https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip'
$expected = '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('bili-mp4-deps-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $archive = Join-Path $temporary 'ffmpeg.zip'
    Invoke-WebRequest -Uri $url -OutFile $archive -TimeoutSec 300
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
        throw 'FFmpeg SHA256 校验失败，未安装任何二进制文件。'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $temporary
    $package = Join-Path $temporary 'ffmpeg-9.0.2-essentials_build'
    New-Item -ItemType Directory -Path $ToolsDirectory -Force | Out-Null
    foreach ($name in @('ffmpeg.exe', 'ffprobe.exe')) {
        Copy-Item -LiteralPath (Join-Path $package ('bin\' + $name)) -Destination $ToolsDirectory
    }
    Copy-Item -LiteralPath (Join-Path $package 'LICENSE') -Destination (Join-Path $ToolsDirectory 'FFmpeg-LICENSE.txt')
    Write-Output 'FFmpeg / FFprobe 已准备完毕。'
} finally {
    # Remove only the unique dependency-extraction directory created by this script.
    $resolvedTemporary = [IO.Path]::GetFullPath($temporary)
    $resolvedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTemporary.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path $resolvedTemporary -Leaf).StartsWith('bili-mp4-deps-')) {
        Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force
    }
}
