# ============================================
# 硬件指纹工具 - 主目录快捷打包脚本
# 版本: 2.0（独立目录版本）
# 日期: 2025-11-02
# 说明: 调用独立目录的打包脚本
# ============================================

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   硬件指纹工具 - 快捷打包脚本" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "此脚本将调用独立目录的打包脚本" -ForegroundColor Yellow
Write-Host "工具目录: .\硬件指纹工具\" -ForegroundColor Cyan
Write-Host "==================================================`n" -ForegroundColor Cyan

# 检查独立目录是否存在
if (-not (Test-Path "硬件指纹工具\打包指纹工具.ps1")) {
    Write-Host "❌ 错误：未找到独立打包脚本" -ForegroundColor Red
    Write-Host "请确保以下文件存在：" -ForegroundColor Yellow
    Write-Host "   硬件指纹工具\打包指纹工具.ps1" -ForegroundColor Gray
    Write-Host "`n按任意键退出..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# 调用独立目录的打包脚本
Write-Host "正在启动独立打包脚本...`n" -ForegroundColor Green
& ".\硬件指纹工具\打包指纹工具.ps1"

# 打包完成后的提示
Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "💡 提示：" -ForegroundColor Yellow
Write-Host "   - 独立工具不会被主程序打包覆盖" -ForegroundColor Gray
Write-Host "   - 打包后的exe位于：dist\硬件指纹工具\" -ForegroundColor Gray
Write-Host "   - 可直接分发给用户使用" -ForegroundColor Gray
Write-Host "==================================================`n" -ForegroundColor Cyan
