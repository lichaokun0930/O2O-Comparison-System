# O2O Price Comparison Tool - Command Line Launcher

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  O2O Product Price Comparison Tool" -ForegroundColor Cyan
Write-Host "  Command Line Version" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check data files first
Write-Host "📂 检查数据文件..." -ForegroundColor Cyan
$storeAData = Get-ChildItem "..\upload\本店\*.xlsx" -ErrorAction SilentlyContinue | Select-Object -First 1
$storeBData = Get-ChildItem "..\upload\竞对\*.xlsx" -ErrorAction SilentlyContinue | Select-Object -First 1

if ($storeAData -and $storeBData) {
    Write-Host "✅ 数据文件已就绪:" -ForegroundColor Green
    Write-Host "   本店: $($storeAData.Name)" -ForegroundColor Cyan
    Write-Host "   竞对: $($storeBData.Name)" -ForegroundColor Cyan
} else {
    Write-Host "⚠️  未检测到数据文件" -ForegroundColor Yellow
    Write-Host "   请将 Excel 文件放入:" -ForegroundColor Yellow
    Write-Host "   - upload\本店\" -ForegroundColor White
    Write-Host "   - upload\竞对\" -ForegroundColor White
    Write-Host ""
    Write-Host "💡 程序支持运行时手动选择文件" -ForegroundColor Gray
}
Write-Host ""

# Step 2: Model selection
Write-Host "请选择嵌入模型:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  [1] paraphrase-multilingual-mpnet-base-v2  (通用型)" -ForegroundColor White
Write-Host "      大小: ~420MB | 速度: 正常 | 准确率: 良好" -ForegroundColor Gray
Write-Host ""
Write-Host "  [2] BAAI/bge-base-zh-v1.5  (中文优化 - 推荐)" -ForegroundColor Cyan
Write-Host "      大小: ~560MB | 速度: 正常 | 准确率: 优秀" -ForegroundColor Gray
Write-Host ""
Write-Host "  [3] moka-ai/m3e-base  (电商场景)" -ForegroundColor White
Write-Host "      大小: ~400MB | 速度: 较快 | 准确率: 优秀" -ForegroundColor Gray
Write-Host ""
Write-Host "  [4] BAAI/bge-large-zh-v1.5  (⭐ 最强性能)" -ForegroundColor Magenta
Write-Host "      大小: ~1.3GB | 速度: 较慢 | 准确率: 顶级" -ForegroundColor Gray
Write-Host ""
Write-Host "  [5] BAAI/bge-m3  (新一代多语言)" -ForegroundColor White
Write-Host "      大小: ~2.2GB | 速度: 较慢 | 准确率: 顶级" -ForegroundColor Gray
Write-Host ""
Write-Host "  [6] BAAI/bge-small-zh-v1.5  (速度优先)" -ForegroundColor White
Write-Host "      大小: ~100MB | 速度: 快速 | 准确率: 良好+" -ForegroundColor Gray
Write-Host ""
Write-Host "  [7] intfloat/multilingual-e5-large  (🌍 多语言旗舰)" -ForegroundColor Yellow
Write-Host "      大小: ~2.2GB | 速度: 慢 | 准确率: 顶级+ | 支持100+语言" -ForegroundColor Gray
Write-Host ""
Write-Host "  [8] GanymedeNil/text2vec-large-chinese  (🇨🇳 中文强化)" -ForegroundColor Yellow
Write-Host "      大小: ~1.3GB | 速度: 较慢 | 准确率: 顶级 | 电商优化" -ForegroundColor Gray
Write-Host ""
Write-Host "  [9] BAAI/bge-large-zh-v1.5  (⭐⭐ 推荐)" -ForegroundColor Magenta
Write-Host "      大小: ~1.3GB | 速度: 较慢 | 准确率: 顶级 | 黄金标准" -ForegroundColor Gray
Write-Host ""
Write-Host "  [Enter] 使用默认交互式选择" -ForegroundColor DarkGray
Write-Host ""

$modelChoice = Read-Host "请输入选项 (1-9 或直接按 Enter)"

# Model mapping
$modelMap = @{
    "1" = "paraphrase-multilingual-mpnet-base-v2"
    "2" = "BAAI/bge-base-zh-v1.5"
    "3" = "moka-ai/m3e-base"
    "4" = "BAAI/bge-large-zh-v1.5"
    "5" = "BAAI/bge-m3"
    "6" = "BAAI/bge-small-zh-v1.5"
    "7" = "intfloat/multilingual-e5-large"
    "8" = "GanymedeNil/text2vec-large-chinese"
    "9" = "BAAI/bge-large-zh-v1.5"
}

if ($modelMap.ContainsKey($modelChoice)) {
    $selectedModel = $modelMap[$modelChoice]
    $env:SENTENCE_BERT_MODEL = $selectedModel
    Write-Host ""
    Write-Host "✅ 已选择嵌入模型: $selectedModel" -ForegroundColor Green
    Write-Host ""
    
    # 第二步：选择 Cross-Encoder 精排模型
    Write-Host "请选择精排模型 (Cross-Encoder):" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  [1] cross-encoder/ms-marco-MiniLM-L-6-v2  (默认)" -ForegroundColor White
    Write-Host "      大小: ~90MB | 速度: 极快 | 准确率: 中等 | 语言: 英文优先" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  [2] BAAI/bge-reranker-large  (⭐推荐)" -ForegroundColor Magenta
    Write-Host "      大小: ~1.3GB | 速度: 中 | 准确率: 极高 (+40%) | 语言: 中英双语" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  [3] BAAI/bge-reranker-base  (⚡平衡)" -ForegroundColor Cyan
    Write-Host "      大小: ~309MB | 速度: 快 | 准确率: 高 (+25%) | 语言: 中英双语" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  [4] cross-encoder/ms-marco-MiniLM-L-12-v2" -ForegroundColor White
    Write-Host "      大小: ~130MB | 速度: 快 | 准确率: 中高 | 语言: 英文优先" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  [Enter] 使用默认 (BGE-Reranker-Base)" -ForegroundColor DarkGray
    Write-Host ""
    
    $ceChoice = Read-Host "请输入选项 (1-4 或直接按 Enter)"
    
    $ceModelMap = @{
        "1" = "cross-encoder/ms-marco-MiniLM-L-6-v2"
        "2" = "BAAI/bge-reranker-large"
        "3" = "BAAI/bge-reranker-base"
        "4" = "cross-encoder/ms-marco-MiniLM-L-12-v2"
    }
    
    if ($ceModelMap.ContainsKey($ceChoice)) {
        $selectedCE = $ceModelMap[$ceChoice]
        $env:CROSS_ENCODER_MODEL = $selectedCE
        Write-Host ""
        Write-Host "✅ 已选择精排模型: $selectedCE" -ForegroundColor Green
    } elseif ([string]::IsNullOrWhiteSpace($ceChoice)) {
        $env:CROSS_ENCODER_MODEL = "BAAI/bge-reranker-base"
        Write-Host ""
        Write-Host "✅ 使用默认精排模型: BAAI/bge-reranker-base" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "⚠️ 无效选择，使用默认: BAAI/bge-reranker-base" -ForegroundColor Yellow
        $env:CROSS_ENCODER_MODEL = "BAAI/bge-reranker-base"
    }
} else {
    Write-Host ""
    Write-Host "使用默认交互式选择模式" -ForegroundColor Yellow
}
Write-Host ""

# Set environment variables (CPU mode + balanced performance)
$env:CUDA_VISIBLE_DEVICES = ""
$env:USE_TORCH_SIM = "0"
$env:ENCODE_BATCH_SIZE = "256"
$env:MATCH_TOPK_SOFT = "80"

# Fix tqdm display issues in PowerShell
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "CPU mode enabled (balanced performance)" -ForegroundColor Green
Write-Host "   Encoding batch size: 256 | Top candidates: 80" -ForegroundColor Cyan
Write-Host ""

# Check Python availability
$pythonPath = "D:\办公\Python\python.exe"
if (!(Test-Path $pythonPath)) {
    Write-Host "Python not found: $pythonPath" -ForegroundColor Red
    Write-Host "Please update pythonPath variable in script" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Launch comparison tool
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  启动比价分析工具..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Run main program (use absolute path)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$mainScript = Join-Path (Split-Path -Parent $scriptDir) "product_comparison_tool_local.py"

if (Test-Path $mainScript) {
    & $pythonPath $mainScript
} else {
    Write-Host ""
    Write-Host "❌ 错误: 找不到主程序文件" -ForegroundColor Red
    Write-Host "   期望路径: $mainScript" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "按 Enter 退出"
    exit 1
}

# Program finished
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Program Finished" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Check if report was generated
$latestReport = Get-ChildItem "..\reports\matched_products_comparison_final_*.xlsx" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($latestReport) {
    Write-Host "Report generated:" -ForegroundColor Green
    Write-Host "   $($latestReport.FullName)" -ForegroundColor Cyan
    Write-Host ""
    
    $openReport = Read-Host "Open report? (Y/N)"
    if ($openReport -eq 'Y' -or $openReport -eq 'y') {
        Start-Process $latestReport.FullName
    }
}

Write-Host "Press Enter to exit..." -ForegroundColor DarkGray
Read-Host
