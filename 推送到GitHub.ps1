# Git 推送更新到 GitHub 快捷脚本
# 用途: 一键将代码更新推送到 GitHub

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Git 推送更新到 GitHub" -ForegroundColor Yellow
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "[第1步] 查看修改状态..." -ForegroundColor Green
git status --short
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n错误: 当前目录不是 Git 仓库！" -ForegroundColor Red
    pause
    exit 1
}

$status = git status --short
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Host "`n没有新的修改需要提交" -ForegroundColor Yellow
    Write-Host "当前代码已经是最新的！" -ForegroundColor White
    pause
    exit 0
}

Write-Host "`n发现以下修改:" -ForegroundColor Cyan
git status --short

Write-Host "`n[第2步] 请输入本次更新说明" -ForegroundColor Green
Write-Host "示例: 修复模糊匹配BUG / 优化性能 / 更新文档" -ForegroundColor Gray
Write-Host -NoNewline "更新说明: " -ForegroundColor Yellow
$commitMessage = Read-Host

if ([string]::IsNullOrWhiteSpace($commitMessage)) {
    $commitMessage = "代码更新 - $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    Write-Host "使用默认说明: $commitMessage" -ForegroundColor Gray
}

Write-Host "`n[第3步] 添加所有修改..." -ForegroundColor Green
git add .
if ($LASTEXITCODE -ne 0) {
    Write-Host "添加文件失败！" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "文件已添加" -ForegroundColor Green

Write-Host "`n[第4步] 提交到本地仓库..." -ForegroundColor Green
git commit -m "$commitMessage"
if ($LASTEXITCODE -ne 0) {
    Write-Host "提交失败！" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "提交成功" -ForegroundColor Green

Write-Host "`n[第5步] 推送到 GitHub..." -ForegroundColor Green
Write-Host "仓库地址: https://github.com/lichaokun0930/O2O-Comparison-System" -ForegroundColor Gray

git push
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n推送失败！" -ForegroundColor Red
    Write-Host "可能原因:" -ForegroundColor Yellow
    Write-Host "  1. 网络连接问题" -ForegroundColor White
    Write-Host "  2. GitHub 认证失败" -ForegroundColor White
    Write-Host "  3. 远程仓库有新提交需要先拉取" -ForegroundColor White
    Write-Host "`n建议操作:" -ForegroundColor Yellow
    Write-Host "  git pull --rebase" -ForegroundColor Cyan
    Write-Host "  然后重新运行本脚本" -ForegroundColor Cyan
    pause
    exit 1
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "   推送成功！GitHub 代码已更新" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

Write-Host "`n提交信息: $commitMessage" -ForegroundColor Cyan
Write-Host "查看更新: https://github.com/lichaokun0930/O2O-Comparison-System" -ForegroundColor Cyan
Write-Host "推送时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan

Write-Host "`n提示: GitHub 上的代码已更新为最新版本！" -ForegroundColor Yellow
Write-Host ""

pause