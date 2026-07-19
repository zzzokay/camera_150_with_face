$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BinDir = Join-Path $Root "ffmpeg\bin"
$TempDir = Join-Path $Root "_ffmpeg_download"
$ZipPath = Join-Path $TempDir "ffmpeg-release-essentials.zip"
$ExtractDir = Join-Path $TempDir "extract"
$Url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

$Required = @("ffplay.exe", "ffprobe.exe", "ffmpeg.exe")
$Ready = $true
foreach ($Name in $Required) {
    if (-not (Test-Path (Join-Path $BinDir $Name))) {
        $Ready = $false
    }
}

if ($Ready) {
    Write-Host "[OK] FFmpeg tools already exist."
    exit 0
}

if (Test-Path $TempDir) {
    Remove-Item -Recurse -Force $TempDir
}

New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null

try {
    Write-Host "[INFO] Downloading FFmpeg..."
    Invoke-WebRequest -Uri $Url -OutFile $ZipPath -UseBasicParsing

    Write-Host "[INFO] Extracting FFmpeg..."
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

    $Ffplay = Get-ChildItem -Path $ExtractDir -Recurse -Filter "ffplay.exe" | Select-Object -First 1
    if (-not $Ffplay) {
        throw "ffplay.exe was not found after extraction."
    }

    $SourceBin = $Ffplay.Directory.FullName
    foreach ($Name in $Required) {
        $Source = Join-Path $SourceBin $Name
        if (-not (Test-Path $Source)) {
            throw "$Name is missing."
        }
        Copy-Item -Force $Source (Join-Path $BinDir $Name)
    }

    Write-Host "[OK] FFmpeg installed to $BinDir"
}
finally {
    if (Test-Path $TempDir) {
        Remove-Item -Recurse -Force $TempDir
    }
}
