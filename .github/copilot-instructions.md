# O2O 商品比价分析平台 - AI 开发指南

本平台是基于 NLP 的 O2O 商品比价分析系统，支持智能商品匹配、断点续爬数据采集和 ETL 数据标准化。

## 架构全景：三大独立模块

### 1. 比价分析引擎 (`product_comparison_tool_local.py`, 3000+ 行)
**数据流**: Excel 输入 → 向量化 → 三阶段匹配 → 9-Sheet 报告输出
- **智能匹配管道**: 条码精确匹配 → 分类硬匹配 (要求分类一致) → 软匹配 (跨分类兜底)
- **核心算法** (`_core_fuzzy_match`, Line 1451-1650):
  - 粗筛: Sentence-BERT 余弦相似度 Top-K 候选 (可选 GPU 加速)
  - 精排: Cross-Encoder 打分 + 多维度综合评分 (文本/品牌/分类/规格/价格)
  - 综合得分公式: `text_weight*文本相似度 + brand_weight*品牌分 + category_weight*分类分 + specs_weight*规格分`
- **输出 9 个 Sheet**: 条码匹配/模糊匹配/差异品/独有商品(全/去重)/品类缺口/折扣优势

### 2. 数据采集器 (`meituan_shop_goods_writer_breakpoint.py`)
**特色**: 真正断点续爬 - 记录精确断档位置，支持 Ctrl+C 中断和恢复
- **门店指纹识别** (可选): 集成 `store_fingerprint.get_enhanced_store_key()` 实现跨设备门店匹配
- **状态持久化**: `resume_state_{store}.json` 保存断档 category/product 索引
- **追加模式写入**: CSV 追加而非覆盖，确保时间序列完整性

### 3. ETL 数据管道 (`run_price_panel_etl.py`)
**职责**: 整合比价结果 + 历史销售 + 订单四张表 → Parquet/CSV 标准化输出
- **自动化流程**: `--auto-match` 自动调用比价脚本生成最新匹配数据
- **数据契约**: 
  - 输入: `reports/matched_products_comparison_final_*.xlsx` + `raw/historical_sales/` + `raw/orders/`
  - 输出: `intermediate/*.parquet` (含 `match_sku_key` 主键和派生字段)

### 4. 硬件指纹工具 (`硬件指纹工具/`, 独立模块)
**特色**: 独立打包，不受主程序打包覆盖，用于授权系统的硬件指纹生成
- **核心文件**: `generate_fingerprint.py` - 生成机器唯一硬件指纹
- **打包脚本**: `打包指纹工具.ps1` - 独立打包为单文件exe
- **输出**: `dist/硬件指纹工具/硬件指纹工具.exe` + `my_fingerprint.txt`
- **使用场景**: 用户获取硬件指纹 → 管理员生成授权密钥
- **重要**: 此工具目录不参与主程序打包，永久独立存在

## 关键实现细节（必须了解的 "隐藏逻辑"）

### 配置优先级机制（三级覆盖）
```python
# 优先级: 环境变量 > 上传目录 > Config 类硬编码
# Line 163-180: Config 类定义
# 1. 环境变量 (最高): COMPARE_STORE_A_FILE / COMPARE_STORE_B_FILE
# 2. 上传目录 (推荐): upload/本店/*.xlsx, upload/竞对/*.xlsx
# 3. Config 硬编码: STORE_A_FILENAME / STORE_B_FILENAME
```

### 向量缓存持久化策略
- **缓存文件**: `embedding_cache.joblib` (joblib 序列化)
- **缓存键**: `clean_text(商品名称) + 一级分类 + 三级分类`
- **失效条件**: 商品数据大幅变化时手动删除文件强制重建
- **代码位置**: Line 750-820, `load_and_process_store_data()` 内

### 性能调优环境变量
```powershell
# GPU 加速余弦相似度 (默认关闭)
$env:USE_TORCH_SIM = '1'  # 启用 CUDA，失败自动回退 CPU

# 批大小 (根据显存调整)
$env:ENCODE_BATCH_SIZE = '128'  # 显存 4-8GB (默认)
$env:ENCODE_BATCH_SIZE = '256'  # 显存 ≥8GB
$env:ENCODE_BATCH_SIZE = '32'   # CPU 模式或显存 <4GB

# 强制 CPU 模式 (CUDA 错误时)
$env:CUDA_VISIBLE_DEVICES = ''
$env:USE_TORCH_SIM = '0'
```

### 匹配质量调优参数（嵌入在函数内部）
```python
# Line 1451: _core_fuzzy_match() 函数参数
params = {
    'price_similarity_percent': 20,      # 价格容差 ±20%
    'composite_threshold': 0.2,          # 综合得分阈值
    'text_weight': 0.5,                  # 文本相似度权重 50%
    'brand_weight': 0.3,                 # 品牌匹配权重 30%
    'category_weight': 0.1,              # 分类匹配权重 10%
    'specs_weight': 0.1,                 # 规格匹配权重 10%
    'candidates_to_check': 1000,         # 粗筛候选商品数量
    'require_category_match': False,     # 是否强制分类匹配
}
```

## 开发工作流（实际命令，非理论）

### 日常比价分析
```powershell
# 1. 准备数据: 将 Excel 放入 upload/本店/ 和 upload/竞对/
# 2. 运行脚本 (上传目录模式，零配置)
.\start_smart_comparison.ps1  # 不存在时用 .\cpu_mode.ps1 替代

# 3. 查看输出
reports/matched_products_comparison_final_YYYYMMDD_HHMMSS.xlsx
```

### 调试匹配质量问题
```powershell
# Step 1: 导出清洗后数据查看预处理效果
# 编辑 product_comparison_tool_local.py Line 329
EXPORT_CLEANED_SHEETS = True  # 改为 True

# Step 2: 重新运行
python product_comparison_tool_local.py

# Step 3: 查看 reports/*.xlsx 中的 "店A清洗"/"店B清洗" Sheet
# 检查 cleaned_商品名称、standardized_brand、extract_specs 效果

# Step 4: 调整权重/阈值 (Line 1451 _core_fuzzy_match 内)
# Step 5: 删除缓存重新测试
Remove-Item embedding_cache.joblib
```

### ETL 完整流程（含自动比价）
```powershell
# 完整流程: 比价 → 整合历史销售 → 整合订单 → 输出 Parquet
python run_price_panel_etl.py --auto-match --verbose

# 输出文件:
# - intermediate/traffic_cost_dim.csv  (流量和成本维度)
# - intermediate/historical_sales.csv  (历史销售)
# - logs/etl_run_log_YYYYMMDD_HHMMSS.json (运行日志)
```

### CUDA 问题诊断与修复
```powershell
# 诊断 GPU 状态
.\diagnose_gpu.ps1

# 强制 CPU 模式运行
.\cpu_mode.ps1

# 如果 cpu_mode.ps1 不存在，手动设置环境变量
$env:CUDA_VISIBLE_DEVICES = ''
$env:USE_TORCH_SIM = '0'
$env:ENCODE_BATCH_SIZE = '32'
python product_comparison_tool_local.py
```

## 项目约定（与通用实践不同的设计）

### 1. 文本预处理函数是匹配质量的核心
- `clean_text()` (Line 372): 统一繁简、去停用词、标准化单位
- `extract_brand()` (Line 378): 从商品名和分类中提取品牌
- `extract_specs()`: 提取规格 (如 "500ml", "250g")
- **重要**: 修改这些函数直接影响向量缓存，需删除 `embedding_cache.joblib` 重建

### 2. Excel Sheet 顺序有业务逻辑
```python
# Line 1680-1730: export_to_excel() 输出顺序
# 1-2: 精确/模糊匹配 (核心对比)
# 3: 差异品对比 (同类替代品)
# 4-5: 独有商品全部 (原始数据)
# 6-7: 独有商品去重 (按商品名聚合，显示 SKU 数量)
# 8: 品类缺口分析 (战略补品建议)
# 9: 折扣优势对比 (促销决策)
```

### 3. ABAB 列排列模式（提升对比效率）
```python
# 对比类 Sheet 使用 ABAB 交替列排列，而非传统的 AAA...BBB 分组
# 示例: 商品名_A | 商品名_B | 价格_A | 价格_B | 库存_A | 库存_B
# 代码位置: Line 1680-1730, 搜索 "# 定义ABAB列排列"
```

### 4. 模型选择交互式运行时选择
```python
# Line 163-260: Config.AVAILABLE_MODELS 预定义 6 个模型
# 运行时提示用户选择模型编号（1-6）
# 推荐模型:
#   - 速度优先: 模型 3 (M3E 电商场景)
#   - 准确率优先: 模型 5 (BGE-M3 多粒度)
#   - 平衡: 模型 2 (BGE-Base 中文优化)
```

## 扩展开发场景

### 新增匹配算法维度
```python
# 1. 在 _core_fuzzy_match() 中添加新维度得分计算 (Line 1550-1600)
# 2. 修改综合得分公式权重分配
# 3. 更新 params 字典添加新参数
# 4. 删除 embedding_cache.joblib 重新测试
```

### 新增 Excel 输出 Sheet
```python
# 1. 在 generate_final_reports() 中生成新 DataFrame (Line 1584)
# 2. 在 export_to_excel() 中添加 writer.write() 调用 (Line 1680)
# 3. 按需应用 ABAB 列排列逻辑
```

### 集成新数据源
```python
# 1. 在 load_and_process_store_data() 中添加列名映射 (Line 720-750)
# 2. 确保必需列: 商品名称、条码、原价、售价、库存、月售、一级分类、三级分类
# 3. 调用 clean_text/extract_brand/extract_specs 进行预处理
```

## 关键文件清单

| 文件 | 行数 | 职责 | 修改频率 |
|------|------|------|---------|
| `product_comparison_tool_local.py` | 3057 | 主比价引擎 | 高 (算法调优) |
| `run_price_panel_etl.py` | 935 | ETL 管道 | 中 (数据源扩展) |
| `meituan_shop_goods_writer_breakpoint.py` | 373 | 断点续爬 | 低 (稳定功能) |
| `硬件指纹工具/generate_fingerprint.py` | ~100 | 硬件指纹生成 | 低 (独立工具) |
| `硬件指纹工具/打包指纹工具.ps1` | ~100 | 指纹工具打包脚本 | 低 (独立打包) |
| `cpu_mode.ps1` | - | CPU 模式快捷脚本 | 低 (环境配置) |
| `upload/README.md` | - | 上传目录使用说明 | 低 (文档) |
| `快速开始指南.md` | - | 新手入门指南 | 低 (文档) |

## 常见陷阱与注意事项

1. **修改预处理函数后忘记删除缓存**: 导致匹配结果不变
2. **在低内存环境处理大数据集**: 调小 `ENCODE_BATCH_SIZE` 避免 OOM
3. **CUDA 错误卡住流程**: 使用 `cpu_mode.ps1` 或手动设置环境变量
4. **手动编辑生成的 Excel 后作为输入**: 破坏列结构，建议始终使用原始导出文件
5. **PyTorch CUDA 库不兼容 (Python 3.13+)**: 卸载 CUDA 版本并安装 CPU 版本
   ```powershell
   # 修复 PyTorch CUDA 错误
   pip uninstall torch torchvision torchaudio -y
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   ```
6. **硬件指纹工具被主程序打包覆盖**: 使用独立目录 `硬件指纹工具/`，永久保存
   ```powershell
   # 独立打包指纹工具（不会被主程序覆盖）
   .\打包指纹工具.ps1
   # 或进入工具目录执行
   cd 硬件指纹工具
   .\打包指纹工具.ps1
   ```
7. **Streamlit Web 版本**: 使用子进程隔离避免 CUDA 加载，强制 CPU 模式运行
5. **PyTorch CUDA 库不兼容 (Python 3.13+)**: 卸载 CUDA 版本并安装 CPU 版本
   ```powershell
   # 修复 PyTorch CUDA 错误
   pip uninstall torch torchvision torchaudio -y
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   ```
6. **Streamlit Web 版本**: 使用子进程隔离避免 CUDA 加载，强制 CPU 模式运行
