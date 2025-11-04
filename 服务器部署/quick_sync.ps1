# 快速同步脚本 - 仅同步核心文件
# 使用方法: .\quick_sync.ps1

$ServerIP = "101.200.0.185"

Write-Host "🚀 快速同步到服务器..." -ForegroundColor Cyan

# 同步核心文件
scp comparison_app.py root@${ServerIP}:/root/o2o_tool/
scp product_comparison_tool_local.py root@${ServerIP}:/root/o2o_tool/

Write-Host "✅ 文件已上传" -ForegroundColor Green

# 重启服务
Write-Host "🔄 重启服务..." -ForegroundColor Yellow
ssh root@${ServerIP} "sudo systemctl restart o2o-tool"

Write-Host "✅ 完成！访问: http://${ServerIP}:8555" -ForegroundColor Green
