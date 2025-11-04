# 本地运行文件夹

此文件夹包含在 **本地 Windows 环境**运行比价工具所需的文件。

## 📁 文件说明

### 启动脚本
- **start_comparison.ps1** - 命令行版本启动（推荐）⭐
- **start_app.ps1** - Streamlit Web 版本启动

### 诊断工具
- **cpu_mode.ps1** - 强制 CPU 模式运行
- **diagnose_gpu.ps1** - GPU 环境诊断
- **diagnose_performance.ps1** - 性能诊断工具

### 修复工具
- **fix_cuda_error.py** - CUDA 错误修复工具
- **fix_pytorch.ps1** - PyTorch 修复脚本

### 测试脚本
- **test_column_order.ps1** - 列顺序测试
- **test_gpu_performance.ps1** - GPU 性能测试
- **test_threshold_fix.ps1** - 阈值修复测试

### 文档
- **CUDA错误解决方案.md** - CUDA 问题排查指南
- **快速开始指南.md** - 新手入门指南
- **streamlit使用指南.md** - Web 版本使用说明

## 🚀 快速开始

### 命令行版本（推荐）
```powershell
.\start_comparison.ps1
```

**特点**：
- ✅ 交互式选择 AI 模型（1-6）
- ✅ 自动检测数据文件
- ✅ 分析完成后询问是否打开报告
- ✅ 友好的进度提示

### Web 版本
```powershell
.\start_app.ps1
```

**特点**：
- ✅ 浏览器界面操作
- ✅ 拖拽上传文件
- ✅ 实时进度条
- ✅ 点击下载报告

## ⚠️ 常见问题

### CUDA 错误？
```powershell
.\cpu_mode.ps1
```

### 性能慢？
```powershell
.\diagnose_performance.ps1
```

### PyTorch 安装问题？
```powershell
.\fix_pytorch.ps1
```

## 📊 性能优化

当前配置（已优化）：
- 编码批大小：256
- 候选商品数：80

如需调整，编辑 `start_comparison.ps1`：
```powershell
$env:ENCODE_BATCH_SIZE = "256"    # 批大小
$env:MATCH_TOPK_SOFT = "80"       # 候选数
```

## 🔙 返回根目录

```powershell
cd ..
```
