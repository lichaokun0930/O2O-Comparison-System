#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Streamlit 安全启动器 - 在导入任何库之前设置环境变量
这个脚本必须在所有其他导入之前运行
"""

# ============================================================================
# 第一步：设置环境变量（在导入任何库之前）
# ============================================================================
import os
import sys

# 强制 CPU 模式，禁用所有 CUDA 相关功能
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['USE_TORCH_SIM'] = '0'
os.environ['ENCODE_BATCH_SIZE'] = '32'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'  # 避免 Intel MKL 冲突

# 禁用 PyTorch CUDA
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'

print("=" * 60)
print("🛡️  安全模式启动器")
print("=" * 60)
print("✅ 环境变量已设置（CPU 模式）")
print("✅ CUDA 已禁用")
print("=" * 60)

# ============================================================================
# 第二步：现在可以安全地启动 Streamlit
# ============================================================================
if __name__ == "__main__":
    # 运行 streamlit
    from streamlit.web import cli as stcli
    
    # 设置参数
    sys.argv = [
        "streamlit",
        "run",
        "comparison_app.py",
        "--server.port=8501",
        "--server.address=localhost",
    ]
    
    # 启动
    sys.exit(stcli.main())
