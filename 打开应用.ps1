# O2O 比价工具 - 一键启动脚本
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  O2O 比价工具 - Web 版启动器"            -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 清理旧进程
Write-Host "[1/3] 🧹 清理旧进程..." -ForegroundColor Yellow
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *streamlit*" 2>$null | Out-Null
Start-Sleep -Seconds 2

# 2. 启动 Streamlit
Write-Host "[2/3] 🚀 启动 Streamlit 服务..." -ForegroundColor Yellow

$startCmd = @"
`$env:CUDA_VISIBLE_DEVICES = ''
`$env:USE_TORCH_SIM = '0'
`$env:ENCODE_BATCH_SIZE = '32'
Set-Location '$PWD'
& 'D:\办公\Python\python.exe' -m streamlit run comparison_app.py
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $startCmd -WindowStyle Normal

Write-Host "等待服务启动..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# 3. 打开浏览器
Write-Host "[3/3] 🌐 打开浏览器..." -ForegroundColor Yellow
Start-Process "http://localhost:8501"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ✅ 应用启动成功！"                     -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "📌 访问地址: http://localhost:8501" -ForegroundColor Cyan
Write-Host "💡 提示: 关闭弹出的 PowerShell 窗口即可停止服务" -ForegroundColor Yellow
Write-Host ""
