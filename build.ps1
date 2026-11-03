param([string]$Python = 'python', [string]$Destination = (Join-Path $PSScriptRoot 'dist'))
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath 'bin\ffmpeg.exe') -or -not (Test-Path -LiteralPath 'bin\ffprobe.exe')) {
        & (Join-Path $PSScriptRoot 'prepare_tools.ps1')
    }
    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name 'BiliCacheToMP4' --distpath $Destination --workpath (Join-Path $PSScriptRoot 'build') app.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 构建失败' }
    $package = Join-Path $Destination 'BiliCacheToMP4'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'bin') -Destination $package -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination (Join-Path $package '使用说明.md') -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'THIRD_PARTY.md') -Destination $package -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'VALIDATION.md') -Destination $package -Force
    Write-Output ('已生成：' + (Join-Path $package 'BiliCacheToMP4.exe'))
} finally {
    Pop-Location
}
