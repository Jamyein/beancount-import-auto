param ([string]$targetFile)

$archiveDir = ".\archived"
if (-not (Test-Path $archiveDir)) { New-Item -ItemType Directory -Path $archiveDir | Out-Null }

if (Test-Path $targetFile) {
    Move-Item -Path $targetFile -Destination $archiveDir -Force
    Write-Host "   [系统] 文件已移至 archived/ 文件夹" -ForegroundColor Gray
}