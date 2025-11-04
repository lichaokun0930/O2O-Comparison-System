# ============================================
# 硬件指纹工具 - 独立打包脚本
# 版本: 1.0
# 日期: 2025-11-02
# ============================================

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "     硬件指纹工具 - 独立打包脚本" -ForegroundColor Cyan
Write-Host "================================================`n" -ForegroundColor Cyan

# 记录开始时间
$StartTime = Get-Date

# 设置工作目录
$WorkDir = "硬件指纹工具"
$OutputDir = "dist\硬件指纹工具"

# 切换到项目根目录（如果当前在工具目录内）
if (Test-Path "..\generate_fingerprint.py") {
    cd ..
}

Write-Host "[1/5] 清理旧的打包文件..." -ForegroundColor Yellow
if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
    Write-Host "   ✓ 已删除旧版本exe" -ForegroundColor Green
}

if (Test-Path "build") {
    Remove-Item "build" -Recurse -Force
    Write-Host "   ✓ 已清理build目录" -ForegroundColor Green
}

if (Test-Path "*.spec") {
    Remove-Item "*.spec" -Force
    Write-Host "   ✓ 已清理spec文件" -ForegroundColor Green
}

Write-Host "`n[2/5] 检查源文件..." -ForegroundColor Yellow
if (-not (Test-Path "$WorkDir\generate_fingerprint.py")) {
    Write-Host "   ❌ 错误：找不到源文件 generate_fingerprint.py" -ForegroundColor Red
    exit 1
}
Write-Host "   ✓ 源文件检查通过" -ForegroundColor Green

Write-Host "`n[3/5] 检查打包环境..." -ForegroundColor Yellow
try {
    $pyinstaller = Get-Command pyinstaller -ErrorAction Stop
    Write-Host "   ✓ PyInstaller已安装: $($pyinstaller.Source)" -ForegroundColor Green
} catch {
    Write-Host "   ❌ 错误：未安装PyInstaller" -ForegroundColor Red
    Write-Host "   请运行: pip install pyinstaller" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n[4/5] 开始打包（独立exe）..." -ForegroundColor Yellow
Write-Host "   源文件: $WorkDir\generate_fingerprint.py" -ForegroundColor Cyan
Write-Host "   输出目录: $OutputDir" -ForegroundColor Cyan
Write-Host "   模式: 单文件exe（--onefile）`n" -ForegroundColor Cyan

# 执行打包命令
pyinstaller --onefile `
    --name "硬件指纹工具" `
    --distpath "dist" `
    --workpath "build\fingerprint_tool" `
    --specpath "." `
    --noconfirm `
    --clean `
    --console `
    "$WorkDir\generate_fingerprint.py"

# 检查打包结果
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ 打包失败！错误代码: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "`n[5/5] 整理打包结果..." -ForegroundColor Yellow

# 创建独立目录
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# 移动exe到独立目录
if (Test-Path "dist\硬件指纹工具.exe") {
    Move-Item "dist\硬件指纹工具.exe" "$OutputDir\" -Force
    Write-Host "   ✓ exe已移动到: $OutputDir\" -ForegroundColor Green
} else {
    Write-Host "   ❌ 错误：未找到打包后的exe文件" -ForegroundColor Red
    exit 1
}

# 清理临时文件
if (Test-Path "build") {
    Remove-Item "build" -Recurse -Force
    Write-Host "   ✓ 已清理build目录" -ForegroundColor Green
}

if (Test-Path "硬件指纹工具.spec") {
    Remove-Item "硬件指纹工具.spec" -Force
    Write-Host "   ✓ 已清理spec文件" -ForegroundColor Green
}

# 计算文件大小
$ExeSize = (Get-Item "$OutputDir\硬件指纹工具.exe").Length / 1MB

# 计算耗时
$Duration = (Get-Date) - $StartTime

Write-Host "`n================================================" -ForegroundColor Green
Write-Host "           ✅ 打包成功！" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host "📦 输出文件: $OutputDir\硬件指纹工具.exe" -ForegroundColor Cyan
Write-Host "📏 文件大小: $([math]::Round($ExeSize, 2)) MB" -ForegroundColor Cyan
Write-Host "⏱️  耗时: $($Duration.ToString('mm\:ss'))" -ForegroundColor Cyan
Write-Host "`n📝 使用方法:" -ForegroundColor Yellow
Write-Host "   1. 双击运行exe文件" -ForegroundColor White
Write-Host "   2. 程序会生成 my_fingerprint.txt" -ForegroundColor White
Write-Host "   3. 将txt文件发送给管理员获取授权" -ForegroundColor White
Write-Host "`n💡 提示: 此工具独立存在，不会被主程序打包覆盖" -ForegroundColor Cyan
Write-Host "================================================`n" -ForegroundColor Green

# 询问是否测试运行
$Test = Read-Host "是否立即测试运行exe？(y/n)"
if ($Test -eq 'y' -or $Test -eq 'Y') {
    Write-Host "`n正在运行测试..." -ForegroundColor Yellow
    & "$OutputDir\硬件指纹工具.exe"
    
    if (Test-Path "my_fingerprint.txt") {
        Write-Host "`n✅ 测试成功！指纹文件已生成" -ForegroundColor Green
        $Fingerprint = Get-Content "my_fingerprint.txt"
        Write-Host "   硬件指纹: $Fingerprint" -ForegroundColor Cyan
    } else {
        Write-Host "`n⚠️  警告：未生成指纹文件，请检查exe是否正常运行" -ForegroundColor Yellow
    }
}

Write-Host "`n按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
