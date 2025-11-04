# O2O 商品比价分析工具

**智能商品比价 · 数据驱动决策 · AI 精准匹配**

---

## 📂 目录结构

```
比价数据/
│
├── 📁 本地运行/                    # 本地 Windows 运行文件
│   ├── start_comparison.ps1       # ⭐ 命令行版启动（推荐）
│   ├── start_app.ps1              # Web 版启动
│   ├── diagnose_*.ps1             # 诊断工具
│   ├── fix_*.ps1                  # 修复工具
│   ├── test_*.ps1                 # 测试脚本
│   └── README.md                  # 📖 本地运行说明
│
├── 📁 服务器部署/                  # 服务器部署文件
│   ├── deploy_to_aliyun.ps1      # ⭐ 打包脚本
│   ├── server_setup.sh           # ⭐ 服务器部署脚本
│   ├── Dockerfile                # Docker 配置
│   ├── requirements.txt          # 依赖列表
│   ├── 部署指南.md               # 📖 通用部署指南
│   ├── 阿里云部署指南.md         # 📖 阿里云专用指南
│   └── README.md                 # 📖 部署说明
│
├── 🐍 product_comparison_tool_local.py  # 核心比价引擎
├── 🌐 comparison_app.py                 # Streamlit Web 应用
├── 🕷️ meituan_shop_goods_writer_breakpoint.py  # 数据采集器
├── 🔄 run_price_panel_etl.py           # ETL 数据管道
│
├── 📁 upload/                    # 数据上传目录
│   ├── 本店/
│   └── 竞对/
│
├── 📁 reports/                   # 生成的比价报告
├── 📁 intermediate/              # ETL 中间数据
├── 📁 logs/                      # 运行日志
├── 📁 .streamlit/                # Streamlit 配置
│
├── 💾 embedding_cache.joblib     # 向量缓存（104MB）
│
└── 📚 核心文档/                  # 技术说明文档
    ├── 严格模式说明.md
    ├── 分类字段重组说明.md
    ├── 动态权重配置说明.md
    ├── 智能文件识别使用指南.md
    ├── 模型自适应阈值说明.md
    ├── 比价测算模块设计.md
    ├── 清洗数据独立展示说明.md
    ├── 美团分类保留方案.md
    └── CHANGELOG.md
```

---

## 🚀 快速开始

### 本地运行（Windows）

```powershell
# 进入本地运行目录
cd 本地运行

# 方式1：命令行版本（推荐）
.\start_comparison.ps1

# 方式2：Web 版本
.\start_app.ps1
```

**详细说明**：查看 `本地运行/README.md`

---

### 服务器部署（Linux）

```powershell
# 进入服务器部署目录
cd 服务器部署

# 步骤1：本地打包
.\deploy_to_aliyun.ps1

# 步骤2：上传到服务器（VS Code Remote 或 SCP）

# 步骤3：服务器端执行
# cd /root/o2o_tool
# sudo ./server_setup.sh
```

**详细说明**：查看 `服务器部署/README.md` 或 `服务器部署/阿里云部署指南.md`

---

## 📚 文档索引

### 快速访问

| 类别 | 文档 | 位置 |
|------|------|------|
| **本地使用** | 快速开始指南 | `本地运行/快速开始指南.md` |
|  | CUDA 错误解决 | `本地运行/CUDA错误解决方案.md` |
|  | Streamlit 使用 | `本地运行/streamlit使用指南.md` |
| **服务器部署** | 部署指南 | `服务器部署/部署指南.md` |
|  | 阿里云部署 ⭐ | `服务器部署/阿里云部署指南.md` |
|  | 用户使用指南 | `服务器部署/最终用户使用指南.md` |
| **核心技术** | 比价测算设计 | `比价测算模块设计.md` |
|  | 动态权重配置 | `动态权重配置说明.md` |
|  | 模型阈值说明 | `模型自适应阈值说明.md` |

---

## ⚙️ 核心组件说明

| 文件 | 说明 | 运行环境 |
|------|------|---------|
| **product_comparison_tool_local.py** | 比价引擎核心（3100+ 行） | 本地/服务器通用 |
| **comparison_app.py** | Streamlit Web 界面（544 行） | 本地/服务器通用 |
| **meituan_shop_goods_writer_breakpoint.py** | 美团数据采集器 | 本地 |
| **run_price_panel_etl.py** | ETL 数据管道 | 本地 |
| **embedding_cache.joblib** | 向量缓存 | 本地（加速比对） |

---

## 🎯 核心功能

### 1. 智能商品比价
- ✅ **三阶段匹配**：条码精确 → 分类硬匹配 → 软匹配
- ✅ **AI 算法**：Sentence-BERT + Cross-Encoder
- ✅ **9-Sheet 报告**：全方位分析
- ✅ **向量缓存**：第二次运行速度提升 10 倍

### 2. 数据采集
- ✅ **断点续爬**：支持 Ctrl+C 中断和恢复
- ✅ **门店指纹识别**：跨设备匹配
- ✅ **追加模式写入**：时间序列完整

### 3. ETL 数据管道
- ✅ **自动化流程**：比价 → 整合销售 → 输出标准化数据
- ✅ **多源整合**：4张表合并
- ✅ **Parquet 输出**：高效存储

---

## 🔧 环境要求

### Windows 本地环境
- **Python**: 3.11+
- **PyTorch**: 2.9.0+cpu
- **核心库**: sentence-transformers, streamlit, pandas
- **内存**: 8GB+

### Linux 服务器环境
- **系统**: Ubuntu 20.04+
- **Python**: 3.11+
- **CPU**: 2核+
- **内存**: 4GB+
- **硬盘**: 10GB+

---

## 📊 性能参考

| 商品数量 | 向量编码 | 匹配计算 | 总耗时 |
|---------|---------|---------|--------|
| 1000 行 | 30秒 | 1分钟 | ~2分钟 |
| 5000 行 | 2分钟 | 6分钟 | ~8分钟 |
| 10000行 | 5分钟 | 15分钟 | ~20分钟 |

**优化配置**（已应用）：
- `ENCODE_BATCH_SIZE = 256`（批大小）
- `MATCH_TOPK_SOFT = 80`（候选数）

---

## 🛠️ 常用命令

### 本地诊断
```powershell
cd 本地运行
.\diagnose_performance.ps1   # 性能诊断
.\diagnose_gpu.ps1           # GPU 检测
.\cpu_mode.ps1               # 强制 CPU 模式
```

### 服务器管理
```bash
sudo systemctl status o2o-tool    # 查看状态
journalctl -u o2o-tool -f         # 查看日志
sudo systemctl restart o2o-tool   # 重启服务
```

---

## 📞 获取帮助

### 问题排查路径

```
遇到问题
    │
    ├─ 本地运行问题 → 查看 本地运行/README.md
    │                → 运行诊断工具
    │
    ├─ 部署问题 → 查看 服务器部署/README.md
    │           → 查看 服务器部署/阿里云部署指南.md
    │
    └─ 技术细节 → 查看根目录各说明文档
```

### 文档优先级

1. **新手入门**：`本地运行/快速开始指南.md` ⭐
2. **部署指南**：`服务器部署/阿里云部署指南.md` ⭐
3. **用户使用**：`服务器部署/最终用户使用指南.md`
4. **技术深入**：根目录各技术文档

---

## 🎉 开始使用

**本地运行**：
```powershell
cd 本地运行
.\start_comparison.ps1
```

**服务器部署**：
```powershell
cd 服务器部署
.\deploy_to_aliyun.ps1
```

**查看文档**：
```powershell
# 本地使用文档
type 本地运行\README.md

# 部署文档
type 服务器部署\README.md
```

---

**祝您使用愉快！** 🚀
