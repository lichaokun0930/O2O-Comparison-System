# -*- coding: utf-8 -*-
"""
O2O比价工具 - 图形界面启动器
为小白用户提供友好的图形界面
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import threading
from datetime import datetime

# ===== 授权检查（必须在GUI显示之前） =====
# 导入授权模块（从主程序）
if getattr(sys, 'frozen', False):
    # 打包环境：执行授权检查
    # ⚠️ 关键：必须先设置 GUI_MODE 环境变量，否则 check_authorization() 会使用 input() 卡死
    os.environ['GUI_MODE'] = '1'
    
    # 注意：不要在这里设置 HF_HOME 等环境变量！
    # 主程序 product_comparison_tool_local.py 已经有完整的模型路径检测逻辑（Line 588-610）
    # 让主程序自己处理，就像 Streamlit 版本一样
    
    try:
        from product_comparison_tool_local import check_authorization
        auth_result = check_authorization()
        
        # 确保所有授权窗口都已销毁
        import time
        time.sleep(0.5)  # 等待500ms确保窗口完全销毁
        
        if not auth_result:
            # 授权失败，直接退出
            sys.exit(1)
    except Exception as e:
        # 如果授权检查失败，显示错误（确保有 tk 初始化）
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            messagebox.showerror("授权检查失败", f"无法加载授权模块：\n{str(e)}")
            root.destroy()
        except:
            pass  # 如果 tk 也失败，静默退出
        sys.exit(1)
# 开发环境跳过授权检查

class ComparisionToolGUI:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("O2O商品比价工具 v2.3")
        self.window.geometry("800x900")  # 🔧 增加窗口高度：750→900，为日志框留出更多空间
        self.window.resizable(True, True)  # 允许调整大小
        
        # 强制窗口置顶和激活
        self.window.attributes('-topmost', True)
        self.window.lift()
        self.window.focus_force()
        self.window.after(100, lambda: self.window.attributes('-topmost', False))  # 100ms后取消置顶
        
        # 变量
        self.store_a_file = tk.StringVar()
        self.store_b_file = tk.StringVar()
        self.progress_var = tk.StringVar(value="准备就绪")
        self.model_choice = tk.StringVar(value="平衡模式")  # 🆕 模型选择（默认Base）
        
        self.setup_ui()
    
    def setup_ui(self):
        """设置界面"""
        # 标题
        title_frame = tk.Frame(self.window, bg="#2196F3", height=80)
        title_frame.pack(fill=tk.X)
        title_label = tk.Label(
            title_frame, 
            text="🛒 O2O商品比价分析工具",
            font=("微软雅黑", 18, "bold"),
            bg="#2196F3",
            fg="white"
        )
        title_label.pack(pady=20)
        
        # 主内容区
        content_frame = tk.Frame(self.window, padx=30, pady=20)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # 文件选择区
        self.create_file_section(content_frame)
        
        # 🆕 模型配置区
        self.create_model_config_section(content_frame)
        
        # 按钮区
        self.create_button_section(content_frame)
        
        # 进度区
        self.create_progress_section(content_frame)
        
    def create_file_section(self, parent):
        """创建文件选择区域"""
        file_frame = tk.LabelFrame(parent, text="📁 数据文件选择", font=("微软雅黑", 10), padx=10, pady=10)
        file_frame.pack(fill=tk.X, pady=10)
        
        # 本店文件
        tk.Label(file_frame, text="本店数据：", font=("微软雅黑", 9)).grid(row=0, column=0, sticky=tk.W, pady=5)
        tk.Entry(file_frame, textvariable=self.store_a_file, width=40, state="readonly").grid(row=0, column=1, padx=5)
        tk.Button(file_frame, text="浏览...", command=self.browse_store_a, width=8).grid(row=0, column=2)
        
        # 竞对文件
        tk.Label(file_frame, text="竞对数据：", font=("微软雅黑", 9)).grid(row=1, column=0, sticky=tk.W, pady=5)
        tk.Entry(file_frame, textvariable=self.store_b_file, width=40, state="readonly").grid(row=1, column=1, padx=5)
        tk.Button(file_frame, text="浏览...", command=self.browse_store_b, width=8).grid(row=1, column=2)
        
        # 提示
        tip_label = tk.Label(
            file_frame, 
            text="💡 提示：选择美团或其他平台导出的Excel文件",
            font=("微软雅黑", 8),
            fg="gray"
        )
        tip_label.grid(row=2, column=0, columnspan=3, pady=5)
    
    def create_model_config_section(self, parent):
        """🆕 创建模型配置区域"""
        config_frame = tk.LabelFrame(parent, text="⚙️ 模型配置", font=("微软雅黑", 10), padx=10, pady=10)
        config_frame.pack(fill=tk.X, pady=10)
        
        # 模型选择标签
        tk.Label(config_frame, text="比价模式：", font=("微软雅黑", 9)).grid(row=0, column=0, sticky=tk.W, pady=5, padx=5)
        
        # 模型选择下拉框（仅2档：使用现有模型）
        model_dropdown = ttk.Combobox(
            config_frame,
            textvariable=self.model_choice,
            values=["高精度模式", "平衡模式"],
            state="readonly",
            width=15,
            font=("微软雅黑", 9)
        )
        model_dropdown.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        model_dropdown.current(1)  # 默认选择"平衡模式"
        
        # 模式说明
        mode_info = {
            "高精度模式": "⭐⭐⭐⭐⭐ 最高准确率 | 速度：慢 | 适合：重要决策",
            "平衡模式": "⭐⭐⭐⭐ 推荐 | 速度快50% | 适合：日常比价"
        }
        
        self.mode_info_label = tk.Label(
            config_frame,
            text=mode_info["平衡模式"],
            font=("微软雅黑", 8),
            fg="#666"
        )
        self.mode_info_label.grid(row=0, column=2, sticky=tk.W, padx=10)
        
        # 绑定选择事件，更新说明文本
        def update_mode_info(event):
            selected_mode = self.model_choice.get()
            self.mode_info_label.config(text=mode_info.get(selected_mode, ""))
        
        model_dropdown.bind("<<ComboboxSelected>>", update_mode_info)
        
        # 🔧 简化说明文本（从5行缩减到3行，节省垂直空间）
        detail_text = (
            "💡 高精度：Large模型，最准确，适合重要决策 | "
            "平衡：Base模型，速度快50%，准确率仅降2%（推荐） | "
            "成本倒推、品类缺口不受模型影响"
        )
        detail_label = tk.Label(
            config_frame,
            text=detail_text,
            font=("微软雅黑", 7),
            fg="gray",
            justify=tk.LEFT,
            bg="#f5f5f5",
            padx=10,
            pady=3  # 🔧 减少垂直填充：5→3
        )
        detail_label.grid(row=1, column=0, columnspan=3, sticky=tk.W+tk.E, pady=(5, 0))  # 🔧 调整间距
    
    def create_button_section(self, parent):
        """创建按钮区域"""
        button_frame = tk.Frame(parent)
        button_frame.pack(pady=20)
        
        # 开始分析按钮
        self.start_btn = tk.Button(
            button_frame,
            text="🚀 开始比价分析",
            command=self.start_analysis,
            font=("微软雅黑", 12, "bold"),
            bg="#4CAF50",
            fg="white",
            width=20,
            height=2,
            cursor="hand2"
        )
        self.start_btn.pack(side=tk.LEFT, padx=10)
        
        # 打开报告按钮
        self.open_report_btn = tk.Button(
            button_frame,
            text="📊 打开报告文件夹",
            command=self.open_reports_folder,
            font=("微软雅黑", 10),
            bg="#2196F3",
            fg="white",
            width=15,
            height=2,
            cursor="hand2"
        )
        self.open_report_btn.pack(side=tk.LEFT, padx=10)
    
    def create_progress_section(self, parent):
        """创建进度区域"""
        progress_frame = tk.LabelFrame(parent, text="📈 运行状态", font=("微软雅黑", 10), padx=10, pady=10)
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # 进度条（改为确定模式，支持百分比显示）
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate', maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # 状态文本
        self.progress_label = tk.Label(
            progress_frame,
            textvariable=self.progress_var,
            font=("微软雅黑", 9),
            fg="#666"
        )
        self.progress_label.pack(pady=5)
        
        # 详细日志框架标题
        log_label = tk.Label(
            progress_frame,
            text="📋 详细进度日志：",
            font=("微软雅黑", 9, "bold"),
            fg="#2196F3"
        )
        log_label.pack(anchor=tk.W, pady=(10, 5))
        
        # 🔧 修复：创建带滚动条的文本框，并确保其占据剩余所有垂直空间
        log_frame = tk.Frame(progress_frame, relief=tk.SUNKEN, borderwidth=1)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))  # 🔧 添加 pady 确保底部留白
        
        # 滚动条
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 文本框 - 显示详细日志（🔧 添加最小高度，确保可见性）
        self.log_text = tk.Text(
            log_frame,
            font=("微软雅黑", 9),  # 修复：Consolas不支持中文，改为微软雅黑
            bg="#f5f5f5",
            fg="#333",
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            state=tk.DISABLED,  # 只读
            padx=5,
            pady=5
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        # 配置文本标签颜色
        self.log_text.tag_config("success", foreground="#4CAF50")
        self.log_text.tag_config("error", foreground="#F44336")
        self.log_text.tag_config("warning", foreground="#FF9800")
        self.log_text.tag_config("info", foreground="#2196F3")
        self.log_text.tag_config("progress", foreground="#9C27B0")
        
        # 添加欢迎消息到日志框
        self.log_text.config(state=tk.NORMAL)
        welcome_msg = (
            "欢迎使用O2O商品比价分析工具！\n"
            "请选择本店和竞对数据文件，然后点击'开始比价分析'按钮。\n"
            "分析过程中的详细进度将在此处实时显示。\n"
            + "="*60 + "\n"
        )
        self.log_text.insert(tk.END, welcome_msg, "info")
        self.log_text.config(state=tk.DISABLED)
    
    def browse_store_a(self):
        """选择本店文件"""
        filename = filedialog.askopenfilename(
            title="选择本店数据文件",
            filetypes=[("Excel文件", "*.xlsx *.xls"), ("所有文件", "*.*")]
        )
        if filename:
            self.store_a_file.set(filename)
    
    def browse_store_b(self):
        """选择竞对文件"""
        filename = filedialog.askopenfilename(
            title="选择竞对数据文件",
            filetypes=[("Excel文件", "*.xlsx *.xls"), ("所有文件", "*.*")]
        )
        if filename:
            self.store_b_file.set(filename)
    
    def start_analysis(self):
        """开始分析"""
        # 检查文件
        if not self.store_a_file.get() or not self.store_b_file.get():
            messagebox.showwarning("提示", "请先选择本店和竞对数据文件！")
            return
        
        # 🆕 设置模型环境变量（根据用户选择，使用现有模型）
        model_mode = self.model_choice.get()
        if model_mode == "高精度模式":
            os.environ['EMBEDDING_MODEL'] = 'BAAI/bge-large-zh-v1.5'
            os.environ['RERANKER_MODEL'] = 'BAAI/bge-reranker-large'
        else:  # 平衡模式（默认）
            os.environ['EMBEDDING_MODEL'] = 'BAAI/bge-base-zh-v1.5'
            os.environ['RERANKER_MODEL'] = 'BAAI/bge-reranker-base'
        
        # 传递模型模式名称（用于日志显示）
        os.environ['MODEL_MODE'] = model_mode
        
        # 设置文件路径环境变量
        os.environ['COMPARE_STORE_A_FILE'] = self.store_a_file.get()
        os.environ['COMPARE_STORE_B_FILE'] = self.store_b_file.get()
        os.environ['GUI_MODE'] = '1'  # 标记GUI模式，避免交互式输入
        
        # 禁用按钮
        self.start_btn.config(state=tk.DISABLED)
        
        # 重置进度条为0%（determinate模式）
        self.progress_bar['value'] = 0
        self.progress_var.set(f"正在加载模型 ({model_mode})...")
        
        # 清空日志框
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # 启动分析线程
        thread = threading.Thread(target=self.run_analysis)
        thread.daemon = True
        thread.start()
    
    def run_analysis(self):
        """运行分析（后台线程）"""
        from datetime import datetime
        
        # 记录开始时间
        start_time = datetime.now()
        log_file = Path("logs") / f"gui_run_{start_time.strftime('%Y%m%d_%H%M%S')}.log"
        log_file.parent.mkdir(exist_ok=True)
        
        def log(msg):
            """写日志"""
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            log_msg = f"[{timestamp}] {msg}\n"
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_msg)
            print(log_msg.strip())  # 同时打印到控制台
        
        log("=" * 60)
        log("GUI分析任务启动")
        log(f"本店文件: {self.store_a_file.get()}")
        log(f"竞对文件: {self.store_b_file.get()}")
        log("=" * 60)
        
        try:
            # 重定向stdout来捕获进度信息
            import io
            import re
            import sys as sys_module  # 避免命名冲突
            
            log("开始重定向stdout...")
            
            class ProgressCapture(io.StringIO):
                """捕获并解析进度信息"""
                def __init__(self, gui_callback, original_stdout):
                    super().__init__()
                    self.gui_callback = gui_callback
                    self.original_stdout = original_stdout
                    self.last_line = ""
                    self.buffer = ""  # 缓冲区用于处理tqdm的回车覆盖
                
                def write(self, s):
                    # 同时输出到原始stdout（用于调试）
                    try:
                        if self.original_stdout and hasattr(self.original_stdout, 'write'):
                            self.original_stdout.write(s)
                            self.original_stdout.flush()
                    except:
                        pass
                    
                    # 确保s是字符串
                    if isinstance(s, bytes):
                        try:
                            s = s.decode('utf-8', errors='replace')
                        except:
                            s = str(s)
                    else:
                        s = str(s) if s is not None else ''
                    
                    if s:
                        # 处理回车符（tqdm用\r实现进度条刷新）
                        if '\r' in s and '\n' not in s:
                            # tqdm进度条更新（覆盖式）
                            self.buffer = s.replace('\r', '')
                            self.gui_callback(self.buffer, is_progress=True)
                        elif '\n' in s:
                            # 正常文本输出
                            lines = s.split('\n')
                            for line in lines:
                                if line.strip():
                                    self.last_line = line.strip()
                                    self.gui_callback(line.strip(), is_progress=False)
                        else:
                            # 普通输出
                            if s.strip():
                                self.last_line = s.strip()
                                self.gui_callback(s.strip(), is_progress=False)
                    
                    return len(s)
                
                def flush(self):
                    """实现flush方法避免缓冲问题"""
                    try:
                        if self.original_stdout and hasattr(self.original_stdout, 'flush'):
                            self.original_stdout.flush()
                    except:
                        pass
            
            # 创建进度捕获器（保留原始stdout）
            old_stdout = sys_module.stdout
            old_stderr = sys_module.stderr
            progress_capture = ProgressCapture(self.update_progress_from_stdout, old_stdout)
            sys_module.stdout = progress_capture
            sys_module.stderr = progress_capture  # 同时捕获stderr
            
            self.progress_var.set("正在加载数据和模型...")
            log("准备导入主程序...")
            
            try:
                # 导入主程序
                log("导入 product_comparison_tool_local...")
                from product_comparison_tool_local import main
                log("✓ 主程序导入成功")
                
                # 运行分析
                log("开始运行 main() 函数...")
                main()
                log("✓ main() 函数执行完成")
                
            except Exception as inner_e:
                log(f"❌ 主程序执行出错: {type(inner_e).__name__}: {str(inner_e)}")
                import traceback
                log("详细错误堆栈:")
                for line in traceback.format_exc().split('\n'):
                    log(f"  {line}")
                raise  # 重新抛出异常
            finally:
                # 恢复stdout和stderr
                log("恢复stdout/stderr...")
                sys_module.stdout = old_stdout
                sys_module.stderr = old_stderr
            
            # 完成
            log("✓ 分析流程全部完成")
            self.progress_bar['value'] = 100  # 设置为100%
            self.progress_var.set("✅ 分析完成！")
            
            # 查找最新生成的报告文件
            import glob
            import sys as sys_find
            from pathlib import Path as PathLib
            
            # 确定reports文件夹位置（同open_reports_folder逻辑）
            if getattr(sys_find, 'frozen', False):
                exe_dir = PathLib(sys_find.executable).parent
                reports_dir = exe_dir / "reports"
            else:
                reports_dir = PathLib("reports")
            
            # 备用位置
            if not reports_dir.exists():
                reports_dir = PathLib.cwd() / "reports"
            
            if reports_dir.exists():
                # 获取最新的报告文件
                report_files = sorted(
                    reports_dir.glob("matched_products_comparison_final_*.xlsx"),
                    key=lambda x: x.stat().st_mtime,
                    reverse=True
                )
                if report_files:
                    latest_report = report_files[0]
                    report_size = latest_report.stat().st_size / (1024 * 1024)  # MB
                    
                    completion_msg = (
                        f"🎉 比价分析完成！\n\n"
                        f"📊 报告文件：\n"
                        f"   {latest_report.name}\n\n"
                        f"💾 文件大小：{report_size:.2f} MB\n\n"
                        f"📁 保存位置：\n"
                        f"   {latest_report.absolute()}\n\n"
                        f"点击下方'📊 打开报告文件夹'按钮查看报告"
                    )
                    log(f"报告生成成功: {latest_report.name} ({report_size:.2f} MB)")
                    log(f"报告位置: {latest_report.absolute()}")
                else:
                    completion_msg = "比价分析完成！\n报告已保存到 reports/ 文件夹"
                    log("报告生成成功（未找到具体文件）")
            else:
                completion_msg = "比价分析完成！\n报告已保存到 reports/ 文件夹"
                log(f"报告生成成功（reports目录不存在: {reports_dir}）")
            
            log("显示完成对话框...")
            messagebox.showinfo("完成", completion_msg)
            log("用户已确认完成对话框")
            
        except Exception as e:
            # 详细错误信息
            import traceback
            error_detail = traceback.format_exc()
            
            log("=" * 60)
            log(f"❌ GUI捕获到异常: {type(e).__name__}: {str(e)}")
            log("详细错误堆栈:")
            for line in error_detail.split('\n'):
                log(f"  {line}")
            log("=" * 60)
            
            # 记录到错误文件
            error_log_path = Path("logs") / f"gui_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            error_log_path.parent.mkdir(exist_ok=True)
            with open(error_log_path, 'w', encoding='utf-8') as f:
                f.write(f"GUI运行错误 - {datetime.now()}\n")
                f.write("="*60 + "\n")
                f.write(error_detail)
            
            # 重置进度条
            self.progress_bar['value'] = 0
            self.progress_var.set("❌ 分析失败")
            log("设置进度文本为'分析失败'")
            
            # 显示详细错误
            error_msg = f"分析过程出错：\n\n{str(e)}\n\n详细日志已保存到：\n{error_log_path}"
            log(f"准备显示错误对话框: {str(e)[:100]}")
            messagebox.showerror("错误", error_msg)
            log("用户已确认错误对话框")
        
        finally:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            log("=" * 60)
            log(f"GUI分析任务结束 (耗时: {duration:.1f}秒)")
            log("恢复'开始分析'按钮状态...")
            self.start_btn.config(state=tk.NORMAL)
            log(f"详细日志已保存: {log_file}")
            log("=" * 60)
    
    def update_progress_from_stdout(self, text, is_progress=False):
        """从stdout更新进度显示"""
        import re
        
        def update_ui():
            # 确保文本是str类型，处理编码问题
            try:
                if isinstance(text, bytes):
                    clean_text = text.decode('utf-8', errors='ignore')
                else:
                    clean_text = str(text)
            except Exception as e:
                print(f"编码转换错误: {e}")
                return
            
            # 清理ANSI控制字符
            clean_text = re.sub(r'\x1b\[[0-9;]*m', '', clean_text)
            clean_text = clean_text.strip()
            
            if not clean_text:
                return
            
            # 解析tqdm进度条百分比
            # 格式: "硬分类匹配进度:  50%|█████     | 10/20 [00:30<00:30,  1.50s/it]"
            percent_match = re.search(r'(\d+)%', clean_text)
            if percent_match:
                percent = int(percent_match.group(1))
                # 更新进度条
                self.progress_bar['value'] = percent
            elif is_progress and '/' in clean_text:
                # 尝试从 "10/20" 格式计算百分比
                ratio_match = re.search(r'(\d+)/(\d+)', clean_text)
                if ratio_match:
                    current = int(ratio_match.group(1))
                    total = int(ratio_match.group(2))
                    if total > 0:
                        percent = int((current / total) * 100)
                        self.progress_bar['value'] = percent
            
            # 更新顶部状态文本（简短版本）
            short_text = clean_text[:100] if len(clean_text) > 100 else clean_text
            self.progress_var.set(short_text)
            
            # 添加到详细日志框
            self.log_text.config(state=tk.NORMAL)
            
            # 根据内容选择颜色标签
            if '✓' in clean_text or '成功' in clean_text or '完成' in clean_text:
                tag = "success"
            elif '❌' in clean_text or '错误' in clean_text or '失败' in clean_text:
                tag = "error"
            elif '⏸️' in clean_text or 'ℹ️' in clean_text or '检测' in clean_text:
                tag = "warning"
            elif is_progress or '%' in clean_text or 'it/s' in clean_text or '进度' in clean_text:
                tag = "progress"
                # 进度条信息不添加到日志（避免刷屏），只更新状态栏
                self.log_text.config(state=tk.DISABLED)
                return
            else:
                tag = "info"
            
            # 添加时间戳
            from datetime import datetime
            timestamp = datetime.now().strftime('%H:%M:%S')
            log_line = f"[{timestamp}] {clean_text}\n"
            
            # 插入文本
            self.log_text.insert(tk.END, log_line, tag)
            
            # 自动滚动到底部
            self.log_text.see(tk.END)
            
            # 限制日志行数（保留最后1000行）
            line_count = int(self.log_text.index('end-1c').split('.')[0])
            if line_count > 1000:
                self.log_text.delete('1.0', f'{line_count - 1000}.0')
            
            self.log_text.config(state=tk.DISABLED)
        
        # 在主线程更新GUI
        self.window.after(0, update_ui)
    
    def open_reports_folder(self):
        """打开报告文件夹"""
        import sys
        
        # 确定reports文件夹的实际位置
        # 1. 首先检查exe程序所在目录的reports
        if getattr(sys, 'frozen', False):
            # 打包后的环境
            exe_dir = Path(sys.executable).parent
            reports_path = exe_dir / "reports"
        else:
            # 开发环境
            reports_path = Path("reports").absolute()
        
        # 2. 如果不存在，检查当前工作目录
        if not reports_path.exists():
            reports_path = Path.cwd() / "reports"
        
        # 3. 如果还不存在，检查_internal目录
        if not reports_path.exists() and getattr(sys, 'frozen', False):
            reports_path = Path(sys._MEIPASS) / "reports"
        
        # 打开文件夹或显示提示
        if reports_path.exists():
            os.startfile(reports_path)
        else:
            messagebox.showinfo("提示", f"reports文件夹不存在\n\n已检查位置：\n{reports_path}\n\n请确认分析是否成功完成")
    
    def run(self):
        """运行GUI"""
        self.window.mainloop()

if __name__ == "__main__":
    app = ComparisionToolGUI()
    app.run()
