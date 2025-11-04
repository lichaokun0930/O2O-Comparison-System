# O2O 比价工具 - 阿里云部署打包脚本
# 功能：自动打包项目文件，生成部署包

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  O2O 比价工具 - 阿里云部署打包"         -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 定义需要打包的文件
$必需文件 = @(
    "comparison_app.py",
    "product_comparison_tool_local.py",
    "requirements.txt"
)

$可选文件 = @(
    "README.md",
    "最终用户使用指南.md",
    "阿里云部署指南.md"
)

$必需目录 = @(
    ".streamlit"
)

# 2. 创建临时打包目录
$临时目录 = "deploy_package_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
Write-Host "[1/6] 创建打包目录: $临时目录" -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $临时目录 | Out-Null

# 3. 复制必需文件
Write-Host "[2/6] 复制必需文件..." -ForegroundColor Yellow
$复制成功 = 0
$复制失败 = 0

foreach ($文件 in $必需文件) {
    if (Test-Path $文件) {
        Copy-Item $文件 $临时目录\
        Write-Host "  ✅ $文件" -ForegroundColor Green
        $复制成功++
    } else {
        Write-Host "  ❌ 缺失: $文件" -ForegroundColor Red
        $复制失败++
    }
}

# 4. 复制可选文件
Write-Host "[3/6] 复制可选文件..." -ForegroundColor Yellow
foreach ($文件 in $可选文件) {
    if (Test-Path $文件) {
        Copy-Item $文件 $临时目录\
        Write-Host "  ✅ $文件" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  跳过: $文件 (可选)" -ForegroundColor DarkGray
    }
}

# 5. 复制目录
Write-Host "[4/6] 复制配置目录..." -ForegroundColor Yellow
foreach ($目录 in $必需目录) {
    if (Test-Path $目录) {
        Copy-Item -Recurse $目录 $临时目录\
        Write-Host "  ✅ $目录\" -ForegroundColor Green
    } else {
        Write-Host "  ❌ 缺失: $目录\" -ForegroundColor Red
        $复制失败++
    }
}

# 创建 upload 目录结构
New-Item -ItemType Directory -Force -Path "$临时目录\upload\本店" | Out-Null
New-Item -ItemType Directory -Force -Path "$临时目录\upload\竞对" | Out-Null
Write-Host "  ✅ upload/ (空目录结构)" -ForegroundColor Green

# 6. 检查是否有错误
if ($复制失败 -gt 0) {
    Write-Host ""
    Write-Host "❌ 打包失败！缺少 $复制失败 个必需文件/目录" -ForegroundColor Red
    Write-Host "请检查项目完整性后重试" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "按回车键退出"
    exit 1
}

# 7. 压缩打包
$压缩包名称 = "o2o_tool_deploy_$(Get-Date -Format 'yyyyMMdd_HHmmss').zip"
Write-Host "[5/6] 压缩打包: $压缩包名称" -ForegroundColor Yellow

try {
    Compress-Archive -Path "$临时目录\*" -DestinationPath $压缩包名称 -Force
    $压缩包大小 = [math]::Round((Get-Item $压缩包名称).Length / 1MB, 2)
    Write-Host "  ✅ 打包完成！大小: $压缩包大小 MB" -ForegroundColor Green
} catch {
    Write-Host "  ❌ 压缩失败: $_" -ForegroundColor Red
    exit 1
}

# 8. 清理临时目录
Write-Host "[6/6] 清理临时文件..." -ForegroundColor Yellow
Remove-Item -Recurse -Force $临时目录
Write-Host "  ✅ 清理完成" -ForegroundColor Green

# 9. 显示部署说明
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ✅ 打包成功！"                          -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "📦 部署包: " -NoNewline
Write-Host "$压缩包名称" -ForegroundColor Cyan
Write-Host "📊 文件数量: $复制成功 个" -ForegroundColor White
Write-Host "💾 包大小: $压缩包大小 MB" -ForegroundColor White
Write-Host ""

# 10. 提供上传命令
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  下一步：上传到阿里云"                   -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "方式1: 使用 SCP 上传（推荐）" -ForegroundColor Yellow
Write-Host "--------------------------------------" -ForegroundColor DarkGray
$scp命令 = "scp $压缩包名称 root@您的阿里云IP:/root/"
Write-Host $scp命令 -ForegroundColor White
Write-Host ""

Write-Host "方式2: 使用 VS Code Remote" -ForegroundColor Yellow
Write-Host "--------------------------------------" -ForegroundColor DarkGray
Write-Host "1. 按 F1 → Remote-SSH: Connect to Host" -ForegroundColor White
Write-Host "2. 选择阿里云服务器" -ForegroundColor White
Write-Host "3. 拖拽 $压缩包名称 到 /root/ 目录" -ForegroundColor White
Write-Host ""

Write-Host "方式3: 使用阿里云控制台上传" -ForegroundColor Yellow
Write-Host "--------------------------------------" -ForegroundColor DarkGray
Write-Host "1. 登录阿里云控制台 → ECS → 远程连接" -ForegroundColor White
Write-Host "2. 使用文件传输功能上传" -ForegroundColor White
Write-Host ""

# 11. 提供服务器端解压命令
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  服务器端操作命令"                       -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "# 1. 连接服务器" -ForegroundColor Yellow
Write-Host "ssh root@您的阿里云IP" -ForegroundColor White
Write-Host ""
Write-Host "# 2. 解压文件" -ForegroundColor Yellow
Write-Host "cd /root" -ForegroundColor White
Write-Host "unzip $压缩包名称 -d o2o_tool" -ForegroundColor White
Write-Host "cd o2o_tool" -ForegroundColor White
Write-Host ""
Write-Host "# 3. 安装依赖" -ForegroundColor Yellow
Write-Host "pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple" -ForegroundColor White
Write-Host ""
Write-Host "# 4. 启动测试" -ForegroundColor Yellow
Write-Host "export CUDA_VISIBLE_DEVICES=''" -ForegroundColor White
Write-Host "export USE_TORCH_SIM='0'" -ForegroundColor White
Write-Host "python3 -m streamlit run comparison_app.py" -ForegroundColor White
Write-Host ""

Write-Host "========================================" -ForegroundColor Green
Write-Host "详细部署步骤请查看: 阿里云部署指南.md" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# 12. 询问是否复制 SCP 命令
Write-Host "是否复制 SCP 上传命令到剪贴板？ (Y/N)" -ForegroundColor Yellow -NoNewline
$回答 = Read-Host " "
if ($回答 -eq 'Y' -or $回答 -eq 'y') {
    Set-Clipboard -Value $scp命令
    Write-Host "✅ 已复制！粘贴到终端执行即可上传" -ForegroundColor Green
}

Write-Host ""
Write-Host "按回车键退出..." -ForegroundColor DarkGray
Read-Host
