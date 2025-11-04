`# -*- coding: utf-8 -*-
"""
O2O 商品比价分析工具 - Streamlit Web 版
运行方式: streamlit run comparison_app.py
"""

# ⚠️ 关键：必须在导入任何其他模块之前设置环境变量，避免 CUDA 错误
import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''  # 禁用 GPU
os.environ['USE_TORCH_SIM'] = '0'        # 强制 CPU 模式
os.environ['ENCODE_BATCH_SIZE'] = '32'   # 默认批次大小

import streamlit as st
import pandas as pd
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import logging
import time
import threading
from io import StringIO

# 自定义输出捕获器，用于捕获 tqdm 进度
class StreamlitProgressCapture:
    """捕获标准输出并更新 Streamlit 进度条"""
    def __init__(self, progress_bar, status_text):
        self.progress_bar = progress_bar
        self.status_text = status_text
        self.buffer = StringIO()
        self.current_progress = 0
        
    def write(self, text):
        """捕获输出文本"""
        if text.strip():
            # 解析 tqdm 进度条
            if '%|' in text or 'it/s' in text or 's/it' in text:
                # 提取百分比
                import re
                match = re.search(r'(\d+)%', text)
                if match:
                    percent = int(match.group(1))
                    # 映射到 50-85% 范围（匹配阶段）
                    adjusted_progress = 50 + (percent * 0.35)
                    self.progress_bar.progress(min(int(adjusted_progress), 85))
                    
                # 提取速度和剩余时间
                if 'it/s' in text:
                    speed_match = re.search(r'([\d.]+)it/s', text)
                    if speed_match:
                        speed = float(speed_match.group(1))
                        self.status_text.text(f"🔍 匹配中... 速度: {speed:.1f} 商品/秒")
            
            # 检查是否是模型下载信息
            elif 'Downloading' in text or 'Download' in text:
                self.status_text.text("⬇️ 正在下载模型文件...")
            elif 'Fetching' in text:
                self.status_text.text("🔍 获取模型信息...")
                
    def flush(self):
        pass

# 设置页面配置（必须是第一个 Streamlit 命令）
st.set_page_config(
    page_title="O2O 商品比价分析工具",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化 session state
if 'analysis_running' not in st.session_state:
    st.session_state.analysis_running = False
if 'result_file' not in st.session_state:
    st.session_state.result_file = None
if 'log_messages' not in st.session_state:
    st.session_state.log_messages = []

# 自定义 CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .upload-section {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .stButton>button {
        width: 100%;
        background-color: #1f77b4;
        color: white;
        font-size: 1.2rem;
        padding: 0.75rem;
        border-radius: 8px;
        border: none;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #1557a0;
    }
    .success-box {
        padding: 1rem;
        background-color: #d4edda;
        border-left: 5px solid #28a745;
        border-radius: 5px;
        margin: 1rem 0;
    }
    .info-box {
        padding: 1rem;
        background-color: #d1ecf1;
        border-left: 5px solid #17a2b8;
        border-radius: 5px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

def show_log(message, level="info"):
    """显示日志消息"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    icon = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "ℹ️")
    log_entry = f"{icon} [{timestamp}] {message}"
    st.session_state.log_messages.append(log_entry)

def get_file_info(uploaded_file):
    """获取上传文件的信息"""
    if uploaded_file:
        size_mb = uploaded_file.size / (1024 * 1024)
        return f"{uploaded_file.name} ({size_mb:.1f} MB)"
    return "未选择文件"

def save_uploaded_file(uploaded_file, prefix="store"):
    """保存上传的文件到临时目录"""
    if uploaded_file is not None:
        temp_dir = Path(tempfile.gettempdir()) / "o2o_comparison"
        temp_dir.mkdir(exist_ok=True)
        
        file_path = temp_dir / f"{prefix}_{uploaded_file.name}"
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return str(file_path)
    return None

def run_comparison(store_a_path, store_b_path, model_choice, use_gpu, batch_size, enable_cross_encoder, progress_bar, status_text):
    """运行比价分析（通过子进程隔离，避免 CUDA 错误）"""
    try:
        import subprocess
        import json
        
        # 阶段 1: 准备环境 (10%)
        progress_bar.progress(10)
        status_text.text("📦 准备环境...")
        show_log("准备启动分析子进程...", "info")
        
        # 模型映射
        model_map = {
            'BGE-M3 多粒度模型 (推荐)': '5',
            'M3E 电商场景模型 (速度快)': '3',
            'BGE-Large 旗舰模型 (准确率高)': '4',
            'BGE-Base 中文优化': '2',
            'BGE-Small 轻量模型': '6',
            '标准多语言模型': '1'
        }
        
        model_num = model_map.get(model_choice, '5')
        cross_encoder_choice = '2' if enable_cross_encoder else ''
        
        # 准备环境变量（传递给子进程）
        env = os.environ.copy()
        env['COMPARE_STORE_A_FILE'] = store_a_path
        env['COMPARE_STORE_B_FILE'] = store_b_path
        env['ENCODE_BATCH_SIZE'] = str(batch_size)
        env['CUDA_VISIBLE_DEVICES'] = ''
        env['USE_TORCH_SIM'] = '0'
        
        # 阶段 2-3: 启动子进程 (15-40%)
        progress_bar.progress(15)
        status_text.text("⚙️ 启动分析引擎...")
        show_log("正在启动比价分析子进程（CPU 模式）...", "info")
        
        # 通过子进程运行，完全隔离 PyTorch
        # 使用当前 Python 解释器（运行 Streamlit 的同一个 Python）
        python_exe = sys.executable  # 使用当前 Python
        cmd = [
            python_exe,
            'product_comparison_tool_local.py'
        ]
        
        # 准备输入（自动选择模型）
        input_text = f"{model_num}\n{cross_encoder_choice}\n"
        
        progress_bar.progress(30)
        status_text.text("🤖 加载 AI 模型...")
        show_log("子进程正在加载模型...", "info")
        
        # 运行子进程并捕获输出
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',  # 强制使用 UTF-8 编码（修复 GBK 错误）
            errors='replace',   # 遇到无法解码的字符用 � 替换
            env=env,
            bufsize=1,
            universal_newlines=True
        )
        
        # 发送模型选择
        process.stdin.write(input_text)
        process.stdin.flush()
        process.stdin.close()
        
        # 读取输出并更新进度
        output_lines = []
        for line in iter(process.stdout.readline, ''):
            output_lines.append(line.strip())
            line_lower = line.lower()
            
            # 根据输出更新进度
            if '步骤 2/7' in line or '加载模型' in line:
                progress_bar.progress(35)
                status_text.text("🤖 加载文本分析模型...")
            elif '步骤 3/7' in line or '查找文件' in line:
                progress_bar.progress(40)
                status_text.text("� 查找数据文件...")
            elif '步骤 4/7' in line or '处理数据' in line:
                progress_bar.progress(50)
                status_text.text("📊 加载和清洗商品数据...")
            elif '向量' in line or 'embedding' in line_lower:
                progress_bar.progress(60)
                status_text.text("🧮 向量化编码中...")
            elif '步骤 5/7' in line or '匹配' in line:
                progress_bar.progress(70)
                status_text.text("🔍 智能匹配中...")
            elif '硬分类匹配' in line or '软分类' in line:
                progress_bar.progress(75)
                status_text.text("🔍 三阶段匹配进行中...")
            elif '步骤 6/7' in line or '生成报告' in line:
                progress_bar.progress(85)
                status_text.text("📝 生成分析报告...")
            elif '步骤 7/7' in line or '导出' in line:
                progress_bar.progress(90)
                status_text.text("� 导出 Excel 文件...")
            elif '全部流程完成' in line:
                progress_bar.progress(95)
                status_text.text("✅ 分析完成！")
            
            # 显示重要日志
            if any(keyword in line for keyword in ['✅', '⚠️', '❌', 'ERROR', 'WARNING']):
                show_log(line.strip(), "info")
        
        # 等待进程完成
        process.wait()
        
        progress_bar.progress(95)
        status_text.text("🔎 查找生成的报告文件...")
        
        if process.returncode == 0:
            # 查找最新生成的报告
            reports_dir = Path('reports')
            if reports_dir.exists():
                report_files = list(reports_dir.glob('matched_products_comparison_final_*.xlsx'))
                if report_files:
                    latest_report = max(report_files, key=lambda p: p.stat().st_mtime)
                    progress_bar.progress(100)
                    status_text.text("✅ 分析完成！")
                    show_log(f"分析完成！报告: {latest_report.name}", "success")
                    return str(latest_report)
            
            progress_bar.progress(100)
            status_text.text("⚠️ 分析完成但未找到报告")
            show_log("分析完成，但未找到报告文件", "warning")
            show_log("请检查 reports/ 目录", "warning")
        else:
            status_text.text(f"❌ 分析失败 (退出代码: {process.returncode})")
            show_log(f"子进程异常退出，代码: {process.returncode}", "error")
            # 显示最后几行输出
            if output_lines:
                show_log("最后的输出:", "error")
                for line in output_lines[-10:]:
                    if line:
                        show_log(f"  {line}", "error")
        
        return None
        
    except Exception as e:
        status_text.text(f"❌ 错误: {str(e)}")
        show_log(f"分析出错: {str(e)}", "error")
        import traceback
        st.error(f"```\n{traceback.format_exc()}\n```")
        return None

# ============================================================================
# 主界面
# ============================================================================

# 标题
st.markdown('<div class="main-header">🏪 O2O 商品比价分析工具</div>', unsafe_allow_html=True)
st.markdown("---")

# 侧边栏 - 配置选项
with st.sidebar:
    st.header("⚙️ 配置选项")
    
    st.subheader("📊 模型选择")
    model_choice = st.selectbox(
        "向量化模型",
        [
            'BGE-M3 多粒度模型 (推荐)',
            'M3E 电商场景模型 (速度快)',
            'BGE-Large 旗舰模型 (准确率高)',
            'BGE-Base 中文优化',
            'BGE-Small 轻量模型',
            '标准多语言模型'
        ],
        help="不同模型在速度和准确率上有不同权衡"
    )
    
    enable_cross_encoder = st.checkbox(
        "启用 Cross-Encoder 精排",
        value=False,
        help="启用后会使用 BGE-Reranker-Large 进行二次精排，准确率提升 40% 但速度较慢"
    )
    
    st.subheader("🚀 性能配置")
    
    st.info("💡 Streamlit 版本当前仅支持 CPU 模式\n\n如需 GPU 加速，请使用命令行版本运行")
    
    use_gpu = False  # Streamlit 版本固定使用 CPU
    
    batch_size = st.slider(
        "批处理大小",
        min_value=16,
        max_value=128,
        value=32,
        step=16,
        help="CPU 模式推荐 32，处理大数据集可调整到 64"
    )
    
    st.markdown("---")
    st.subheader("📖 使用说明")
    st.info("""
    1. 上传本店和竞对的 Excel 数据
    2. 选择合适的模型和性能配置
    3. 点击"开始分析"按钮
    4. 等待分析完成后下载报告
    
    **报告包含 9 个 Sheet**:
    - 条码精确匹配
    - 名称模糊匹配
    - 差异品对比
    - 独有商品分析
    - 品类缺口识别
    - 折扣优势对比
    """)
    
    st.markdown("---")
    st.caption("版本: v2.0 Streamlit Edition")

# 主区域 - 文件上传
col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="upload-section">', unsafe_allow_html=True)
    st.subheader("📂 本店数据")
    uploaded_store_a = st.file_uploader(
        "选择本店商品数据 Excel 文件",
        type=['xlsx', 'xls'],
        key='store_a',
        help="支持美团、饿了么等平台导出的商品数据"
    )
    if uploaded_store_a:
        st.success(f"✅ {get_file_info(uploaded_store_a)}")
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="upload-section">', unsafe_allow_html=True)
    st.subheader("📂 竞对数据")
    uploaded_store_b = st.file_uploader(
        "选择竞争对手商品数据 Excel 文件",
        type=['xlsx', 'xls'],
        key='store_b',
        help="支持美团、饿了么等平台导出的商品数据"
    )
    if uploaded_store_b:
        st.success(f"✅ {get_file_info(uploaded_store_b)}")
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")

# 开始分析按钮
if uploaded_store_a and uploaded_store_b:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀 开始比价分析", type="primary", disabled=st.session_state.analysis_running):
            st.session_state.analysis_running = True
            st.session_state.log_messages = []
            st.session_state.result_file = None
            
            # 保存上传的文件
            show_log("保存上传的文件...", "info")
            store_a_path = save_uploaded_file(uploaded_store_a, "store_a")
            store_b_path = save_uploaded_file(uploaded_store_b, "store_b")
            
            show_log(f"本店文件: {uploaded_store_a.name}", "info")
            show_log(f"竞对文件: {uploaded_store_b.name}", "info")
            show_log(f"模型: {model_choice}", "info")
            show_log(f"批处理大小: {batch_size}", "info")
            
            # 创建进度显示区域
            st.markdown("---")
            progress_container = st.container()
            with progress_container:
                st.subheader("📊 分析进度")
                progress_bar = st.progress(0)
                status_text = st.empty()
                status_text.text("准备开始...")
                
                st.info("""
                **预计耗时**: 2-5 分钟  
                **阶段说明**:
                1. 📦 环境准备
                2. 🤖 模型加载（首次运行会下载模型，约 500MB-2GB）
                3. 📊 数据加载
                4. 🔄 数据清洗
                5. 🧮 向量编码
                6. 🔍 智能匹配
                7. 📝 生成报告
                8. ✅ 完成
                """)
            
            # 运行分析
            result_file = run_comparison(
                store_a_path,
                store_b_path,
                model_choice,
                use_gpu,
                batch_size,
                enable_cross_encoder,
                progress_bar,
                status_text
            )
            
            if result_file and os.path.exists(result_file):
                st.session_state.result_file = result_file
                st.balloons()
                st.success("🎉 分析完成！请查看下方的报告下载和预览区域。")
            
            st.session_state.analysis_running = False
            st.rerun()
else:
    st.info("👆 请先上传本店和竞对的数据文件")

# 显示日志
if st.session_state.log_messages:
    st.markdown("---")
    st.subheader("📋 运行日志")
    log_container = st.container()
    with log_container:
        for log in st.session_state.log_messages:
            st.text(log)

# 显示结果
if st.session_state.result_file and os.path.exists(st.session_state.result_file):
    st.markdown("---")
    st.markdown('<div class="success-box">', unsafe_allow_html=True)
    st.subheader("✅ 分析完成！")
    
    result_path = Path(st.session_state.result_file)
    file_size = result_path.stat().st_size / (1024 * 1024)
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.metric("报告文件", result_path.name)
    with col2:
        st.metric("文件大小", f"{file_size:.2f} MB")
    with col3:
        st.metric("生成时间", datetime.fromtimestamp(result_path.stat().st_mtime).strftime("%H:%M:%S"))
    
    # 下载按钮
    with open(st.session_state.result_file, 'rb') as f:
        st.download_button(
            label="📥 下载完整报告",
            data=f,
            file_name=result_path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 报告预览
    st.markdown("---")
    st.subheader("📊 报告预览")
    
    try:
        # 读取并显示部分数据
        excel_file = pd.ExcelFile(st.session_state.result_file)
        sheet_names = excel_file.sheet_names
        
        st.info(f"报告包含 {len(sheet_names)} 个工作表: {', '.join(sheet_names)}")
        
        # 选择要预览的 Sheet
        selected_sheet = st.selectbox("选择要预览的工作表", sheet_names)
        
        if selected_sheet:
            df = pd.read_excel(st.session_state.result_file, sheet_name=selected_sheet)
            st.dataframe(df.head(20), use_container_width=True)
            st.caption(f"显示前 20 行，共 {len(df)} 行数据")
            
            # 统计信息
            if len(df) > 0:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("总行数", len(df))
                with col2:
                    st.metric("总列数", len(df.columns))
                with col3:
                    if '售价' in df.columns or '价格' in df.columns:
                        price_col = '售价' if '售价' in df.columns else '价格'
                        avg_price = df[price_col].mean()
                        st.metric("平均价格", f"¥{avg_price:.2f}")
    
    except Exception as e:
        st.warning(f"无法预览报告: {str(e)}")

# 页脚
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 2rem 0;">
    <p>💡 提示: 首次运行会下载模型文件，请耐心等待</p>
    <p>⚡ 性能优化: 使用 GPU 可提升 3-5 倍速度</p>
    <p>📧 技术支持: 查看项目文档或提交 Issue</p>
</div>
""", unsafe_allow_html=True)
