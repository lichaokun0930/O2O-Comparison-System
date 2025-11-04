# 代码同步脚本 - 上传修改到服务器
# 使用方法: .\sync_to_server.ps1

param(
    [string]$ServerIP = "101.200.0.185",
    [string]$ServerUser = "root",
    [string]$ServerPath = "/root/o2o_tool"
)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  同步代码到阿里云服务器"                -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 需要同步的文件列表
$files = @(
    "comparison_app.py",
    "product_comparison_tool_local.py",
    "requirements.txt",
    ".streamlit\config.toml"
)

Write-Host "📋 准备同步以下文件:" -ForegroundColor Yellow
foreach ($file in $files) {
    if (Test-Path $file) {
        $size = [math]::Round((Get-Item $file).Length / 1KB, 2)
        Write-Host "  ✅ $file ($size KB)" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  $file (文件不存在)" -ForegroundColor Yellow
    }
}
Write-Host ""

# 确认上传
$confirm = Read-Host "是否继续上传到 ${ServerIP}? (Y/N)"
if ($confirm -ne 'Y' -and $confirm -ne 'y') {
    Write-Host "已取消" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "🚀 开始上传..." -ForegroundColor Green
Write-Host ""

# 上传文件
$uploadedCount = 0
$failedCount = 0

foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "📤 上传: $file" -ForegroundColor Cyan
        
        # 处理子目录中的文件
        $remoteFile = $file -replace '\\', '/'
        $remotePath = "$ServerPath/$remoteFile"
        
        # 如果是 .streamlit/config.toml，需要先创建目录
        if ($file -like "*.streamlit*") {
            ssh "${ServerUser}@${ServerIP}" "mkdir -p $ServerPath/.streamlit" 2>$null
        }
        
        # 使用 SCP 上传
        scp $file "${ServerUser}@${ServerIP}:$remotePath"
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✅ 成功" -ForegroundColor Green
            $uploadedCount++
        } else {
            Write-Host "  ❌ 失败" -ForegroundColor Red
            $failedCount++
        }
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  上传完成"                              -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "成功: $uploadedCount 个文件" -ForegroundColor Green
Write-Host "失败: $failedCount 个文件" -ForegroundColor Red
Write-Host ""

# 询问是否重启服务
if ($uploadedCount -gt 0) {
    $restart = Read-Host "是否重启服务器上的应用? (Y/N)"
    if ($restart -eq 'Y' -or $restart -eq 'y') {
        Write-Host ""
        Write-Host "🔄 重启服务中..." -ForegroundColor Yellow
        ssh "${ServerUser}@${ServerIP}" "sudo systemctl restart o2o-tool"
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ 服务已重启" -ForegroundColor Green
            Write-Host ""
            Write-Host "访问地址: http://${ServerIP}:8555" -ForegroundColor Cyan
        } else {
            Write-Host "❌ 重启失败，请手动执行:" -ForegroundColor Red
            Write-Host "   ssh ${ServerUser}@${ServerIP}" -ForegroundColor White
            Write-Host "   sudo systemctl restart o2o-tool" -ForegroundColor White
        }
    }
}

Write-Host ""
Write-Host "按回车键退出..." -ForegroundColor DarkGray
Read-Host
