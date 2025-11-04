# ===============================================
# O2O Comparison Tool - Optimized Full Package
# GPU 加速版本 - 使用支持 CUDA 的 Python
# ===============================================

# 🚀 使用支持 GPU 的 Python 环境
$PYTHON_EXE = "D:\办公\Python\python.exe"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   GPU 加速版本 - 4 Core Models" -ForegroundColor Magenta
Write-Host "   使用 GPU Python: $PYTHON_EXE" -ForegroundColor Cyan
Write-Host "   包含平衡+精确双模式 + GPU 加速 (约 10-11GB)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 验证 GPU Python 环境
Write-Host "`n🔍 验证 GPU Python 环境..." -ForegroundColor Cyan
if (-not (Test-Path $PYTHON_EXE)) {
    Write-Host "  ❌ GPU Python 不存在: $PYTHON_EXE" -ForegroundColor Red
    Write-Host "  使用系统默认 Python（CPU 版本）" -ForegroundColor Yellow
    $PYTHON_EXE = "python"
} else {
    $torchInfo = & $PYTHON_EXE -c "import torch; print(f'{torch.__version__}|{torch.cuda.is_available()}')" 2>$null
    if ($torchInfo -match "(.+)\|(True|False)") {
        $torchVersion = $Matches[1]
        $cudaAvailable = $Matches[2]
        Write-Host "  ✅ PyTorch: $torchVersion" -ForegroundColor Green
        if ($cudaAvailable -eq "True") {
            Write-Host "  ✅ CUDA: 可用 - 打包后程序支持 GPU 加速！" -ForegroundColor Green
        } else {
            Write-Host "  ⚠️  CUDA: 不可用 - 打包后仅支持 CPU" -ForegroundColor Yellow
        }
    }
}

$modelCache = "$env:USERPROFILE\.cache\huggingface\hub"
$tempBackup = "$env:TEMP\huggingface_backup_$(Get-Date -Format 'yyyyMMddHHmmss')"

# 1. Backup non-essential models
Write-Host "`n[1/4] Backing up non-essential models..." -ForegroundColor Yellow

if (-not (Test-Path $modelCache)) {
    Write-Host "  ERROR Model cache not found!" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Path $tempBackup -Force | Out-Null
Write-Host "  Backup location: $tempBackup" -ForegroundColor Gray

$movedCount = 0
$keptModels = @()

Get-ChildItem $modelCache -Directory -Filter "models--*" | ForEach-Object {
    $modelName = $_.Name -replace 'models--', '' -replace '--', '/'
    
    if ($_.Name -match "bge-base-zh-v1.5" -or $_.Name -match "bge-large-zh-v1.5" -or $_.Name -match "bge-reranker-base" -or $_.Name -match "bge-reranker-large") {
        # Keep core models (4个核心模型)
        $keptModels += $modelName
        Write-Host "  KEEP $modelName" -ForegroundColor Green
    } else {
        # Move to backup
        Move-Item $_.FullName -Destination $tempBackup -Force
        $movedCount++
        Write-Host "  BACKUP $modelName" -ForegroundColor Gray
    }
}

Write-Host "`n  Summary:" -ForegroundColor Cyan
Write-Host "    Core models (keep): $($keptModels.Count)" -ForegroundColor Green
Write-Host "    Test models (backup): $movedCount" -ForegroundColor Gray

if ($keptModels.Count -ne 4) {
    Write-Host "`n  WARNING Expected 4 core models, found $($keptModels.Count)" -ForegroundColor Yellow
    Write-Host "  Core models should be:" -ForegroundColor Yellow
    Write-Host "    1. BAAI/bge-base-zh-v1.5 (平衡嵌入)" -ForegroundColor Gray
    Write-Host "    2. BAAI/bge-large-zh-v1.5 (精确嵌入)" -ForegroundColor Gray
    Write-Host "    3. BAAI/bge-reranker-base (平衡重排序)" -ForegroundColor Gray
    Write-Host "    4. BAAI/bge-reranker-large (推荐重排序)" -ForegroundColor Gray
    
    $continue = Read-Host "`n  Continue packaging? (Y/N)"
    if ($continue -ne 'Y' -and $continue -ne 'y') {
        Write-Host "  Restoring backups..." -ForegroundColor Yellow
        Get-ChildItem $tempBackup | Move-Item -Destination $modelCache -Force
        Remove-Item $tempBackup -Force
        Write-Host "  Cancelled" -ForegroundColor Red
        exit 0
    }
}

# 2. Run packaging inline
Write-Host "`n[2/4] Starting packaging (4 core models ~3.4GB)..." -ForegroundColor Yellow
Write-Host "  包含平衡+精确双模式，预计 5-8 分钟" -ForegroundColor Cyan

# Check Python
try {
    $pythonVersion = & $PYTHON_EXE --version 2>&1
    Write-Host "  Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  ERROR Python not found: $PYTHON_EXE" -ForegroundColor Red
    # Restore and exit
    Get-ChildItem $tempBackup | Move-Item -Destination $modelCache -Force
    Remove-Item $tempBackup -Force
    exit 1
}

# Create build script
$buildScript = @"
import PyInstaller.__main__
import os

model_cache = os.path.expanduser('~/.cache/huggingface')

PyInstaller.__main__.run([
    'gui_launcher.py',
    '--name=O2O_Comparison_Tool',
    '--onedir',
    '--windowed',
    '--noconfirm',
    '--clean',
    '--hidden-import=pandas',
    '--hidden-import=numpy',
    '--hidden-import=openpyxl',
    '--hidden-import=sentence_transformers',
    '--hidden-import=torch',
    '--hidden-import=transformers',
    '--hidden-import=transformers.models.metaclip_2',
    '--hidden-import=sklearn',
    '--hidden-import=jieba',
    '--hidden-import=opencc',
    '--hidden-import=joblib',
    f'--add-data={model_cache};.cache/huggingface',
    '--add-data=product_comparison_tool_local.py;.',
    '--add-data=authorized_keys.json;.',
    '--add-data=prebuilt_cache;prebuilt_cache',
    '--add-data=upload;upload',
    '--exclude-module=matplotlib',
    '--exclude-module=IPython',
    '--exclude-module=jupyter',
    '--exclude-module=notebook',
])
"@

$buildScript | Out-File -FilePath "build_optimized.py" -Encoding UTF8

# Run packaging with GPU Python
Write-Host "`n  使用 GPU Python 执行打包..." -ForegroundColor Cyan
Write-Host "  Python: $PYTHON_EXE" -ForegroundColor Gray
try {
    & $PYTHON_EXE build_optimized.py
    
    if ($LASTEXITCODE -ne 0) {
        throw "Packaging failed"
    }
    
    Write-Host "`n  OK Packaging completed!" -ForegroundColor Green
    
} catch {
    Write-Host "`n  ERROR Packaging failed: $_" -ForegroundColor Red
    Write-Host "  Restoring backups..." -ForegroundColor Yellow
    Get-ChildItem $tempBackup | Move-Item -Destination $modelCache -Force
    Remove-Item $tempBackup -Force
    Remove-Item "build_optimized.py" -Force -ErrorAction SilentlyContinue
    exit 1
}

# Cleanup build script
Remove-Item "build_optimized.py" -Force -ErrorAction SilentlyContinue
Remove-Item "O2O_Comparison_Tool.spec" -Force -ErrorAction SilentlyContinue

# ⚠️ 硬件指纹工具已独立，不再打包进主程序
# 使用独立脚本: .\打包指纹工具.ps1 或进入 硬件指纹工具\ 目录执行
Write-Host "`n  💡 提示：硬件指纹工具已独立，位于 硬件指纹工具\ 目录" -ForegroundColor Cyan
Write-Host "     使用 .\打包指纹工具.ps1 单独打包该工具" -ForegroundColor Gray

# 3. Restore backups
Write-Host "`n[3/4] Restoring backup models..." -ForegroundColor Yellow

Get-ChildItem $tempBackup | ForEach-Object {
    $modelName = $_.Name -replace 'models--', '' -replace '--', '/'
    Move-Item $_.FullName -Destination $modelCache -Force
    Write-Host "  RESTORED $modelName" -ForegroundColor Gray
}

Remove-Item $tempBackup -Force
Write-Host "  OK All models restored" -ForegroundColor Green

# 4. Summary
Write-Host "`n[4/4] Packaging summary" -ForegroundColor Yellow

# 检查主程序目录中的文件
$mainProgramFiles = Get-ChildItem "dist\O2O_Comparison_Tool" -Filter "*.exe" -ErrorAction SilentlyContinue

if ($mainProgramFiles) {
    Write-Host "`n  打包的可执行文件:" -ForegroundColor Cyan
    $mainProgramFiles | ForEach-Object {
        $fileSize = [math]::Round($_.Length / 1MB, 2)
        $fileName = $_.Name
        Write-Host "    - $fileName - $fileSize MB" -ForegroundColor White
    }
}

$zipFile = Get-ChildItem "O2O_Comparison_Tool_v2.3_Full_*.zip" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($zipFile) {
    $zipSize = [math]::Round($zipFile.Length / 1GB, 2)
    Write-Host "`n  ============================================================" -ForegroundColor Green
    Write-Host "   SUCCESS - Optimized package created!" -ForegroundColor Green
    Write-Host "  ============================================================" -ForegroundColor Green
    Write-Host "`n  Package: $($zipFile.Name)" -ForegroundColor Cyan
    Write-Host "  Size: $zipSize GB - saved ~14GB!" -ForegroundColor Cyan
    Write-Host "`n  Included models:" -ForegroundColor Yellow
    $keptModels | ForEach-Object { Write-Host "    OK $_" -ForegroundColor Gray }
    Write-Host "`n  Comparison:" -ForegroundColor Yellow
    Write-Host "    Old approach: ~17GB with 15 models" -ForegroundColor Red
    Write-Host "    New approach: ~$zipSize GB with 2 models" -ForegroundColor Green
    $saved = [math]::Round(17 - $zipSize, 1)
    $percent = [math]::Round((17 - $zipSize) / 17 * 100, 0)
    Write-Host "    Space saved: ~$saved GB - $percent percent" -ForegroundColor Cyan
} else {
    Write-Host "`n  WARNING Package file not found" -ForegroundColor Yellow
    Write-Host "  Please check the dist directory manually" -ForegroundColor Yellow
}

Write-Host "`n  Done!" -ForegroundColor Cyan

