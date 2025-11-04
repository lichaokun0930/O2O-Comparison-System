# O2O 商品比价分析平台 - 程序文件

## � 文件夹结构

### 核心程序文件
- product_comparison_tool_local.py - 主比价引擎
- run_price_panel_etl.py - ETL数据管道
- meituan_shop_goods_writer_breakpoint.py - 数据采集器
- comparison_app.py - Streamlit Web界面

### 打包脚本
- 打包双模式版.ps1 - 包含平衡+精确两套模型（推荐）
- 打包完整版_优化.ps1 - 仅精确模式模型

### 数据目录
- upload/ - 上传Excel文件（本店/竞对）
- reports/ - 输出比价报告
- raw/ - 原始数据（历史销售/订单）
- intermediate/ - 中间处理结果
- logs/ - 运行日志

### 模型文件
- models/ - NLP模型文件（需下载）

### 硬件指纹工具
- 硬件指纹工具/ - 源码和打包脚本
- 硬件指纹工具.zip - 打包好的工具（可直接分发）

### 用户文档
- 快速开始指南.md - 新手入门
- 使用说明.txt - 基础使用
- 用户使用手册.txt - 详细手册
- 用户密钥使用图解指南.md - 授权说明
- 智能文件识别使用指南.md - 文件识别功能

### 辅助脚本
- cpu_mode.ps1 - CPU模式运行
- diagnose_gpu.ps1 - GPU诊断
- start_smart_comparison.ps1 - 快速启动

### 配置文件
- authorized_keys.json - 授权密钥配置
- requirements.txt - Python依赖
- embedding_cache.joblib - 向量缓存（可选）
- cross_encoder_cache.joblib - 重排序缓存（可选）

##  快速开始

1. 安装依赖: pip install -r requirements.txt
2. 下载模型: python download_extra_models.py
3. 运行程序: python product_comparison_tool_local.py
4. 或打包发布: .\打包双模式版.ps1

##  打包发布

执行打包脚本后，在 dist/ 目录下生成可执行文件。

---
更新时间: 2025年11月2日
