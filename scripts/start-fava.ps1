# ===============================
# 路径定位
# ===============================
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootPath   = Split-Path -Parent $scriptPath
Set-Location $rootPath

$lastFilePath = Join-Path $scriptPath ".last_beancount"

# ===============================
# 获取 beancount 文件
# ===============================
$files = Get-ChildItem -Path $rootPath -Filter *.beancount | Sort-Object Name

if ($files.Count -eq 0) {
    Write-Host "根目录下未找到 beancount 文件" -ForegroundColor Red
    exit 1
}

# ===============================
# 读取上次选择
# ===============================
$lastIndex = $null
if (Test-Path $lastFilePath) {
    $lastName = Get-Content $lastFilePath -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt $files.Count; $i++) {
        if ($files[$i].Name -eq $lastName) {
            $lastIndex = $i
            break
        }
    }
}

Write-Host ""
Write-Host "请选择要启动的 beancount 账本：" -ForegroundColor Cyan
Write-Host ""

for ($i = 0; $i -lt $files.Count; $i++) {
    if ($i -eq $lastIndex) {
        Write-Host ("  [{0}] {1}  (上次)" -f ($i + 1), $files[$i].Name) -ForegroundColor Yellow
    } else {
        Write-Host ("  [{0}] {1}" -f ($i + 1), $files[$i].Name)
    }
}

# ===============================
# 稳定选择循环
# ===============================
while ($true) {
    if ($lastIndex -ne $null) {
        $prompt = "输入编号并回车（直接回车 = 上次选择）"
    } else {
        $prompt = "输入编号并回车"
    }

    $input = Read-Host "`n$prompt"

    # 直接回车：使用上次选择
    if ([string]::IsNullOrWhiteSpace($input) -and $lastIndex -ne $null) {
        $selectedFile = $files[$lastIndex]
        break
    }

    # 数字选择
    if ($input -match '^\d+$') {
        $idx = [int]$input
        if ($idx -ge 1 -and $idx -le $files.Count) {
            $selectedFile = $files[$idx - 1]
            break
        }
    }

    Write-Host "❌ 输入无效，请重新输入" -ForegroundColor Red
}

# ===============================
# 记录本次选择
# ===============================
$selectedFile.Name | Set-Content $lastFilePath

Write-Host ""
Write-Host "启动账本：" $selectedFile.Name -ForegroundColor Green
Write-Host ""

# ===============================
# 自动打开浏览器（延迟，防止端口未就绪）
# ===============================
Start-Job {
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:5000"
} | Out-Null

# ===============================
# 启动 fava（前台阻塞）
# ===============================
fava $selectedFile.FullName
