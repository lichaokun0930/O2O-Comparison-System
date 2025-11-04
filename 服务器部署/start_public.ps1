# O2O 比价工具 - 内网穿透快速启动脚本

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  O2O 比价工具 - 公网访问启动器"         -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: 启动本地服务
Write-Host "[1/2] 启动本地 Streamlit 服务..." -ForegroundColor Yellow
$env:CUDA_VISIBLE_DEVICES = ''
$env:USE_TORCH_SIM = '0'
$env:ENCODE_BATCH_SIZE = '32'

Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
Set-Location '$PWD'
Write-Host '本地服务运行在端口 8555...' -ForegroundColor Green
& 'D:\办公\Python\python.exe' -m streamlit run comparison_app.py --server.port 8555 --server.address 0.0.0.0
"@ -WindowStyle Normal

Start-Sleep -Seconds 5

# Step 2: 提示内网穿透
Write-Host ""
Write-Host "[2/2] 配置内网穿透（选择一种方式）" -ForegroundColor Yellow
Write-Host ""
Write-Host "方式1: 使用 ngrok（国际）" -ForegroundColor Green
Write-Host "  1. 访问 https://ngrok.com/ 注册账号"
Write-Host "  2. 下载 ngrok.exe"
Write-Host "  3. 运行: ngrok http 8555"
Write-Host ""
Write-Host "方式2: 使用 NATAPP（国内，推荐）" -ForegroundColor Green
Write-Host "  1. 访问 https://natapp.cn/ 注册账号"
Write-Host "  2. 下载 natapp.exe"
Write-Host "  3. 获取免费隧道 token"
Write-Host "  4. 运行: natapp.exe -authtoken=你的token"
Write-Host ""
Write-Host "方式3: 使用花生壳" -ForegroundColor Green
Write-Host "  1. 访问 https://hsk.oray.com/ 下载客户端"
Write-Host "  2. 注册并配置内网穿透"
Write-Host "  3. 映射本地端口 8555"
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  本地服务已启动在: http://localhost:8555" -ForegroundColor Cyan
Write-Host "  配置内网穿透后，即可生成公网链接！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "按任意键检查是否安装了 ngrok..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# 检查 ngrok
if (Test-Path "ngrok.exe") {
    Write-Host ""
    Write-Host "检测到 ngrok.exe！是否立即启动？(Y/N)" -ForegroundColor Green
    $choice = Read-Host
    if ($choice -eq 'Y' -or $choice -eq 'y') {
        Write-Host "启动 ngrok..." -ForegroundColor Yellow
        .\ngrok.exe http 8555
    }
} else {
    Write-Host ""
    Write-Host "未检测到 ngrok.exe" -ForegroundColor Yellow
    Write-Host "请手动下载并运行内网穿透工具" -ForegroundColor Yellow
}
