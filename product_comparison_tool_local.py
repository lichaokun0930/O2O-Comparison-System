# -*- coding: utf-8 -*-
r"""
商品比对分析工具 v8.5（本地执行版）
python product_comparison_tool_local.py
.\.venv\Scripts\Activate.ps1
.\cpu_mode.ps1
.\cpu_mode.ps1
# 选择模型 5

# 方法1：直接运行（推荐）
cd "d:\Python1\O2O_Analysis\O2O数据分析\比价数据"
$env:CUDA_VISIBLE_DEVICES=''; $env:USE_TORCH_SIM='0'
& "D:\办公\Python\python.exe" product_comparison_tool_local.py
功能:
    - 自动对比两个店铺（如美团、饿了么）的商品数据。
    - 支持“条码精确匹配”和“商品名称模糊匹配”两种模式。
    - 输出详细的 Excel 报告，包含匹配结果、独有商品等。

使用方法:
    1) 将此脚本与两个 Excel 文件放同一文件夹。
    2) 在下方 Config 中配置店铺名与文件名。
    3) 运行脚本后，结果自动写入 reports/ 目录（带时间戳）。

优化记录:
    - v8.5: 引入规格相似度维度，进一步提升匹配准确率。
    - v8.4: 调整综合评分权重并引入柔性分类相似度。
    - v8.3: 本地执行版，移除 Colab 依赖。
"""

# ==============================================================================
# 1. 自动依赖检查与导入库
# ==============================================================================
import sys
import io

# 🔧 修复打包后 Windows emoji 编码问题（必须在最开头）
if sys.stdout is None or (hasattr(sys.stdout, 'encoding') and sys.stdout.encoding != 'utf-8'):
    if sys.stdout is not None and hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr is not None and hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
import re
import jieba
import os
import logging
import torch
import time
import ssl
import urllib3
from pathlib import Path

# ==============================================================================
# 打包环境检测：必须在导入 SentenceTransformer 之前设置环境变量！
# ==============================================================================
BUNDLED_MODEL_CACHE = None  # 全局变量，存储打包的模型缓存路径

# ============================================================================
# 授权密钥配置（时间密钥算法 - 无需维护JSON文件）
# ============================================================================
import hashlib
from datetime import datetime, timedelta
import platform
import subprocess
import uuid
from typing import Optional, Tuple

# 🔐 主密钥盐值（与生成器保持一致）
MASTER_SALT = "O2O_COMPARISON_TOOL_2025_SECRET_SALT_V1"


def _fingerprint_cache_paths() -> Tuple[str, ...]:
    """返回指纹缓存文件候选路径（按优先级排列）。"""
    paths: list[str] = []

    env_path = os.environ.get('O2O_FINGERPRINT_CACHE')
    if env_path:
        paths.append(env_path)

    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    paths.append(os.path.join(base_dir, '.fingerprint_cache'))

    appdata_dir = os.environ.get('APPDATA') or os.path.expanduser('~')
    if appdata_dir:
        paths.append(os.path.join(appdata_dir, 'O2OComparison', '.fingerprint_cache'))

    unique_paths: list[str] = []
    for candidate in paths:
        if candidate and candidate not in unique_paths:
            unique_paths.append(candidate)
    return tuple(unique_paths)


def _load_cached_fingerprint() -> Tuple[Optional[str], Optional[str]]:
    for cache_path in _fingerprint_cache_paths():
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as fp:
                    cached_fp = fp.read().strip()
                if cached_fp and len(cached_fp) == 16:
                    logging.debug("指纹缓存命中: %s", cache_path)
                    return cached_fp, cache_path
        except Exception as exc:
            logging.debug("读取指纹缓存失败 %s: %s", cache_path, exc)
    return None, None


def _save_fingerprint_cache(fingerprint: str) -> Optional[str]:
    for cache_path in _fingerprint_cache_paths():
        try:
            directory = os.path.dirname(cache_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as fp:
                fp.write(fingerprint)
            logging.debug("指纹缓存写入成功: %s", cache_path)
            return cache_path
        except Exception as exc:
            logging.debug("写入指纹缓存失败 %s: %s", cache_path, exc)
            continue
    return None


def get_machine_fingerprint():
    """
    获取当前机器的硬件指纹（用于绑定密钥）
    
    优化策略：
    1. 优先从缓存读取（.fingerprint_cache）
    2. 使用快速方法（MAC + 机器名 + 用户名）
    3. 缓存结果避免重复计算
    """
    cached_fp, _ = _load_cached_fingerprint()
    if cached_fp:
        return cached_fp
    
    # 2. 生成新指纹（使用快速方法）
    components = []
    
    try:
        # MAC 地址（最稳定，速度快）
        try:
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                           for elements in range(0,2*6,2)][::-1])
            components.append(mac)
        except: pass
        
        # 机器名
        try:
            components.append(platform.node())
        except: pass
        
        # 用户名
        try:
            components.append(os.getlogin())
        except:
            try:
                components.append(os.environ.get('USERNAME', ''))
            except: pass
        
        # Windows系统：仅获取CPU ID（尽量快速，如失败立即跳过）
        if platform.system() == 'Windows':
            try:
                start = time.perf_counter()
                cpu_id_raw = subprocess.check_output(
                    'wmic cpu get ProcessorId',
                    shell=True,
                    timeout=2,
                    creationflags=0x08000000  # CREATE_NO_WINDOW，避免闪窗
                )
                cpu_id = cpu_id_raw.decode(errors='ignore').split('\n')[1].strip()
                if cpu_id:
                    components.append(cpu_id)
                elapsed = time.perf_counter() - start
                if elapsed > 1:  # 记录偶发的慢调用，便于后续排查
                    logging.debug("获取CPU指纹耗时 %.2fs", elapsed)
            except Exception as exc:
                logging.debug("获取CPU指纹失败: %s", exc)
                pass  # 超时或失败则跳过
        
        if not components:
            # 完全失败，使用UUID作为兜底
            components.append(str(uuid.getnode()))
        
        fingerprint_str = '|'.join(components)
        fingerprint = hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]
        
        # 3. 缓存结果（多路径兜底）
        _save_fingerprint_cache(fingerprint)
        
        return fingerprint
    except:
        return None

def verify_license_key_simple(license_key: str) -> tuple[bool, str]:
    """
    验证纯时间密钥（简化版，无硬件绑定）
    
    Args:
        license_key: 用户输入的密钥（12位）
    
    Returns:
        (是否有效, 到期日期字符串/错误信息)
    """
    # 向前检查未来1年内的所有可能日期
    today = datetime.now()
    
    for days_offset in range(0, 366):
        check_date = today + timedelta(days=days_offset)
        expire_str = check_date.strftime("%Y%m%d")
        
        # 简化版：不使用硬件指纹，只用日期
        raw_data = f"{expire_str}-{MASTER_SALT}"
        hash_obj = hashlib.sha256(raw_data.encode('utf-8'))
        expected_key = hash_obj.hexdigest()[:12].upper()
        
        if expected_key == license_key.upper():
            # 找到匹配的密钥，检查是否过期
            expire_date = datetime.strptime(expire_str, "%Y%m%d")
            if today <= expire_date:
                return True, expire_str
            else:
                return False, f"密钥已过期（过期日期：{expire_str}）"
    
    # 向后检查过去30天（允许小幅时钟误差）
    for days_offset in range(-30, 0):
        check_date = today + timedelta(days=days_offset)
        expire_str = check_date.strftime("%Y%m%d")
        
        raw_data = f"{expire_str}-{MASTER_SALT}"
        hash_obj = hashlib.sha256(raw_data.encode('utf-8'))
        expected_key = hash_obj.hexdigest()[:12].upper()
        
        if expected_key == license_key.upper():
            expire_date = datetime.strptime(expire_str, "%Y%m%d")
            if today <= expire_date:
                return True, expire_str
            else:
                return False, f"密钥已过期（过期日期：{expire_str}）"
    
    return False, "密钥无效或格式错误"

# 管理员主密钥（可以跳过硬件验证）
MASTER_KEY = "O2O_ADMIN_2025"

# 程序过期时间（额外的安全措施，防止旧版本流传）
PROGRAM_EXPIRE_DATE = "20260630"  # 2026年6月30日过期（半年后）

def check_program_expiration():
    """
    检查程序是否过期（时间炸弹，防止旧版本流传）
    
    注意：此检查在授权通过后执行，避免影响启动速度
    """
    try:
        expire_date = datetime.strptime(PROGRAM_EXPIRE_DATE, "%Y%m%d")
        if datetime.now() > expire_date:
            error_msg = (
                f"程序版本已过期\n\n"
                f"此版本已于 {expire_date.strftime('%Y年%m月%d日')} 过期。\n"
                f"请联系管理员获取最新版本。\n\n"
                f"说明：为保证功能稳定性，程序每半年更新一次。"
            )
            
            # GUI模式使用messagebox
            if os.environ.get('GUI_MODE') == '1':
                try:
                    import tkinter as tk
                    from tkinter import messagebox
                    root = tk.Tk()
                    root.withdraw()
                    messagebox.showerror("程序已过期", error_msg)
                    root.destroy()
                except:
                    print(error_msg)
                    input("按回车键退出...")
            else:
                print("\n" + "="*60)
                print("  程序版本已过期")
                print("="*60)
                print()
                print(f"  此版本已于 {expire_date.strftime('%Y年%m月%d日')} 过期。")
                print("  请联系管理员获取最新版本。")
                print()
                print("  说明：为保证功能稳定性，程序每半年更新一次。")
                print("="*60)
                print()
                input("按回车键退出...")
            return False
    except Exception as e:
        print(f"⚠️  时间检查异常: {e}")
    
    return True

def check_authorization():
    """
    检查授权密钥（简化版 - 纯时间密钥，无硬件绑定）
    
    优化：
    1. 延迟 tkinter 初始化（仅在真正需要时创建）
    2. 移除硬件指纹依赖，简化流程
    3. 快速失败（过期检查后置）
    """
    # 开发环境不检查授权
    if not getattr(sys, 'frozen', False):
        return True
    
    # GUI模式：使用自定义输入对话框
    if os.environ.get('GUI_MODE') == '1':
        try:
            import tkinter as tk
            from tkinter import messagebox
            
            def ask_key_input(title, prompt):
                """自定义密钥输入对话框"""
                dialog = tk.Tk()
                dialog.title(title)
                dialog.geometry("380x160")
                dialog.resizable(False, False)
                
                # 强制置顶并获取焦点
                dialog.attributes('-topmost', True)
                dialog.lift()
                dialog.focus_force()
                
                # 居中显示
                dialog.update_idletasks()
                x = (dialog.winfo_screenwidth() // 2) - (380 // 2)
                y = (dialog.winfo_screenheight() // 2) - (160 // 2)
                dialog.geometry(f"380x160+{x}+{y}")
                
                # 提示标签
                label = tk.Label(dialog, text=prompt, font=("Arial", 10), justify='left', wraplength=350)
                label.pack(pady=15)
                
                # 输入框
                entry = tk.Entry(dialog, width=35, font=("Arial", 11), show="*")
                entry.pack(pady=5)
                entry.focus_set()
                
                result = {'key': None}
                
                def on_ok():
                    result['key'] = entry.get()
                    dialog.destroy()
                
                def on_cancel():
                    result['key'] = None
                    dialog.destroy()
                
                # 按钮框架
                button_frame = tk.Frame(dialog)
                button_frame.pack(pady=15)
                
                ok_btn = tk.Button(button_frame, text="确定", width=10, command=on_ok)
                ok_btn.pack(side=tk.LEFT, padx=10)
                
                cancel_btn = tk.Button(button_frame, text="取消", width=10, command=on_cancel)
                cancel_btn.pack(side=tk.LEFT, padx=10)
                
                # 回车确认
                entry.bind('<Return>', lambda e: on_ok())
                
                # 强制窗口激活
                dialog.after(100, lambda: dialog.focus_force())
                
                dialog.wait_window()
                return result['key']
            
            def show_message(msg_type, title, message):
                """显示消息框"""
                temp_root = tk.Tk()
                temp_root.withdraw()
                temp_root.attributes('-topmost', True)
                
                if msg_type == 'info':
                    messagebox.showinfo(title, message, parent=temp_root)
                elif msg_type == 'warning':
                    messagebox.showwarning(title, message, parent=temp_root)
                elif msg_type == 'error':
                    messagebox.showerror(title, message, parent=temp_root)
                
                temp_root.destroy()
            
            try:
                # 最多3次输入机会
                for attempt in range(3):
                    prompt = (
                        "O2O 比价工具 - 授权验证\n\n"
                        f"请输入授权密钥 ({attempt + 1}/3):"
                    )
                    user_key = ask_key_input("授权验证", prompt)
                    
                    if user_key is None:  # 用户点击取消
                        show_message('warning', "授权取消", "用户取消授权，程序将退出")
                        return False
                    
                    user_key = user_key.strip()
                    if not user_key:
                        show_message('warning', "输入错误", "密钥不能为空")
                        continue
                    
                    # 检查主密钥
                    if user_key == MASTER_KEY:
                        show_message('info', "授权成功", "主密钥验证通过（永久有效）")
                        
                        # 授权通过后检查程序过期时间
                        if not check_program_expiration():
                            return False
                        
                        return True
                    
                    # 使用简化版时间密钥验证
                    valid, result_msg = verify_license_key_simple(user_key)
                    
                    if valid:
                        # 验证通过
                        expire_date = datetime.strptime(result_msg, "%Y%m%d")
                        days_left = (expire_date - datetime.now()).days
                        success_msg = (
                            f"密钥验证通过\n\n"
                            f"有效期至: {expire_date.strftime('%Y年%m月%d日')}\n"
                            f"剩余天数: {days_left} 天"
                        )
                        show_message('info', "授权成功", success_msg)
                        
                        # 授权通过后检查程序过期时间
                        if not check_program_expiration():
                            return False
                        
                        return True
                    else:
                        # 验证失败
                        remaining = 2 - attempt
                        if remaining > 0:
                            show_message('warning', "密钥验证失败", f"{result_msg}\n\n还有 {remaining} 次机会")
                        else:
                            show_message('error', "密钥验证失败", result_msg)
                
                # 3次全部失败
                fail_msg = (
                    "授权失败\n\n"
                    "密钥验证失败原因可能是：\n"
                    "  1. 密钥输入错误\n"
                    "  2. 密钥已过期\n\n"
                    "请联系管理员获取正确的授权密钥"
                )
                show_message('error', "授权失败", fail_msg)
                return False
            
            except Exception as e:
                # GUI失败回退到命令行模式
                print(f"GUI授权对话框失败: {e}")
                print("回退到命令行模式...")
                # 继续执行下面的命令行逻辑
        
        except Exception as e:
            # 导入tkinter失败，回退到命令行模式
            print(f"GUI模块加载失败: {e}")
            print("回退到命令行模式...")
    
    # 命令行模式：使用print和input
    print("\n" + "="*60)
    print("  🔐 O2O 比价工具 - 授权验证")
    print("="*60)
    print()

    # 最多允许3次输入机会
    for attempt in range(3):
        try:
            user_key = input("请输入授权密钥: ").strip()
        except:
            # GUI模式下input()可能失败
            print("❌ 无法获取输入，请在命令行模式下运行")
            return False
        
        if not user_key:
            print("❌ 密钥不能为空\n")
            continue
        
        # 检查主密钥（永久有效）
        if user_key == MASTER_KEY:
            print("\n主密钥验证通过（永久有效）")
            print("="*60)
            
            # 授权通过后检查程序过期时间
            if not check_program_expiration():
                return False
            
            return True
        
        # 使用简化版时间密钥验证
        valid, result_msg = verify_license_key_simple(user_key)
        
        if valid:
            # 验证通过
            expire_date = datetime.strptime(result_msg, "%Y%m%d")
            days_left = (expire_date - datetime.now()).days
            print(f"\n✅ 密钥验证通过")
            print(f"   📅 有效期至: {expire_date.strftime('%Y年%m月%d日')}")
            print(f"   ⏰ 剩余天数: {days_left} 天")
            print("="*60)
            
            # 授权通过后检查程序过期时间
            if not check_program_expiration():
                return False
            
            return True
        else:
            # 验证失败
            remaining = 2 - attempt
            if remaining > 0:
                print(f"❌ 密钥验证失败: {result_msg}")
                print(f"   还有 {remaining} 次机会\n")
            else:
                print(f"❌ 密钥验证失败: {result_msg}\n")
    
    # 3次输入失败
    print("="*60)
    print("  ❌ 授权失败")
    print("="*60)
    print()
    print("  密钥验证失败原因可能是：")
    print("    1. 密钥输入错误")
    print("    2. 密钥已过期")
    print()
    print("  请联系管理员获取有效的授权密钥。")
    print()
    print("="*60)
    print()
    input("按回车键退出...")
    return False

if getattr(sys, 'frozen', False):
    # 打包后的环境
    bundle_dir = Path(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)))
    bundled_model_cache = bundle_dir / '.cache' / 'huggingface'  # 🔧 修复：正确的缓存路径
    
    print(f"[INFO] Detected packaged environment")
    print(f"   _MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
    print(f"   bundle_dir: {bundle_dir}")
    print(f"   bundled_model_cache: {bundled_model_cache}")
    print(f"   exists: {bundled_model_cache.exists()}")
    
    if bundled_model_cache.exists():
        # 优先使用打包的模型
        hub_path = bundled_model_cache / 'hub'
        os.environ['HF_HOME'] = str(bundled_model_cache)
        os.environ['TRANSFORMERS_CACHE'] = str(hub_path)
        os.environ['SENTENCE_TRANSFORMERS_HOME'] = str(bundled_model_cache)
        BUNDLED_MODEL_CACHE = bundled_model_cache  # 保存到全局变量
        
        print(f"[OK] Using bundled model cache: {bundled_model_cache}")
        print(f"   HF_HOME: {os.environ.get('HF_HOME')}")
        print(f"   TRANSFORMERS_CACHE: {os.environ.get('TRANSFORMERS_CACHE')}")
        print(f"   SENTENCE_TRANSFORMERS_HOME: {os.environ.get('SENTENCE_TRANSFORMERS_HOME')}")
        print(f"[OFFLINE] No internet required for model loading")
        
        # 列出找到的模型
        if hub_path.exists():
            models = list(hub_path.glob("models--*"))
            print(f"   Found {len(models)} models:")
            for model in models:
                print(f"     - {model.name}")
    else:
        print(f"[WARN] Bundled model cache not found")
        print(f"   Checked path: {bundled_model_cache}")
else:
    # 开发环境，使用默认路径
    print(f"[DEV] Development mode (not packaged)")

# 现在才导入 SentenceTransformer，此时环境变量已设置
from sentence_transformers import SentenceTransformer
try:
    from sentence_transformers import CrossEncoder
except ImportError:
    CrossEncoder = None
from typing import Iterable, Optional, Tuple, List
# 使用本地实现的余弦相似度以避免依赖 scikit-learn（在 Py3.13 上可能缺少预编译轮子）
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """计算两组向量的余弦相似度矩阵。
    a: (N, D), b: (M, D) -> 返回 (N, M)
    支持可选 GPU 加速：设置环境变量 USE_TORCH_SIM=1 且 CUDA 可用时启用。
    """
    if a.size == 0 or b.size == 0:
        return np.zeros((a.shape[0], b.shape[0]))

    try:
        use_torch_sim = os.environ.get('USE_TORCH_SIM', '0') == '1' and torch.cuda.is_available()
    except Exception:
        use_torch_sim = False

    if use_torch_sim:
        try:
            with torch.no_grad():
                ta = torch.from_numpy(a).to('cuda', dtype=torch.float32)
                tb = torch.from_numpy(b).to('cuda', dtype=torch.float32)
                ta = torch.nn.functional.normalize(ta, p=2, dim=1)
                tb = torch.nn.functional.normalize(tb, p=2, dim=1)
                sim = ta @ tb.T
                return sim.cpu().numpy()
        except Exception as cuda_error:
            # CUDA错误处理：打印警告并回退到CPU
            print(f"⚠️ CUDA计算失败，自动切换到CPU模式: {cuda_error}")
            # 清理CUDA缓存
            try:
                torch.cuda.empty_cache()
            except:
                pass
            # 强制禁用后续GPU使用
            os.environ['USE_TORCH_SIM'] = '0'

    a_norm = np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = np.linalg.norm(b, axis=1, keepdims=True)
    # 避免除零
    a_safe = a / (a_norm + 1e-12)
    b_safe = b / (b_norm + 1e-12)
    return a_safe @ b_safe.T
import warnings
import sys
import importlib
from tqdm.auto import tqdm
from tqdm.auto import tqdm as tqdm_auto
import unicodedata
import difflib
from decimal import Decimal
import hashlib
import joblib
from pathlib import Path
def _sanitize_sheet_name(name: str, existing: Optional[set] = None) -> str:
    r"""将工作表名清洗为 Excel 可接受的名称：
    - 替换非法字符 : \ / ? * [ ] 为下划线
    - 去首尾空白
    - 截断至 31 个字符
    - 保证唯一：如已存在，则追加 _1/_2 等后缀
    """
    s = str(name or '').strip()
    s = re.sub(r'[:\\/\?\*\[\]]', '_', s)
    max_len = 31
    s = s[:max_len]
    if existing is not None:
        base = s
        i = 1
        while s in existing or not s:
            suffix = f"_{i}"
            s = (base[:max_len - len(suffix)] + suffix) if len(base) + len(suffix) > max_len else base + suffix
            i += 1
        existing.add(s)
    return s

# 解决SSL证书问题和网络连接问题
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置更好的网络重试机制
def setup_requests_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

REQUIRED_PACKAGES = [
    'pandas', 'numpy', 'jieba', 'torch', 'sentence_transformers', 'openpyxl', 'tqdm'
]

print("检查依赖库...")
for pkg in REQUIRED_PACKAGES:
    try:
        if pkg == 'sklearn':
            importlib.import_module('sklearn.metrics')
        else:
            importlib.import_module(pkg)
        print(f"[OK] {pkg} - 已安装")
    except ImportError:
        print(f"[ERROR] 缺少依赖库：{pkg}，请在终端运行：pip install {pkg}")
        sys.exit(1)
import joblib
import hashlib

warnings.filterwarnings('ignore')

# 配置日志：强制使用 UTF-8 编码避免 Emoji 错误
import sys
import io

# 强制标准输出使用 UTF-8 编码
# GUI模式下sys.stdout/stderr可能是None，需要先检查
if sys.stdout is not None and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr is not None and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
elif sys.stdout is not None and hasattr(sys.stdout, 'buffer'):
    # Python 3.6 及以下版本的兼容方案（仅当stdout有效时）
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 配置 logging 使用 UTF-8
class UTF8StreamHandler(logging.StreamHandler):
    """强制使用 UTF-8 编码的日志处理器"""
    def __init__(self, stream=None):
        # 确保 stream 使用 UTF-8
        if stream is None:
            stream = sys.stderr
        super().__init__(stream)
        self.setFormatter(logging.Formatter('%(message)s'))
    
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            # 强制写入时使用 UTF-8
            stream.write(msg + self.terminator)
            stream.flush()
        except (UnicodeEncodeError, UnicodeDecodeError):
            # 如果还是编码失败，移除 emoji
            try:
                msg_clean = msg.encode('ascii', errors='ignore').decode('ascii')
                stream.write(msg_clean + self.terminator)
                stream.flush()
            except:
                pass  # 完全失败则忽略

# 配置根 logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
# 移除所有现有的 handler
for handler in logger.handlers[:]:
    logger.removeHandler(handler)
# 添加 UTF-8 handler
logger.addHandler(UTF8StreamHandler())

# Enable progress bars for pandas operations like .apply()
tqdm_auto.pandas()

# 兜底模式（仅当明确允许时才启用），默认禁止以保证精度
SIMPLE_FALLBACK = os.environ.get('ALLOW_SIMPLE_FALLBACK', '0') == '1'

# ==============================================================================
# 2. 缓存管理器（性能优化核心组件）
# ==============================================================================
class CacheManager:
    """统一的缓存管理器，支持向量、相似度矩阵和 Cross-Encoder 结果缓存"""
    
    def __init__(self, cache_dir: str = '.'):
        # 确定缓存目录：打包环境优先使用 prebuilt_cache
        if getattr(sys, 'frozen', False):
            # 打包环境：尝试从 _MEIPASS 加载预构建缓存
            base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            prebuilt_cache = Path(base_path) / 'prebuilt_cache'
            
            if prebuilt_cache.exists():
                self.cache_dir = prebuilt_cache
                logging.info(f"🎯 使用预构建缓存: {self.cache_dir}")
            else:
                # 如果没有预构建缓存，使用程序目录（可写）
                self.cache_dir = Path(os.path.dirname(sys.executable))
                logging.info(f"📂 使用程序目录缓存: {self.cache_dir}")
        else:
            # 开发环境：使用指定目录
            self.cache_dir = Path(cache_dir)
        
        self.cache_dir.mkdir(exist_ok=True)
        
        # 三种独立缓存
        self.embedding_cache_file = self.cache_dir / 'embedding_cache.joblib'
        self.similarity_cache_file = self.cache_dir / 'similarity_matrix_cache.joblib'
        self.cross_encoder_cache_file = self.cache_dir / 'cross_encoder_cache.joblib'
        
        # 加载现有缓存
        self.embedding_cache = self._load_cache(self.embedding_cache_file)
        self.similarity_cache = self._load_cache(self.similarity_cache_file)
        self.cross_encoder_cache = self._load_cache(self.cross_encoder_cache_file)
        
        # 缓存统计
        self.stats = {
            'embedding_hits': 0,
            'embedding_misses': 0,
            'similarity_hits': 0,
            'similarity_misses': 0,
            'cross_encoder_hits': 0,
            'cross_encoder_misses': 0,
        }
    
    def _load_cache(self, cache_file: Path) -> dict:
        """加载缓存文件"""
        if cache_file.exists():
            try:
                cache = joblib.load(cache_file)
                logging.info(f"✅ 加载缓存: {cache_file.name} ({len(cache)} 条记录)")
                return cache
            except Exception as e:
                logging.warning(f"⚠️ 缓存加载失败 {cache_file.name}: {e}，将重建缓存")
                return {}
        return {}
    
    def _save_cache(self, cache: dict, cache_file: Path):
        """保存缓存文件（增量叠加模式）"""
        try:
            # 🆕 增量叠加逻辑：如果文件已存在，先加载旧缓存，然后合并
            if cache_file.exists():
                try:
                    old_cache = joblib.load(cache_file)
                    old_count = len(old_cache)
                    
                    # 合并缓存：新缓存会覆盖旧缓存中的同名键
                    old_cache.update(cache)
                    
                    new_count = len(old_cache)
                    added_count = new_count - old_count
                    
                    # 保存合并后的缓存
                    joblib.dump(old_cache, cache_file, compress=3)
                    
                    if added_count > 0:
                        logging.info(f"💾 缓存叠加保存: {cache_file.name} (新增 {added_count} 条，总计 {new_count} 条)")
                    else:
                        logging.info(f"💾 缓存更新: {cache_file.name} (无新增，总计 {new_count} 条)")
                    
                except Exception as e:
                    logging.warning(f"⚠️ 旧缓存加载失败，将直接保存新缓存: {e}")
                    joblib.dump(cache, cache_file, compress=3)
                    logging.info(f"💾 保存缓存: {cache_file.name} ({len(cache)} 条记录)")
            else:
                # 文件不存在，直接保存
                joblib.dump(cache, cache_file, compress=3)
                logging.info(f"💾 保存缓存: {cache_file.name} ({len(cache)} 条记录)")
                
        except Exception as e:
            logging.error(f"❌ 缓存保存失败 {cache_file.name}: {e}")
    
    def get_embedding_cache_key(self, model_identifier: str, text: str) -> str:
        """生成向量缓存键"""
        cache_text = f"{model_identifier}||{text}"
        return hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
    
    def get_similarity_cache_key(self, model_identifier: str, ids_a: List, ids_b: List) -> str:
        """生成相似度矩阵缓存键"""
        # 使用排序后的商品ID列表生成唯一键
        ids_a_str = ','.join(map(str, sorted(ids_a)))
        ids_b_str = ','.join(map(str, sorted(ids_b)))
        cache_text = f"{model_identifier}||{ids_a_str}||{ids_b_str}"
        return hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
    
    def get_cross_encoder_cache_key(self, model_identifier: str, text_a: str, text_b: str) -> str:
        """生成 Cross-Encoder 缓存键（文本对）"""
        # 标准化顺序：按字典序排列，确保 (A,B) 和 (B,A) 使用同一缓存
        if text_a > text_b:
            text_a, text_b = text_b, text_a
        cache_text = f"{model_identifier}||{text_a}||{text_b}"
        return hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
    
    def get_embedding(self, model_identifier: str, text: str) -> Optional[np.ndarray]:
        """获取向量缓存"""
        key = self.get_embedding_cache_key(model_identifier, text)
        if key in self.embedding_cache:
            self.stats['embedding_hits'] += 1
            return self.embedding_cache[key]
        self.stats['embedding_misses'] += 1
        return None
    
    def set_embedding(self, model_identifier: str, text: str, vector: np.ndarray):
        """设置向量缓存"""
        key = self.get_embedding_cache_key(model_identifier, text)
        self.embedding_cache[key] = np.array(vector).flatten()
    
    def get_similarity_matrix(self, model_identifier: str, ids_a: List, ids_b: List) -> Optional[np.ndarray]:
        """获取相似度矩阵缓存"""
        key = self.get_similarity_cache_key(model_identifier, ids_a, ids_b)
        if key in self.similarity_cache:
            self.stats['similarity_hits'] += 1
            return self.similarity_cache[key]
        self.stats['similarity_misses'] += 1
        return None
    
    def set_similarity_matrix(self, model_identifier: str, ids_a: List, ids_b: List, matrix: np.ndarray):
        """设置相似度矩阵缓存"""
        key = self.get_similarity_cache_key(model_identifier, ids_a, ids_b)
        self.similarity_cache[key] = matrix
    
    def get_cross_encoder_score(self, model_identifier: str, text_a: str, text_b: str) -> Optional[float]:
        """获取 Cross-Encoder 分数缓存"""
        key = self.get_cross_encoder_cache_key(model_identifier, text_a, text_b)
        if key in self.cross_encoder_cache:
            self.stats['cross_encoder_hits'] += 1
            return self.cross_encoder_cache[key]
        self.stats['cross_encoder_misses'] += 1
        return None
    
    def set_cross_encoder_score(self, model_identifier: str, text_a: str, text_b: str, score: float):
        """设置 Cross-Encoder 分数缓存"""
        key = self.get_cross_encoder_cache_key(model_identifier, text_a, text_b)
        self.cross_encoder_cache[key] = float(score)
    
    def save_all(self):
        """保存所有缓存"""
        self._save_cache(self.embedding_cache, self.embedding_cache_file)
        self._save_cache(self.similarity_cache, self.similarity_cache_file)
        self._save_cache(self.cross_encoder_cache, self.cross_encoder_cache_file)
    
    def print_stats(self):
        """打印缓存统计信息"""
        total_embedding = self.stats['embedding_hits'] + self.stats['embedding_misses']
        total_similarity = self.stats['similarity_hits'] + self.stats['similarity_misses']
        total_cross = self.stats['cross_encoder_hits'] + self.stats['cross_encoder_misses']
        
        print("\n" + "="*60)
        print("📊 缓存性能统计")
        print("="*60)
        
        if total_embedding > 0:
            hit_rate = self.stats['embedding_hits'] / total_embedding * 100
            print(f"向量缓存: {self.stats['embedding_hits']}/{total_embedding} 命中 ({hit_rate:.1f}%)")
        
        if total_similarity > 0:
            hit_rate = self.stats['similarity_hits'] / total_similarity * 100
            print(f"相似度矩阵缓存: {self.stats['similarity_hits']}/{total_similarity} 命中 ({hit_rate:.1f}%)")
        
        if total_cross > 0:
            hit_rate = self.stats['cross_encoder_hits'] / total_cross * 100
            saved_time = self.stats['cross_encoder_hits'] * 0.01  # 假设每次节省 10ms
            print(f"Cross-Encoder 缓存: {self.stats['cross_encoder_hits']}/{total_cross} 命中 ({hit_rate:.1f}%)")
            print(f"预估节省时间: {saved_time:.1f} 秒")
        
        print("="*60 + "\n")

# 全局缓存管理器实例
cache_manager = CacheManager()

# ==============================================================================
# 3. 日志与全局配置 (需要修改的参数都在这里)
# ==============================================================================
class Config:
    # --- 店铺名称配置 (建议使用上传目录模式，无需手动修改) ---
    # 💡 推荐：使用上传目录模式（upload/本店、upload/竞对），自动识别店铺名
    # ⚠️ 仅在禁用上传目录模式时，才需要手动修改这里的店铺名和文件名
    
    # >>> 备用配置：手动指定店铺名称和文件名 <<<
    STORE_A_NAME = '本店'  # 上传目录模式启用时，此值会被自动覆盖
    STORE_B_NAME = '竞对'  # 上传目录模式启用时，此值会被自动覆盖
    # <<< 店铺名称配置区域结束 >>>
    
    # 备用文件名（仅在上传目录中无文件时使用）
    STORE_A_FILENAME = '本店数据.xlsx'
    STORE_B_FILENAME = '竞对数据.xlsx'
    
    # 上传入口配置 - 通过不同目录区分本店和竞对（🌟推荐模式）
    UPLOAD_DIR_STORE_A = 'upload/store_a'   # 本店数据上传目录
    UPLOAD_DIR_STORE_B = 'upload/store_b'   # 竞对数据上传目录
    USE_UPLOAD_DIRS = True                  # 启用上传目录模式（推荐保持为True）
    # ⚠️ 若设为 False，将使用上面的 STORE_A_FILENAME 和 STORE_B_FILENAME
    OUTPUT_FILE = 'matched_products_comparison_final.xlsx'
    
    # 模型选项配置 - 支持多个预定义模型
    # 📌 两阶段匹配策略：
    #   1. Sentence-BERT (句向量) - 快速粗筛，将商品转为向量后计算余弦相似度
    #   2. Cross-Encoder (交叉编码器) - 精准精排，直接判断两个商品是否匹配
    AVAILABLE_MODELS = {
        '1': {
            'name': 'paraphrase-multilingual-mpnet-base-v2',
            'display_name': '标准多语言模型 (原模型)',
            'description': '通用多语言模型，成熟稳定',
            'size': '~420MB',
            'speed': '正常',
            'accuracy': '良好',
            'recommended_threshold': {'hard': 0.42, 'soft': 0.38},  # 🔧 根据18:57正常数据反推的阈值
        },
        '2': {
            'name': 'BAAI/bge-base-zh-v1.5',
            'display_name': 'BGE中文优化模型',
            'description': '专为中文优化，准确率提升15-20%',
            'size': '~560MB',
            'speed': '正常',
            'accuracy': '优秀',
            'recommended_threshold': {'hard': 0.42, 'soft': 0.38},  # 🔧 与模型1保持一致
        },
        '3': {
            'name': 'moka-ai/m3e-base',
            'display_name': 'M3E电商场景模型',
            'description': '针对电商场景优化',
            'size': '~400MB',
            'speed': '较快',
            'accuracy': '优秀',
            'recommended_threshold': {'hard': 0.42, 'soft': 0.38},  # 🔧 与模型1保持一致
        },
        '4': {
            'name': 'BAAI/bge-large-zh-v1.5',
            'display_name': 'BGE-Large 旗舰模型 ⭐',
            'description': 'BGE系列最强版本，1024维向量，准确率最高',
            'size': '~1.3GB',
            'speed': '较慢',
            'accuracy': '顶级',
            'recommended_threshold': {'hard': 0.42, 'soft': 0.38},  # 🔧 降低阈值，增加召回率
        },
        '5': {
            'name': 'BAAI/bge-m3',
            'display_name': 'BGE-M3 多粒度模型',
            'description': '支持混合检索，多语言多粒度，最新一代模型',
            'size': '~2.2GB',
            'speed': '较慢',
            'accuracy': '顶级',
            'recommended_threshold': {'hard': 0.42, 'soft': 0.38},  # 🔧 回归18:57历史数据阈值，配合三级分类检查关闭
        },
        '6': {
            'name': 'BAAI/bge-small-zh-v1.5',
            'display_name': 'BGE-Small 轻量模型',
            'description': '速度快，适合大批量数据，准确率略低',
            'size': '~100MB',
            'speed': '快速',
            'accuracy': '良好+',
            'recommended_threshold': {'hard': 0.52, 'soft': 0.50},  # 轻量模型略宽松
        },
        # 🚀 高级模型选项
        '7': {
            'name': 'intfloat/multilingual-e5-large',
            'display_name': 'E5-Large 多语言旗舰 🌍',
            'description': '多语言场景最强，支持100+语言，1024维向量',
            'size': '~2.2GB',
            'speed': '慢',
            'accuracy': '顶级+',
            'recommended_threshold': {'hard': 0.42, 'soft': 0.38},  # 🔧 降低阈值，增加召回率
        },
        '8': {
            'name': 'GanymedeNil/text2vec-large-chinese',
            'display_name': 'Text2Vec-Large 中文强化 🇨🇳',
            'description': '中文语义理解最强，1024维，电商场景优化',
            'size': '~1.3GB',
            'speed': '较慢',
            'accuracy': '顶级',
            'recommended_threshold': {'hard': 0.42, 'soft': 0.38},  # 🔧 降低阈值，增加召回率
        },
        '9': {
            'name': 'BAAI/bge-large-zh-v1.5',  # 备选：推荐使用选项4
            'display_name': 'BGE-Large-ZH v1.5 (推荐) ⭐⭐',
            'description': '中文商品匹配黄金标准，准确率极高',
            'size': '~1.3GB',
            'speed': '较慢',
            'accuracy': '顶级',
            'recommended_threshold': {'hard': 0.42, 'soft': 0.38},  # 🔧 降低阈值，增加召回率
        },
    }
    
    # --- Cross-Encoder 可用模型配置 ---
    AVAILABLE_CROSS_ENCODERS = {
        '1': {
            'name': 'cross-encoder/ms-marco-MiniLM-L-6-v2',
            'display_name': 'MS-Marco-MiniLM (默认)',
            'description': '微软开源轻量级模型，速度快但中文效果一般',
            'size': '~90MB',
            'speed': '极快',
            'accuracy': '中等',
            'language': '英文优先'
        },
        '2': {
            'name': 'BAAI/bge-reranker-large',
            'display_name': 'BGE-Reranker-Large ⭐推荐',
            'description': '中文优化大模型，准确率提升40%，电商场景强力推荐',
            'size': '~1.3GB',
            'speed': '中',
            'accuracy': '极高',
            'language': '中英双语'
        },
        '3': {
            'name': 'BAAI/bge-reranker-base',
            'display_name': 'BGE-Reranker-Base ⚡平衡',
            'description': '速度与准确率平衡，比Large快15%，准确率提升25%',
            'size': '~309MB',
            'speed': '快',
            'accuracy': '高',
            'language': '中英双语'
        },
        '4': {
            'name': 'cross-encoder/ms-marco-MiniLM-L-12-v2',
            'display_name': 'MS-Marco-MiniLM-L12',
            'description': 'MS-Marco深层版本，准确率略高于L-6但速度较慢',
            'size': '~130MB',
            'speed': '快',
            'accuracy': '中高',
            'language': '英文优先'
        },
    }
    
    # 默认模型：打包版本使用 bge-large-zh-v1.5 (模型4)
    # 开发环境可手动选择其他模型
    # 🆕 支持通过环境变量覆盖（GUI模式传递）
    SENTENCE_BERT_MODEL = os.environ.get('EMBEDDING_MODEL', 'BAAI/bge-base-zh-v1.5')  # 默认平衡模式
    ENABLE_MODEL_SELECTION = True  # 启用运行时模型选择
    EMBEDDING_CACHE_FILE = 'embedding_cache.joblib'
    # 导出目录（相对于脚本所在目录）。默认统一写入 reports/ 便于管理
    OUTPUT_DIR = 'reports'

    # 向量编码批大小（根据GPU显存自动调整）
    # 显存 ≥8GB: 256 (最快)
    # 显存 4-8GB: 64 (保守，防止RTX 2060 6GB显存溢出)
    # 显存 <4GB: 32 (非常保守)
    # CPU模式: 32 (避免内存溢出)
    ENCODE_BATCH_SIZE = int(os.environ.get('ENCODE_BATCH_SIZE', '64'))  # 降低默认值从128→64

    # 可选：强制计算设备（'cuda' 或 'cpu'），为 None 时自动检测
    FORCE_DEVICE: Optional[str] = None

    # 是否导出清洗后的数据相关 Sheet（店A清洗、店B清洗、合并清洗对比）
    EXPORT_CLEANED_SHEETS = False

    # --- 成本预测功能配置 (🆕 第一阶段) ---
    ENABLE_COST_PREDICTION = True  # 总开关：启用成本预测功能
    COST_PREDICTION_STRATEGY = 'markup_rate'  # 预测策略：'markup_rate'=加价率法
    EXPORT_COST_SHEETS = True  # 导出成本分析相关 Sheet
    COST_COLUMN_NAME = '成本'  # 成本列名称（本店数据中的列名）
    
    # 成本预测参数
    COST_PREDICTION_MIN_SAMPLES = 3  # 品类最少样本量（少于此值降级到上级分类）
    COST_CONFIDENCE_THRESHOLD = 0.5  # 最低置信度阈值
    
    # 🆕 售价加权预测配置
    USE_SALE_PRICE_WEIGHT = True  # 是否使用售价进行加权预测
    ORIGINAL_PRICE_WEIGHT = 0.7  # 原价权重（定价策略，稳定性高）
    SALE_PRICE_WEIGHT = 0.3  # 售价权重（实际利润，反映促销）
    
    # 🛡️ 极端折扣保护机制（防止引流品污染成本预测）
    MIN_DISCOUNT_RATE = 0.50  # 最低折扣率50%（售价低于原价50%时视为异常促销，不使用售价预测）
    MAX_DISCOUNT_RATE = 1.05  # 最高折扣率105%（售价超过原价5%时可能是数据错误）
    SALE_PRICE_WEIGHT_DECAY_THRESHOLD = 0.70  # 折扣率低于70%时，售价权重衰减
    
    # 🎯 非匹配商品置信度惩罚（品类泛化风险）
    NON_MATCHED_CONFIDENCE_PENALTY = 0.15  # 非匹配商品置信度降低15%（无同款验证）
    
    # --- Cross-Encoder (精排模型) 配置 ---
    # Cross-Encoder 用于精确判断两个商品是否匹配，准确率远高于Sentence-BERT
    # 💡 升级建议：
    #   - 当前: ms-marco-MiniLM-L-6-v2 (英文训练，中文效果一般)
    #   - 推荐: BAAI/bge-reranker-large (中文优化，准确率提升40%)
    #   - 电商: BAAI/bge-reranker-base (速度与准确率平衡)
    USE_LOCAL_CROSS_ENCODER = False
    # ONLINE_CROSS_ENCODER = 'cross-encoder/ms-marco-MiniLM-L-6-v2'  # 英文模型（不推荐中文场景）
    # 🆕 支持通过环境变量覆盖（GUI模式传递）
    ONLINE_CROSS_ENCODER = os.environ.get('RERANKER_MODEL', 'BAAI/bge-reranker-base')  # 默认平衡模式
    # ONLINE_CROSS_ENCODER = 'BAAI/bge-reranker-base'   # ⚡ 平衡选项：速度快15%
    LOCAL_CROSS_ENCODER_PATH = 'D:/AI_Models/cross-encoder-model' # ‼️替换为你的模型文件夹实际路径

    # 离线首选：本地 Sentence-BERT 模型目录（包含 config.json、pytorch_model.bin/safetensors 等）
    USE_LOCAL_SENTENCE_BERT = False
    LOCAL_SENTENCE_BERT_PATH = 'D:/AI_Models/sentence-transformers/paraphrase-multilingual-mpnet-base-v2'

    # FUZZY_MATCH_PARAMS 已被移动到具体的匹配函数内部，以实现更精细的控制
    # FUZZY_MATCH_PARAMS = {
    #     "price_similarity_percent": 20,
    #     "composite_threshold": 0.2, # 🔄 Colab tuned: 0.2
    #     "strict_threshold_for_generic_cat": 0.30, # 进一步提高对“弱匹配”的审查标准
    #     "text_weight": 0.5, # 🔄 调整文本权重，为分类权重让出空间
    #     "brand_weight": 0.3, # 🔄 品牌权重30%
    #     "category_weight": 0.1, #  启用分类权重10%，提升分类匹配率
    #     "specs_weight": 0.1,
    #     "candidates_to_check": 1000, # 🔄 增大到1000，Colab中检查所有潜在匹配项
    #     "require_category_match": False, # 🔄 测试：关闭分类过滤，使用全量匹配模式
    # }

# ==============================================================================
# 3. 核心辅助函数
# ==============================================================================
# 常见品牌列表（基于数据分析扩展）
COMMON_BRANDS = [
    '君乐宝', '味全', '新希望', '公牛', '海氏海诺', '瀚思', '康益博士', '惠选', '阿尔卑斯',
    '美的', 'SKG', '麦德氏', '元气森林', 'BGM', '九阳', '小赤兔', '来乐', '古风',
    'lucky熊', '鸿尘', '冠银', '泓萱'
]
COMMON_BRANDS = [brand.lower() for brand in COMMON_BRANDS]  # 转为小写便于匹配

def clean_text(text):
    if isinstance(text, str):
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', '', text)
        return text.lower().strip()
    return ""

def extract_brand(name, vendor_category):
    if isinstance(name, str):
        name_lower = name.lower()
        match = re.search(r'[【\[（(](.*?)[】\])）]', name_lower)
        if match:
            return match.group(1).strip()
    if isinstance(vendor_category, str):
        parts = [p.strip() for p in vendor_category.split('>') if p.strip()]
        if len(parts) > 0:
            return parts[0]
    return "其他"

def extract_brand_enhanced(text):
    """提取品牌信息 - 使用扩展的品牌列表和正则匹配（Colab版本整合）"""
    if pd.isna(text) or not text:
        return ""
    
    text_lower = text.lower()
    
    # 首先检查已知品牌列表
    for brand in COMMON_BRANDS:
        if brand in text_lower:
            return brand
    
    # 英文品牌模式 (2-20字符，可含数字)
    english_pattern = r'\b([A-Za-z][A-Za-z0-9]{1,19})\b'
    # 中文品牌模式 (2-8字符)
    chinese_pattern = r'[\u4e00-\u9fff]{2,8}'
    
    matches = re.findall(english_pattern, text) + re.findall(chinese_pattern, text)
    
    if matches:
        # 返回最长的匹配项（通常是品牌名）
        return max(matches, key=len)
    
    return ""

def extract_specifications(text):
    """提取产品规格信息（Colab版本新增功能）"""
    if pd.isna(text) or not text:
        return {}
    
    text = str(text)
    specs = {}
    
    # 容量/重量规格
    volume_pattern = r'(\d+(?:\.\d+)?)\s*([mlkgL克升毫升公斤斤])'
    volume_matches = re.findall(volume_pattern, text)
    for value, unit in volume_matches:
        specs[f'容量({unit})'] = float(value)
    
    # 尺寸规格
    size_pattern = r'(\d+(?:\.\d+)?)\s*[xX*×]\s*(\d+(?:\.\d+)?)\s*[xX*×]?\s*(\d+(?:\.\d+)?)?'
    size_matches = re.findall(size_pattern, text)
    if size_matches:
        dims = size_matches[0]
        if dims[2]:  # 三维
            specs['尺寸'] = f"{dims[0]}×{dims[1]}×{dims[2]}"
        else:  # 二维
            specs['尺寸'] = f"{dims[0]}×{dims[1]}"
    
    # 功率规格
    power_pattern = r'(\d+(?:\.\d+)?)\s*(w|W|瓦|功率)'
    power_matches = re.findall(power_pattern, text)
    if power_matches:
        specs['功率(W)'] = float(power_matches[0][0])
    
    return specs

def categorize_price_band(price):
    """价格分层（Colab版本新增功能）"""
    if pd.isna(price) or price == 0:
        return "未知"
    
    if price <= 20:
        return "低价位(≤20)"
    elif price <= 50:
        return "中低价位(20-50)"
    elif price <= 100:
        return "中价位(50-100)"
    elif price <= 200:
        return "中高价位(100-200)"
    else:
        return "高价位(>200)"

def calculate_feature_similarity(features1, features2):
    """计算特征相似度（基于规格参数）（Colab版本新增功能）"""
    if not features1 or not features2:
        return 0.0
    
    # 找到共同的规格键
    common_keys = set(features1.keys()) & set(features2.keys())
    if not common_keys:
        return 0.0
    
    similarity_scores = []
    for key in common_keys:
        val1, val2 = features1[key], features2[key]
        if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
            # 数值型：计算相对差异
            max_val = max(val1, val2)
            if max_val > 0:
                similarity = 1 - abs(val1 - val2) / max_val
                similarity_scores.append(similarity)
        elif str(val1).lower() == str(val2).lower():
            # 字符型：完全匹配
            similarity_scores.append(1.0)
    
    return sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0.0

def calculate_discount(row, sale_price_col, original_price_col):
    """计算折扣（Colab版本新增功能）"""
    try:
        sale_price = pd.to_numeric(row.get(sale_price_col, 0), errors='coerce')
        original_price = pd.to_numeric(row.get(original_price_col, 0), errors='coerce')
        
        if pd.isna(sale_price) or pd.isna(original_price) or original_price == 0:
            return None
            
        discount = (original_price - sale_price) / original_price * 100
        return round(discount, 2)
    except:
        return None

def tokenize_text(text):
    """文本分词（Colab版本新增功能）"""
    if pd.isna(text) or not text:
        return []
    
    text = str(text).lower()
    # 简单分词：按空格和常见分隔符分割
    import re
    tokens = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', text)
    return [token for token in tokens if len(token) > 1]

def standardize_brand(brand):
    """品牌标准化（Colab版本新增功能）"""
    if pd.isna(brand) or not brand:
        return ""
    
    brand = str(brand).lower().strip()
    # 移除常见的品牌后缀
    suffixes_to_remove = ['牌', '品牌', '公司', 'co', 'ltd', 'inc']
    for suffix in suffixes_to_remove:
        if brand.endswith(suffix):
            brand = brand[:-len(suffix)].strip()
    
    return brand

def get_average_word_vector(tokens, word2vec_model, vector_size):
    """获取词向量平均值（Colab版本新增功能）"""
    if not tokens or not word2vec_model:
        return np.zeros(vector_size)
    
    vectors = []
    for token in tokens:
        try:
            if hasattr(word2vec_model, 'wv') and token in word2vec_model.wv:
                vectors.append(word2vec_model.wv[token])
            elif hasattr(word2vec_model, '__getitem__') and token in word2vec_model:
                vectors.append(word2vec_model[token])
        except:
            continue
    
    if vectors:
        return np.mean(vectors, axis=0)
    else:
        return np.zeros(vector_size)

def extract_specs(name: str) -> str:
    """从商品名称中提取规格信息"""
    if not isinstance(name, str):
        return ""
    
    # 匹配常见的规格单位
    # 例如: 500ml, 1.5L, 2kg, 300g, 12*50g, 6连包, 5片, 12支/盒
    patterns = [
        r'(\d+\.?\d*\s*[gG克])',
        r'(\d+\.?\d*\s*[kK][gG千克])',
        r'(\d+\.?\d*\s*[mM][lL毫升])',
        r'(\d+\.?\d*\s*[lL升])',
        r'(\d+\s*[\*xX]\s*\d+\s*[gG克]?)', # 12*50g
        r'(\d+\s*[连包片袋装支听])' # 6连包
    ]
    found_specs = []
    for pattern in patterns:
        matches = re.findall(pattern, name)
        found_specs.extend([re.sub(r'\s', '', m).lower() for m in matches])
    
    return " ".join(sorted(list(set(found_specs)))) # 排序去重，确保顺序不影响比较

def calculate_feature_similarity(row_a, row_b):
    # 品牌相似度计算
    brand_a = row_a.get('standardized_brand')
    brand_b = row_b.get('standardized_brand')
    brand_similarity = 1 if brand_a and brand_b and brand_a != '其他' and brand_a == brand_b else 0

    # 规格相似度计算
    specs_a = row_a.get('specs')
    specs_b = row_b.get('specs')
    specs_similarity = 1 if specs_a and specs_a == specs_b else 0

    # 🔧 新增：分类相似度计算
    # 一级分类相似度
    cat1_a = row_a.get('美团一级分类', '')
    cat1_b = row_b.get('美团一级分类', '')
    cat1_similarity = 1 if cat1_a and cat1_b and str(cat1_a) == str(cat1_b) else 0
    
    # 三级分类相似度  
    cat3_a = row_a.get('美团三级分类', '')
    cat3_b = row_b.get('美团三级分类', '')
    cat3_similarity = 1 if cat3_a and cat3_b and str(cat3_a) == str(cat3_b) else 0
    
    # 综合分类相似度（一级分类权重更高）
    category_similarity = cat1_similarity * 0.7 + cat3_similarity * 0.3

    return brand_similarity, category_similarity, specs_similarity, False  # 保持向后兼容

# === 参数覆盖/高准确率预设 ===
def _as_float(env_key: str, default: Optional[float]) -> Optional[float]:
    v = os.environ.get(env_key)
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        return default

def _as_int(env_key: str, default: Optional[int]) -> Optional[int]:
    v = os.environ.get(env_key)
    if v is None:
        return default
    try:
        return int(v)
    except Exception:
        return default

def override_match_params(params: dict, phase: str) -> dict:
    """允许通过环境变量覆盖匹配参数；并提供高准确率预设。
    可用环境变量：
      - COMPARE_STRICT=1  启用高准确率预设（更窄价格窗、更高阈值、可强制品牌一致）
      - MATCH_PRICE_WINDOW_HARD / MATCH_PRICE_WINDOW_SOFT （百分比整数，如 15）
      - MATCH_THRESHOLD_HARD / MATCH_THRESHOLD_SOFT （0-1 浮点）
      - MATCH_TEXT_WEIGHT / MATCH_BRAND_WEIGHT / MATCH_CATEGORY_WEIGHT / MATCH_SPECS_WEIGHT
      - MATCH_REQUIRE_BRAND=1  强制品牌一致（当两侧品牌均非空且非“其他”）
    """
    phase_upper = (phase or '').upper()
    out = dict(params)

    # 预设：高准确率
    if os.environ.get('COMPARE_STRICT', '0') == '1':
        if phase_upper == 'HARD':
            out['price_similarity_percent'] = min(out.get('price_similarity_percent', 15), 12)
            out['composite_threshold'] = max(out.get('composite_threshold', 0.5), 0.6)
        else:  # SOFT
            out['price_similarity_percent'] = min(out.get('price_similarity_percent', 20), 15)
            out['composite_threshold'] = max(out.get('composite_threshold', 0.3), 0.55)  # 🔧 兼容高质量模型(如BGE-M3)
        # 提升文本/品牌权重（更保守）
        out['text_weight'] = max(out.get('text_weight', 0.5), 0.6)
        out['brand_weight'] = max(out.get('brand_weight', 0.3), 0.35)
        out['require_brand_match'] = True

    # 细粒度覆盖
    price_env = _as_int(f"MATCH_PRICE_WINDOW_{phase_upper}", None)
    if price_env is not None:
        out['price_similarity_percent'] = price_env
    thr_env = _as_float(f"MATCH_THRESHOLD_{phase_upper}", None)
    if thr_env is not None:
        out['composite_threshold'] = thr_env

    tw = _as_float('MATCH_TEXT_WEIGHT', None)
    bw = _as_float('MATCH_BRAND_WEIGHT', None)
    cw = _as_float('MATCH_CATEGORY_WEIGHT', None)
    sw = _as_float('MATCH_SPECS_WEIGHT', None)
    if tw is not None: out['text_weight'] = tw
    if bw is not None: out['brand_weight'] = bw
    if cw is not None: out['category_weight'] = cw
    if sw is not None: out['specs_weight'] = sw

    if os.environ.get('MATCH_REQUIRE_BRAND', '0') == '1':
        out['require_brand_match'] = True
    if os.environ.get('MATCH_REQUIRE_CAT3', '0') == '1':
        out['require_cat3_match'] = True
    if os.environ.get('MATCH_REQUIRE_SPECS', '0') == '1':
        out['require_specs_match'] = True
    mto = _as_int('MATCH_MIN_TOKEN_OVERLAP', None)
    if mto is not None:
        out['min_token_overlap'] = max(0, int(mto))

    return out

def load_and_process_store_data(filepath: str, model: Optional[SentenceTransformer], cache_path: str = None, role: Optional[str] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if not filepath or not os.path.exists(filepath):
        logging.error(f"文件路径无效: {filepath}")
        return pd.DataFrame(), pd.DataFrame()

    try:
        # 尝试多种编码读取 Excel（修复 GBK 编码错误）
        try:
            df = pd.read_excel(filepath, engine='openpyxl')
        except Exception as e1:
            try:
                df = pd.read_excel(filepath, engine='xlrd')
            except Exception as e2:
                # 如果是 CSV 文件，尝试多种编码
                if filepath.lower().endswith('.csv'):
                    for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']:
                        try:
                            df = pd.read_csv(filepath, encoding=encoding)
                            break
                        except Exception:
                            continue
                    else:
                        raise Exception(f"无法用任何编码读取 CSV 文件: {e1}")
                else:
                    raise Exception(f"Excel 读取失败: {e1}")
        
        # 🔧 智能检测多表头和汇总表（修复徐州问题门店等特殊格式）
        # 检测是否存在大量 "Unnamed" 列或第一行是汇总标题
        unnamed_count = sum(1 for col in df.columns if 'Unnamed' in str(col))
        if unnamed_count > 5 or (len(df) > 0 and any(keyword in str(df.iloc[0, 0]) for keyword in ['概览', '汇总', '统计', '门店'])):
            logging.warning(f"检测到多表头或汇总表格式，尝试智能解析...")
            # 尝试跳过前几行找到真正的数据表头
            for skip_rows in range(1, min(10, len(df))):
                try:
                    df_test = pd.read_excel(filepath, skiprows=skip_rows, engine='openpyxl')
                    # 检查是否有标准列名
                    if '商品名称' in df_test.columns or '售价' in df_test.columns:
                        df = df_test
                        logging.info(f"✅ 智能解析成功：跳过前{skip_rows}行，找到数据表头")
                        break
                except:
                    continue
            else:
                logging.error(f"❌ 无法解析多表头格式，请检查文件: {filepath}")
                return pd.DataFrame(), pd.DataFrame()
                
    except Exception as e:
        logging.error(f"读取文件 {filepath} 失败: {e}")
        return pd.DataFrame(), pd.DataFrame()

    # 标准化列名：去除空格和特殊字符
    df.columns = df.columns.str.strip()  # 去除首尾空格
    df.columns = df.columns.str.replace(r'\s+', '', regex=True)  # 去除所有空格
    
    # 🆕 列名别名映射（兼容不同的列名格式）
    column_aliases = {
        '规格名称': '规格',
        '店内分类': '商家分类',
        '条形码(upc/ean等)': '条码',
        '条形码': '条码',
        'upc': '条码',
        'ean': '条码',
        '货号': '店内码',
        '店内货号': '店内码',
        '采购成本': '成本',
        '进货成本': '成本',
        '成本价': '成本',
    }
    
    # 应用别名映射
    df.rename(columns=column_aliases, inplace=True)
    
    # 调试：打印实际列名
    filename = os.path.basename(filepath)
    logging.info(f"📋 [{filename}] 读取到的列名: {', '.join(df.columns.tolist())}")
    
    # 定义必需列和可选列
    required_cols = ['商品名称', '原价', '售价']  # 核心必需列
    optional_cols = ['条码', '商家分类', '月售', '库存', '美团一级分类', '美团三级分类', '店内码', '规格', '单位', '成本']  # 可选列（🆕 添加成本）
    
    # 检查必需列
    missing_required = [col for col in required_cols if col not in df.columns]
    if missing_required:
        logging.error(f"[{filename}] 文件缺少必需列: {missing_required}")
        return pd.DataFrame(), pd.DataFrame()
    
    # 自动补充可选列（允许本店和竞对列不一致）
    for col in optional_cols:
        if col not in df.columns:
            df[col] = np.nan
            logging.info(f"[{filename}] 文件中缺少「{col}」列，已自动填充为空值。")

    # 条码统一归一化：
    # - 去科学计数法（1.234E+12 -> 1234000000000）
    # - 去小数（1234567890123.0 -> 1234567890123）
    # - 去非数字字符
    # 注意：若源文件在 Excel 中已以数字格式保存且丢失前导零，则无法还原前导零；建议在源文件中将条码列设为“文本”。
    def _normalize_barcode(v):
        if pd.isna(v):
            return np.nan
        s = str(v).strip()
        if not s:
            return np.nan
        # 科学计数法 -> 十进制字符串
        if 'e' in s.lower():
            try:
                s = format(Decimal(s), 'f')
            except Exception:
                pass
        # 去小数部分
        if '.' in s:
            s = s.split('.')[0]
        # 仅保留数字
        s = re.sub(r'\D', '', s)
        return s or np.nan

    try:
        df['条码'] = df['条码'].apply(_normalize_barcode).astype('object')
    except Exception:
        # 兜底：尽量不让条码列导致崩溃
        df['条码'] = df['条码'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        df['条码'].replace(['nan', 'None', ''], np.nan, inplace=True)
    df['cleaned_商品名称'] = df['商品名称'].apply(clean_text)
    df['standardized_brand'] = df.apply(lambda row: extract_brand(row['商品名称'], row['商家分类']), axis=1)
    df['specs'] = df['商品名称'].apply(extract_specs) # 新增：提取规格

    # 兼容分类字段
    df['一级分类'] = df['美团一级分类'].fillna(df['商家分类'].apply(lambda x: str(x).split('>')[0] if pd.notna(x) else ''))
    
    def get_cat3(row):
        if pd.notna(row['美团三级分类']):
            return row['美团三级分类']
        if pd.notna(row['商家分类']) and '>' in str(row['商家分类']):
            parts = str(row['商家分类']).split('>')
            return parts[2] if len(parts) > 2 else parts[-1]  # 优先取第三级，否则取最后一级
        return ''
    df['三级分类'] = df.apply(get_cat3, axis=1)
    df['cleaned_一级分类'] = df['一级分类'].apply(clean_text)
    df['cleaned_三级分类'] = df['三级分类'].apply(clean_text)

    # === 向量编码前：可选预过滤（按一级分类）与采样，减少计算规模 ===
    try:
        cat_list_env = os.environ.get('COMPARE_CAT1_LIST')
        cat_regex_env = os.environ.get('COMPARE_CAT1_REGEX')
        original_len = len(df)
        if cat_list_env:
            items = [s.strip().lower() for s in re.split(r'[;,，；]\s*', cat_list_env) if s.strip()]
            df = df[df['一级分类'].astype(str).str.lower().isin(items)]
        if cat_regex_env:
            pattern = re.compile(cat_regex_env, flags=re.IGNORECASE)
            df = df[df['一级分类'].astype(str).apply(lambda s: bool(pattern.search(s)))]
        if len(df) != original_len:
            logging.info(f"预过滤(一级分类)后：{original_len} -> {len(df)}")

        # 采样上限（仅测试用）：COMPARE_MAX_A / COMPARE_MAX_B
        if role:
            max_key = f"COMPARE_MAX_{role.upper()}"
            max_n = os.environ.get(max_key)
            if max_n and str(max_n).isdigit():
                n = int(max_n)
                if n > 0 and len(df) > n:
                    df = df.head(n)
                    logging.info(f"应用{max_key}={n}：截取前 {n} 条用于快速测试")
    except Exception as _:
        pass

    # --- 向量生成与缓存 ---
    if SIMPLE_FALLBACK or model is None:
        logging.info("简化兜底模式：跳过向量编码，后续采用轻量文本相似度（无需模型）")
        # 放一个占位列，保持后续流程不报错
        df['vector'] = [np.zeros(1)] * len(df)
    else:
        # 🔧 获取模型名称用于缓存键（确保不同模型使用不同缓存）
        model_name = 'unknown'
        
        try:
            # SentenceTransformer 的标准结构：model._modules['0'].auto_model.config._name_or_path
            if hasattr(model, '_modules') and '0' in model._modules:
                if hasattr(model._modules['0'], 'auto_model'):
                    model_name = model._modules['0'].auto_model.config._name_or_path
            # 备选方法：从 model_name 属性获取
            elif hasattr(model, 'model_name'):
                model_name = model.model_name
            # 备选方法：从 _model_name 属性获取
            elif hasattr(model, '_model_name'):
                model_name = model._model_name
        except Exception as e:
            logging.warning(f"无法获取模型名称，使用默认值 'unknown': {e}")
            model_name = 'unknown'
        
        # 缓存键：需要规范化路径
        model_identifier = model_name.replace('/', '_').replace('\\', '_')
        
        # 日志显示：保持原始模型名称（更友好）
        display_name = model_name if len(model_name) < 80 else model_name[:40] + "..." + model_name[-35:]
        logging.info(f"正在为「{os.path.basename(filepath)}」的商品生成文本向量 (模型: {display_name})...")
        
        texts = (df['cleaned_商品名称'] + ' ' + df['cleaned_一级分类'] + ' ' + df['cleaned_三级分类']).astype(str).tolist()

        #  使用统一的缓存管理器



                # 🚀 使用统一的缓存管理器
        texts_to_encode = []
        indices_to_encode = []
        final_embeddings = [None] * len(df)
        
        for i, text in enumerate(texts):
            cached_vector = cache_manager.get_embedding(model_identifier, text)
            if cached_vector is not None:
                final_embeddings[i] = cached_vector
            else:
                texts_to_encode.append(text)
                indices_to_encode.append(i)

        # 🎯 显示缓存命中统计
        cache_hit_count = len(df) - len(texts_to_encode)
        cache_hit_rate = (cache_hit_count / len(df) * 100) if len(df) > 0 else 0
        if cache_hit_count > 0:
            logging.info(f"💾 向量缓存命中: {cache_hit_count}/{len(df)} 条 ({cache_hit_rate:.1f}%)")
        
        if texts_to_encode:
            logging.info(f"Cache miss {len(texts_to_encode)} items, computing new vectors...")
            
            # 🚀 优化1: 自动调整batch_size（根据GPU显存）
            optimal_batch_size = Config.ENCODE_BATCH_SIZE
            try:
                import torch
                if torch.cuda.is_available():
                    gpu_mem_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
                    if gpu_mem_gb >= 8:
                        optimal_batch_size = 256  # 8GB+ GPU
                    elif gpu_mem_gb >= 6:
                        optimal_batch_size = 64   # 6-8GB GPU (RTX 2060，保守批大小)
                    elif gpu_mem_gb >= 4:
                        optimal_batch_size = 48   # 4-6GB GPU
                    else:
                        optimal_batch_size = 32   # <4GB GPU
                    logging.info(f"GPU detected ({gpu_mem_gb:.1f}GB), optimal batch_size={optimal_batch_size}")
            except:
                pass
            
            t0 = time.perf_counter()
            # 🚀 优化2: 批量编码 + 预归一化
            new_embeddings = model.encode(
                texts_to_encode, 
                show_progress_bar=True, 
                batch_size=optimal_batch_size,
                convert_to_numpy=True,
                normalize_embeddings=True  # 预归一化，加速后续余弦相似度计算
            )
            t1 = time.perf_counter()
            
            # 🧹 清理GPU缓存（防止CUDA累积错误）
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
            except Exception:
                pass
            
            speed = len(texts_to_encode) / (t1 - t0)
            logging.info(f"Vector encoding complete: {len(texts_to_encode)} items in {t1 - t0:.2f}s ({speed:.1f} items/s, batch={optimal_batch_size})")
            
            for i, embedding in enumerate(new_embeddings):
                original_index = indices_to_encode[i]
                # 🔧 确保向量格式统一：展平为一维数组
                vec = np.array(embedding).flatten()
                final_embeddings[original_index] = vec
                # 保存到缓存
                cache_manager.set_embedding(model_identifier, texts[original_index], vec)
        else:
            logging.info(f"All vectors loaded from cache ({len(df)} items), encoding skipped")
        
        # 🔧 确保所有向量都是一维数组
        embeddings = [np.array(e).flatten() if e is not None else np.zeros(1) for e in final_embeddings]
        df['vector'] = list(embeddings)

    df_with_barcode = df[df['条码'].notna()].copy().drop_duplicates(subset=['条码'], keep='first')
    df_no_barcode = df[df['条码'].isna()].copy()

    logging.info(f"处理完成: 总商品 {len(df)} | 有条码 {len(df_with_barcode)} | 无条码 {len(df_no_barcode)}")
    return df_with_barcode, df_no_barcode

def check_model_exists(model_name: str) -> bool:
    """检查SentenceTransformer模型是否已缓存到本地"""
    import torch
    from pathlib import Path
    
    # 检查HuggingFace Hub缓存位置（新版本的缓存结构）
    hub_cache_path = Path.home() / ".cache" / "huggingface" / "hub" / f"models--sentence-transformers--{model_name}"
    
    if hub_cache_path.exists():
        # 检查是否有snapshots目录和模型文件
        snapshots_dir = hub_cache_path / "snapshots"
        if snapshots_dir.exists():
            # 查找任何子目录中的模型文件
            for snapshot_dir in snapshots_dir.iterdir():
                if snapshot_dir.is_dir():
                    model_files = list(snapshot_dir.glob("*.safetensors")) + list(snapshot_dir.glob("*.bin")) + list(snapshot_dir.glob("pytorch_model.bin"))
                    if model_files:
                        return True
    
    # 检查旧版本的缓存位置
    old_cache_paths = [
        Path.home() / ".cache" / "torch" / "sentence_transformers" / model_name.replace("/", "_"),
        Path.home() / ".cache" / "huggingface" / "transformers" / model_name.replace("/", "_"),
    ]
    
    for path in old_cache_paths:
        if path.exists() and (list(path.glob("*.bin")) or list(path.glob("*.safetensors"))):
            return True
    
    return False

# ==============================================================================
# 4. 主流程函数
# ==============================================================================

def get_local_model_path(model_name: str) -> str:
    """
    在打包环境下，返回本地模型的实际路径；否则返回模型名称
    """
    global BUNDLED_MODEL_CACHE
    if BUNDLED_MODEL_CACHE and BUNDLED_MODEL_CACHE.exists():
        # 打包环境，尝试使用本地模型
        hub_path = BUNDLED_MODEL_CACHE / 'hub'
        # 将模型名称转换为目录名格式，如 BAAI/bge-large-zh-v1.5 -> models--BAAI--bge-large-zh-v1.5
        model_dir_name = 'models--' + model_name.replace('/', '--')
        local_model_dir = hub_path / model_dir_name
        
        if local_model_dir.exists():
            # 找到refs/main获取snapshot
            refs_file = local_model_dir / 'refs' / 'main'
            if refs_file.exists():
                snapshot_id = refs_file.read_text().strip()
                snapshot_path = local_model_dir / 'snapshots' / snapshot_id
                if snapshot_path.exists():
                    print(f"📁 使用打包的本地模型: {snapshot_path}")
                    return str(snapshot_path)
        
        print(f"⚠️ 打包的模型目录不完整，回退到使用模型名称: {model_name}")
    
    return model_name

def _normalize_filename_for_match(name: str) -> str:
    """
    用于文件名宽松匹配的归一化：
    - NFKC 规整（全角->半角）
    - 小写、去首尾空白
    - 统一短横线/破折号：—、–、－ -> -
    - 去除所有空白字符
    - 移除常见扩展名后缀（.xlsx/.xls）
    - 统一中文括号为英文括号
    """
    if not isinstance(name, str):
        name = str(name or "")
    s = unicodedata.normalize('NFKC', name).lower().strip()
    s = s.replace('—', '-').replace('–', '-').replace('－', '-')
    s = s.replace('（', '(').replace('）', ')').replace('【', '[').replace('】', ']')
    # 去除扩展名
    s = re.sub(r"\.(xlsx|xls)$", "", s)
    # 去除所有空白
    s = re.sub(r"\s+", "", s)
    return s

def get_adaptive_threshold(model_name: str, cfg, match_type: str = 'soft') -> float:
    """根据模型自动获取推荐阈值
    
    Args:
        model_name: 模型名称
        cfg: 配置对象
        match_type: 'hard' 或 'soft'
    
    Returns:
        推荐的阈值
    """
    models = getattr(cfg, 'AVAILABLE_MODELS', {})
    
    # 查找模型对应的推荐阈值
    for model_info in models.values():
        if model_info['name'] == model_name:
            thresholds = model_info.get('recommended_threshold', {'hard': 0.5, 'soft': 0.5})
            threshold = thresholds.get(match_type, 0.5)
            print(f"📊 [{match_type.upper()}匹配] 当前模型推荐阈值: {threshold:.2f}")
            return threshold
    
    # 默认阈值
    print(f"⚠️ 未找到模型配置，使用默认阈值: 0.5")
    return 0.5

def select_embedding_model(cfg) -> str:
    """交互式选择嵌入模型"""
    if not getattr(cfg, 'ENABLE_MODEL_SELECTION', True):
        return cfg.SENTENCE_BERT_MODEL
    
    # 检查是否通过环境变量指定了模型
    env_model = os.environ.get('SENTENCE_BERT_MODEL')
    if env_model:
        print(f"🔧 通过环境变量指定模型: {env_model}")
        return env_model
    
    # 检测标准输入是否可用（是否被重定向或管道输入）
    import sys
    
    # 增加环境变量检测：GUI模式下强制使用默认模型
    if os.environ.get('GUI_MODE') == '1':
        model_mode = os.environ.get('MODEL_MODE', '未知')
        print(f"ℹ️ 检测到GUI模式，使用用户选择的模型: {model_mode}")
        print(f"   嵌入模型: {cfg.SENTENCE_BERT_MODEL}")
        return cfg.SENTENCE_BERT_MODEL
    
    if not sys.stdin or not hasattr(sys.stdin, 'isatty') or not sys.stdin.isatty():
        print("ℹ️ 检测到非交互式模式（标准输入被重定向），使用默认模型")
        return cfg.SENTENCE_BERT_MODEL
    
    print("\n" + "="*70)
    print("🤖 嵌入模型选择")
    print("="*70)
    print("请选择用于商品比对的嵌入模型：\n")
    
    models = getattr(cfg, 'AVAILABLE_MODELS', {})
    if not models:
        return cfg.SENTENCE_BERT_MODEL
    
    # 显示模型选项
    for key, model_info in sorted(models.items()):
        print(f"  [{key}] {model_info['display_name']}")
        print(f"      📝 说明: {model_info['description']}")
        print(f"      📦 大小: {model_info['size']} | ⚡ 速度: {model_info['speed']} | 🎯 准确率: {model_info['accuracy']}")
        print()
    
    print("💡 提示:")
    print("   - 选项4 (BGE-Large) ⭐ 最强性能，准确率最高，适合高质量要求场景")
    print("   - 选项5 (BGE-M3) 最新一代，支持混合检索，多语言场景最优")
    print("   - 选项2 (BGE-Base) 性能与速度平衡，推荐日常使用")
    print("   - 选项6 (BGE-Small) 速度最快，适合大批量数据处理")
    if not getattr(sys, 'frozen', False):
        # 仅在开发环境显示下载提示
        print("   - 首次使用新模型需要下载，约5-30分钟（视模型大小）")
    print()
    
    # 获取用户选择
    while True:
        try:
            choice = input("请输入模型编号 (1-6, 回车=使用默认模型1): ").strip()
            
            # 默认选择
            if not choice:
                choice = '1'
                print(f"✅ 使用默认模型: {models['1']['display_name']}")
            
            if choice in models:
                selected_model = models[choice]['name']
                print(f"\n✅ 已选择: {models[choice]['display_name']}")
                print(f"   模型路径: {selected_model}")
                print(f"   预期效果: {models[choice]['description']}")
                print("="*70)
                return selected_model
            else:
                print(f"❌ 无效选择，请输入 1-{len(models)} 之间的数字")
        except KeyboardInterrupt:
            print("\n\n⚠️ 用户取消选择，使用默认模型")
            return cfg.SENTENCE_BERT_MODEL
        except Exception as e:
            print(f"❌ 输入错误: {e}，请重新输入")

def select_cross_encoder_model(cfg) -> str:
    """交互式选择 Cross-Encoder 精排模型"""
    if not getattr(cfg, 'ENABLE_MODEL_SELECTION', True):
        return cfg.ONLINE_CROSS_ENCODER
    
    # 检查是否通过环境变量指定了模型
    env_model = os.environ.get('CROSS_ENCODER_MODEL')
    if env_model:
        print(f"🔧 通过环境变量指定 Cross-Encoder 模型: {env_model}")
        return env_model
    
    # 增加GUI模式检测
    if os.environ.get('GUI_MODE') == '1':
        model_mode = os.environ.get('MODEL_MODE', '未知')
        print(f"ℹ️ 检测到GUI模式，使用用户选择的精排模型: {model_mode}")
        print(f"   精排模型: {cfg.ONLINE_CROSS_ENCODER}")
        return cfg.ONLINE_CROSS_ENCODER
    
    # 检测标准输入是否可用
    import sys
    if not sys.stdin or not hasattr(sys.stdin, 'isatty') or not sys.stdin.isatty():
        print("ℹ️ 检测到非交互式模式，使用默认 Cross-Encoder 模型")
        return cfg.ONLINE_CROSS_ENCODER
    
    print("\n" + "="*70)
    print("🎯 Cross-Encoder 精排模型选择")
    print("="*70)
    print("Cross-Encoder 用于精准精排，提升匹配准确率\n")
    
    models = getattr(cfg, 'AVAILABLE_CROSS_ENCODERS', {})
    if not models:
        return cfg.ONLINE_CROSS_ENCODER
    
    # 显示模型选项
    for key, model_info in sorted(models.items()):
        print(f"  [{key}] {model_info['display_name']}")
        print(f"      📝 说明: {model_info['description']}")
        print(f"      📦 大小: {model_info['size']} | ⚡ 速度: {model_info['speed']} | 🎯 准确率: {model_info['accuracy']}")
        print(f"      🌐 语言: {model_info['language']}")
        print()
    
    print("💡 提示:")
    print("   - 选项2 (BGE-Reranker-Large) ⭐ 中文场景强力推荐，准确率+40%")
    print("   - 选项3 (BGE-Reranker-Base) ⚡ 速度与准确率平衡，准确率+25%")
    print("   - 选项1 (MS-Marco-MiniLM) 速度最快，但中文效果一般")
    print("   - Cross-Encoder 与 Sentence-BERT 配合使用，两阶段匹配更精准")
    if not getattr(sys, 'frozen', False):
        # 仅在开发环境显示下载提示
        print("   - 首次使用新模型需要下载，约1-10分钟（视模型大小）")
    print()
    
    # 获取用户选择
    while True:
        try:
            choice = input(f"请输入模型编号 (1-{len(models)}, 回车=使用默认模型1): ").strip()
            
            # 默认选择
            if not choice:
                choice = '1'
                print(f"✅ 使用默认模型: {models['1']['display_name']}")
            
            if choice in models:
                selected_model = models[choice]['name']
                print(f"\n✅ 已选择: {models[choice]['display_name']}")
                print(f"   模型路径: {selected_model}")
                print(f"   预期效果: {models[choice]['description']}")
                print("="*70)
                return selected_model
            else:
                print(f"❌ 无效选择，请输入 1-{len(models)} 之间的数字")
        except KeyboardInterrupt:
            print("\n\n⚠️ 用户取消选择，使用默认模型")
            return cfg.ONLINE_CROSS_ENCODER
        except Exception as e:
            print(f"❌ 输入错误: {e}，请重新输入")

def scan_excel_files_in_dir(directory: str) -> List[str]:
    """扫描指定目录中的所有Excel文件"""
    excel_files = []
    if not os.path.exists(directory):
        return excel_files
    try:
        for f in os.listdir(directory):
            if f.lower().endswith((".xlsx", ".xls")) and not f.startswith("~$"):
                excel_files.append(f)
    except Exception as e:
        logging.error(f"❌ 扫描目录 {directory} 时出错：{e}")
    return sorted(excel_files)

def get_latest_file_from_upload_dir(upload_dir: str, store_type: str) -> Tuple[Optional[str], str]:
    """从上传目录获取最新的Excel文件，返回(文件路径, 店铺名称)"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_upload_dir = os.path.join(base_dir, upload_dir)
    
    # 确保目录存在
    if not os.path.exists(full_upload_dir):
        return None, ""
    
    excel_files = scan_excel_files_in_dir(full_upload_dir)
    
    if not excel_files:
        return None, ""
    
    # 如果有多个文件，选择最新的
    if len(excel_files) > 1:
        files_with_time = []
        for f in excel_files:
            filepath = os.path.join(full_upload_dir, f)
            mtime = os.path.getmtime(filepath)
            files_with_time.append((f, mtime, filepath))
        
        # 按修改时间排序，最新的在前
        files_with_time.sort(key=lambda x: x[1], reverse=True)
        latest_file = files_with_time[0][2]
        latest_filename = files_with_time[0][0]
        
        print(f"📋 {store_type}上传目录发现 {len(excel_files)} 个文件，使用最新文件: {latest_filename}")
        if len(excel_files) > 1:
            print(f"   💡 提示: 其他文件将被忽略")
            for fname, mtime, _ in files_with_time[1:]:
                mtime_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
                print(f"      - {fname} ({mtime_str})")
    else:
        latest_file = os.path.join(full_upload_dir, excel_files[0])
        latest_filename = excel_files[0]
    
    # 从文件名提取店铺名称
    store_name = os.path.splitext(latest_filename)[0][:40]
    
    return latest_file, store_name

def detect_files_from_upload_dirs(cfg) -> Tuple[Optional[str], Optional[str], str, str]:
    """从上传目录检测文件，返回(本店文件路径, 竞对文件路径, 本店名称, 竞对名称)"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    upload_a_dir = getattr(cfg, 'UPLOAD_DIR_STORE_A', 'upload/store_a')
    upload_b_dir = getattr(cfg, 'UPLOAD_DIR_STORE_B', 'upload/store_b')
    
    print("\n" + "="*60)
    print("📂 Upload Directory Detection")
    print("="*60)
    print(f"📁 Store A: {upload_a_dir}")
    print(f"📁 Store B: {upload_b_dir}")
    print()
    
    # 检测本店文件
    store_a_file, store_a_name = get_latest_file_from_upload_dir(upload_a_dir, "Store A")
    
    # 检测竞对文件
    store_b_file, store_b_name = get_latest_file_from_upload_dir(upload_b_dir, "Store B")
    
    # 显示检测结果
    if store_a_file:
        size = os.path.getsize(store_a_file)
        size_str = f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/(1024*1024):.1f}MB"
        mtime = os.path.getmtime(store_a_file)
        mtime_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
        print(f"✅ Store A: {store_a_name}.xlsx ({size_str}, {mtime_str})")
    else:
        print(f"❌ Store A: No Excel files found")
    
    if store_b_file:
        size = os.path.getsize(store_b_file)
        size_str = f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/(1024*1024):.1f}MB"
        mtime = os.path.getmtime(store_b_file)
        mtime_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
        print(f"✅ Store B: {store_b_name}.xlsx ({size_str}, {mtime_str})")
    else:
        print(f"❌ Store B: No Excel files found")
    
    print("="*60)
    
    return store_a_file, store_b_file, store_a_name, store_b_name

def get_local_filepath(filename: str) -> Optional[str]:
    current_directory = os.path.dirname(os.path.abspath(__file__))
    # 1) 精确匹配（包含原扩展名）
    filepath = os.path.join(current_directory, filename)
    if os.path.exists(filepath):
        logging.info(f"✅ 文件 '{filename}' 已找到。")
        return filepath

    # 2) 宽松匹配：在同目录查找 .xls/.xlsx，做归一化比对（跳过 ~$/临时文件）
    try:
        target_norm = _normalize_filename_for_match(filename)
        candidates = [f for f in os.listdir(current_directory) if f.lower().endswith((".xlsx", ".xls")) and not f.startswith("~$")]
        # 先尝试归一化完全相等
        for cand in candidates:
            if _normalize_filename_for_match(cand) == target_norm:
                path = os.path.join(current_directory, cand)
                logging.info(f"✅ 未找到精确同名，但找到归一化匹配文件：'{cand}'（由 '{filename}' 匹配）")
                return path
        # 再尝试相似度匹配（≥0.9）
        ratios = [(cand, difflib.SequenceMatcher(None, _normalize_filename_for_match(cand), target_norm).ratio()) for cand in candidates]
        if ratios:
            best_cand, best_score = max(ratios, key=lambda x: x[1])
            if best_score >= 0.9:
                path = os.path.join(current_directory, best_cand)
                logging.warning(f"⚠️ 精确文件未找到，使用相似文件：'{best_cand}'（相似度 {best_score:.2f}，由 '{filename}' 匹配）")
                return path
        logging.error(f"❌ 错误：文件 '{filename}' 在脚本所在目录未找到！当前目录为：{current_directory}。目录内可用文件：{candidates}")
        return None
    except Exception as e:
        logging.error(f"❌ 在目录 '{current_directory}' 搜索文件时出错：{e}")
        return None

def match_by_barcode(df_a: pd.DataFrame, df_b: pd.DataFrame, name_a: str, name_b: str) -> pd.DataFrame:
    if df_a.empty or df_b.empty:
        return pd.DataFrame()

    merged = pd.merge(df_a, df_b, on='条码', how='inner', suffixes=(f'_{name_a}', f'_{name_b}'))
    if merged.empty:
        return merged

    def _ensure_suffix(columns: Iterable[str], suffix: str) -> None:
        for col in columns:
            if col == '条码':
                continue
            target = f"{col}_{suffix}"
            if target in merged.columns:
                continue
            if col in merged.columns:
                merged.rename(columns={col: target}, inplace=True)

    _ensure_suffix(df_a.columns, name_a)
    _ensure_suffix(df_b.columns, name_b)

    # 为两侧补充带后缀的条码列，便于下游稳定引用
    barcode_col_a = f"条码_{name_a}"
    barcode_col_b = f"条码_{name_b}"
    if barcode_col_a not in merged.columns:
        merged[barcode_col_a] = merged['条码']
    if barcode_col_b not in merged.columns:
        merged[barcode_col_b] = merged['条码']
    return merged

def perform_hard_category_matching(df_a: pd.DataFrame, df_b: pd.DataFrame, name_a: str, name_b: str, cross_encoder=None, cfg=None) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    阶段一：硬分类优先匹配
    - 找出A店和B店中，一级分类和三级分类完全一致的商品。
    - 在这些分类完全相同的分组内，进行高精度的模糊匹配。
    - 返回匹配上的商品，以及A店和B店中未匹配的商品。
    """
    if df_a.empty or df_b.empty:
        return pd.DataFrame(), df_a, df_b

    # 确保分类列存在
    if '一级分类' not in df_a.columns or '三级分类' not in df_a.columns or \
       '一级分类' not in df_b.columns or '三级分类' not in df_b.columns:
        logging.warning("⚠️ 硬分类匹配阶段缺少分类列，跳过此阶段。")
        return pd.DataFrame(), df_a, df_b

    # 创建唯一的分类ID
    df_a['category_id'] = df_a['一级分类'].astype(str) + '_' + df_a['三级分类'].astype(str)
    df_b['category_id'] = df_b['一级分类'].astype(str) + '_' + df_b['三级分类'].astype(str)

    # 找出共有的分类ID
    common_categories = set(df_a['category_id']) & set(df_b['category_id'])
    logging.info(f"硬分类匹配：找到 {len(common_categories)} 个共同的商品分类。")

    all_hard_matches = []
    
    # 获取自适应阈值
    adaptive_threshold = 0.5  # 默认值
    if cfg:
        adaptive_threshold = get_adaptive_threshold(cfg.SENTENCE_BERT_MODEL, cfg, match_type='hard')
    
    # 复制一份参数用于硬匹配，通常硬匹配的阈值可以更高
    hard_match_params = {
        "price_similarity_percent": 15,
        "composite_threshold": adaptive_threshold,  # 使用自适应阈值
        "text_weight": 0.6, # 提升文本权重
        "brand_weight": 0.3, # 品牌权重
        "specs_weight": 0.1, # 规格权重
        "category_weight": 0.0, # 硬分类匹配阶段，分类已100%相同，权重为0
        "candidates_to_check": int(os.environ.get('MATCH_TOPK_HARD', '20')),
        "require_category_match": False, # 在这个函数内部，分类已经匹配，不需要再次检查
        "require_cat3_match": False,  # ✅ 硬分类已经按category_id分组，无需二次检查
    }
    hard_match_params = override_match_params(hard_match_params, phase='HARD')

    # 记录所有在硬匹配中处理过的商品索引
    matched_indices_a = set()
    matched_indices_b = set()

    for category in tqdm(common_categories, desc="Hard Category Match", dynamic_ncols=True, mininterval=0.5, file=sys.stdout, ascii=True):
        group_a = df_a[df_a['category_id'] == category]
        group_b = df_b[df_b['category_id'] == category]

        if group_a.empty or group_b.empty:
            continue

        # 在分类分组内进行模糊匹配
        # 注意：这里调用的是一个通用的匹配核心逻辑，我们把它命名为 _core_fuzzy_match
        matches_in_group = _core_fuzzy_match(group_a, group_b, name_a, name_b, hard_match_params, cross_encoder)

        if not matches_in_group.empty:
            all_hard_matches.append(matches_in_group)
            
            # ✅ 修复：优先使用原始索引（包括被去重删除的CD商品）
            if 'all_matched_indices_a' in matches_in_group.attrs:
                matched_indices_a.update(matches_in_group.attrs['all_matched_indices_a'])
                matched_indices_b.update(matches_in_group.attrs['all_matched_indices_b'])
                print(f"   ✅ 使用原始索引: 本店{len(matches_in_group.attrs['all_matched_indices_a'])}个, 竞对{len(matches_in_group.attrs['all_matched_indices_b'])}个")
            else:
                # 兜底：使用去重后的索引（旧逻辑）
                matched_indices_a.update(matches_in_group[f'index_{name_a}'].tolist())
                matched_indices_b.update(matches_in_group[f'index_{name_b}'].tolist())

    if not all_hard_matches:
        return pd.DataFrame(), df_a.drop(columns=['category_id']), df_b.drop(columns=['category_id'])

    final_hard_matches = pd.concat(all_hard_matches, ignore_index=True)

    # 找出未匹配的商品
    unmatched_a = df_a[~df_a.index.isin(matched_indices_a)].copy()
    unmatched_b = df_b[~df_b.index.isin(matched_indices_b)].copy()

    # 清理辅助列
    final_hard_matches = final_hard_matches.drop(columns=[f'index_{name_a}', f'index_{name_b}'], errors='ignore')
    unmatched_a = unmatched_a.drop(columns=['category_id'], errors='ignore')
    unmatched_b = unmatched_b.drop(columns=['category_id'], errors='ignore')
    
    return final_hard_matches, unmatched_a, unmatched_b


def perform_soft_fuzzy_matching(df_a: pd.DataFrame, df_b: pd.DataFrame, name_a: str, name_b: str, cross_encoder=None, cfg=None) -> pd.DataFrame:
    """
    阶段二：软分类兜底匹配
    - 对所有在硬分类匹配中未找到匹配的剩余商品进行匹配。
    - ✅ 性能优化：改为按一级分类分组匹配，避免全量比对
    """
    if df_a.empty or df_b.empty:
        return pd.DataFrame()

    # 确保分类列存在
    if '一级分类' not in df_a.columns or '一级分类' not in df_b.columns:
        logging.warning("⚠️ 软分类匹配阶段缺少一级分类列，使用全量匹配（性能较差）。")
        return _perform_soft_match_without_grouping(df_a, df_b, name_a, name_b, cross_encoder, cfg)
    
    # ✅ 性能优化：按一级分类分组匹配
    df_a['cat1_group'] = df_a['一级分类'].astype(str)
    df_b['cat1_group'] = df_b['一级分类'].astype(str)
    
    common_cat1 = set(df_a['cat1_group']) & set(df_b['cat1_group'])
    logging.info(f"软分类匹配：找到 {len(common_cat1)} 个共同的一级分类，将分组处理（避免全量比对）")
    
    all_soft_matches = []
    matched_indices_a = set()
    matched_indices_b = set()
    
    # 获取自适应阈值
    adaptive_threshold = 0.5
    if cfg:
        adaptive_threshold = get_adaptive_threshold(cfg.SENTENCE_BERT_MODEL, cfg, match_type='soft')
    
    # 软匹配参数
    soft_match_params = {
        "price_similarity_percent": 20,
        "composite_threshold": adaptive_threshold,
        "text_weight": 0.5,
        "brand_weight": 0.3,
        "category_weight": 0.1,
        "specs_weight": 0.1,
        "candidates_to_check": int(os.environ.get('MATCH_TOPK_SOFT', '100')),
        "require_category_match": False,  # ✅ 已分组，无需再检查一级分类
        "require_cat3_match": True,  # 🔧 开启三级分类强制匹配
        "require_brand_match": False,  # 可选：设为True强制品牌一致
    }
    soft_match_params = override_match_params(soft_match_params, phase='SOFT')
    
    # 按一级分类分组匹配
    for cat1 in tqdm(common_cat1, desc="Soft Category Match (Optimized)", dynamic_ncols=True, mininterval=0.5, file=sys.stdout, ascii=True):
        group_a = df_a[df_a['cat1_group'] == cat1]
        group_b = df_b[df_b['cat1_group'] == cat1]
        
        if group_a.empty or group_b.empty:
            continue
        
        # 在分组内匹配（性能提升：从 N×M 降为 n×m，其中 n,m << N,M）
        matches_in_group = _core_fuzzy_match(group_a, group_b, name_a, name_b, soft_match_params, cross_encoder)
        
        if not matches_in_group.empty:
            all_soft_matches.append(matches_in_group)
            
            # ✅ 修复：优先使用原始索引
            if 'all_matched_indices_a' in matches_in_group.attrs:
                matched_indices_a.update(matches_in_group.attrs['all_matched_indices_a'])
                matched_indices_b.update(matches_in_group.attrs['all_matched_indices_b'])
            else:
                matched_indices_a.update(matches_in_group[f'index_{name_a}'].tolist())
                matched_indices_b.update(matches_in_group[f'index_{name_b}'].tolist())
    
    # === 🔧 方案2C：智能混合策略 - 三级分类补充匹配 ===
    enable_cat3_fallback = os.environ.get('ENABLE_CAT3_FALLBACK', '1') == '1'
    
    if enable_cat3_fallback and '三级分类' in df_a.columns and '三级分类' in df_b.columns:
        # 找出未匹配的商品
        unmatched_a = df_a[~df_a.index.isin(matched_indices_a)].copy()
        unmatched_b = df_b[~df_b.index.isin(matched_indices_b)].copy()
        
        # 智能筛选：只对可能被错误分类的商品进行三级分类匹配
        def is_likely_misclassified(row):
            """判断商品是否可能被错误分类"""
            name = str(row.get('商品名称', '')).lower()
            price = pd.to_numeric(row.get('原价', 0), errors='coerce')
            
            # 条件1: 包含知名品牌关键词
            brand_keywords = ['可口可乐', '百事', '康师傅', '统一', '雀巢', '伊利', '蒙牛', '农夫山泉', 
                            '娃哈哈', '达利园', '奥利奥', '乐事', '卫龙', '三只松鼠', '良品铺子']
            has_brand = any(brand in name for brand in brand_keywords)
            
            # 条件2: 价格在典型范围（排除异常商品）
            normal_price = 1 <= price <= 100 if pd.notna(price) else True
            
            # 条件3: 商品名称长度适中（排除描述过短或过长的异常数据）
            name_len_ok = 5 <= len(name) <= 100
            
            return (has_brand or normal_price) and name_len_ok
        
        if not unmatched_a.empty and not unmatched_b.empty:
            candidates_a = unmatched_a[unmatched_a.apply(is_likely_misclassified, axis=1)]
            candidates_b = unmatched_b[unmatched_b.apply(is_likely_misclassified, axis=1)]
            
            if not candidates_a.empty and not candidates_b.empty:
                # 按三级分类分组
                candidates_a['cat3_group'] = candidates_a['三级分类'].astype(str)
                candidates_b['cat3_group'] = candidates_b['三级分类'].astype(str)
                
                common_cat3 = set(candidates_a['cat3_group']) & set(candidates_b['cat3_group'])
                
                if common_cat3:
                    logging.info(f"🔧 三级分类补充匹配：找到 {len(common_cat3)} 个共同三级分类，候选商品 A:{len(candidates_a)} B:{len(candidates_b)}")
                    
                    cat3_matches = []
                    # 修复进度条显示：添加 leave=True 确保完成后保留，ncols=80 固定宽度
                    pbar = tqdm(common_cat3, desc="   L3 Category Supplement", 
                               ncols=100, mininterval=1.0, 
                               file=sys.stdout, leave=True, ascii=True)
                    
                    for cat3 in pbar:
                        group_a_cat3 = candidates_a[candidates_a['cat3_group'] == cat3]
                        group_b_cat3 = candidates_b[candidates_b['cat3_group'] == cat3]
                        
                        if group_a_cat3.empty or group_b_cat3.empty:
                            continue
                        
                        # 使用相同的匹配参数，但不强制一级分类
                        cat3_params = soft_match_params.copy()
                        cat3_params['require_category_match'] = False  # 允许一级分类不同
                        cat3_params['require_cat3_match'] = True  # 强制三级分类相同
                        
                        matches_cat3 = _core_fuzzy_match(group_a_cat3, group_b_cat3, name_a, name_b, cat3_params, cross_encoder)
                        
                        if not matches_cat3.empty:
                            cat3_matches.append(matches_cat3)
                    
                    pbar.close()  # 显式关闭进度条，确保正确换行
                    sys.stdout.flush()  # 刷新输出缓冲
                    
                    if cat3_matches:
                        cat3_matches_df = pd.concat(cat3_matches, ignore_index=True)
                        cat3_matches_df = cat3_matches_df.drop(columns=[f'index_{name_a}', f'index_{name_b}'], errors='ignore')
                        all_soft_matches.append(cat3_matches_df)
                        logging.info(f"   ✅ 三级分类补充匹配成功：新增 {len(cat3_matches_df)} 条跨一级分类匹配")
                
                candidates_a.drop(columns=['cat3_group'], errors='ignore', inplace=True)
                candidates_b.drop(columns=['cat3_group'], errors='ignore', inplace=True)
    
    if not all_soft_matches:
        # 清理辅助列
        df_a.drop(columns=['cat1_group'], errors='ignore', inplace=True)
        df_b.drop(columns=['cat1_group'], errors='ignore', inplace=True)
        return pd.DataFrame()
    
    final_soft_matches = pd.concat(all_soft_matches, ignore_index=True)
    final_soft_matches = final_soft_matches.drop(columns=[f'index_{name_a}', f'index_{name_b}'], errors='ignore')
    
    # 清理辅助列
    df_a.drop(columns=['cat1_group'], errors='ignore', inplace=True)
    df_b.drop(columns=['cat1_group'], errors='ignore', inplace=True)
    
    return final_soft_matches


def _perform_soft_match_without_grouping(df_a: pd.DataFrame, df_b: pd.DataFrame, name_a: str, name_b: str, cross_encoder=None, cfg=None) -> pd.DataFrame:
    """
    兜底方案：不分组的全量软匹配（性能较差，仅在缺少分类列时使用）
    """
    adaptive_threshold = 0.5
    if cfg:
        adaptive_threshold = get_adaptive_threshold(cfg.SENTENCE_BERT_MODEL, cfg, match_type='soft')

    soft_match_params = {
        "price_similarity_percent": 20,
        "composite_threshold": adaptive_threshold,
        "text_weight": 0.5,
        "brand_weight": 0.3,
        "category_weight": 0.1,
        "specs_weight": 0.1,
        "candidates_to_check": int(os.environ.get('MATCH_TOPK_SOFT', '100')),
        "require_category_match": True,
        "require_cat3_match": True,
    }
    soft_match_params = override_match_params(soft_match_params, phase='SOFT')

    soft_matches = _core_fuzzy_match(df_a, df_b, name_a, name_b, soft_match_params, cross_encoder)
    
    if not soft_matches.empty:
        soft_matches = soft_matches.drop(columns=[f'index_{name_a}', f'index_{name_b}'], errors='ignore')

    return soft_matches


def _core_fuzzy_match(df_a: pd.DataFrame, df_b: pd.DataFrame, name_a: str, name_b: str, params: dict, cross_encoder=None) -> pd.DataFrame:
    """
    模糊匹配的核心计算逻辑，被硬匹配和软匹配共同调用。
    """
    if df_a.empty or df_b.empty:
        return pd.DataFrame()

    k = params.get('candidates_to_check', 50)
    matched_products = []

    # 预处理 B 侧数值列
    df_b_temp = df_b.copy()
    df_b_temp['原价_numeric'] = pd.to_numeric(df_b_temp['原价'], errors='coerce')

    use_simple = SIMPLE_FALLBACK or (df_a['vector'].iloc[0].shape == (1,))
    sim_matrix = None
    top_k_indices = None
    
    if not use_simple:
        # 🚀 P1: 相似度矩阵缓存优化
        try:
            df_a_vectors = np.vstack([np.array(v).flatten() for v in df_a['vector']])
            df_b_vectors = np.vstack([np.array(v).flatten() for v in df_b['vector']])
            
            # 尝试从缓存获取相似度矩阵
            # 提取模型标识符（假设向量已经包含模型信息）
            model_identifier = "default"  # 默认值
            if hasattr(cross_encoder, 'model_name'):
                model_identifier = cross_encoder.model_name.replace('/', '_').replace('\\', '_')
            
            # 使用商品索引作为缓存键
            ids_a = df_a.index.tolist()
            ids_b = df_b.index.tolist()
            
            cached_matrix = cache_manager.get_similarity_matrix(model_identifier, ids_a, ids_b)
            
            if cached_matrix is not None:
                sim_matrix = cached_matrix
                logging.debug(f"✅ 相似度矩阵缓存命中: {len(ids_a)}×{len(ids_b)}")
            else:
                # 计算新的相似度矩阵
                sim_matrix = cosine_similarity(df_a_vectors, df_b_vectors)
                # 保存到缓存
                cache_manager.set_similarity_matrix(model_identifier, ids_a, ids_b, sim_matrix)
                logging.debug(f"💾 相似度矩阵已缓存: {len(ids_a)}×{len(ids_b)}")
            
            top_k_indices = np.argsort(sim_matrix, axis=1)[:, -k:]
        except Exception as e:
            logging.warning(f"⚠️ 向量相似度计算失败，降级为逐对比较: {e}")
            use_simple = True
            top_k_indices = None

    for i in tqdm(range(len(df_a)), desc=f"Core Fuzzy Match ({name_a} vs {name_b})", leave=False, dynamic_ncols=True, mininterval=0.5, file=sys.stdout, ascii=True):
        row_a = df_a.iloc[i]
        price_a = pd.to_numeric(row_a['原价'], errors='coerce')
        if pd.isna(price_a) or price_a == 0:
            continue

        price_min = price_a * (1 - params['price_similarity_percent'] / 100)
        price_max = price_a * (1 + params['price_similarity_percent'] / 100)

        best_overall_score = -1
        best_match_row_b = None

        candidate_pairs = []
        valid_candidates = []

        if use_simple:
            # 简化模式：先用价格+（可选）分类筛选，再用 difflib 文本相似度取 Top-K
            mask = df_b_temp['原价_numeric'].between(price_min, price_max)
            if params.get("require_category_match", False):
                mask &= (df_b_temp['一级分类'].astype(str) == str(row_a.get('一级分类', '')))
            if params.get('require_cat3_match', False):
                mask &= (df_b_temp['三级分类'].astype(str) == str(row_a.get('三级分类','')))
            cand_df = df_b_temp[mask]
            if cand_df.empty:
                continue
            # 计算文本相似度（difflib）
            a_text = f"{row_a.get('cleaned_商品名称','')} {row_a.get('cleaned_一级分类','')} {row_a.get('cleaned_三级分类','')}"
            scores = []
            cand_rows = []
            for _, rb in cand_df.iterrows():
                b_text = f"{rb.get('cleaned_商品名称','')} {rb.get('cleaned_一级分类','')} {rb.get('cleaned_三级分类','')}"
                try:
                    s = difflib.SequenceMatcher(None, a_text, b_text).ratio()
                except Exception:
                    s = 0.0
                scores.append(s)
                cand_rows.append(rb)
            if not scores:
                continue
            # 选 Top-K
            order = np.argsort(np.array(scores))[-k:]
            valid_candidates = [cand_rows[idx] for idx in order]
            candidate_pairs = [[row_a['商品名称'], r['商品名称']] for r in valid_candidates]
        else:
            # 精排：对粗筛出的候选商品进行详细打分
            for b_idx in top_k_indices[i]:
                row_b = df_b_temp.iloc[b_idx]
                # 价格过滤
                if not (price_min <= row_b['原价_numeric'] <= price_max):
                    continue
                # 新增：强制分类过滤（如果参数要求）
                if params.get("require_category_match", False):
                    cat1_a = str(row_a.get('一级分类', '')).strip()
                    cat1_b = str(row_b.get('一级分类', '')).strip()
                    # 要求两侧分类都非空且完全匹配
                    if not cat1_a or not cat1_b or cat1_a != cat1_b:
                        continue
                candidate_pairs.append([row_a['商品名称'], row_b['商品名称']])
                valid_candidates.append(row_b)

        # 如果要求品牌/三级分类/规格一致，则提前过滤候选
        if params.get('require_brand_match', False):
            def _brand_ok(ra, rb):
                ba = str(ra.get('standardized_brand') or '').strip().lower()
                bb = str(rb.get('standardized_brand') or '').strip().lower()
                if not ba or not bb or ba == '其他' or bb == '其他':
                    return False
                return ba == bb
            new_pairs = []
            new_valid = []
            for pair, rb in zip(candidate_pairs, valid_candidates):
                if _brand_ok(row_a, rb):
                    new_pairs.append(pair)
                    new_valid.append(rb)
            candidate_pairs, valid_candidates = new_pairs, new_valid

        if params.get('require_cat3_match', False) and candidate_pairs:
            new_pairs = []
            new_valid = []
            cat3a = str(row_a.get('三级分类',''))
            for pair, rb in zip(candidate_pairs, valid_candidates):
                if str(rb.get('三级分类','')) == cat3a:
                    new_pairs.append(pair)
                    new_valid.append(rb)
            candidate_pairs, valid_candidates = new_pairs, new_valid

        if params.get('require_specs_match', False) and candidate_pairs:
            new_pairs = []
            new_valid = []
            sa = str(row_a.get('specs') or '').strip()
            for pair, rb in zip(candidate_pairs, valid_candidates):
                sb = str(rb.get('specs') or '').strip()
                if sa and sb and sa == sb:
                    new_pairs.append(pair)
                    new_valid.append(rb)
            candidate_pairs, valid_candidates = new_pairs, new_valid

        # 最小分词重叠（基于 cleaned_商品名称），用于过滤语义完全不相干的条目
        min_overlap = int(params.get('min_token_overlap', 0) or 0)
        if min_overlap > 0 and candidate_pairs:
            a_tokens = set(tokenize_text(row_a.get('cleaned_商品名称','')))
            new_pairs = []
            new_valid = []
            for pair, rb in zip(candidate_pairs, valid_candidates):
                b_tokens = set(tokenize_text(rb.get('cleaned_商品名称','')))
                if len(a_tokens & b_tokens) >= min_overlap:
                    new_pairs.append(pair)
                    new_valid.append(rb)
            candidate_pairs, valid_candidates = new_pairs, new_valid

        if not candidate_pairs:
            continue

        # 🚀 P0: 使用Cross-Encoder进行精排打分（支持缓存）
        if cross_encoder and not use_simple:
            # 获取模型标识符（支持多种 CrossEncoder 结构）
            ce_model_identifier = "default"
            try:
                # 方法1: 从 model_name 属性获取
                if hasattr(cross_encoder, 'model_name'):
                    ce_model_identifier = cross_encoder.model_name
                # 方法2: 从 config._name_or_path 获取
                elif hasattr(cross_encoder, 'config') and hasattr(cross_encoder.config, '_name_or_path'):
                    ce_model_identifier = cross_encoder.config._name_or_path
                # 方法3: 从 _name_or_path 获取
                elif hasattr(cross_encoder, '_name_or_path'):
                    ce_model_identifier = cross_encoder._name_or_path
                # 方法4: 从模型的第一层获取
                elif hasattr(cross_encoder, 'model') and hasattr(cross_encoder.model, 'config'):
                    ce_model_identifier = cross_encoder.model.config._name_or_path
            except Exception as e:
                logging.warning(f"无法获取 Cross-Encoder 模型名称，使用默认值: {e}")
            
            ce_model_identifier = ce_model_identifier.replace('/', '_').replace('\\', '_')
            
            # 批量检查缓存
            cached_scores = []
            pairs_to_predict = []
            pairs_to_predict_indices = []
            
            for idx, pair in enumerate(candidate_pairs):
                text_a, text_b = pair[0], pair[1]
                cached_score = cache_manager.get_cross_encoder_score(ce_model_identifier, text_a, text_b)
                if cached_score is not None:
                    cached_scores.append((idx, cached_score))
                else:
                    pairs_to_predict.append(pair)
                    pairs_to_predict_indices.append(idx)
            
            # 初始化分数数组
            raw_scores = [None] * len(candidate_pairs)
            
            # 填充缓存命中的分数
            for idx, score in cached_scores:
                raw_scores[idx] = score
            
            # 批量预测未缓存的文本对
            if pairs_to_predict:
                new_scores = cross_encoder.predict(pairs_to_predict, show_progress_bar=False)
                
                # 🧹 清理GPU缓存（防止CUDA累积错误）
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()
                except Exception:
                    pass
                
                for i, score in enumerate(new_scores):
                    original_idx = pairs_to_predict_indices[i]
                    raw_scores[original_idx] = score
                    # 保存到缓存
                    text_a, text_b = pairs_to_predict[i]
                    cache_manager.set_cross_encoder_score(ce_model_identifier, text_a, text_b, float(score))
            
            # Sigmoid归一化
            text_scores = 1 / (1 + np.exp(-np.array(raw_scores)))
        else:
            # 简化模式或无 CrossEncoder：
            if use_simple:
                # 已按 difflib 选出候选，这里再次取 difflib 分数作为文本相似度
                a_text = f"{row_a.get('cleaned_商品名称','')} {row_a.get('cleaned_一级分类','')} {row_a.get('cleaned_三级分类','')}"
                text_scores = []
                for row_b in valid_candidates:
                    b_text = f"{row_b.get('cleaned_商品名称','')} {row_b.get('cleaned_一级分类','')} {row_b.get('cleaned_三级分类','')}"
                    try:
                        text_scores.append(difflib.SequenceMatcher(None, a_text, b_text).ratio())
                    except Exception:
                        text_scores.append(0.0)
            else:
                # 使用向量余弦相似度
                text_scores = [sim_matrix[i, df_b.index.get_loc(row.name)] for row in valid_candidates]

        for idx, row_b in enumerate(valid_candidates):
            text_sim = text_scores[idx]
            
            # 计算品牌、分类、规格等特征的相似度
            brand_sim, cat_sim, specs_sim, _ = calculate_feature_similarity(row_a, row_b)

            # 计算综合得分（对品牌完全一致给予轻微加成）
            brand_bonus = 0.05 if (params.get('require_brand_match', False) and brand_sim == 1) else 0.0
            composite_score = (
                text_sim * params.get('text_weight', 0.6) +
                brand_sim * params.get('brand_weight', 0.2) +
                cat_sim * params.get('category_weight', 0.1) +
                specs_sim * params.get('specs_weight', 0.1) +
                brand_bonus
            )

            if composite_score > best_overall_score and composite_score >= params['composite_threshold']:
                best_overall_score = composite_score
                best_match_row_b = row_b

        if best_match_row_b is not None:
            match_info = {}
            for col in df_a.columns.difference(['vector', 'category_id']):
                match_info[f"{col}_{name_a}"] = row_a[col]
            for col in df_b.columns.difference(['vector', 'category_id', '原价_numeric']):
                match_info[f"{col}_{name_b}"] = best_match_row_b[col]
            
            match_info['composite_similarity_score'] = best_overall_score
            # 保存原始索引，用于后续从未匹配列表中排除
            match_info[f'index_{name_a}'] = row_a.name
            match_info[f'index_{name_b}'] = best_match_row_b.name
            matched_products.append(match_info)

    # 🔧 【修复】竞对侧去重：记录所有原始索引，避免CD商品被误判为独有商品
    matched_df = pd.DataFrame(matched_products)
    if not matched_df.empty and f'index_{name_b}' in matched_df.columns:
        before_dedup = len(matched_df)
        
        # ✅ 关键修复：去重前先记录所有原始索引（包括即将被删除的CD商品）
        all_matched_a_indices = matched_df[f'index_{name_a}'].tolist()
        all_matched_b_indices = matched_df[f'index_{name_b}'].tolist()
        
        # 按得分排序，保留每个竞对商品的最佳匹配
        matched_df = matched_df.sort_values('composite_similarity_score', ascending=False)
        matched_df = matched_df.drop_duplicates(subset=[f'index_{name_b}'], keep='first')
        after_dedup = len(matched_df)
        
        if before_dedup > after_dedup:
            print(f"   🔧 竞对侧去重: 移除 {before_dedup - after_dedup} 个重复匹配（保留得分最高的匹配）")
        
        # ✅ 将原始索引保存为DataFrame属性，供调用方使用
        matched_df.attrs['all_matched_indices_a'] = all_matched_a_indices
        matched_df.attrs['all_matched_indices_b'] = all_matched_b_indices
    
    return matched_df

class DifferentialMatchConfig:
    """差异品匹配动态权重配置"""
    
    # 是否强制要求三级分类一致（默认False，允许三级分类不同但会标记警告）
    REQUIRE_CAT3_MATCH = True  # 🔧 开启三级分类强制匹配，与软分类阶段保持一致
    
    # 品类权重配置
    CATEGORY_WEIGHTS = {
        # 差异品匹配：各品类阈值配置（优化：提高下限，减少不相关匹配）
        # 饮料类：品牌多，名称相似，价格敏感
        '饮料': {
            'similarity_min': 0.42,  # 🔧 提高下限 0.35→0.42
            'similarity_max': 0.65,
            'price_tolerance': 0.35,
            'description': '品牌众多，价格敏感'
        },
        # 零食类：品类繁杂，规格多样
        '休闲食品': {
            'similarity_min': 0.40,  # 🔧 提高下限 0.30→0.40
            'similarity_max': 0.62,
            'price_tolerance': 0.40,
            'description': '品类繁杂，规格多样'
        },
        '粮油调味': {
            'similarity_min': 0.42,  # 🔧 提高下限 0.35→0.42
            'similarity_max': 0.65,
            'price_tolerance': 0.50,
            'description': '品牌差异大，价格范围广'
        },
        '方便食品': {
            'similarity_min': 0.40,  # 🔧 提高下限 0.30→0.40
            'similarity_max': 0.62,
            'price_tolerance': 0.45,
            'description': '品类多样，规格差异大'
        },
        '乳品烘焙': {
            'similarity_min': 0.42,  # 🔧 提高下限 0.35→0.42
            'similarity_max': 0.65,
            'price_tolerance': 0.40,
            'description': '品牌集中，价格稳定'
        },
        # 日用品类：品牌差异大，功能相似即可
        '个人护理': {
            'similarity_min': 0.40,  # 🔧 提高下限 0.32→0.40
            'similarity_max': 0.62,
            'price_tolerance': 0.40,
            'description': '功能相似即可，品牌差异大'
        },
        '家居用品': {
            'similarity_min': 0.40,  # 🔧 提高下限 0.30→0.40
            'similarity_max': 0.62,
            'price_tolerance': 0.40,
            'description': '功能导向，价格差异大'
        },
        '清洁用品': {
            'similarity_min': 0.40,  # 🔧 提高下限 0.32→0.40
            'similarity_max': 0.62,
            'price_tolerance': 0.45,
            'description': '功能主导，品牌多样'
        },
        # 生鲜类：规格和价格都很敏感
        '水果': {
            'similarity_min': 0.45,  # 🔧 提高下限 0.40→0.45
            'similarity_max': 0.70,
            'price_tolerance': 0.50,
            'description': '季节性强，价格波动大'
        },
        '蔬菜': {
            'similarity_min': 0.45,  # 🔧 提高下限 0.40→0.45
            'similarity_max': 0.70,
            'price_tolerance': 0.50,
            'description': '季节性强，价格波动大'
        },
        '肉禽蛋': {
            'similarity_min': 0.42,  # 🔧 提高下限 0.38→0.42
            'similarity_max': 0.68,
            'price_tolerance': 0.45,
            'description': '品类明确，价格敏感'
        },
        '海鲜水产': {
            'similarity_min': 0.42,  # 🔧 提高下限 0.35→0.42
            'similarity_max': 0.65,
            'price_tolerance': 0.50,
            'description': '规格差异大，价格波动'
        },
        # 默认配置
        'default': {
            'similarity_min': 0.40,  # 🔧 提高下限 0.32→0.40
            'similarity_max': 0.65,
            'price_tolerance': 0.40,
            'description': '未分类商品默认策略'
        }
    }
    
    @classmethod
    def get_config(cls, category):
        """
        获取品类配置
        支持模糊匹配：如果精确匹配失败，尝试包含匹配
        """
        # 精确匹配
        if category in cls.CATEGORY_WEIGHTS:
            return cls.CATEGORY_WEIGHTS[category]
        
        # 模糊匹配（包含关系）
        for key, config in cls.CATEGORY_WEIGHTS.items():
            if key in str(category) or str(category) in key:
                return config
        
        # 返回默认配置
        return cls.CATEGORY_WEIGHTS['default']
    
    @classmethod
    def get_config_info(cls, category):
        """获取配置说明"""
        config = cls.get_config(category)
        return f"相似度[{config['similarity_min']}-{config['similarity_max']}], 价格±{int(config['price_tolerance']*100)}%"

def deduplicate_unique_products(df, store_name):
    """
    对独有商品按商品名称去重
    
    Args:
        df: 独有商品DataFrame
        store_name: 店铺名称
    
    Returns:
        去重后的DataFrame，包含SKU数量统计
    """
    if df.empty:
        return df
    
    # 按商品名称分组统计
    agg_dict = {
        '售价': 'first',  # 保留第一条记录的售价
        '原价': 'first',
        '美团一级分类': 'first',
        '美团三级分类': 'first',
        '条码': lambda x: ', '.join([str(b) for b in x.dropna().unique() if str(b) != 'nan']),  # 合并条码
        '库存': 'sum',  # 库存求和
        '月售': 'sum',  # 月售求和
    }
    
    # ⭐关键：保留vector列供差异品分析使用
    if 'vector' in df.columns:
        agg_dict['vector'] = lambda x: x.iloc[0]  # 保留第一条记录的向量（保持原格式）
    
    grouped = df.groupby('商品名称', as_index=False).agg(agg_dict)
    
    # 添加SKU数量列
    sku_counts = df.groupby('商品名称').size().reset_index(name='SKU数量')
    grouped = grouped.merge(sku_counts, on='商品名称', how='left')
    
    # 重新排序列
    cols_order = ['商品名称', 'SKU数量', '美团一级分类', '美团三级分类', '售价', '原价', '库存', '月售', '条码']
    cols_order = [c for c in cols_order if c in grouped.columns]
    other_cols = [c for c in grouped.columns if c not in cols_order]
    grouped = grouped[cols_order + other_cols]
    
    # 按分类和售价排序
    if '美团一级分类' in grouped.columns:
        grouped = grouped.sort_values(['美团一级分类', '售价'], ascending=[True, False])
    
    print(f"   去重前: {len(df)} 条，去重后: {len(grouped)} 条独有商品")
    return grouped

def find_differential_products(df_a_unique, df_b_unique, name_a, name_b, cfg=None):
    """
    差异品分析：在独有商品中找同分类、价格相似但不完全相同的商品
    
    Args:
        df_a_unique: 本店独有商品
        df_b_unique: 竞对独有商品
        name_a: 本店名称
        name_b: 竞对名称
        cfg: 配置对象（用于获取向量模型）
    
    Returns:
        差异品对比DataFrame
    """
    if df_a_unique.empty or df_b_unique.empty:
        return pd.DataFrame()
    
    print(f"\n🔍 开始差异品分析...")
    print(f"   本店独有: {len(df_a_unique)} 条，竞对独有: {len(df_b_unique)} 条")
    print(f"   匹配模式: {'✅一对一最佳匹配' if True else '多对多'} | 三级分类: {'⚠️强制一致' if DifferentialMatchConfig.REQUIRE_CAT3_MATCH else '✅允许不同(标记警告)'}")
    
    differential_matches = []
    
    # 确保必要的列存在
    required_cols = ['商品名称', '售价', '美团一级分类', 'vector']
    for col in required_cols:
        if col not in df_a_unique.columns or col not in df_b_unique.columns:
            print(f"   ⚠️ 缺少必要列 '{col}'，跳过差异品分析")
            return pd.DataFrame()
    
    # 诊断信息：检查共同分类
    cats_a = set(df_a_unique['美团一级分类'].dropna().unique())
    cats_b = set(df_b_unique['美团一级分类'].dropna().unique())
    common_cats = cats_a & cats_b
    print(f"   一级分类: A店{len(cats_a)}个, B店{len(cats_b)}个, 共同{len(common_cats)}个")
    
    # 检查三级分类覆盖
    if '美团三级分类' in df_a_unique.columns and '美团三级分类' in df_b_unique.columns:
        cats3_a = set(df_a_unique['美团三级分类'].dropna().unique())
        cats3_b = set(df_b_unique['美团三级分类'].dropna().unique())
        common_cats3 = cats3_a & cats3_b
        print(f"   三级分类: A店{len(cats3_a)}个, B店{len(cats3_b)}个, 共同{len(common_cats3)}个")
    
    if not common_cats:
        print(f"   ⚠️ 没有共同的一级分类，无法匹配差异品")
        return pd.DataFrame()
    
    # 智能价格选择：优先使用原价，原价无效则使用售价
    df_a_unique = df_a_unique.copy()
    df_b_unique = df_b_unique.copy()
    
    # 转换原价和售价为数值（使用.get()安全获取列，避免KeyError）
    if '原价' in df_a_unique.columns:
        df_a_unique['原价_numeric'] = pd.to_numeric(df_a_unique['原价'], errors='coerce')
    else:
        df_a_unique['原价_numeric'] = pd.NA
    df_a_unique['售价_numeric'] = pd.to_numeric(df_a_unique['售价'], errors='coerce')
    
    if '原价' in df_b_unique.columns:
        df_b_unique['原价_numeric'] = pd.to_numeric(df_b_unique['原价'], errors='coerce')
    else:
        df_b_unique['原价_numeric'] = pd.NA
    df_b_unique['售价_numeric'] = pd.to_numeric(df_b_unique['售价'], errors='coerce')
    
    # 智能价格选择：原价 > 0 优先，否则用售价
    df_a_unique['对比价格'] = df_a_unique.apply(
        lambda row: row['原价_numeric'] if (pd.notna(row['原价_numeric']) and row['原价_numeric'] > 0) else row['售价_numeric'],
        axis=1
    )
    df_a_unique['价格来源'] = df_a_unique.apply(
        lambda row: '原价' if (pd.notna(row['原价_numeric']) and row['原价_numeric'] > 0) else '售价',
        axis=1
    )
    
    df_b_unique['对比价格'] = df_b_unique.apply(
        lambda row: row['原价_numeric'] if (pd.notna(row['原价_numeric']) and row['原价_numeric'] > 0) else row['售价_numeric'],
        axis=1
    )
    df_b_unique['价格来源'] = df_b_unique.apply(
        lambda row: '原价' if (pd.notna(row['原价_numeric']) and row['原价_numeric'] > 0) else '售价',
        axis=1
    )
    
    # 按一级分类分组匹配
    categories_a = df_a_unique['美团一级分类'].unique()
    matched_count = 0
    
    # 调试：检查价格数据
    valid_price_a = df_a_unique['对比价格'].notna() & (df_a_unique['对比价格'] > 0)
    valid_price_b = df_b_unique['对比价格'].notna() & (df_b_unique['对比价格'] > 0)
    orig_count_a = (df_a_unique['价格来源'] == '原价').sum()
    orig_count_b = (df_b_unique['价格来源'] == '原价').sum()
    print(f"   💰 价格检查: A店有效价格 {valid_price_a.sum()}/{len(df_a_unique)} (原价{orig_count_a}, 售价{valid_price_a.sum()-orig_count_a})")
    print(f"   💰 价格检查: B店有效价格 {valid_price_b.sum()}/{len(df_b_unique)} (原价{orig_count_b}, 售价{valid_price_b.sum()-orig_count_b})")
    
    print(f"   开始分类匹配（共 {len(common_cats)} 个共同分类）...")
    
    # 导入进度条
    from tqdm import tqdm
    
    # 使用进度条遍历分类
    for idx, category in enumerate(tqdm(categories_a, desc="   Differential Analysis", ncols=100, ascii=True), 1):
        # 获取该分类的动态权重配置
        config = DifferentialMatchConfig.get_config(category)
        config_info = DifferentialMatchConfig.get_config_info(category)
        
        # 🔧 调试：输出前3个分类的配置信息
        if idx <= 3:
            tqdm.write(f"   📋 [{category}] 配置: {config_info} (相似度范围: {config['similarity_min']:.2f}-{config['similarity_max']:.2f})")
        
        # 筛选同分类商品
        df_a_cat = df_a_unique[df_a_unique['美团一级分类'] == category].copy()
        df_b_cat = df_b_unique[df_b_unique['美团一级分类'] == category].copy()
        
        # 调试：检查对比价格列是否存在
        if idx <= 3 and ('对比价格' not in df_a_cat.columns or '对比价格' not in df_b_cat.columns):
            tqdm.write(f"   ⚠️ [{category}] 缺少对比价格列!")
            tqdm.write(f"       A列: {[c for c in df_a_cat.columns if '价格' in c or '价' in c]}")
            tqdm.write(f"       B列: {[c for c in df_b_cat.columns if '价格' in c or '价' in c]}")
        
        if df_a_cat.empty or df_b_cat.empty:
            continue
        
        # 计算向量相似度
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np
            
            # 诊断：检查vector格式（仅前3个分类）
            if idx <= 3:
                sample_vec_a = df_a_cat['vector'].iloc[0] if len(df_a_cat) > 0 else None
                sample_vec_b = df_b_cat['vector'].iloc[0] if len(df_b_cat) > 0 else None
                tqdm.write(f"       🔍 Vector格式: A类型={type(sample_vec_a).__name__}, B类型={type(sample_vec_b).__name__}")
                if sample_vec_a is not None:
                    if isinstance(sample_vec_a, (list, np.ndarray)):
                        tqdm.write(f"       🔍 Vector长度: A={len(sample_vec_a)}, 首5值={sample_vec_a[:5] if len(sample_vec_a)>=5 else sample_vec_a}")
            
            vectors_a = np.array(df_a_cat['vector'].tolist())
            vectors_b = np.array(df_b_cat['vector'].tolist())
            sim_matrix = cosine_similarity(vectors_a, vectors_b)
        except Exception as e:
            if idx <= 3:
                import traceback
                tqdm.write(f"   ⚠️ [{category}] 计算相似度失败: {e}")
                tqdm.write(f"       详细错误: {traceback.format_exc()[:200]}")
            continue
        
        category_matches = 0
        debug_info = {
            'total_a': len(df_a_cat),
            'total_b': len(df_b_cat),
            'valid_price_a': 0,
            'valid_price_b': 0,
            'similarity_in_range': 0,
            'price_in_range': 0,
            'cat3_mismatch': 0,
            'final_matches': 0
        }
        
        # 用于记录每个商品的最佳匹配（一对一）
        best_matches_a = {}  # {idx_a: (idx_b, similarity, match_record)}
        
        # 遍历本店商品，找差异品
        for i, row_a in df_a_cat.iterrows():
            price_a = row_a['对比价格']
            if pd.isna(price_a) or price_a <= 0:
                continue
            
            debug_info['valid_price_a'] += 1
            
            # 使用动态价格范围
            price_min = price_a * (1 - config['price_tolerance'])
            price_max = price_a * (1 + config['price_tolerance'])
            
            # 获取该商品在相似度矩阵中的索引
            idx_a = df_a_cat.index.get_loc(i)
            similarities = sim_matrix[idx_a]
            
            # 找到相似度在动态范围内且价格相似的商品
            for j, row_b in df_b_cat.iterrows():
                idx_b = df_b_cat.index.get_loc(j)
                similarity = similarities[idx_b]
                
                # 使用动态相似度范围检查
                if similarity < config['similarity_min'] or similarity > config['similarity_max']:
                    continue
                
                debug_info['similarity_in_range'] += 1
                
                # 调试：检查B店价格数据
                price_b = row_b.get('对比价格', None)
                if price_b is None or pd.isna(price_b) or price_b <= 0:
                    # 第一次遇到时打印调试信息
                    if debug_info['similarity_in_range'] == 1 and idx <= 3:
                        tqdm.write(f"       ⚠️ 调试: B店row缺少有效价格 - 对比价格={price_b}, 原价={row_b.get('原价_numeric')}, 售价={row_b.get('售价_numeric')}")
                    continue
                
                debug_info['valid_price_b'] += 1
                
                # 价格范围检查
                if price_b < price_min or price_b > price_max:
                    continue
                
                debug_info['price_in_range'] += 1
                
                # 三级分类检查：优先匹配相同三级分类
                cat3_a = row_a.get('美团三级分类', '')
                cat3_b = row_b.get('美团三级分类', '')
                cat3_match = False
                cat3_warning = ''
                
                if cat3_a and cat3_b and str(cat3_a) != 'nan' and str(cat3_b) != 'nan':
                    if cat3_a == cat3_b:
                        cat3_match = True
                        cat3_warning = ''
                    else:
                        # 三级分类不同，但允许匹配（可能是分类错误）
                        cat3_match = False
                        cat3_warning = f'⚠️三级分类不同({cat3_a}≠{cat3_b})'
                        debug_info['cat3_mismatch'] += 1
                        # ⚠️ 如果启用严格三级分类匹配，跳过不一致的商品
                        if DifferentialMatchConfig.REQUIRE_CAT3_MATCH:
                            continue  # 跳过三级分类不一致的商品
                
                # 🆕 品牌检查：排除同品牌商品（防止"可口可乐330ml" vs "可口可乐500ml"被判为差异品）
                brand_a = row_a.get('standardized_brand', '').strip().lower()
                brand_b = row_b.get('standardized_brand', '').strip().lower()
                
                # 如果两个商品品牌相同且都不为空，跳过（不是真正的差异品）
                if brand_a and brand_b and brand_a == brand_b:
                    debug_info['same_brand_skipped'] = debug_info.get('same_brand_skipped', 0) + 1
                    continue  # 跳过同品牌商品
                
                # 构建差异品匹配记录 - 完整的ABAB格式
                price_diff_pct = ((price_b - price_a) / price_a) * 100
                
                # 基础字段 - ABAB格式
                match_record = {
                    f'商品名称_{name_a}': row_a['商品名称'],
                    f'商品名称_{name_b}': row_b['商品名称'],
                    f'美团一级分类_{name_a}': category,
                    f'美团一级分类_{name_b}': category,
                }
                
                # 三级分类 - ABAB格式
                if '美团三级分类' in row_a.index and '美团三级分类' in row_b.index:
                    match_record[f'美团三级分类_{name_a}'] = row_a.get('美团三级分类', '')
                    match_record[f'美团三级分类_{name_b}'] = row_b.get('美团三级分类', '')
                
                # 原价 - ABAB格式
                match_record[f'原价_{name_a}'] = row_a.get('原价_numeric', '')
                match_record[f'原价_{name_b}'] = row_b.get('原价_numeric', '')
                
                # 售价 - ABAB格式
                match_record[f'售价_{name_a}'] = row_a.get('售价_numeric', '')
                match_record[f'售价_{name_b}'] = row_b.get('售价_numeric', '')
                
                # 月售 - ABAB格式
                if '月售' in row_a.index and '月售' in row_b.index:
                    match_record[f'月售_{name_a}'] = row_a.get('月售', 0)
                    match_record[f'月售_{name_b}'] = row_b.get('月售', 0)
                
                # 库存 - ABAB格式
                if '库存' in row_a.index and '库存' in row_b.index:
                    match_record[f'库存_{name_a}'] = row_a.get('库存', 0)
                    match_record[f'库存_{name_b}'] = row_b.get('库存', 0)
                
                # 分析字段（放在最后）
                match_record[f'对比价格来源_{name_a}'] = row_a['价格来源']
                match_record[f'对比价格来源_{name_b}'] = row_b['价格来源']
                match_record['price_diff_pct'] = round(price_diff_pct, 1)
                match_record['similarity_score'] = round(similarity, 3)
                match_record['差异分析'] = '同类替代品' if similarity > 0.45 else '同类相关品'
                match_record['分类一致性'] = '三级分类一致' if cat3_match else cat3_warning if cat3_warning else '无三级分类'
                
                # ⭐ 一对一最佳匹配：只保留每个A店商品相似度最高的那个B店商品
                if i not in best_matches_a:
                    best_matches_a[i] = (j, similarity, match_record)
                else:
                    # 如果已有匹配，比较相似度，保留更好的
                    _, prev_sim, _ = best_matches_a[i]
                    if similarity > prev_sim:
                        best_matches_a[i] = (j, similarity, match_record)
        
        # 将最佳匹配添加到结果中
        for idx_a, (idx_b, sim, match_record) in best_matches_a.items():
            differential_matches.append(match_record)
            category_matches += 1
            debug_info['final_matches'] += 1
        
        # 每个分类处理后显示进度
        if category_matches > 0:
            matched_count += category_matches
            cat3_mismatch_pct = (debug_info['cat3_mismatch'] / category_matches * 100) if category_matches > 0 else 0
            same_brand_skipped = debug_info.get('same_brand_skipped', 0)
            tqdm.write(f"   ✅ [{category}] 找到 {category_matches} 对差异品 ({config_info}){' | 三级分类不一致:'+str(debug_info['cat3_mismatch'])+'对' if debug_info['cat3_mismatch'] > 0 else ''}{' | 同品牌已排除:'+str(same_brand_skipped)+'对' if same_brand_skipped > 0 else ''}")
        elif idx <= 5:  # 前5个显示详细调试（增加到5个）
            tqdm.write(f"   ⚪ [{category}] 0对 ({config_info})")
            tqdm.write(f"       🔍 漏斗: A商品{debug_info['total_a']} → A有效价格{debug_info['valid_price_a']} → 相似度符合{debug_info['similarity_in_range']} → B有效价格{debug_info['valid_price_b']} → 价格符合{debug_info['price_in_range']} → 三级分类检查后{debug_info['price_in_range']-debug_info['cat3_mismatch']} → 一对一最佳匹配{debug_info['final_matches']}")
            
            # 额外诊断：显示实际相似度分布（仅前3个分类）
            if idx <= 3 and len(sim_matrix) > 0:
                sim_flat = sim_matrix.flatten()
                sim_in_range = sim_flat[(sim_flat >= config['similarity_min']) & (sim_flat <= config['similarity_max'])]
                tqdm.write(f"       📊 相似度: 最大{sim_flat.max():.3f}, 均值{sim_flat.mean():.3f}, 最小{sim_flat.min():.3f}, 在范围内{len(sim_in_range)}/{len(sim_flat)}")
    
    if not differential_matches:
        print(f"   ❌ 未找到符合条件的差异品")
        print(f"\n   � 详细诊断:")
        print(f"      • 共同分类数: {len(common_cats)}")
        print(f"      • A店有效价格: {valid_price_a.sum()}/{len(df_a_unique)}")
        print(f"      • B店有效价格: {valid_price_b.sum()}/{len(df_b_unique)}")
        print(f"      • vector列存在: A={('vector' in df_a_unique.columns)}, B={('vector' in df_b_unique.columns)}")
        print(f"\n   �💡 可能原因:")
        print(f"      1. ⭐去重后缺少vector列（已修复，请重新运行）")
        print(f"      2. 价格差异超出各品类动态容差范围（饮料±35%, 休闲食品±40%, 生鲜±50%等）")
        print(f"      3. 相似度不在各品类动态范围内（如饮料0.30-0.60, 休闲食品0.25-0.60等）")
        print(f"      4. 一级分类不匹配（需要两店有共同的分类）")
        print(f"      5. 商品价格缺失或为0")
        print(f"\n   🔧 建议操作:")
        print(f"      → 重新运行完整比价分析（已修复vector列保留问题）")
        print(f"      → 如仍然0匹配，可临时放宽阈值测试")
        return pd.DataFrame()
    
    df_differential = pd.DataFrame(differential_matches)
    
    # 统计三级分类匹配情况
    cat3_mismatch = df_differential[df_differential['分类一致性'].str.contains('⚠️', na=False)]
    if len(cat3_mismatch) > 0:
        print(f"   ⚠️  发现 {len(cat3_mismatch)} 对商品三级分类不一致（可能存在分类错误）")
    
    # 按相似度降序排序
    df_differential = df_differential.sort_values('similarity_score', ascending=False)
    
    print(f"   ✅ 找到 {len(df_differential)} 对差异品匹配")
    return df_differential

def analyze_category_gaps(df_a_unique, df_b_unique, name_a, name_b):
    """
    品类缺口分析：找出竞对有但本店没有的细分品类（商品明细展开）
    
    Returns:
        品类缺口分析DataFrame（每个商品一行）
    """
    if df_a_unique.empty or df_b_unique.empty:
        return pd.DataFrame()
    
    print(f"\n📊 开始品类缺口分析...")
    
    # 统计各店的分类组合
    if '美团三级分类' in df_a_unique.columns and '美团三级分类' in df_b_unique.columns:
        # 按一级+三级组合分析
        df_a_unique['分类组合'] = df_a_unique['美团一级分类'].astype(str) + ' > ' + df_a_unique['美团三级分类'].astype(str)
        df_b_unique['分类组合'] = df_b_unique['美团一级分类'].astype(str) + ' > ' + df_b_unique['美团三级分类'].astype(str)
    else:
        # 只按一级分类分析
        df_a_unique['分类组合'] = df_a_unique['美团一级分类'].astype(str)
        df_b_unique['分类组合'] = df_b_unique['美团一级分类'].astype(str)
    
    # 找出竞对独有的分类
    categories_a = set(df_a_unique['分类组合'].unique())
    categories_b = set(df_b_unique['分类组合'].unique())
    gap_categories = categories_b - categories_a
    
    if not gap_categories:
        print(f"   本店品类覆盖完整，无明显缺口")
        return pd.DataFrame()
    
    # 🔧 方案A：展开所有商品明细
    gap_products = []
    total_gap_products = 0
    
    for category in sorted(gap_categories):
        cat_products = df_b_unique[df_b_unique['分类组合'] == category].copy()
        
        # 转换数值列
        cat_products['售价_numeric'] = pd.to_numeric(cat_products['售价'], errors='coerce')
        cat_products['原价_numeric'] = pd.to_numeric(cat_products.get('原价', 0), errors='coerce')
        cat_products['月售_numeric'] = pd.to_numeric(cat_products.get('月售', 0), errors='coerce')
        cat_products['库存_numeric'] = pd.to_numeric(cat_products.get('库存', 0), errors='coerce')
        
        # 按月售降序排序（销量高的在前）
        cat_products = cat_products.sort_values('月售_numeric', ascending=False)
        
        # 构建每个商品的记录
        for _, product in cat_products.iterrows():
            gap_products.append({
                '缺失品类': category,
                '商品名称': product.get('商品名称', ''),
                '美团一级分类': product.get('美团一级分类', ''),
                '美团三级分类': product.get('美团三级分类', ''),
                '售价': product.get('售价_numeric', ''),
                '原价': product.get('原价_numeric', ''),
                '月售': product.get('月售_numeric', ''),
                '库存': product.get('库存_numeric', ''),
                '条码': product.get('条码', ''),
                f'店铺_{name_b}': name_b,
                '建议': '考虑引进',
            })
            total_gap_products += 1
    
    if not gap_products:
        return pd.DataFrame()
    
    df_gaps = pd.DataFrame(gap_products)
    
    # 调整列顺序，把关键信息放前面
    cols_order = ['缺失品类', '商品名称', '美团一级分类', '美团三级分类', '售价', '原价', 
                  '月售', '库存', '条码', f'店铺_{name_b}', '建议']
    # 保留实际存在的列
    cols_order = [col for col in cols_order if col in df_gaps.columns]
    df_gaps = df_gaps[cols_order]
    
    print(f"   ✅ 发现 {len(gap_categories)} 个品类缺口，共 {total_gap_products} 个商品")
    return df_gaps

# ========================================
# 🆕 成本预测模块 (第一阶段：加价率法 + 售价加权优化)
# ========================================

def calculate_markup_rate(df, cost_col='成本', price_col='原价', markup_col_suffix='', use_weights=True):
    """
    计算加价率 = 价格 / 成本
    
    【多价格支持】可计算原价加价率或售价加价率：
    - 原价加价率：反映商品正常定价策略（稳定）
    - 售价加价率：反映实际利润空间（考虑促销）
    
    【方案A: 加权加价率优化】🆕
    - 按销量加权：月售高的商品权重大
    - 智能回退：无月售数据时使用简单平均
    - 向后兼容：use_weights=False 时使用原逻辑
    
    Args:
        df: 商品数据
        cost_col: 成本列名
        price_col: 价格列名（'原价' 或 '售价'）
        markup_col_suffix: 加价率列后缀（区分原价和售价加价率）
        use_weights: 是否使用销量加权（默认True）
    
    Returns:
        df: 添加了 markup_rate 列和可选的 sample_weight 列的数据
    """
    if cost_col not in df.columns or price_col not in df.columns:
        return df
    
    # 计算加价率，避免除零
    df = df.copy()
    markup_col = f'markup_rate{markup_col_suffix}' if markup_col_suffix else 'markup_rate'
    
    df[markup_col] = df.apply(
        lambda row: row[price_col] / row[cost_col] if pd.notna(row[cost_col]) and row[cost_col] > 0 else None,
        axis=1
    )
    
    # 过滤异常值（加价率 < 1.0 或 > 10.0）
    df.loc[(df[markup_col] < 1.0) | (df[markup_col] > 10.0), markup_col] = None
    
    # 🆕 问题修复1: 过滤极端折扣商品的售价加价率（防止促销品污染统计）
    if price_col == '售价' and '原价' in df.columns:
        # 计算折扣率
        discount_rates = df['售价'] / df['原价']
        # 极端折扣商品（折扣率<50%）的售价加价率不参与统计
        extreme_discount_mask = (discount_rates < 0.50) & df[markup_col].notna()
        df.loc[extreme_discount_mask, markup_col] = None
        
        filtered_count = extreme_discount_mask.sum()
        if filtered_count > 0:
            print(f"      🛡️ 过滤极端折扣商品: {filtered_count}个（售价加价率不参与统计）")
    
    # 🆕 方案A: 计算样本权重（销量加权）
    if use_weights and '月售' in df.columns:
        weight_col = f'sample_weight{markup_col_suffix}' if markup_col_suffix else 'sample_weight'
        
        # 销量权重：月售越高，权重越大（对数缩放，避免极端值主导）
        df[weight_col] = df['月售'].fillna(1).apply(lambda x: np.log1p(x) + 1)  # log1p(x) = log(1+x)
        
        # 标准化权重（可选，便于调试）
        # df[weight_col] = df[weight_col] / df[weight_col].sum()
    
    return df


def validate_cost_prediction(predicted_cost, row, store_a_df=None, cfg=None):
    """
    【方案C: 成本预测异常检测】🆕
    
    检测并修正不合理的成本预测，减少极端错误。
    
    三大检测规则：
    1. 成本不能超过售价的80%（防止亏本预测）
    2. 加价率不能低于1.2（行业底线）
    3. 品牌加价率一致性检查（同品牌应接近）
    
    Args:
        predicted_cost: 预测的成本
        row: 当前商品数据（必须包含原价_B、售价_B等字段）
        store_a_df: 本店数据（用于品牌加价率查询，可选）
        cfg: 配置对象
    
    Returns:
        tuple: (adjusted_cost, adjusted_confidence, validation_flag)
            - adjusted_cost: 调整后的成本
            - adjusted_confidence: 调整后的置信度
            - validation_flag: 验证标记（'正常', '调整:成本过高', etc.）
    """
    if cfg is None:
        cfg = Config()
    
    if pd.isna(predicted_cost) or predicted_cost <= 0:
        return predicted_cost, 0.0, '无效预测'
    
    # 获取商品价格信息（兼容多种列名格式）
    sale_price_b = None
    orig_price_b = None
    
    for col_suffix in ['_B', f'_{cfg.STORE_B_NAME}', '']:
        if f'售价{col_suffix}' in row.index and pd.notna(row.get(f'售价{col_suffix}')):
            sale_price_b = row[f'售价{col_suffix}']
            break
    
    for col_suffix in ['_B', f'_{cfg.STORE_B_NAME}', '']:
        if f'原价{col_suffix}' in row.index and pd.notna(row.get(f'原价{col_suffix}')):
            orig_price_b = row[f'原价{col_suffix}']
            break
    
    if pd.isna(orig_price_b) or orig_price_b <= 0:
        return predicted_cost, 0.0, '缺少价格数据'
    
    # 使用售价（如果有），否则使用原价
    reference_price = sale_price_b if pd.notna(sale_price_b) and sale_price_b > 0 else orig_price_b
    
    # === 规则0: 极端折扣亏本销售检测（优先级最高）===
    if pd.notna(sale_price_b) and sale_price_b > 0 and pd.notna(orig_price_b) and orig_price_b > 0:
        discount_rate = sale_price_b / orig_price_b
        
        # 极端折扣场景（折扣率<30%，即打3折以下）
        if discount_rate < 0.30:
            min_cost_ratio = 0.85  # 成本至少是售价的85%
            min_allowed_cost = sale_price_b * min_cost_ratio
            
            if predicted_cost < min_allowed_cost:
                # 极端促销品，成本应接近售价（亏本或微利销售）
                adjusted_cost = sale_price_b * 0.90  # 调整为售价的90%
                adjusted_confidence = 0.55
                return adjusted_cost, adjusted_confidence, f'调整:极端折扣({discount_rate:.0%})亏本预测'
    
    # === 规则1: 成本不能超过售价的80% ===
    max_cost_ratio = 0.80  # 最大成本占比
    max_allowed_cost = reference_price * max_cost_ratio
    
    if predicted_cost > max_allowed_cost:
        adjusted_cost = reference_price * 0.70  # 调整为70%（更保守）
        adjusted_confidence = 0.40
        return adjusted_cost, adjusted_confidence, f'调整:成本过高(>{max_cost_ratio:.0%}售价)'
    
    # === 规则2: 售价加价率不能低于1.2（行业底线）===
    min_markup = 1.20  # 最低加价率
    # 🆕 问题修复2: 使用售价计算加价率（更能反映实际利润空间）
    current_markup = reference_price / predicted_cost
    
    if current_markup < min_markup:
        # 调整为最低1.5倍售价加价率
        adjusted_cost = reference_price / 1.50  # 🆕 使用售价而非原价
        adjusted_confidence = 0.50
        return adjusted_cost, adjusted_confidence, f'调整:售价加价率过低(<{min_markup})'
    
    # === 规则3: 品牌加价率一致性检查 ===
    if store_a_df is not None and len(store_a_df) > 0:
        # 提取品牌（兼容多种列名）
        brand = None
        for brand_col in ['品牌', '品牌_A', f'品牌_{cfg.STORE_A_NAME}']:
            if brand_col in row.index and pd.notna(row.get(brand_col)):
                brand = row[brand_col]
                break
        
        if brand and cfg.COST_COLUMN_NAME in store_a_df.columns and '原价' in store_a_df.columns:
            # 查找本店同品牌商品的平均加价率
            brand_col_in_df = None
            for col in ['品牌', 'standardized_brand']:
                if col in store_a_df.columns:
                    brand_col_in_df = col
                    break
            
            if brand_col_in_df:
                brand_products = store_a_df[store_a_df[brand_col_in_df] == brand]
                
                if len(brand_products) >= 3:  # 至少3个样本
                    # 计算品牌平均加价率
                    brand_markups = []
                    for _, prod in brand_products.iterrows():
                        if (pd.notna(prod.get('原价')) and prod['原价'] > 0 and
                            pd.notna(prod.get(cfg.COST_COLUMN_NAME)) and prod[cfg.COST_COLUMN_NAME] > 0):
                            brand_markups.append(prod['原价'] / prod[cfg.COST_COLUMN_NAME])
                    
                    if len(brand_markups) >= 3:
                        brand_avg_markup = np.median(brand_markups)  # 使用中位数（更稳健）
                        markup_diff = abs(current_markup - brand_avg_markup)
                        
                        # 如果差异>0.5（如品牌平均2.0，当前预测1.3或2.7），调整
                        if markup_diff > 0.5:
                            adjusted_cost = orig_price_b / brand_avg_markup
                            adjusted_confidence = 0.65
                            return adjusted_cost, adjusted_confidence, f'调整:品牌加价率({brand}平均{brand_avg_markup:.2f})'
    
    # 所有检查通过，预测合理
    return predicted_cost, None, '正常'


def predict_competitor_cost(matched_df, store_a_df, cfg=None):
    """
    预测竞对成本（基于本店品类加价率）
    
    策略：
    1. 条形码精确匹配 → 直接使用本店成本（置信度 0.95）
    2. 三级分类加价率 → 竞对价格 / 三级分类平均加价率（置信度根据样本量）
    3. 一级分类加价率 → 兜底方案（置信度较低）
    
    【🆕 售价加权优化】：
    - 主预测：基于原价加价率（稳定，反映定价策略）
    - 辅助预测：基于售价加价率（反映实际利润空间）
    - 加权融合：原价权重70% + 售价权重30%
    - 置信度调整：原价/售价一致性越高，置信度越高
    
    Args:
        matched_df: 匹配结果 DataFrame
        store_a_df: 本店原始数据（含成本）
        cfg: 配置对象
    
    Returns:
        matched_df: 添加了成本预测列的 DataFrame
    """
    if cfg is None:
        cfg = Config()
    
    cost_col = cfg.COST_COLUMN_NAME
    
    # 检查是否有成本数据
    if cost_col not in store_a_df.columns:
        print("   ⚠️  本店数据中未找到成本列，跳过成本预测")
        return matched_df
    
    print("\n" + "="*60)
    print("🧮 竞对成本预测分析")
    print("="*60)
    
    # 计算本店原价加价率和售价加价率
    store_a_with_markup = calculate_markup_rate(store_a_df.copy(), cost_col, '原价', '_原价', use_weights=True)
    if '售价' in store_a_df.columns and cfg.USE_SALE_PRICE_WEIGHT:
        store_a_with_markup = calculate_markup_rate(store_a_with_markup, cost_col, '售价', '_售价', use_weights=True)
    
    # 🆕 方案A: 使用加权平均计算品类加价率（按销量加权）
    def weighted_agg(df, value_col, weight_col):
        """加权聚合函数"""
        if weight_col not in df.columns or df[weight_col].isna().all():
            # 回退：无权重时使用简单平均
            return df[value_col].agg(['mean', 'std', 'count'])
        
        # 过滤有效数据
        valid_mask = df[value_col].notna() & df[weight_col].notna()
        valid_df = df[valid_mask]
        
        if len(valid_df) == 0:
            return pd.Series({'mean': None, 'std': None, 'count': 0})
        
        weights = valid_df[weight_col]
        values = valid_df[value_col]
        
        # 加权平均
        weighted_mean = np.average(values, weights=weights)
        
        # 加权标准差
        weighted_variance = np.average((values - weighted_mean) ** 2, weights=weights)
        weighted_std = np.sqrt(weighted_variance)
        
        return pd.Series({
            'mean': weighted_mean,
            'std': weighted_std,
            'count': len(valid_df)
        })
    
    # 按品类统计原价加价率（加权）
    if 'sample_weight_原价' in store_a_with_markup.columns:
        category_markup_orig_level3 = store_a_with_markup.groupby('美团三级分类').apply(
            lambda x: weighted_agg(x, 'markup_rate_原价', 'sample_weight_原价')
        ).dropna()
        
        category_markup_orig_level1 = store_a_with_markup.groupby('美团一级分类').apply(
            lambda x: weighted_agg(x, 'markup_rate_原价', 'sample_weight_原价')
        ).dropna()
    else:
        # 回退：无权重时使用原逻辑
        category_markup_orig_level3 = store_a_with_markup.groupby('美团三级分类').agg({
            'markup_rate_原价': ['mean', 'std', 'count']
        }).dropna()
        
        category_markup_orig_level1 = store_a_with_markup.groupby('美团一级分类').agg({
            'markup_rate_原价': ['mean', 'std', 'count']
        }).dropna()
    
    # 按品类统计售价加价率（如果启用，同样加权）
    category_markup_sale_level3 = pd.DataFrame()
    category_markup_sale_level1 = pd.DataFrame()
    if 'markup_rate_售价' in store_a_with_markup.columns and cfg.USE_SALE_PRICE_WEIGHT:
        if 'sample_weight_售价' in store_a_with_markup.columns:
            category_markup_sale_level3 = store_a_with_markup.groupby('美团三级分类').apply(
                lambda x: weighted_agg(x, 'markup_rate_售价', 'sample_weight_售价')
            ).dropna()
            
            category_markup_sale_level1 = store_a_with_markup.groupby('美团一级分类').apply(
                lambda x: weighted_agg(x, 'markup_rate_售价', 'sample_weight_售价')
            ).dropna()
        else:
            # 回退：无权重时使用原逻辑
            category_markup_sale_level3 = store_a_with_markup.groupby('美团三级分类').agg({
                'markup_rate_售价': ['mean', 'std', 'count']
            }).dropna()
            
            category_markup_sale_level1 = store_a_with_markup.groupby('美团一级分类').agg({
                'markup_rate_售价': ['mean', 'std', 'count']
            }).dropna()
    
    # 🆕 方案B: 计算品牌+分类组合加价率（多维度分层）
    brand_cat3_markup_orig = pd.DataFrame()
    brand_cat1_markup_orig = pd.DataFrame()
    brand_cat3_markup_sale = pd.DataFrame()
    brand_cat1_markup_sale = pd.DataFrame()
    
    MIN_BRAND_CATEGORY_SAMPLES = 3  # 品牌+分类最小样本数
    
    if '品牌' in store_a_with_markup.columns:
        # 品牌+三级分类（原价加价率）
        if 'sample_weight_原价' in store_a_with_markup.columns:
            brand_cat3_markup_orig = store_a_with_markup.groupby(['品牌', '美团三级分类']).apply(
                lambda x: weighted_agg(x, 'markup_rate_原价', 'sample_weight_原价') if len(x) >= MIN_BRAND_CATEGORY_SAMPLES else pd.Series({'mean': None, 'std': None, 'count': 0})
            ).dropna()
            
            brand_cat1_markup_orig = store_a_with_markup.groupby(['品牌', '美团一级分类']).apply(
                lambda x: weighted_agg(x, 'markup_rate_原价', 'sample_weight_原价') if len(x) >= MIN_BRAND_CATEGORY_SAMPLES else pd.Series({'mean': None, 'std': None, 'count': 0})
            ).dropna()
        
        # 品牌+分类（售价加价率）
        if 'markup_rate_售价' in store_a_with_markup.columns and cfg.USE_SALE_PRICE_WEIGHT:
            if 'sample_weight_售价' in store_a_with_markup.columns:
                brand_cat3_markup_sale = store_a_with_markup.groupby(['品牌', '美团三级分类']).apply(
                    lambda x: weighted_agg(x, 'markup_rate_售价', 'sample_weight_售价') if len(x) >= MIN_BRAND_CATEGORY_SAMPLES else pd.Series({'mean': None, 'std': None, 'count': 0})
                ).dropna()
                
                brand_cat1_markup_sale = store_a_with_markup.groupby(['品牌', '美团一级分类']).apply(
                    lambda x: weighted_agg(x, 'markup_rate_售价', 'sample_weight_售价') if len(x) >= MIN_BRAND_CATEGORY_SAMPLES else pd.Series({'mean': None, 'std': None, 'count': 0})
                ).dropna()
    
    # 🆕 方案B: 计算价格区间加价率
    def get_price_range(price):
        """将价格分配到区间"""
        if pd.isna(price) or price <= 0:
            return None
        if price < 10:
            return '0-10元'
        elif price < 30:
            return '10-30元'
        elif price < 50:
            return '30-50元'
        elif price < 100:
            return '50-100元'
        else:
            return '100元以上'
    
    price_range_markup_orig = pd.DataFrame()
    price_range_markup_sale = pd.DataFrame()
    
    store_a_with_markup['价格区间'] = store_a_with_markup['原价'].apply(get_price_range)
    
    if 'sample_weight_原价' in store_a_with_markup.columns:
        price_range_markup_orig = store_a_with_markup.groupby('价格区间').apply(
            lambda x: weighted_agg(x, 'markup_rate_原价', 'sample_weight_原价')
        ).dropna()
    
    if 'markup_rate_售价' in store_a_with_markup.columns and cfg.USE_SALE_PRICE_WEIGHT:
        if 'sample_weight_售价' in store_a_with_markup.columns:
            price_range_markup_sale = store_a_with_markup.groupby('价格区间').apply(
                lambda x: weighted_agg(x, 'markup_rate_售价', 'sample_weight_售价')
            ).dropna()
    
    print(f"   📊 本店加价率统计（方案A+B：销量加权 + 多维分层）：")
    print(f"      三级分类: {len(category_markup_orig_level3)}个")
    print(f"      一级分类: {len(category_markup_orig_level1)}个")
    if not brand_cat3_markup_orig.empty or not brand_cat1_markup_orig.empty:
        print(f"      🆕 品牌+三级分类: {len(brand_cat3_markup_orig)}个")
        print(f"      🆕 品牌+一级分类: {len(brand_cat1_markup_orig)}个")
    if not price_range_markup_orig.empty:
        print(f"      🆕 价格区间: {len(price_range_markup_orig)}个")
    if cfg.USE_SALE_PRICE_WEIGHT and not category_markup_sale_level3.empty:
        print(f"      售价加权模式: 启用（原价权重{cfg.ORIGINAL_PRICE_WEIGHT*100}% + 售价权重{cfg.SALE_PRICE_WEIGHT*100}%）")
    
    # 初始化预测列
    matched_df = matched_df.copy()
    matched_df['预测成本_B'] = None
    matched_df['预测成本_原价基准'] = None  # 🆕 保留原价基准预测
    matched_df['预测成本_售价基准'] = None  # 🆕 保留售价基准预测
    matched_df['预测方法'] = None
    matched_df['置信度'] = None
    # 🔧 修复：不要初始化成本_A为None，稍后从原始列复制
    # matched_df['成本_A'] = None
    matched_df['加价率_A'] = None
    
    # 获取列名
    barcode_col_a = f'条码_{cfg.STORE_A_NAME}' if f'条码_{cfg.STORE_A_NAME}' in matched_df.columns else '条码_A'
    barcode_col_b = f'条码_{cfg.STORE_B_NAME}' if f'条码_{cfg.STORE_B_NAME}' in matched_df.columns else '条码_B'
    cost_col_a = f'{cost_col}_{cfg.STORE_A_NAME}' if f'{cost_col}_{cfg.STORE_A_NAME}' in matched_df.columns else f'{cost_col}_A'
    orig_price_col_b = f'原价_{cfg.STORE_B_NAME}' if f'原价_{cfg.STORE_B_NAME}' in matched_df.columns else '原价_B'
    sale_price_col_b = f'售价_{cfg.STORE_B_NAME}' if f'售价_{cfg.STORE_B_NAME}' in matched_df.columns else '售价_B'
    cat3_col_a = f'美团三级分类_{cfg.STORE_A_NAME}' if f'美团三级分类_{cfg.STORE_A_NAME}' in matched_df.columns else '美团三级分类_A'
    cat1_col_a = f'美团一级分类_{cfg.STORE_A_NAME}' if f'美团一级分类_{cfg.STORE_A_NAME}' in matched_df.columns else '美团一级分类_A'
    
    # 🔧 修复：统一成本列名为成本_A
    if cost_col_a != '成本_A':
        if cost_col_a in matched_df.columns:
            matched_df['成本_A'] = matched_df[cost_col_a]
            print(f"   🔧 将成本列 {cost_col_a} 复制到 成本_A，非空数量: {matched_df['成本_A'].notna().sum()}")
        else:
            matched_df['成本_A'] = None
            print(f"   ⚠️  未找到成本列 {cost_col_a}，成本_A将为空")
    else:
        # cost_col_a 就是 成本_A，确保列存在
        if '成本_A' not in matched_df.columns:
            matched_df['成本_A'] = None
            print(f"   ⚠️  matched_df中不存在成本_A列，将为空")
    
    barcode_match_count = 0
    brand_cat3_match_count = 0  # 🆕 方案B: 品牌+三级分类计数
    cat3_match_count = 0
    brand_cat1_match_count = 0  # 🆕 方案B: 品牌+一级分类计数
    cat1_match_count = 0
    price_range_match_count = 0  # 🆕 方案B: 价格区间计数
    weighted_count = 0  # 🆕 售价加权预测计数
    
    for idx, row in matched_df.iterrows():
        # 🔧 修复：成本_A已经在上面复制好了，这里直接使用
        # if cost_col_a in matched_df.columns and pd.notna(row.get(cost_col_a)):
        #     matched_df.at[idx, '成本_A'] = row[cost_col_a]
        
        # 计算加价率
        if pd.notna(row.get('成本_A')) and pd.notna(row.get(orig_price_col_b)) and row[orig_price_col_b] > 0 and row['成本_A'] > 0:
            matched_df.at[idx, '加价率_A'] = row[orig_price_col_b] / row['成本_A']
        
        # 策略1: 条形码匹配
        # 🔧 修复：条码相同不代表成本相同，需要基于加价率预测竞对成本
        # 标记条码匹配状态，后续使用更高的置信度
        is_barcode_match = (barcode_col_a in matched_df.columns and barcode_col_b in matched_df.columns and
            pd.notna(row.get(barcode_col_a)) and pd.notna(row.get(barcode_col_b)) and
            str(row[barcode_col_a]) == str(row[barcode_col_b]))
        
        # 不再直接使用本店成本，继续使用加价率预测
        
        # 获取竞对价格
        orig_price_b = row.get(orig_price_col_b)
        sale_price_b = row.get(sale_price_col_b)
        
        if pd.isna(orig_price_b) or orig_price_b <= 0:
            continue
        
        # 🆕 获取品牌和分类信息（方案B）
        # 注意：品牌使用竞对的（brand_b），分类使用本店的（cat3/cat1），因为要匹配本店的加价率表
        brand_col_b = f'品牌_{cfg.STORE_B_NAME}' if f'品牌_{cfg.STORE_B_NAME}' in matched_df.columns else '品牌_B'
        brand_b = row.get(brand_col_b, '')
        
        # 🆕 方案B 优先级1: 品牌+三级分类加价率（最精准）
        # 使用竞对品牌 + 本店三级分类匹配本店的品牌+分类加价率
        cat3_a = row.get(cat3_col_a)
        if (pd.notna(brand_b) and brand_b != '' and 
            pd.notna(cat3_a) and 
            not brand_cat3_markup_orig.empty and 
            (brand_b, cat3_a) in brand_cat3_markup_orig.index):
            
            stats_orig = brand_cat3_markup_orig.loc[(brand_b, cat3_a)]
            mean_markup_orig = stats_orig['mean']
            count_orig = stats_orig['count']
            
            if count_orig >= MIN_BRAND_CATEGORY_SAMPLES and pd.notna(mean_markup_orig) and mean_markup_orig > 1.0:
                # 原价基准预测
                cost_pred_orig = orig_price_b / mean_markup_orig
                matched_df.at[idx, '预测成本_原价基准'] = cost_pred_orig
                
                # 售价加权预测（如果启用）
                use_sale_price = False
                sale_price_weight_adjusted = cfg.SALE_PRICE_WEIGHT
                
                if (cfg.USE_SALE_PRICE_WEIGHT and 
                    pd.notna(sale_price_b) and sale_price_b > 0 and
                    not brand_cat3_markup_sale.empty and
                    (brand_b, cat3_a) in brand_cat3_markup_sale.index):
                    
                    discount_rate = sale_price_b / orig_price_b
                    if cfg.MIN_DISCOUNT_RATE <= discount_rate <= cfg.MAX_DISCOUNT_RATE:
                        stats_sale = brand_cat3_markup_sale.loc[(brand_b, cat3_a)]
                        mean_markup_sale = stats_sale['mean']
                        
                        if pd.notna(mean_markup_sale) and mean_markup_sale > 1.0:
                            cost_pred_sale = sale_price_b / mean_markup_sale
                            matched_df.at[idx, '预测成本_售价基准'] = cost_pred_sale
                            
                            prediction_diff_ratio = abs(cost_pred_orig - cost_pred_sale) / cost_pred_orig
                            if prediction_diff_ratio < 0.5:
                                use_sale_price = True
                                
                                if discount_rate < cfg.SALE_PRICE_WEIGHT_DECAY_THRESHOLD:
                                    decay_factor = (discount_rate - cfg.MIN_DISCOUNT_RATE) / (cfg.SALE_PRICE_WEIGHT_DECAY_THRESHOLD - cfg.MIN_DISCOUNT_RATE)
                                    sale_price_weight_adjusted = cfg.SALE_PRICE_WEIGHT * decay_factor
                                    orig_price_weight_adjusted = 1 - sale_price_weight_adjusted
                                else:
                                    orig_price_weight_adjusted = cfg.ORIGINAL_PRICE_WEIGHT
                                
                                cost_pred_weighted = (cost_pred_orig * orig_price_weight_adjusted + 
                                                    cost_pred_sale * sale_price_weight_adjusted)
                                matched_df.at[idx, '预测成本_B'] = cost_pred_weighted
                                matched_df.at[idx, '预测方法'] = f'品牌+三级分类({brand_b})(售价加权{sale_price_weight_adjusted:.0%})'
                                
                                consistency = 1 - abs(cost_pred_orig - cost_pred_sale) / max(cost_pred_orig, cost_pred_sale)
                                base_confidence = 0.90  # 🆕 品牌+分类最高置信度
                                confidence = min(0.95, base_confidence * (0.8 + 0.2 * consistency))
                                
                                if is_barcode_match:
                                    confidence = min(0.95, confidence + 0.1)
                                    barcode_match_count += 1
                                
                                matched_df.at[idx, '置信度'] = max(cfg.COST_CONFIDENCE_THRESHOLD, confidence)
                                weighted_count += 1
                                
                                # 🆕 异常检测
                                current_cost = matched_df.at[idx, '预测成本_B']
                                adjusted_cost, adjusted_confidence, validation_flag = validate_cost_prediction(
                                    current_cost, row, store_a_df, cfg
                                )
                                if validation_flag != '正常':
                                    matched_df.at[idx, '预测成本_B'] = adjusted_cost
                                    if adjusted_confidence is not None:
                                        matched_df.at[idx, '置信度'] = adjusted_confidence
                                    current_method = matched_df.at[idx, '预测方法']
                                    matched_df.at[idx, '预测方法'] = f"{current_method} [{validation_flag}]"
                                
                                brand_cat3_match_count += 1  # 🆕 统计品牌+三级分类命中数
                                continue  # 🆕 找到品牌+分类加价率，跳过后续判断
                
                # 未使用售价加权，仅用原价
                if not use_sale_price:
                    matched_df.at[idx, '预测成本_B'] = cost_pred_orig
                    matched_df.at[idx, '预测方法'] = f'品牌+三级分类({brand_b})(原价)'
                    confidence = 0.90  # 🆕 品牌+分类高置信度
                    
                    if is_barcode_match:
                        confidence = min(0.95, confidence + 0.1)
                        barcode_match_count += 1
                    
                    matched_df.at[idx, '置信度'] = max(cfg.COST_CONFIDENCE_THRESHOLD, confidence)
                    
                    # 🆕 异常检测
                    current_cost = matched_df.at[idx, '预测成本_B']
                    adjusted_cost, adjusted_confidence, validation_flag = validate_cost_prediction(
                        current_cost, row, store_a_df, cfg
                    )
                    if validation_flag != '正常':
                        matched_df.at[idx, '预测成本_B'] = adjusted_cost
                        if adjusted_confidence is not None:
                            matched_df.at[idx, '置信度'] = adjusted_confidence
                        current_method = matched_df.at[idx, '预测方法']
                        matched_df.at[idx, '预测方法'] = f"{current_method} [{validation_flag}]"
                    
                    brand_cat3_match_count += 1  # 🆕 统计品牌+三级分类命中数
                    continue  # 🆕 找到品牌+分类加价率，跳过后续判断
        
        # 策略2: 三级分类加价率（含售价加权）
        cat3 = row.get(cat3_col_a)
        if pd.notna(cat3) and cat3 in category_markup_orig_level3.index:
            stats_orig = category_markup_orig_level3.loc[cat3]
            # 🆕 兼容两种数据结构（MultiIndex vs 单层Index）
            if isinstance(stats_orig, pd.DataFrame):
                # MultiIndex 结构（旧逻辑）
                mean_markup_orig = stats_orig[('markup_rate_原价', 'mean')]
                std_markup_orig = stats_orig[('markup_rate_原价', 'std')]
                count_orig = stats_orig[('markup_rate_原价', 'count')]
            else:
                # 单层 Index 结构（加权聚合后）
                mean_markup_orig = stats_orig['mean']
                std_markup_orig = stats_orig['std']
                count_orig = stats_orig['count']
            
            # 检查加价率有效性
            if count_orig >= cfg.COST_PREDICTION_MIN_SAMPLES and pd.notna(mean_markup_orig) and mean_markup_orig > 1.0:
                # 原价基准预测
                cost_pred_orig = orig_price_b / mean_markup_orig
                matched_df.at[idx, '预测成本_原价基准'] = cost_pred_orig
                
                # 🆕 售价加权预测（含极端折扣保护）
                use_sale_price = False  # 是否使用售价加权
                discount_rate = None
                sale_price_weight_adjusted = cfg.SALE_PRICE_WEIGHT  # 动态调整的售价权重
                
                if (cfg.USE_SALE_PRICE_WEIGHT and 
                    pd.notna(sale_price_b) and sale_price_b > 0 and
                    cat3 in category_markup_sale_level3.index):
                    
                    # 🛡️ 极端折扣检测
                    discount_rate = sale_price_b / orig_price_b
                    
                    # 检查1: 折扣率是否在合理范围内
                    if cfg.MIN_DISCOUNT_RATE <= discount_rate <= cfg.MAX_DISCOUNT_RATE:
                        stats_sale = category_markup_sale_level3.loc[cat3]
                        # 🆕 兼容两种数据结构
                        if isinstance(stats_sale, pd.DataFrame):
                            mean_markup_sale = stats_sale[('markup_rate_售价', 'mean')]
                        else:
                            mean_markup_sale = stats_sale['mean']
                        
                        if pd.notna(mean_markup_sale) and mean_markup_sale > 1.0:
                            cost_pred_sale = sale_price_b / mean_markup_sale
                            matched_df.at[idx, '预测成本_售价基准'] = cost_pred_sale
                            
                            # 检查2: 原价/售价预测差异是否过大（防止售价极端波动）
                            prediction_diff_ratio = abs(cost_pred_orig - cost_pred_sale) / cost_pred_orig
                            
                            if prediction_diff_ratio < 0.5:  # 差异<50%，可以使用售价
                                use_sale_price = True
                                
                                # 🔧 折扣率动态权重调整
                                # 折扣越深（引流品），售价权重越低
                                if discount_rate < cfg.SALE_PRICE_WEIGHT_DECAY_THRESHOLD:
                                    # 折扣率50%-70%时，售价权重线性衰减
                                    decay_factor = (discount_rate - cfg.MIN_DISCOUNT_RATE) / (cfg.SALE_PRICE_WEIGHT_DECAY_THRESHOLD - cfg.MIN_DISCOUNT_RATE)
                                    sale_price_weight_adjusted = cfg.SALE_PRICE_WEIGHT * decay_factor
                                    orig_price_weight_adjusted = 1 - sale_price_weight_adjusted
                                else:
                                    # 折扣率>=70%，正常权重
                                    orig_price_weight_adjusted = cfg.ORIGINAL_PRICE_WEIGHT
                                
                                # 加权平均
                                cost_pred_weighted = (cost_pred_orig * orig_price_weight_adjusted + 
                                                    cost_pred_sale * sale_price_weight_adjusted)
                                matched_df.at[idx, '预测成本_B'] = cost_pred_weighted
                                matched_df.at[idx, '预测方法'] = f'三级分类(售价加权{sale_price_weight_adjusted:.0%})'
                                
                                # 置信度调整：原价/售价预测一致性
                                consistency = 1 - abs(cost_pred_orig - cost_pred_sale) / max(cost_pred_orig, cost_pred_sale)
                                base_confidence = 0.5 + (count_orig / 50) * 0.2
                                if pd.notna(std_markup_orig) and mean_markup_orig > 0:
                                    base_confidence -= (std_markup_orig / mean_markup_orig) * 0.3
                                confidence = min(0.90, base_confidence * (0.8 + 0.2 * consistency))
                                # 🔧 条码匹配提升置信度
                                if is_barcode_match:
                                    confidence = min(0.95, confidence + 0.1)
                                    barcode_match_count += 1
                                matched_df.at[idx, '置信度'] = max(cfg.COST_CONFIDENCE_THRESHOLD, confidence)
                                weighted_count += 1
                
                # 如果不使用售价加权（折扣异常或配置关闭）
                if not use_sale_price:
                    matched_df.at[idx, '预测成本_B'] = cost_pred_orig
                    
                    # 标注原因
                    if discount_rate is not None:
                        if discount_rate < cfg.MIN_DISCOUNT_RATE:
                            matched_df.at[idx, '预测方法'] = f'三级分类(原价) [售价异常低{discount_rate:.0%}]'
                        elif discount_rate > cfg.MAX_DISCOUNT_RATE:
                            matched_df.at[idx, '预测方法'] = f'三级分类(原价) [售价高于原价]'
                        else:
                            matched_df.at[idx, '预测方法'] = '三级分类(原价) [售价预测差异大]'
                    else:
                        matched_df.at[idx, '预测方法'] = '三级分类(原价)'
                    
                    confidence = 0.5 + (count_orig / 50) * 0.2
                    if pd.notna(std_markup_orig) and mean_markup_orig > 0:
                        confidence -= (std_markup_orig / mean_markup_orig) * 0.3
                    # 🔧 条码匹配提升置信度
                    if is_barcode_match:
                        confidence = min(0.95, confidence + 0.1)
                        barcode_match_count += 1
                    matched_df.at[idx, '置信度'] = min(0.85, max(cfg.COST_CONFIDENCE_THRESHOLD, confidence))
                
                # 🆕 方案C: 异常检测验证（三级分类预测）
                current_cost = matched_df.at[idx, '预测成本_B']
                adjusted_cost, adjusted_confidence, validation_flag = validate_cost_prediction(
                    current_cost, row, store_a_df, cfg
                )
                
                if validation_flag != '正常':
                    # 异常检测触发，调整预测
                    matched_df.at[idx, '预测成本_B'] = adjusted_cost
                    if adjusted_confidence is not None:
                        matched_df.at[idx, '置信度'] = adjusted_confidence
                    
                    # 更新预测方法标记
                    current_method = matched_df.at[idx, '预测方法']
                    matched_df.at[idx, '预测方法'] = f"{current_method} [{validation_flag}]"
                
                cat3_match_count += 1
                continue
        
        # 🆕 方案B 优先级3: 品牌+一级分类加价率
        # 使用竞对品牌 + 本店一级分类匹配本店的品牌+分类加价率
        cat1_a = row.get(cat1_col_a)
        if (pd.notna(brand_b) and brand_b != '' and 
            pd.notna(cat1_a) and 
            not brand_cat1_markup_orig.empty and 
            (brand_b, cat1_a) in brand_cat1_markup_orig.index):
            
            stats_orig = brand_cat1_markup_orig.loc[(brand_b, cat1_a)]
            mean_markup_orig = stats_orig['mean']
            count_orig = stats_orig['count']
            
            if count_orig >= MIN_BRAND_CATEGORY_SAMPLES and pd.notna(mean_markup_orig) and mean_markup_orig > 1.0:
                cost_pred_orig = orig_price_b / mean_markup_orig
                matched_df.at[idx, '预测成本_原价基准'] = cost_pred_orig
                matched_df.at[idx, '预测成本_B'] = cost_pred_orig
                matched_df.at[idx, '预测方法'] = f'品牌+一级分类({brand_b})(原价)'
                confidence = 0.75  # 🆕 品牌+一级分类中等置信度
                
                if is_barcode_match:
                    confidence = min(0.95, confidence + 0.1)
                    barcode_match_count += 1
                
                matched_df.at[idx, '置信度'] = max(cfg.COST_CONFIDENCE_THRESHOLD, confidence)
                
                # 🆕 异常检测
                current_cost = matched_df.at[idx, '预测成本_B']
                adjusted_cost, adjusted_confidence, validation_flag = validate_cost_prediction(
                    current_cost, row, store_a_df, cfg
                )
                if validation_flag != '正常':
                    matched_df.at[idx, '预测成本_B'] = adjusted_cost
                    if adjusted_confidence is not None:
                        matched_df.at[idx, '置信度'] = adjusted_confidence
                    current_method = matched_df.at[idx, '预测方法']
                    matched_df.at[idx, '预测方法'] = f"{current_method} [{validation_flag}]"
                
                brand_cat1_match_count += 1  # 🆕 统计品牌+一级分类命中数
                continue  # 🆕 找到品牌+一级分类加价率，跳过后续判断
        
        # 策略3: 一级分类加价率（兜底，同样支持售价加权）
        cat1 = row.get(cat1_col_a)
        if pd.notna(cat1) and cat1 in category_markup_orig_level1.index:
            stats_orig = category_markup_orig_level1.loc[cat1]
            # 🆕 兼容两种数据结构
            if isinstance(stats_orig, pd.DataFrame):
                mean_markup_orig = stats_orig[('markup_rate_原价', 'mean')]
                std_markup_orig = stats_orig[('markup_rate_原价', 'std')]
                count_orig = stats_orig[('markup_rate_原价', 'count')]
            else:
                mean_markup_orig = stats_orig['mean']
                std_markup_orig = stats_orig['std']
                count_orig = stats_orig['count']
            
            if pd.notna(mean_markup_orig) and mean_markup_orig > 1.0:
                cost_pred_orig = orig_price_b / mean_markup_orig
                matched_df.at[idx, '预测成本_原价基准'] = cost_pred_orig
                
                # 售价加权（一级分类，含极端折扣保护）
                use_sale_price = False
                discount_rate = None
                sale_price_weight_adjusted = cfg.SALE_PRICE_WEIGHT
                
                if (cfg.USE_SALE_PRICE_WEIGHT and 
                    pd.notna(sale_price_b) and sale_price_b > 0 and
                    cat1 in category_markup_sale_level1.index):
                    
                    # 🛡️ 极端折扣检测
                    discount_rate = sale_price_b / orig_price_b
                    
                    if cfg.MIN_DISCOUNT_RATE <= discount_rate <= cfg.MAX_DISCOUNT_RATE:
                        stats_sale = category_markup_sale_level1.loc[cat1]
                        # 🆕 兼容两种数据结构
                        if isinstance(stats_sale, pd.DataFrame):
                            mean_markup_sale = stats_sale[('markup_rate_售价', 'mean')]
                        else:
                            mean_markup_sale = stats_sale['mean']
                        
                        if pd.notna(mean_markup_sale) and mean_markup_sale > 1.0:
                            cost_pred_sale = sale_price_b / mean_markup_sale
                            matched_df.at[idx, '预测成本_售价基准'] = cost_pred_sale
                            
                            prediction_diff_ratio = abs(cost_pred_orig - cost_pred_sale) / cost_pred_orig
                            
                            if prediction_diff_ratio < 0.5:
                                use_sale_price = True
                                
                                # 折扣率动态权重调整
                                if discount_rate < cfg.SALE_PRICE_WEIGHT_DECAY_THRESHOLD:
                                    decay_factor = (discount_rate - cfg.MIN_DISCOUNT_RATE) / (cfg.SALE_PRICE_WEIGHT_DECAY_THRESHOLD - cfg.MIN_DISCOUNT_RATE)
                                    sale_price_weight_adjusted = cfg.SALE_PRICE_WEIGHT * decay_factor
                                    orig_price_weight_adjusted = 1 - sale_price_weight_adjusted
                                else:
                                    orig_price_weight_adjusted = cfg.ORIGINAL_PRICE_WEIGHT
                                
                                cost_pred_weighted = (cost_pred_orig * orig_price_weight_adjusted + 
                                                    cost_pred_sale * sale_price_weight_adjusted)
                                matched_df.at[idx, '预测成本_B'] = cost_pred_weighted
                                matched_df.at[idx, '预测方法'] = f'一级分类(售价加权{sale_price_weight_adjusted:.0%})'
                                
                                consistency = 1 - abs(cost_pred_orig - cost_pred_sale) / max(cost_pred_orig, cost_pred_sale)
                                base_confidence = 0.4 + (count_orig / 100) * 0.2
                                if pd.notna(std_markup_orig) and mean_markup_orig > 0:
                                    base_confidence -= (std_markup_orig / mean_markup_orig) * 0.3
                                confidence = min(0.75, base_confidence * (0.8 + 0.2 * consistency))
                                matched_df.at[idx, '置信度'] = max(cfg.COST_CONFIDENCE_THRESHOLD, confidence)
                                weighted_count += 1
                
                if not use_sale_price:
                    matched_df.at[idx, '预测成本_B'] = cost_pred_orig
                    
                    if discount_rate is not None:
                        if discount_rate < cfg.MIN_DISCOUNT_RATE:
                            matched_df.at[idx, '预测方法'] = f'一级分类(原价) [售价异常低{discount_rate:.0%}]'
                        elif discount_rate > cfg.MAX_DISCOUNT_RATE:
                            matched_df.at[idx, '预测方法'] = f'一级分类(原价) [售价高于原价]'
                        else:
                            matched_df.at[idx, '预测方法'] = '一级分类(原价) [售价预测差异大]'
                    else:
                        matched_df.at[idx, '预测方法'] = '一级分类(原价)'
                    
                    confidence = 0.4 + (count_orig / 100) * 0.2
                    if pd.notna(std_markup_orig) and mean_markup_orig > 0:
                        confidence -= (std_markup_orig / mean_markup_orig) * 0.3
                    matched_df.at[idx, '置信度'] = min(0.70, max(cfg.COST_CONFIDENCE_THRESHOLD, confidence))
                
                # 🆕 方案C: 异常检测验证（一级分类预测）
                current_cost = matched_df.at[idx, '预测成本_B']
                adjusted_cost, adjusted_confidence, validation_flag = validate_cost_prediction(
                    current_cost, row, store_a_df, cfg
                )
                
                if validation_flag != '正常':
                    # 异常检测触发，调整预测
                    matched_df.at[idx, '预测成本_B'] = adjusted_cost
                    if adjusted_confidence is not None:
                        matched_df.at[idx, '置信度'] = adjusted_confidence
                    
                    # 更新预测方法标记
                    current_method = matched_df.at[idx, '预测方法']
                    matched_df.at[idx, '预测方法'] = f"{current_method} [{validation_flag}]"
                
                cat1_match_count += 1
                continue  # 🆕 找到一级分类，跳过价格区间兜底
        
        # 🆕 方案B 优先级5: 价格区间加价率（最后兜底）
        if not price_range_markup_orig.empty:
            price_range = get_price_range(orig_price_b)
            if price_range and price_range in price_range_markup_orig.index:
                stats_orig = price_range_markup_orig.loc[price_range]
                mean_markup_orig = stats_orig['mean']
                count_orig = stats_orig['count']
                
                if pd.notna(mean_markup_orig) and mean_markup_orig > 1.0:
                    cost_pred_orig = orig_price_b / mean_markup_orig
                    matched_df.at[idx, '预测成本_原价基准'] = cost_pred_orig
                    matched_df.at[idx, '预测成本_B'] = cost_pred_orig
                    matched_df.at[idx, '预测方法'] = f'价格区间({price_range})'
                    confidence = 0.50  # 🆕 价格区间低置信度
                    
                    if is_barcode_match:
                        confidence = min(0.95, confidence + 0.1)
                        barcode_match_count += 1
                    
                    matched_df.at[idx, '置信度'] = max(cfg.COST_CONFIDENCE_THRESHOLD, confidence)
                    
                    # 🆕 异常检测
                    current_cost = matched_df.at[idx, '预测成本_B']
                    adjusted_cost, adjusted_confidence, validation_flag = validate_cost_prediction(
                        current_cost, row, store_a_df, cfg
                    )
                    if validation_flag != '正常':
                        matched_df.at[idx, '预测成本_B'] = adjusted_cost
                        if adjusted_confidence is not None:
                            matched_df.at[idx, '置信度'] = adjusted_confidence
                        current_method = matched_df.at[idx, '预测方法']
                        matched_df.at[idx, '预测方法'] = f"{current_method} [{validation_flag}]"
                    
                    price_range_match_count += 1  # 🆕 统计价格区间命中数
    
    predicted_count = matched_df['预测成本_B'].notna().sum()
    print(f"\n   ✅ 成本预测完成:")
    print(f"      条码精确匹配: {barcode_match_count} 个")
    if brand_cat3_match_count > 0:  # 🆕 方案B统计
        print(f"      🆕 品牌+三级分类: {brand_cat3_match_count} 个 (置信度0.90-0.95)")
    print(f"      三级分类预测: {cat3_match_count} 个")
    if brand_cat1_match_count > 0:  # 🆕 方案B统计
        print(f"      🆕 品牌+一级分类: {brand_cat1_match_count} 个 (置信度0.75)")
    print(f"      一级分类预测: {cat1_match_count} 个")
    if price_range_match_count > 0:  # 🆕 方案B统计
        print(f"      🆕 价格区间兜底: {price_range_match_count} 个 (置信度0.50)")
    if weighted_count > 0:
        print(f"      售价加权优化: {weighted_count} 个")
    print(f"      总预测数量: {predicted_count} / {len(matched_df)}")
    
    return matched_df


def predict_all_competitor_products_cost(store_b_df, store_a_df, cfg=None):
    """
    🆕 对竞对所有商品（包括独有商品）进行成本倒推
    
    策略：
    1. 基于商品自身的分类匹配本店的品类加价率
    2. 优先使用三级分类，降级到一级分类
    3. 同样支持售价加权预测
    
    Args:
        store_b_df: 竞对所有商品数据
        store_a_df: 本店原始数据（含成本，用于计算加价率）
        cfg: 配置对象
    
    Returns:
        DataFrame: 添加了预测成本列的竞对商品数据
    """
    if cfg is None:
        cfg = Config()
    
    cost_col = cfg.COST_COLUMN_NAME
    
    # 检查是否有成本数据
    if cost_col not in store_a_df.columns:
        print("   ⚠️  本店数据中未找到成本列，跳过全商品成本预测")
        return store_b_df
    
    print("\n" + "="*60)
    print("🧮 竞对全商品成本预测分析")
    print("="*60)
    
    # 计算本店原价加价率和售价加价率（🆕 方案A：销量加权）
    store_a_with_markup = calculate_markup_rate(store_a_df.copy(), cost_col, '原价', '_原价', use_weights=True)
    if '售价' in store_a_df.columns and cfg.USE_SALE_PRICE_WEIGHT:
        store_a_with_markup = calculate_markup_rate(store_a_with_markup, cost_col, '售价', '_售价', use_weights=True)
    
    # 🆕 方案A: 加权聚合函数（与predict_competitor_cost保持一致）
    def weighted_agg(df, value_col, weight_col):
        """加权聚合函数"""
        if weight_col not in df.columns or df[weight_col].isna().all():
            return df[value_col].agg(['mean', 'std', 'count'])
        
        valid_mask = df[value_col].notna() & df[weight_col].notna()
        valid_df = df[valid_mask]
        
        if len(valid_df) == 0:
            return pd.Series({'mean': None, 'std': None, 'count': 0})
        
        weights = valid_df[weight_col]
        values = valid_df[value_col]
        
        weighted_mean = np.average(values, weights=weights)
        weighted_variance = np.average((values - weighted_mean) ** 2, weights=weights)
        weighted_std = np.sqrt(weighted_variance)
        
        return pd.Series({'mean': weighted_mean, 'std': weighted_std, 'count': len(valid_df)})
    
    # 按品类统计原价加价率（🆕 使用加权）
    if 'sample_weight_原价' in store_a_with_markup.columns:
        category_markup_orig_level3 = store_a_with_markup.groupby('美团三级分类').apply(
            lambda x: weighted_agg(x, 'markup_rate_原价', 'sample_weight_原价')
        ).dropna()
        
        category_markup_orig_level1 = store_a_with_markup.groupby('美团一级分类').apply(
            lambda x: weighted_agg(x, 'markup_rate_原价', 'sample_weight_原价')
        ).dropna()
    else:
        category_markup_orig_level3 = store_a_with_markup.groupby('美团三级分类').agg({
            'markup_rate_原价': ['mean', 'std', 'count']
        }).dropna()
        
        category_markup_orig_level1 = store_a_with_markup.groupby('美团一级分类').agg({
            'markup_rate_原价': ['mean', 'std', 'count']
        }).dropna()
    
    # 按品类统计售价加价率（如果启用，🆕 同样加权）
    category_markup_sale_level3 = pd.DataFrame()
    category_markup_sale_level1 = pd.DataFrame()
    if 'markup_rate_售价' in store_a_with_markup.columns and cfg.USE_SALE_PRICE_WEIGHT:
        if 'sample_weight_售价' in store_a_with_markup.columns:
            category_markup_sale_level3 = store_a_with_markup.groupby('美团三级分类').apply(
                lambda x: weighted_agg(x, 'markup_rate_售价', 'sample_weight_售价')
            ).dropna()
            
            category_markup_sale_level1 = store_a_with_markup.groupby('美团一级分类').apply(
                lambda x: weighted_agg(x, 'markup_rate_售价', 'sample_weight_售价')
            ).dropna()
        else:
            category_markup_sale_level3 = store_a_with_markup.groupby('美团三级分类').agg({
                'markup_rate_售价': ['mean', 'std', 'count']
            }).dropna()
            
            category_markup_sale_level1 = store_a_with_markup.groupby('美团一级分类').agg({
                'markup_rate_售价': ['mean', 'std', 'count']
            }).dropna()
    
    # 🆕 方案B: 计算品牌+分类组合加价率
    brand_cat3_markup_orig = pd.DataFrame()
    brand_cat1_markup_orig = pd.DataFrame()
    brand_cat3_markup_sale = pd.DataFrame()
    brand_cat1_markup_sale = pd.DataFrame()
    
    MIN_BRAND_CATEGORY_SAMPLES = 3
    
    if '品牌' in store_a_with_markup.columns:
        if 'sample_weight_原价' in store_a_with_markup.columns:
            brand_cat3_markup_orig = store_a_with_markup.groupby(['品牌', '美团三级分类']).apply(
                lambda x: weighted_agg(x, 'markup_rate_原价', 'sample_weight_原价') if len(x) >= MIN_BRAND_CATEGORY_SAMPLES else pd.Series({'mean': None, 'std': None, 'count': 0})
            ).dropna()
            
            brand_cat1_markup_orig = store_a_with_markup.groupby(['品牌', '美团一级分类']).apply(
                lambda x: weighted_agg(x, 'markup_rate_原价', 'sample_weight_原价') if len(x) >= MIN_BRAND_CATEGORY_SAMPLES else pd.Series({'mean': None, 'std': None, 'count': 0})
            ).dropna()
        
        if 'markup_rate_售价' in store_a_with_markup.columns and cfg.USE_SALE_PRICE_WEIGHT:
            if 'sample_weight_售价' in store_a_with_markup.columns:
                brand_cat3_markup_sale = store_a_with_markup.groupby(['品牌', '美团三级分类']).apply(
                    lambda x: weighted_agg(x, 'markup_rate_售价', 'sample_weight_售价') if len(x) >= MIN_BRAND_CATEGORY_SAMPLES else pd.Series({'mean': None, 'std': None, 'count': 0})
                ).dropna()
                
                brand_cat1_markup_sale = store_a_with_markup.groupby(['品牌', '美团一级分类']).apply(
                    lambda x: weighted_agg(x, 'markup_rate_售价', 'sample_weight_售价') if len(x) >= MIN_BRAND_CATEGORY_SAMPLES else pd.Series({'mean': None, 'std': None, 'count': 0})
                ).dropna()
    
    # 🆕 方案B: 计算价格区间加价率
    def get_price_range(price):
        if pd.isna(price) or price <= 0:
            return None
        if price < 10:
            return '0-10元'
        elif price < 30:
            return '10-30元'
        elif price < 50:
            return '30-50元'
        elif price < 100:
            return '50-100元'
        else:
            return '100元以上'
    
    price_range_markup_orig = pd.DataFrame()
    price_range_markup_sale = pd.DataFrame()
    
    store_a_with_markup['价格区间'] = store_a_with_markup['原价'].apply(get_price_range)
    
    if 'sample_weight_原价' in store_a_with_markup.columns:
        price_range_markup_orig = store_a_with_markup.groupby('价格区间').apply(
            lambda x: weighted_agg(x, 'markup_rate_原价', 'sample_weight_原价')
        ).dropna()
    
    if 'markup_rate_售价' in store_a_with_markup.columns and cfg.USE_SALE_PRICE_WEIGHT:
        if 'sample_weight_售价' in store_a_with_markup.columns:
            price_range_markup_sale = store_a_with_markup.groupby('价格区间').apply(
                lambda x: weighted_agg(x, 'markup_rate_售价', 'sample_weight_售价')
            ).dropna()
    
    print(f"   📊 本店加价率统计（方案A+B：销量加权 + 多维分层）：")
    print(f"      三级分类: {len(category_markup_orig_level3)}个")
    print(f"      一级分类: {len(category_markup_orig_level1)}个")
    if not brand_cat3_markup_orig.empty or not brand_cat1_markup_orig.empty:
        print(f"      🆕 品牌+三级分类: {len(brand_cat3_markup_orig)}个")
        print(f"      🆕 品牌+一级分类: {len(brand_cat1_markup_orig)}个")
    if not price_range_markup_orig.empty:
        print(f"      🆕 价格区间: {len(price_range_markup_orig)}个")

    
    # 初始化预测列
    result_df = store_b_df.copy()
    result_df['预测成本'] = None
    result_df['预测成本_原价基准'] = None
    result_df['预测成本_售价基准'] = None
    result_df['预测方法'] = None
    result_df['置信度'] = None
    
    cat3_match_count = 0
    cat1_match_count = 0
    weighted_count = 0
    
    for idx, row in result_df.iterrows():
        # 获取商品价格
        orig_price = row.get('原价')
        sale_price = row.get('售价')
        
        if pd.isna(orig_price) or orig_price <= 0:
            continue
        
        # 策略1: 三级分类加价率（含售价加权）
        cat3 = row.get('美团三级分类')
        if pd.notna(cat3) and cat3 in category_markup_orig_level3.index:
            stats_orig = category_markup_orig_level3.loc[cat3]
            # 🆕 兼容加权聚合后的单层Index结构
            mean_markup_orig = stats_orig['mean']
            std_markup_orig = stats_orig['std']
            count_orig = stats_orig['count']
            
            if count_orig >= cfg.COST_PREDICTION_MIN_SAMPLES and pd.notna(mean_markup_orig) and mean_markup_orig > 1.0:
                cost_pred_orig = orig_price / mean_markup_orig
                result_df.at[idx, '预测成本_原价基准'] = cost_pred_orig
                
                # 售价加权预测（含极端折扣保护）
                use_sale_price = False
                discount_rate = None
                sale_price_weight_adjusted = cfg.SALE_PRICE_WEIGHT
                
                if (cfg.USE_SALE_PRICE_WEIGHT and 
                    pd.notna(sale_price) and sale_price > 0 and
                    cat3 in category_markup_sale_level3.index):
                    
                    # 🛡️ 极端折扣检测
                    discount_rate = sale_price / orig_price
                    
                    if cfg.MIN_DISCOUNT_RATE <= discount_rate <= cfg.MAX_DISCOUNT_RATE:
                        stats_sale = category_markup_sale_level3.loc[cat3]
                        # 🆕 兼容加权聚合后的单层Index结构
                        mean_markup_sale = stats_sale['mean']
                        
                        if pd.notna(mean_markup_sale) and mean_markup_sale > 1.0:
                            cost_pred_sale = sale_price / mean_markup_sale
                            result_df.at[idx, '预测成本_售价基准'] = cost_pred_sale
                            
                            prediction_diff_ratio = abs(cost_pred_orig - cost_pred_sale) / cost_pred_orig
                            
                            if prediction_diff_ratio < 0.5:
                                use_sale_price = True
                                
                                # 折扣率动态权重调整
                                if discount_rate < cfg.SALE_PRICE_WEIGHT_DECAY_THRESHOLD:
                                    decay_factor = (discount_rate - cfg.MIN_DISCOUNT_RATE) / (cfg.SALE_PRICE_WEIGHT_DECAY_THRESHOLD - cfg.MIN_DISCOUNT_RATE)
                                    sale_price_weight_adjusted = cfg.SALE_PRICE_WEIGHT * decay_factor
                                    orig_price_weight_adjusted = 1 - sale_price_weight_adjusted
                                else:
                                    orig_price_weight_adjusted = cfg.ORIGINAL_PRICE_WEIGHT
                                
                                cost_pred_weighted = (cost_pred_orig * orig_price_weight_adjusted + 
                                                    cost_pred_sale * sale_price_weight_adjusted)
                                result_df.at[idx, '预测成本'] = cost_pred_weighted
                                result_df.at[idx, '预测方法'] = f'三级分类(售价加权{sale_price_weight_adjusted:.0%})'
                                
                                consistency = 1 - abs(cost_pred_orig - cost_pred_sale) / max(cost_pred_orig, cost_pred_sale)
                                base_confidence = 0.5 + (count_orig / 50) * 0.2
                                if pd.notna(std_markup_orig) and mean_markup_orig > 0:
                                    base_confidence -= (std_markup_orig / mean_markup_orig) * 0.3
                                confidence = min(0.90, base_confidence * (0.8 + 0.2 * consistency))
                                
                                # 🎯 非匹配商品置信度惩罚
                                confidence = max(cfg.COST_CONFIDENCE_THRESHOLD, confidence - cfg.NON_MATCHED_CONFIDENCE_PENALTY)
                                result_df.at[idx, '置信度'] = confidence
                                weighted_count += 1
                
                if not use_sale_price:
                    result_df.at[idx, '预测成本'] = cost_pred_orig
                    
                    if discount_rate is not None:
                        if discount_rate < cfg.MIN_DISCOUNT_RATE:
                            result_df.at[idx, '预测方法'] = f'三级分类(原价) [引流品{discount_rate:.0%}]'
                        elif discount_rate > cfg.MAX_DISCOUNT_RATE:
                            result_df.at[idx, '预测方法'] = f'三级分类(原价) [售价高于原价]'
                        else:
                            result_df.at[idx, '预测方法'] = '三级分类(原价) [售价预测差异大]'
                    else:
                        result_df.at[idx, '预测方法'] = '三级分类(原价)'
                    
                    confidence = 0.5 + (count_orig / 50) * 0.2
                    if pd.notna(std_markup_orig) and mean_markup_orig > 0:
                        confidence -= (std_markup_orig / mean_markup_orig) * 0.3
                    
                    # 🎯 非匹配商品置信度惩罚
                    confidence = max(cfg.COST_CONFIDENCE_THRESHOLD, min(0.85, confidence) - cfg.NON_MATCHED_CONFIDENCE_PENALTY)
                    result_df.at[idx, '置信度'] = confidence
                
                # 🆕 方案C: 异常检测验证（三级分类，全商品预测）
                current_cost = result_df.at[idx, '预测成本']
                adjusted_cost, adjusted_confidence, validation_flag = validate_cost_prediction(
                    current_cost, row, store_a_df, cfg
                )
                
                if validation_flag != '正常':
                    # 异常检测触发，调整预测
                    result_df.at[idx, '预测成本'] = adjusted_cost
                    if adjusted_confidence is not None:
                        result_df.at[idx, '置信度'] = adjusted_confidence
                    
                    # 更新预测方法标记
                    current_method = result_df.at[idx, '预测方法']
                    result_df.at[idx, '预测方法'] = f"{current_method} [{validation_flag}]"
                
                cat3_match_count += 1
                continue
        
        # 策略2: 一级分类加价率（兜底）
        cat1 = row.get('美团一级分类')
        if pd.notna(cat1) and cat1 in category_markup_orig_level1.index:
            stats_orig = category_markup_orig_level1.loc[cat1]
            # 🆕 兼容加权聚合后的单层Index结构
            mean_markup_orig = stats_orig['mean']
            std_markup_orig = stats_orig['std']
            count_orig = stats_orig['count']
            
            if pd.notna(mean_markup_orig) and mean_markup_orig > 1.0:
                cost_pred_orig = orig_price / mean_markup_orig
                result_df.at[idx, '预测成本_原价基准'] = cost_pred_orig
                
                # 售价加权（一级分类，含极端折扣保护）
                use_sale_price = False
                discount_rate = None
                sale_price_weight_adjusted = cfg.SALE_PRICE_WEIGHT
                
                if (cfg.USE_SALE_PRICE_WEIGHT and 
                    pd.notna(sale_price) and sale_price > 0 and
                    cat1 in category_markup_sale_level1.index):
                    
                    discount_rate = sale_price / orig_price
                    
                    if cfg.MIN_DISCOUNT_RATE <= discount_rate <= cfg.MAX_DISCOUNT_RATE:
                        stats_sale = category_markup_sale_level1.loc[cat1]
                        # 🆕 兼容加权聚合后的单层Index结构
                        mean_markup_sale = stats_sale['mean']
                        
                        if pd.notna(mean_markup_sale) and mean_markup_sale > 1.0:
                            cost_pred_sale = sale_price / mean_markup_sale
                            result_df.at[idx, '预测成本_售价基准'] = cost_pred_sale
                            
                            prediction_diff_ratio = abs(cost_pred_orig - cost_pred_sale) / cost_pred_orig
                            
                            if prediction_diff_ratio < 0.5:
                                use_sale_price = True
                                
                                if discount_rate < cfg.SALE_PRICE_WEIGHT_DECAY_THRESHOLD:
                                    decay_factor = (discount_rate - cfg.MIN_DISCOUNT_RATE) / (cfg.SALE_PRICE_WEIGHT_DECAY_THRESHOLD - cfg.MIN_DISCOUNT_RATE)
                                    sale_price_weight_adjusted = cfg.SALE_PRICE_WEIGHT * decay_factor
                                    orig_price_weight_adjusted = 1 - sale_price_weight_adjusted
                                else:
                                    orig_price_weight_adjusted = cfg.ORIGINAL_PRICE_WEIGHT
                                
                                cost_pred_weighted = (cost_pred_orig * orig_price_weight_adjusted + 
                                                    cost_pred_sale * sale_price_weight_adjusted)
                                result_df.at[idx, '预测成本'] = cost_pred_weighted
                                result_df.at[idx, '预测方法'] = f'一级分类(售价加权{sale_price_weight_adjusted:.0%})'
                                
                                consistency = 1 - abs(cost_pred_orig - cost_pred_sale) / max(cost_pred_orig, cost_pred_sale)
                                base_confidence = 0.4 + (count_orig / 100) * 0.2
                                if pd.notna(std_markup_orig) and mean_markup_orig > 0:
                                    base_confidence -= (std_markup_orig / mean_markup_orig) * 0.3
                                confidence = min(0.75, base_confidence * (0.8 + 0.2 * consistency))
                                
                                # 🎯 非匹配商品置信度惩罚
                                confidence = max(cfg.COST_CONFIDENCE_THRESHOLD, confidence - cfg.NON_MATCHED_CONFIDENCE_PENALTY)
                                result_df.at[idx, '置信度'] = confidence
                                weighted_count += 1
                
                if not use_sale_price:
                    result_df.at[idx, '预测成本'] = cost_pred_orig
                    
                    if discount_rate is not None:
                        if discount_rate < cfg.MIN_DISCOUNT_RATE:
                            result_df.at[idx, '预测方法'] = f'一级分类(原价) [引流品{discount_rate:.0%}]'
                        elif discount_rate > cfg.MAX_DISCOUNT_RATE:
                            result_df.at[idx, '预测方法'] = f'一级分类(原价) [售价高于原价]'
                        else:
                            result_df.at[idx, '预测方法'] = '一级分类(原价) [售价预测差异大]'
                    else:
                        result_df.at[idx, '预测方法'] = '一级分类(原价)'
                    
                    confidence = 0.4 + (count_orig / 100) * 0.2
                    if pd.notna(std_markup_orig) and mean_markup_orig > 0:
                        confidence -= (std_markup_orig / mean_markup_orig) * 0.3
                    
                    # 🎯 非匹配商品置信度惩罚
                    confidence = max(cfg.COST_CONFIDENCE_THRESHOLD, min(0.70, confidence) - cfg.NON_MATCHED_CONFIDENCE_PENALTY)
                    result_df.at[idx, '置信度'] = confidence
                
                # 🆕 方案C: 异常检测验证（一级分类，全商品预测）
                current_cost = result_df.at[idx, '预测成本']
                adjusted_cost, adjusted_confidence, validation_flag = validate_cost_prediction(
                    current_cost, row, store_a_df, cfg
                )
                
                if validation_flag != '正常':
                    # 异常检测触发，调整预测
                    result_df.at[idx, '预测成本'] = adjusted_cost
                    if adjusted_confidence is not None:
                        result_df.at[idx, '置信度'] = adjusted_confidence
                    
                    # 更新预测方法标记
                    current_method = result_df.at[idx, '预测方法']
                    result_df.at[idx, '预测方法'] = f"{current_method} [{validation_flag}]"
                
                cat1_match_count += 1
    
    predicted_count = result_df['预测成本'].notna().sum()
    print(f"\n   ✅ 全商品成本预测完成:")
    print(f"      三级分类预测: {cat3_match_count} 个")
    print(f"      一级分类预测: {cat1_match_count} 个")
    if weighted_count > 0:
        print(f"      售价加权优化: {weighted_count} 个")
    print(f"      总预测数量: {predicted_count} / {len(result_df)}")
    print(f"      预测覆盖率: {predicted_count/len(result_df)*100:.1f}%")
    
    return result_df


def generate_cost_analysis_sheets(matched_df, store_b_all_df=None, cfg=None):
    """
    生成成本分析相关的 Sheet
    
    Args:
        matched_df: 匹配商品数据（含预测成本）
        store_b_all_df: 🆕 竞对所有商品数据（含预测成本，可选）
        cfg: 配置对象
    
    Returns:
        dict: {sheet_name: dataframe}
    """
    if cfg is None:
        cfg = Config()
    
    sheets = {}
    
    # 过滤有预测成本的数据
    df_with_cost = matched_df[matched_df['预测成本_B'].notna()].copy()
    
    if df_with_cost.empty:
        print("   ⚠️  无成本预测数据，跳过成本分析 Sheet 生成")
        return sheets
    
    print("\n" + "="*60)
    print("📊 生成成本分析报表")
    print("="*60)
    
    # 获取列名（处理带店铺后缀的情况）- 使用和 predict_competitor_cost 相同的逻辑
    def find_column(df, base_name, store_name_suffix=''):
        """智能查找列名，支持店铺名后缀和 _A/_B 后缀"""
        # 优先查找带店铺名的列
        if store_name_suffix:
            col_with_store = f'{base_name}_{store_name_suffix}'
            if col_with_store in df.columns:
                return col_with_store
        # 回退到 _A/_B 后缀
        for suffix in ['_A', '_B']:
            col_with_suffix = f'{base_name}{suffix}'
            if col_with_suffix in df.columns:
                return col_with_suffix
        # 最后尝试无后缀
        if base_name in df.columns:
            return base_name
        return None
    
    name_a_col = find_column(df_with_cost, '商品名称', cfg.STORE_A_NAME if cfg else '')
    name_b_col = find_column(df_with_cost, '商品名称', cfg.STORE_B_NAME if cfg else '')
    price_a_col = find_column(df_with_cost, '原价', cfg.STORE_A_NAME if cfg else '')
    price_b_col = find_column(df_with_cost, '原价', cfg.STORE_B_NAME if cfg else '')
    
    # 检查必需列是否存在
    if not all([name_a_col, name_b_col, price_a_col, price_b_col]):
        print(f"   ⚠️  缺少必需列，无法生成成本分析:")
        print(f"      商品名称_A: {name_a_col}")
        print(f"      商品名称_B: {name_b_col}")
        print(f"      原价_A: {price_a_col}")
        print(f"      原价_B: {price_b_col}")
        return sheets
    
    # Sheet 1: 竞对成本预测汇总
    # 🔧 修复问题3：显示两种预测成本逻辑
    # 🔧 修复问题2：确保成本_A（成本_本店）有数据
    
    # 查找本店成本列（智能查找）
    # 🔧 修复：优先查找原始成本列（不带_A后缀）
    cost_col_name_a = None
    if cfg and cfg.COST_COLUMN_NAME:
        # 1. 尝试带店铺名的列
        store_name_col = f'{cfg.COST_COLUMN_NAME}_{cfg.STORE_A_NAME}'
        if store_name_col in df_with_cost.columns:
            cost_col_name_a = store_name_col
        # 2. 尝试不带后缀的原始列
        elif cfg.COST_COLUMN_NAME in df_with_cost.columns:
            cost_col_name_a = cfg.COST_COLUMN_NAME
    
    # 如果成本_A列不存在或为空，从原始列复制数据
    if '成本_A' not in df_with_cost.columns or df_with_cost['成本_A'].isna().all():
        print(f"   🔧 修复：成本_A列缺失或为空，从 {cost_col_name_a} 复制数据")
        if cost_col_name_a and cost_col_name_a in df_with_cost.columns and cost_col_name_a != '成本_A':
            df_with_cost['成本_A'] = df_with_cost[cost_col_name_a]
            print(f"   ✅ 已从 {cost_col_name_a} 复制 {df_with_cost['成本_A'].notna().sum()} 条成本数据")
        else:
            print(f"   ⚠️  警告：未找到本店成本列（查找：{cost_col_name_a}），成本_A将为空")
            df_with_cost['成本_A'] = None
    
    cost_prediction_cols = [
        name_a_col, name_b_col,
        # ABAB模式：本店价格和成本
        price_a_col, '成本_A',
        # ABAB模式：竞对价格和两种预测成本
        price_b_col, 
        '预测成本_B（售价加权）',  # 🆕 重命名以明确
        '预测成本_原价基准',      # 🆕 显示原价基准预测
        '预测成本_售价基准',      # 🆕 显示售价基准预测（如果有）
        '预测方法', '置信度'
    ]
    
    # 🆕 将'预测成本_B'重命名为'预测成本_B（售价加权）'以明确其含义
    if '预测成本_B' in df_with_cost.columns:
        df_with_cost['预测成本_B（售价加权）'] = df_with_cost['预测成本_B']
    
    # 添加可选列（智能查找）
    optional_base_cols = ['美团一级分类', '美团三级分类', '条码', '月售']
    for base_col in optional_base_cols:
        col_a = find_column(df_with_cost, base_col, cfg.STORE_A_NAME if cfg else '')
        col_b = find_column(df_with_cost, base_col, cfg.STORE_B_NAME if cfg else '')
        if col_a:
            cost_prediction_cols.append(col_a)
        if col_b:
            cost_prediction_cols.append(col_b)
    
    # 计算成本差和优势（基于售价加权版）
    df_with_cost['成本差（售价加权）'] = df_with_cost['成本_A'] - df_with_cost['预测成本_B（售价加权）']
    
    # 🆕 计算原价基准的成本差
    if '预测成本_原价基准' in df_with_cost.columns:
        df_with_cost['成本差（纯原价）'] = df_with_cost['成本_A'] - df_with_cost['预测成本_原价基准']
    
    df_with_cost['成本优势'] = df_with_cost['成本差（售价加权）'].apply(
        lambda x: '本店成本低' if pd.notna(x) and x < -1 else ('竞对成本低' if pd.notna(x) and x > 1 else '成本相近')
    )
    cost_prediction_cols.extend(['成本差（售价加权）', '成本差（纯原价）', '成本优势'])
    
    cost_prediction_cols = [col for col in cost_prediction_cols if col in df_with_cost.columns]
    sheets['竞对成本预测'] = df_with_cost[cost_prediction_cols].copy()
    
    # Sheet 2: 利润空间对比（双视角）
    df_profit = df_with_cost.copy()
    
    # 🔧 修复问题2：确保成本_A有数据
    # （已经在Sheet 1中修复，这里df_profit继承df_with_cost的修复）
    
    # === 本店（A店）毛利计算 ===
    df_profit['毛利_A'] = df_profit[price_a_col] - df_profit['成本_A']
    df_profit['毛利率_A'] = df_profit.apply(
        lambda row: (row['毛利_A'] / row[price_a_col] * 100) if pd.notna(row['毛利_A']) and pd.notna(row[price_a_col]) and row[price_a_col] > 0 and pd.notna(row['成本_A']) else None,
        axis=1
    )
    # 🔧 修复：确保毛利率_A是数值类型再round
    if pd.api.types.is_numeric_dtype(df_profit['毛利率_A']):
        df_profit['毛利率_A'] = df_profit['毛利率_A'].round(2)
    else:
        df_profit['毛利率_A'] = pd.to_numeric(df_profit['毛利率_A'], errors='coerce').round(2)
    
    # === 竞对（B店）售价加权版毛利 ===
    # 🔧 使用统一的列名'预测成本_B（售价加权）'
    if '预测成本_B（售价加权）' not in df_profit.columns and '预测成本_B' in df_profit.columns:
        df_profit['预测成本_B（售价加权）'] = df_profit['预测成本_B']
    
    df_profit['预测毛利_B（售价加权）'] = df_profit[price_b_col] - df_profit['预测成本_B（售价加权）']
    df_profit['预测毛利率_B（售价加权）'] = df_profit.apply(
        lambda row: (row['预测毛利_B（售价加权）'] / row[price_b_col] * 100) if pd.notna(row.get('预测毛利_B（售价加权）')) and pd.notna(row[price_b_col]) and row[price_b_col] > 0 else None,
        axis=1
    )
    # 🔧 修复：确保数值类型再round
    if pd.api.types.is_numeric_dtype(df_profit['预测毛利率_B（售价加权）']):
        df_profit['预测毛利率_B（售价加权）'] = df_profit['预测毛利率_B（售价加权）'].round(2)
    else:
        df_profit['预测毛利率_B（售价加权）'] = pd.to_numeric(df_profit['预测毛利率_B（售价加权）'], errors='coerce').round(2)
    
    # === 竞对（B店）纯原价版毛利 ===
    # 使用预测成本_原价基准（如果存在）
    if '预测成本_原价基准' in df_profit.columns:
        df_profit['预测成本_B（纯原价）'] = df_profit['预测成本_原价基准']
    else:
        df_profit['预测成本_B（纯原价）'] = df_profit['预测成本_B']  # 回退方案
    
    df_profit['预测毛利_B（纯原价）'] = df_profit[price_b_col] - df_profit['预测成本_B（纯原价）']
    df_profit['预测毛利率_B（纯原价）'] = df_profit.apply(
        lambda row: (row['预测毛利_B（纯原价）'] / row[price_b_col] * 100) if pd.notna(row.get('预测毛利_B（纯原价）')) and pd.notna(row[price_b_col]) and row[price_b_col] > 0 else None,
        axis=1
    )
    # 🔧 修复：确保数值类型再round
    if pd.api.types.is_numeric_dtype(df_profit['预测毛利率_B（纯原价）']):
        df_profit['预测毛利率_B（纯原价）'] = df_profit['预测毛利率_B（纯原价）'].round(2)
    else:
        df_profit['预测毛利率_B（纯原价）'] = pd.to_numeric(df_profit['预测毛利率_B（纯原价）'], errors='coerce').round(2)
    
    # === 毛利率对比分析 ===
    # 🔧 修复：使用fillna确保数值类型
    df_profit['毛利率差（售价加权）'] = (df_profit['毛利率_A'].fillna(0) - df_profit['预测毛利率_B（售价加权）'].fillna(0))
    df_profit['毛利率差（售价加权）'] = pd.to_numeric(df_profit['毛利率差（售价加权）'], errors='coerce').round(2)
    
    df_profit['毛利率差（纯原价）'] = (df_profit['毛利率_A'].fillna(0) - df_profit['预测毛利率_B（纯原价）'].fillna(0))
    df_profit['毛利率差（纯原价）'] = pd.to_numeric(df_profit['毛利率差（纯原价）'], errors='coerce').round(2)
    
    # 竞对促销影响
    df_profit['竞对促销影响'] = df_profit.apply(
        lambda row: (row['预测毛利率_B（纯原价）'] - row['预测毛利率_B（售价加权）']) if pd.notna(row.get('预测毛利率_B（纯原价）')) and pd.notna(row.get('预测毛利率_B（售价加权）')) else None,
        axis=1
    )
    # 🔧 修复：确保数值类型再round
    df_profit['竞对促销影响'] = pd.to_numeric(df_profit['竞对促销影响'], errors='coerce').round(2)
    
    # 竞争优势分析（基于售价加权版）
    def analyze_advantage(row):
        if pd.isna(row.get('毛利率差（售价加权）')):
            return '数据不足'
        if row['毛利率差（售价加权）'] > 10:
            return '本店高毛利'
        elif row['毛利率差（售价加权）'] < -10:
            return '竞对高毛利'
        # 🔧 修复：使用'成本差（售价加权）'
        elif row.get('成本优势') == '本店成本低' and row.get(price_a_col, 999999) <= row.get(price_b_col, 0):
            return '成本+价格双优势'
        elif row.get('成本优势') == '本店成本低':
            return '成本优势'
        elif row.get(price_a_col, 999999) < row.get(price_b_col, 0):
            return '价格优势'
        else:
            return '竞争均衡'
    
    df_profit['竞争优势'] = df_profit.apply(analyze_advantage, axis=1)
    
    # 定义列顺序（ABAB对比模式）
    profit_cols = [
        name_a_col, name_b_col,
        # 本店数据
        price_a_col, '成本_A', '毛利_A', '毛利率_A',
        # 🔧 修复：使用统一的列名
        # 竞对售价加权版
        price_b_col, '预测成本_B（售价加权）', '预测毛利_B（售价加权）', '预测毛利率_B（售价加权）',
        # 竞对纯原价版
        '预测成本_B（纯原价）', '预测毛利_B（纯原价）', '预测毛利率_B（纯原价）',
        # 对比分析
        '毛利率差（售价加权）', '毛利率差（纯原价）', '竞对促销影响', '竞争优势', '置信度'
    ]
    
    # 添加可选列（智能查找）
    cat1_col_a = find_column(df_profit, '美团一级分类', cfg.STORE_A_NAME if cfg else '')
    monthly_a = find_column(df_profit, '月售', cfg.STORE_A_NAME if cfg else '')
    monthly_b = find_column(df_profit, '月售', cfg.STORE_B_NAME if cfg else '')
    if cat1_col_a:
        profit_cols.append(cat1_col_a)
    if monthly_a:
        profit_cols.append(monthly_a)
    if monthly_b:
        profit_cols.append(monthly_b)
    
    profit_cols = [col for col in profit_cols if col in df_profit.columns]
    sheets['利润空间对比'] = df_profit[profit_cols].copy()
    
    # Sheet 3: 成本优势商品（双视角对比）
    # 🔧 修复：使用'成本差（售价加权）'代替'成本差'
    # 基于售价加权版筛选成本优势商品
    if '成本差（售价加权）' in df_profit.columns:
        df_advantage = df_profit[
            (df_profit['成本差（售价加权）'] < -1) &  # 本店成本低
            (df_profit[price_a_col] <= df_profit[price_b_col] * 1.05) &  # 价格相近或更低
            (df_profit['置信度'] >= 0.6)  # 中等以上置信度
        ].copy()
    else:
        # 回退方案（如果新列名不存在）
        df_advantage = pd.DataFrame()
    
    if not df_advantage.empty:
        df_advantage = df_advantage.sort_values('成本差（售价加权）', ascending=True)
        
        # === 成本对比（双视角）===
        # （已经在df_profit中计算过）
        
        # === 纯原价版成本差（如果不存在则计算）===
        if '成本差（纯原价）' not in df_advantage.columns and '预测成本_B（纯原价）' in df_advantage.columns:
            df_advantage['成本差（纯原价）'] = df_advantage['成本_A'] - df_advantage['预测成本_B（纯原价）']
        
        # 计算潜在调价空间（基于售价加权版）
        df_advantage['潜在提价空间'] = (df_advantage[price_b_col] - df_advantage[price_a_col]).round(2)
        
        # === 促销影响评估 ===
        def assess_competitor_promotion(row):
            promo_impact = row.get('竞对促销影响', 0)
            if pd.isna(promo_impact):
                return '无促销数据'
            if promo_impact >= 10:
                return '竞对深度促销'
            elif promo_impact >= 5:
                return '竞对温和促销'
            elif promo_impact >= 1:
                return '竞对轻微促销'
            else:
                return '竞对无促销'
        
        df_advantage['竞对促销状态'] = df_advantage.apply(assess_competitor_promotion, axis=1)
        
        # === 智能建议（考虑促销影响）===
        def generate_smart_suggestion(row):
            promo_state = row.get('竞对促销状态', '无促销数据')
            price_gap = row.get('潜在提价空间', 0)
            cost_diff_weighted = row.get('成本差（售价加权）', 0)
            cost_diff_orig = row.get('成本差（纯原价）', 0)
            
            if pd.isna(price_gap) or price_gap <= 0:
                return "价格已达竞对水平，暂不建议调价"
            
            if '深度促销' in promo_state:
                return f"⚠️ 竞对深度促销中，建议观望。正常期可考虑提价至{row[price_b_col]:.2f}元"
            elif '温和促销' in promo_state:
                return f"竞对促销期，可考虑小幅提价至{row[price_a_col] + price_gap/2:.2f}元，促销结束后提至{row[price_b_col]:.2f}元"
            else:
                return f"可考虑提价至{row[price_b_col]:.2f}元，增加毛利{price_gap:.2f}元"
        
        df_advantage['智能建议'] = df_advantage.apply(generate_smart_suggestion, axis=1)
        
        # 定义列顺序
        advantage_cols = [
            name_a_col, price_a_col, '成本_A', '毛利率_A',
            price_b_col, 
            # 售价加权版
            '预测成本_B', '预测毛利率_B（售价加权）', '成本差（售价加权）',
            # 纯原价版
            '预测成本_B（纯原价）', '预测毛利率_B（纯原价）', '成本差（纯原价）',
            # 决策支持
            '竞对促销状态', '竞对促销影响', '潜在提价空间', '智能建议', '置信度'
        ]
        advantage_cols = [col for col in advantage_cols if col in df_advantage.columns]
        sheets['成本优势商品'] = df_advantage[advantage_cols].copy()
        
        print(f"   ✅ 识别出 {len(df_advantage)} 个成本优势商品")
    
    # 🆕 Sheet 4: 竞对全商品成本倒推（双视角对比）
    # 🔧 修复：避免重复商品，基于商品名称+规格去重
    if store_b_all_df is not None:
        # 1. 从matched_df中提取B店数据（包含成本预测）
        matched_b_data = None
        matched_products_set = set()  # 用于去重：(商品名称, 规格)
        
        if matched_df is not None and not matched_df.empty:
            # matched_df包含 _A 和 _B 后缀的列，以及成本预测列
            # 提取所有B店相关列（_B后缀）+ 成本预测列
            b_cols = []
            rename_map = {}
            
            for col in matched_df.columns:
                if col.endswith('_B'):
                    # B店基础列：去掉_B后缀
                    b_cols.append(col)
                    rename_map[col] = col[:-2]
                elif col in ['预测成本_B', '预测成本_原价基准', '预测成本_售价基准', '预测方法', '置信度']:
                    # 成本预测列保留
                    b_cols.append(col)
                    rename_map[col] = col
            
            if b_cols:
                matched_b_data = matched_df[b_cols].copy()
                matched_b_data = matched_b_data.rename(columns=rename_map)
                
                # 重命名成本列：预测成本_B → 预测成本
                if '预测成本_B' in matched_b_data.columns:
                    matched_b_data = matched_b_data.rename(columns={'预测成本_B': '预测成本'})
                
                # 🆕 记录已匹配商品（用于去重）
                for idx, row in matched_b_data.iterrows():
                    product_name = row.get('商品名称', '')
                    spec = row.get('规格', '')  # 规格字段
                    if product_name:
                        matched_products_set.add((product_name, spec if pd.notna(spec) else ''))
                
                print(f"   📊 匹配商品成本数据: {len(matched_b_data)} 个（提取{len(b_cols)}个B店列）")
            else:
                print(f"   ⚠️  matched_df中无B店列，跳过匹配商品")
        
        # 2. 独有商品的成本数据（已在predict_all_competitor_products_cost中倒推）
        # 🔧 修复：从store_b_all_df中排除已匹配的商品
        df_unmatched_with_cost_list = []
        for idx, row in store_b_all_df.iterrows():
            if pd.isna(row.get('预测成本')):
                continue  # 跳过没有预测成本的商品
            
            product_name = row.get('商品名称', '')
            spec = row.get('规格', '')
            product_key = (product_name, spec if pd.notna(spec) else '')
            
            # 🆕 只添加未匹配的商品（避免重复）
            if product_key not in matched_products_set:
                df_unmatched_with_cost_list.append(row)
        
        df_unmatched_with_cost = pd.DataFrame(df_unmatched_with_cost_list) if df_unmatched_with_cost_list else pd.DataFrame()
        print(f"   📊 独有商品成本数据: {len(df_unmatched_with_cost)} 个（已排除{len(matched_products_set)}个已匹配商品）")
        
        # 3. 合并两部分数据
        if matched_b_data is not None and not matched_b_data.empty:
            # 确保列名一致后合并
            df_all_with_cost = pd.concat([matched_b_data, df_unmatched_with_cost], ignore_index=True)
            print(f"   ✅ 合并后总商品数: {len(df_all_with_cost)} 个（匹配{len(matched_b_data)} + 独有{len(df_unmatched_with_cost)}）")
        else:
            df_all_with_cost = df_unmatched_with_cost
            print(f"   ⚠️  仅独有商品: {len(df_all_with_cost)} 个")
        
        if not df_all_with_cost.empty:
            # === 售价加权版计算 ===
            df_all_with_cost['预测毛利（售价加权）'] = df_all_with_cost['原价'] - df_all_with_cost['预测成本']
            df_all_with_cost['预测毛利率（售价加权）'] = df_all_with_cost.apply(
                lambda row: (row['预测毛利（售价加权）'] / row['原价'] * 100) if pd.notna(row['原价']) and row['原价'] > 0 else None,
                axis=1
            ).round(2)
            
            # === 纯原价版计算 ===
            df_all_with_cost['预测成本（纯原价）'] = df_all_with_cost['预测成本_原价基准']
            df_all_with_cost['预测毛利（纯原价）'] = df_all_with_cost['原价'] - df_all_with_cost['预测成本（纯原价）']
            df_all_with_cost['预测毛利率（纯原价）'] = df_all_with_cost.apply(
                lambda row: (row['预测毛利（纯原价）'] / row['原价'] * 100) if pd.notna(row['原价']) and row['原价'] > 0 else None,
                axis=1
            ).round(2)
            
            # === 促销影响分析 ===
            # 计算折扣率（如果有售价）
            if '售价' in df_all_with_cost.columns:
                df_all_with_cost['折扣率'] = df_all_with_cost.apply(
                    lambda row: (row['售价'] / row['原价'] * 100) if pd.notna(row['原价']) and row['原价'] > 0 else None,
                    axis=1
                ).round(2)
            
            # 计算促销对毛利率的影响
            df_all_with_cost['促销影响'] = df_all_with_cost.apply(
                lambda row: (row['预测毛利率（纯原价）'] - row['预测毛利率（售价加权）']) if pd.notna(row['预测毛利率（纯原价）']) and pd.notna(row['预测毛利率（售价加权）']) else None,
                axis=1
            ).round(2)
            
            # 促销强度标记
            def mark_promotion_intensity(row):
                if pd.isna(row['促销影响']):
                    return None
                if row['促销影响'] >= 10:
                    return '深度促销'
                elif row['促销影响'] >= 5:
                    return '温和促销'
                elif row['促销影响'] >= 1:
                    return '轻微促销'
                else:
                    return '无促销'
            
            df_all_with_cost['促销强度'] = df_all_with_cost.apply(mark_promotion_intensity, axis=1)
            
            # 定义要展示的列（ABAB交替对比模式）
            all_product_cols = [
                # 商品基础信息
                '商品名称', '美团一级分类', '美团二级分类', '美团三级分类',
                '条码', '原价', '售价', '库存', '月售', '折扣率',
                
                # 售价加权版预测
                '预测成本', '预测毛利（售价加权）', '预测毛利率（售价加权）',
                
                # 纯原价版预测
                '预测成本（纯原价）', '预测毛利（纯原价）', '预测毛利率（纯原价）',
                
                # 对比分析
                '促销影响', '促销强度',
                
                # 预测元信息
                '预测方法', '置信度',
                
                # 可选：基准数据（供验证）
                '预测成本_原价基准', '预测成本_售价基准'
            ]
            
            # 添加其他可能存在的字段
            optional_cols = ['店内码', '品牌', '规格', '单位', '商品介绍', '店内分类']
            for col in optional_cols:
                if col in df_all_with_cost.columns and col not in all_product_cols:
                    all_product_cols.append(col)
            
            # 过滤存在的列
            all_product_cols = [col for col in all_product_cols if col in df_all_with_cost.columns]
            
            # 按促销强度和置信度排序（深度促销优先，便于识别关键商品）
            sort_keys = []
            sort_ascending = []
            
            if '促销强度' in df_all_with_cost.columns:
                # 定义促销强度排序权重
                promotion_order = {'深度促销': 1, '温和促销': 2, '轻微促销': 3, '无促销': 4}
                df_all_with_cost['_促销排序'] = df_all_with_cost['促销强度'].map(promotion_order).fillna(5)
                sort_keys.append('_促销排序')
                sort_ascending.append(True)
            
            sort_keys.append('置信度')
            sort_ascending.append(False)
            
            df_all_with_cost = df_all_with_cost.sort_values(
                by=sort_keys,
                ascending=sort_ascending
            )
            
            # 删除临时排序列
            if '_促销排序' in df_all_with_cost.columns:
                df_all_with_cost = df_all_with_cost.drop(columns=['_促销排序'])
            
            sheets['竞对全商品成本倒推'] = df_all_with_cost[all_product_cols].copy()
            
            # 统计促销分布
            promotion_stats = df_all_with_cost['促销强度'].value_counts().to_dict() if '促销强度' in df_all_with_cost.columns else {}
            promotion_summary = ', '.join([f"{k}:{v}个" for k, v in promotion_stats.items()]) if promotion_stats else "无"
            
            print(f"   ✅ 竞对全商品成本倒推: {len(df_all_with_cost)} 个商品（覆盖率 {len(df_all_with_cost)/len(store_b_all_df)*100:.1f}%）")
            print(f"      促销分布: {promotion_summary}")
    
    print(f"   ✅ 生成 {len(sheets)} 个成本分析 Sheet")
    return sheets


def generate_final_reports(df_all_a, df_all_b, barcode_matches, fuzzy_matches, name_a, name_b, cfg=None):
    """
    生成所有报告数据
    
    新增返回：
    - df_a_unique_dedup: 去重后的本店独有商品
    - df_b_unique_dedup: 去重后的竞对独有商品
    - df_differential: 差异品对比
    - df_category_gaps: 品类缺口分析
    """
    name_a_col, name_b_col = f'商品名称_{name_a}', f'商品名称_{name_b}'
    
    matched_names_a = set()
    if not barcode_matches.empty and name_a_col in barcode_matches.columns:
        matched_names_a.update(barcode_matches[name_a_col].dropna().tolist())
    if not fuzzy_matches.empty and name_a_col in fuzzy_matches.columns:
        matched_names_a.update(fuzzy_matches[name_a_col].dropna().tolist())

    matched_names_b = set()
    if not barcode_matches.empty and name_b_col in barcode_matches.columns:
        matched_names_b.update(barcode_matches[name_b_col].dropna().tolist())
    if not fuzzy_matches.empty and name_b_col in fuzzy_matches.columns:
        matched_names_b.update(fuzzy_matches[name_b_col].dropna().tolist())

    df_a_unique = df_all_a[~df_all_a['商品名称'].isin(matched_names_a)].copy()
    if not df_a_unique.empty and '店内码' in df_a_unique.columns:
        df_a_unique.rename(columns={'店内码': f'店内码_{name_a}'}, inplace=True)
    
    # 调试：检查vector列
    print(f"   🐛 调试: df_a_unique列名={df_a_unique.columns.tolist()[:10]}... (共{len(df_a_unique.columns)}列)")
    print(f"   🐛 调试: 'vector' in df_a_unique.columns = {('vector' in df_a_unique.columns)}")

    df_b_unique = df_all_b[~df_all_b['商品名称'].isin(matched_names_b)].copy()
    if not df_b_unique.empty and '店内码' in df_b_unique.columns:
        df_b_unique.rename(columns={'店内码': f'店内码_{name_b}'}, inplace=True)
    
    # 调试：检查vector列
    print(f"   🐛 调试: df_b_unique列名={df_b_unique.columns.tolist()[:10]}... (共{len(df_b_unique.columns)}列)")
    print(f"   🐛 调试: 'vector' in df_b_unique.columns = {('vector' in df_b_unique.columns)}")

    all_matches = pd.concat([barcode_matches, fuzzy_matches], ignore_index=True)
    sales_comparison_df = pd.DataFrame()
    discount_filter_df = pd.DataFrame()  # 新增：库存与折扣联合筛选结果
    if not all_matches.empty:
        df = all_matches.copy()
        price_a, price_b = f'售价_{name_a}', f'售价_{name_b}'
        orig_a, orig_b = f'原价_{name_a}', f'原价_{name_b}'
        sales_b = f'月售_{name_b}'
        inventory_a, inventory_b = f'库存_{name_a}', f'库存_{name_b}'

        for col in [price_a, price_b, orig_a, orig_b, sales_b, inventory_a, inventory_b]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        if orig_a in df.columns and orig_b in df.columns:
            df['折扣A'] = df[price_a] / df[orig_a]
            df['折扣B'] = df[price_b] / df[orig_b]
            
            sales_comparison_df = df[
                (df[sales_b] > 0) &
                (df[inventory_a] > 0) &
                (df[inventory_b] > 0) &
                (df['折扣A'] <= df['折扣B'])
            ].sort_values(by=sales_b, ascending=False)

            # 新增：生成“库存都>0、B月售>0、且A折扣>=B折扣（均不为空）”的数据集
            try:
                discount_filter_df = df[
                    (df[inventory_a] > 0) &
                    (df[inventory_b] > 0) &
                    (df[sales_b] > 0) &
                    df['折扣A'].notna() & df['折扣B'].notna() &
                    (df['折扣A'] >= df['折扣B'])
                ].sort_values(by=sales_b, ascending=False)
            except Exception:
                discount_filter_df = pd.DataFrame()
    
    # === 新增功能 2: 差异品分析（在去重前进行，需要vector列）===
    df_differential = find_differential_products(df_a_unique, df_b_unique, name_a, name_b, cfg)
    
    # === 新增功能 1: 独有商品去重 ===
    print(f"\n📦 独有商品去重处理...")
    df_a_unique_dedup = deduplicate_unique_products(df_a_unique, name_a)
    df_b_unique_dedup = deduplicate_unique_products(df_b_unique, name_b)
    
    # === 新增功能 3: 品类缺口分析（使用去重后的数据，更清晰）===
    df_category_gaps = analyze_category_gaps(df_a_unique_dedup, df_b_unique_dedup, name_a, name_b)
    
    # === 🆕 第一阶段功能: 竞对成本预测 ===
    cost_sheets = {}
    
    # 调试：检查成本列是否存在
    print(f"\n🔍 成本预测检查:")
    print(f"   ENABLE_COST_PREDICTION = {cfg.ENABLE_COST_PREDICTION if cfg else 'None'}")
    print(f"   COST_COLUMN_NAME = {cfg.COST_COLUMN_NAME if cfg else 'None'}")
    print(f"   df_all_a 列名包含: {[col for col in df_all_a.columns if '成本' in col or 'cost' in col.lower()]}")
    print(f"   '成本' in df_all_a.columns = {'成本' in df_all_a.columns}")
    
    if cfg and cfg.ENABLE_COST_PREDICTION and cfg.COST_COLUMN_NAME in df_all_a.columns:
        print(f"   ✅ 成本预测功能已启用")
        
        # 🔧 修复：对条码匹配和模糊匹配都进行成本预测
        if not barcode_matches.empty:
            print(f"   📊 对条码精确匹配商品进行成本预测...")
            barcode_matches = predict_competitor_cost(barcode_matches, df_all_a, cfg)
        
        if not fuzzy_matches.empty:
            print(f"   📊 对名称模糊匹配商品进行成本预测...")
            fuzzy_matches = predict_competitor_cost(fuzzy_matches, df_all_a, cfg)
        
        # 🔧 修复：合并条码匹配和模糊匹配的成本预测数据
        matched_with_cost = []
        if not barcode_matches.empty:
            matched_with_cost.append(barcode_matches)
        if not fuzzy_matches.empty:
            matched_with_cost.append(fuzzy_matches)
        
        all_matched_df = pd.concat(matched_with_cost, ignore_index=True) if matched_with_cost else pd.DataFrame()
        
        # 🔧 修复：去重（基于商品名称_B+规格_B，避免同一商品既在条码匹配又在模糊匹配中）
        if not all_matched_df.empty:
            name_col_b = f'商品名称_{cfg.STORE_B_NAME}' if f'商品名称_{cfg.STORE_B_NAME}' in all_matched_df.columns else '商品名称_B'
            spec_col_b = f'规格_{cfg.STORE_B_NAME}' if f'规格_{cfg.STORE_B_NAME}' in all_matched_df.columns else '规格_B'
            
            dedup_cols = [name_col_b]
            if spec_col_b in all_matched_df.columns:
                dedup_cols.append(spec_col_b)
            
            original_count = len(all_matched_df)
            all_matched_df = all_matched_df.drop_duplicates(subset=dedup_cols, keep='first')
            dedup_count = original_count - len(all_matched_df)
            
            if dedup_count > 0:
                print(f"   🔧 去重：移除{dedup_count}个重复匹配商品（合并后总计{len(all_matched_df)}个）")
        
        # 🆕 对竞对所有商品进行成本倒推（包括独有商品）
        # 🔧 修复：只倒推未匹配的商品，避免重复计算
        if not all_matched_df.empty:
            # 获取已匹配商品的条码列表（用于剔除）
            matched_barcodes = set()
            barcode_col_b = f'条码_B'
            if barcode_col_b in all_matched_df.columns:
                matched_barcodes = set(all_matched_df[barcode_col_b].dropna().astype(str))
            
            # 剔除已匹配的商品（基于条码）
            if matched_barcodes and '条码' in df_all_b.columns:
                df_b_unmatched = df_all_b[~df_all_b['条码'].astype(str).isin(matched_barcodes)].copy()
                print(f"   📊 竞对商品分类: 总{len(df_all_b)}个, 已匹配{len(matched_barcodes)}个, 待倒推{len(df_b_unmatched)}个")
            else:
                df_b_unmatched = df_all_b.copy()
                print(f"   ⚠️  无法基于条码剔除，将对全部{len(df_all_b)}个商品倒推")
            
            df_b_with_全商品成本 = predict_all_competitor_products_cost(df_b_unmatched, df_all_a, cfg)
        else:
            # 如果没有匹配商品，则对全部竞对商品倒推
            df_b_with_全商品成本 = predict_all_competitor_products_cost(df_all_b, df_all_a, cfg)
        
        # 生成成本分析Sheet（传入匹配商品和全商品数据）
        if not all_matched_df.empty:
            cost_sheets = generate_cost_analysis_sheets(all_matched_df, df_b_with_全商品成本, cfg)
        else:
            cost_sheets = {}
    else:
        print(f"   ⚠️  成本预测功能未启用，原因:")
        if not cfg:
            print(f"      - cfg 为 None")
        elif not cfg.ENABLE_COST_PREDICTION:
            print(f"      - ENABLE_COST_PREDICTION = False")
        elif cfg.COST_COLUMN_NAME not in df_all_a.columns:
            print(f"      - 列 '{cfg.COST_COLUMN_NAME}' 不存在于 df_all_a 中")
    
    return (df_a_unique, df_b_unique, sales_comparison_df, discount_filter_df,
            df_a_unique_dedup, df_b_unique_dedup, df_differential, df_category_gaps, cost_sheets)

def export_to_excel(writer, df, sheet_name, cfg=None):
    if df is not None and not df.empty:
        # 去掉向量列
        cols_to_drop = [col for col in df.columns if 'vector' in str(col)]
        
        # 🆕 步骤1: 删除所有临时辅助列（防止泄露到Excel）
        auxiliary_cols = [
            col for col in df.columns 
            if any(prefix in str(col) for prefix in [
                'cat3_group_', 'cat1_group_', 'category_id', 
                'cat3_group', 'cat1_group',  # 无后缀版本
                'index_'  # 索引列（如index_A, index_B）
            ])
        ]
        cols_to_drop.extend(auxiliary_cols)
        if auxiliary_cols:
            print(f"   🧹 清理临时辅助列: {auxiliary_cols}")
        
        
        # 全局：非清洗类Sheet一律移除清洗前缀列（cleaned_/standardized_brand/specs），避免干扰阅读
        is_cleaning_sheet = ('清洗数据' in sheet_name) or ('合并清洗数据对比' in sheet_name)
        if not is_cleaning_sheet:
            prefixed_cols = [col for col in df.columns if str(col).startswith('cleaned_') or str(col).startswith('standardized_brand') or str(col).startswith('specs')]
            cols_to_drop.extend(prefixed_cols)
            # 统一隐藏标准化后的分类列（有店铺后缀的形式），仅保留“美团一级/三级分类_*”
            std_category_cols = [col for col in df.columns if str(col).startswith('一级分类_') or str(col).startswith('三级分类_') or str(col).startswith('商家分类_')]
            cols_to_drop.extend(std_category_cols)

        # 对两张主要匹配结果Sheet，额外移除处理列与标准化分类，保持最简展示
        if any(keyword in sheet_name for keyword in ['条码精确匹配', '名称模糊匹配']):
            extra_cols = [col for col in df.columns if ('商家分类' in str(col)) or (str(col) in ['一级分类', '三级分类'])]
            cols_to_drop.extend(extra_cols)
            print(f"📋 {sheet_name}: 保留美团原始分类，已隐藏清洗/处理列")
        
        df = df.drop(columns=cols_to_drop, errors='ignore')
        
        # 🆕 步骤2: 统一列名后缀（店铺名 → _A/_B，确保ABAB排列生效）
        # 获取店铺名称：优先使用传入的cfg，否则使用Config类默认值
        if cfg:
            store_a = cfg.STORE_A_NAME
            store_b = cfg.STORE_B_NAME
        else:
            store_a = Config.STORE_A_NAME
            store_b = Config.STORE_B_NAME
        
        rename_map = {}
        for col in df.columns:
            # 只转换店铺名后缀，已经是_A/_B的不重复转换
            if col.endswith(f'_{store_a}') and not col.endswith('_A'):
                new_col = col.replace(f'_{store_a}', '_A')
                rename_map[col] = new_col
            elif col.endswith(f'_{store_b}') and not col.endswith('_B'):
                new_col = col.replace(f'_{store_b}', '_B')
                rename_map[col] = new_col
        
        if rename_map:
            df = df.rename(columns=rename_map)
            print(f"   🔄 统一列名后缀: {len(rename_map)} 列 (店铺名 → _A/_B)")
            if len(rename_map) <= 5:
                print(f"      示例: {list(rename_map.items())}")
            else:
                print(f"      示例: {list(rename_map.items())[:3]} ...")

        # 🔍 诊断调试输出
        print(f"\n🔍 [{sheet_name}] 列排序诊断:")
        print(f"   店铺A: {store_a}")
        print(f"   店铺B: {store_b}")
        print(f"   总列数: {len(df.columns)}")
        
        # 智能识别 A/B 列（支持店铺名后缀和 _A/_B 后缀）
        a_cols = []
        b_cols = []
        for col in df.columns:
            if col.endswith(f'_{store_a}') or col.endswith('_A'):
                a_cols.append(col)
            elif col.endswith(f'_{store_b}') or col.endswith('_B'):
                b_cols.append(col)
        common_cols = [col for col in df.columns if col not in a_cols + b_cols]
        
        print(f"   A店列数: {len(a_cols)}")
        print(f"   B店列数: {len(b_cols)}")
        print(f"   公共列数: {len(common_cols)}")
        if a_cols:
            print(f"   A店列示例: {a_cols[0]}")
        if b_cols:
            print(f"   B店列示例: {b_cols[0]}")

        # 定义需要ABAB排列的Sheet（对比类表格）
        # 🆕 统一布局：条码匹配、名称匹配、差异品、折扣优势都采用ABAB排列
        abab_sheets = ['条码精确匹配', '名称模糊匹配', '差异品对比', '库存>0&A折扣', '竞对成本预测', '利润空间对比', '成本优势商品']
        needs_abab = any(keyword in sheet_name for keyword in abab_sheets)
        print(f"   是否触发ABAB: {needs_abab}")
        
        if needs_abab:
            # ABAB列排列：按字段类型交替排列A店和B店的列
            print(f"📐 {sheet_name}: 启用ABAB列排列 (店铺: {store_a} vs {store_b})")
            
            # 定义核心字段顺序（按业务重要性）
            field_order = [
                '商品名称', '美团一级分类', '美团三级分类', '条码',
                '售价', '原价', '月售', '库存', '规格名称', '店内码', '折扣'
            ]
            
            # 🆕 自动发现额外字段（不在预定义列表中的A/B列）
            all_a_fields = set()
            all_b_fields = set()
            for col in a_cols:
                # 按优先级顺序移除后缀
                field_name = col
                if field_name.endswith(f'_{store_a}'):
                    field_name = field_name[:-len(f'_{store_a}')]
                elif field_name.endswith('_A'):
                    field_name = field_name[:-2]
                elif field_name.endswith('A'):
                    field_name = field_name[:-1]
                all_a_fields.add(field_name)
            for col in b_cols:
                # 按优先级顺序移除后缀
                field_name = col
                if field_name.endswith(f'_{store_b}'):
                    field_name = field_name[:-len(f'_{store_b}')]
                elif field_name.endswith('_B'):
                    field_name = field_name[:-2]
                elif field_name.endswith('B'):
                    field_name = field_name[:-1]
                all_b_fields.add(field_name)
            
            # 合并所有字段，添加到 field_order 末尾（去重）
            extra_fields = (all_a_fields | all_b_fields) - set(field_order)
            if extra_fields:
                print(f"   🔍 发现额外字段: {sorted(extra_fields)}")
                field_order.extend(sorted(extra_fields))  # 按字母顺序添加
            
            # 构建ABAB排列
            abab_cols = []
            for field in field_order:
                # 尝试多种列名变体（精确店铺名 > A/B后缀）
                col_a_variants = [f'{field}_{store_a}', f'{field}_A', f'{field}A']
                col_b_variants = [f'{field}_{store_b}', f'{field}_B', f'{field}B']
                
                # 查找A店列
                found_a = None
                for var in col_a_variants:
                    if var in df.columns:
                        found_a = var
                        break
                
                # 查找B店列
                found_b = None
                for var in col_b_variants:
                    if var in df.columns:
                        found_b = var
                        break
                
                # ABAB交替添加（优先添加配对的A-B列）
                if found_a and found_b:
                    if found_a not in abab_cols:
                        abab_cols.append(found_a)
                    if found_b not in abab_cols:
                        abab_cols.append(found_b)
                elif found_a:
                    if found_a not in abab_cols:
                        abab_cols.append(found_a)
                elif found_b:
                    if found_b not in abab_cols:
                        abab_cols.append(found_b)
            
            print(f"   ✅ ABAB核心列数: {len(abab_cols)}")
            if abab_cols:
                print(f"   前10列: {abab_cols[:10]}")
            
            # 添加特殊字段（折扣、相似度等）在ABAB列之后
            special_cols = []
            # 差异品对比特有：对比价格来源（动态识别店铺名）
            price_source_a = f'对比价格来源_{store_a}'
            price_source_b = f'对比价格来源_{store_b}'
            if price_source_a in df.columns:
                special_cols.extend([price_source_a, price_source_b])
            # 折扣字段（可能使用A/B或实际店铺名）
            if '折扣A' in df.columns:
                special_cols.extend(['折扣A', '折扣B'])
            elif f'折扣{store_a}' in df.columns:
                special_cols.extend([f'折扣{store_a}', f'折扣{store_b}'])
            # 相似度字段
            if 'composite_similarity_score' in df.columns:
                special_cols.append('composite_similarity_score')
            if 'price_diff_pct' in df.columns:  # 差异品对比：价差%
                special_cols.append('price_diff_pct')
            if 'similarity_score' in df.columns:  # 差异品对比：相似度
                special_cols.append('similarity_score')
            if '差异分析' in df.columns:
                special_cols.append('差异分析')
            if '分类一致性' in df.columns:  # 差异品对比：分类一致性检查
                special_cols.append('分类一致性')
            
            # 其余列：未匹配的A店列 -> 未匹配的B店列 -> 公共列
            a_rest = [c for c in a_cols if c not in abab_cols]
            b_rest = [c for c in b_cols if c not in abab_cols]
            common_rest = [c for c in common_cols if c not in abab_cols + special_cols]
            
            # 最终列顺序
            final_cols = abab_cols + special_cols + a_rest + b_rest + common_rest
            df = df[[c for c in final_cols if c in df.columns]]
            
            # 🔍 保存调试信息到文件
            # 清理文件名中的非法字符（Windows: < > : " / \ | ? *）
            safe_sheet_name = sheet_name.replace('/', '-').replace('\\', '-').replace(':', '-').replace('*', '-').replace('?', '-').replace('<', '-').replace('>', '-').replace('|', '-').replace('"', '')
            debug_file = f"d:/abab_debug_{safe_sheet_name}.txt"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(f"Sheet: {sheet_name}\n")
                f.write(f"店铺: {store_a} vs {store_b}\n\n")
                f.write(f"ABAB列({len(abab_cols)}):\n")
                for i, col in enumerate(abab_cols, 1):
                    f.write(f"  {i}. {col}\n")
                f.write(f"\nSpecial列({len(special_cols)}):\n")
                for col in special_cols:
                    f.write(f"  - {col}\n")
                f.write(f"\n最终列顺序(前20):\n")
                for i, col in enumerate(list(df.columns)[:20], 1):
                    f.write(f"  {i}. {col}\n")
            print(f"   💾 调试信息已保存到: {debug_file}")
        else:
            # 非对比类表格：默认 A列 + B列 + 其他
            ordered_cols = a_cols + b_cols + common_cols
            df = df[ordered_cols]

        # 清洗并确保工作表名合法且唯一
        try:
            existing_names = set(getattr(writer.book, 'sheetnames', []) or [])
        except Exception:
            existing_names = set()
        safe_name = _sanitize_sheet_name(sheet_name, existing_names)
        
        # 🆕 步骤4: Excel展示时将 _A/_B 转换为实际店铺名称（仅用于显示，不影响数据处理）
        display_df = df.copy()
        display_rename = {}
        for col in display_df.columns:
            if col.endswith('_A'):
                display_rename[col] = col.replace('_A', f'_{store_a}')
            elif col.endswith('_B'):
                display_rename[col] = col.replace('_B', f'_{store_b}')
        
        if display_rename:
            display_df = display_df.rename(columns=display_rename)
            print(f"   📊 Excel展示: {len(display_rename)} 列转换为店铺名称")
        
        display_df.to_excel(writer, sheet_name=safe_name, index=False)
        logging.info(f"✅ 工作表「{safe_name}」已导出，包含 {len(df)} 条记录。")
    else:
        try:
            existing_names = set(getattr(writer.book, 'sheetnames', []) or [])
        except Exception:
            existing_names = set()
        safe_name = _sanitize_sheet_name(sheet_name, existing_names)
        pd.DataFrame([{"提示": "此分类下无数据"}]).to_excel(writer, sheet_name=safe_name, index=False)
        logging.info(f"⚠️ 工作表「{safe_name}」无数据，已导出为空白页。")

# ==============================================================================
# 5. 主执行流程 (Main Workflow)
# ==============================================================================
def main():
    # 修复 Windows 控制台编码问题（支持中文和 emoji 输出）
    import sys
    import os
    
    # 设置环境变量强制UTF-8（必须在任何输出前设置）
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    if sys.platform == 'win32':
        try:
            import io
            # 重新包装 stdout/stderr 为 UTF-8 模式（仅当有效时）
            if sys.stdout is not None and hasattr(sys.stdout, 'buffer'):
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
            if sys.stderr is not None and hasattr(sys.stderr, 'buffer'):
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
            
            # Windows 控制台代码页设置为 UTF-8（CMD模式）
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass  # 如果设置失败，继续运行
    
    print("\n" + "="*60)
    print("  商品比对分析工具 v8.5 启动中...")
    print("="*60)
    
    cfg = Config()

    # 🆕 重载模型环境变量（GUI模式传递，需要在 Config 实例化后再次读取）
    embedding_model_override = os.environ.get('EMBEDDING_MODEL')
    reranker_model_override = os.environ.get('RERANKER_MODEL')
    if embedding_model_override:
        cfg.SENTENCE_BERT_MODEL = embedding_model_override
        print(f"✅ 嵌入模型已切换: {embedding_model_override}")
    if reranker_model_override:
        cfg.ONLINE_CROSS_ENCODER = reranker_model_override
        print(f"✅ 精排模型已切换: {reranker_model_override}")

    # 需要在函数顶部声明，以便后续异常分支可以修改该全局变量
    global SIMPLE_FALLBACK

    # 环境变量覆盖（便于与爬虫联动）：
    # COMPARE_STORE_A_FILE / COMPARE_STORE_B_FILE: 直接指定A/B店数据文件的绝对路径
    # COMPARE_STORE_A_NAME / COMPARE_STORE_B_NAME: 覆盖店铺显示名称
    env_a_file = os.environ.get('COMPARE_STORE_A_FILE')
    env_b_file = os.environ.get('COMPARE_STORE_B_FILE')
    env_a_name = os.environ.get('COMPARE_STORE_A_NAME')
    env_b_name = os.environ.get('COMPARE_STORE_B_NAME')
    if env_a_name:
        cfg.STORE_A_NAME = env_a_name
    if env_b_name:
        cfg.STORE_B_NAME = env_b_name
    # 若提供了文件但未提供显示名，则用文件名主干作为显示名（与自动比价子进程保持一致）
    try:
        from pathlib import Path as _Path
        if (not env_a_name) and env_a_file:
            cfg.STORE_A_NAME = _Path(env_a_file).stem[:40]
        if (not env_b_name) and env_b_file:
            cfg.STORE_B_NAME = _Path(env_b_file).stem[:40]
    except Exception:
        pass

    print("\n" + "="*50)
    print("⏳ [步骤 1/7] 检测硬件加速器 (GPU/CPU)...")
    forced = getattr(Config, 'FORCE_DEVICE', None)
    
    # 检查是否有环境变量强制禁用CUDA
    if os.environ.get('CUDA_VISIBLE_DEVICES') == '':
        print("🛠️ 检测到CUDA_VISIBLE_DEVICES=''，强制使用CPU模式")
        device = 'cpu'
    elif forced in ('cuda', 'cpu'):
        device = forced
        print(f"🛠️ 按配置强制使用设备: {device}")
    else:
        # 安全的CUDA可用性检查
        cuda_available = False
        try:
            cuda_available = torch.cuda.is_available()
            if cuda_available:
                # 尝试简单的CUDA操作以确认真正可用
                test_tensor = torch.tensor([1.0]).cuda()
                del test_tensor
                torch.cuda.empty_cache()
        except Exception as cuda_error:
            print(f"⚠️ CUDA检测失败: {cuda_error}")
            cuda_available = False
        
        device = 'cuda' if cuda_available else 'cpu'
        
        # 🚀 自动启用GPU加速：如果检测到GPU，自动设置环境变量
        if cuda_available and os.environ.get('USE_TORCH_SIM') != '1':
            os.environ['USE_TORCH_SIM'] = '1'
            print("🚀 检测到NVIDIA GPU，自动启用GPU加速（向量相似度计算）")
    
    if device == 'cuda':
        print("✅ 使用 GPU 运行（已安装 GPU 版 PyTorch）")
        try:
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"   GPU: {gpu_name} ({gpu_memory:.1f} GB)")
        except:
            pass
    else:
        print("ℹ️ 使用 CPU 运行（未检测到可用 GPU 或未指定使用 GPU）")

    print("\n" + "="*50)
    print("⏳ [步骤 2/7] 正在加载文本分析模型 (若本地无缓存，将自动下载)...")
    
    # 交互式选择 Sentence-BERT 模型（粗筛）
    selected_model = select_embedding_model(cfg)
    if selected_model != cfg.SENTENCE_BERT_MODEL:
        # 查找模型的友好名称
        model_display_name = selected_model
        for model_info in getattr(cfg, 'AVAILABLE_MODELS', {}).values():
            if model_info['name'] == selected_model:
                model_display_name = model_info['display_name']
                break
        cfg.SENTENCE_BERT_MODEL = selected_model
        print(f"\n📝 已切换 Sentence-BERT 到: {model_display_name}")
        print(f"   模型ID: {selected_model}")
    
    # 交互式选择 Cross-Encoder 模型（精排）
    selected_ce_model = select_cross_encoder_model(cfg)
    if selected_ce_model != cfg.ONLINE_CROSS_ENCODER:
        # 查找模型的友好名称
        ce_display_name = selected_ce_model
        for model_info in getattr(cfg, 'AVAILABLE_CROSS_ENCODERS', {}).values():
            if model_info['name'] == selected_ce_model:
                ce_display_name = model_info['display_name']
                break
        cfg.ONLINE_CROSS_ENCODER = selected_ce_model
        print(f"\n📝 已切换 Cross-Encoder 到: {ce_display_name}")
        print(f"   模型ID: {selected_ce_model}")
    
    # 环境变量覆盖本地模型路径/策略
    env_local_sbert = os.environ.get('LOCAL_SENTENCE_BERT_PATH')
    env_use_local_sbert = os.environ.get('USE_LOCAL_SENTENCE_BERT')
    if env_local_sbert:
        cfg.LOCAL_SENTENCE_BERT_PATH = env_local_sbert
        cfg.USE_LOCAL_SENTENCE_BERT = True if str(env_use_local_sbert or '1') == '1' else cfg.USE_LOCAL_SENTENCE_BERT

    env_local_ce = os.environ.get('LOCAL_CROSS_ENCODER_PATH')
    env_use_local_ce = os.environ.get('USE_LOCAL_CROSS_ENCODER')
    if env_local_ce:
        cfg.LOCAL_CROSS_ENCODER_PATH = env_local_ce
        cfg.USE_LOCAL_CROSS_ENCODER = True if str(env_use_local_ce or '1') == '1' else cfg.USE_LOCAL_CROSS_ENCODER

    # 智能检测模型是否需要下载（开发环境提示，打包环境跳过）
    # ⚠️ 关键：必须先定义 model_exists 默认值（打包环境也会用到）
    model_exists = False
    
    # 打包环境：检测内置模型是否存在
    if getattr(sys, 'frozen', False):
        local_model_path = get_local_model_path(cfg.SENTENCE_BERT_MODEL)
        model_exists = os.path.exists(local_model_path)
        if not model_exists:
            print(f"⚠️  打包环境未找到模型: {local_model_path}")
    
    # 开发环境：检测和提示
    if not getattr(sys, 'frozen', False):
        if getattr(cfg, 'USE_LOCAL_SENTENCE_BERT', False) and os.path.exists(cfg.LOCAL_SENTENCE_BERT_PATH):
            model_exists = True
        else:
            model_exists = check_model_exists(cfg.SENTENCE_BERT_MODEL)
        
        if model_exists:
            print("⚡ 检测到本地模型缓存，快速加载中...")
        else:
            # 动态获取模型大小信息
            model_size = "未知大小"
            download_time = "几分钟"
            for model_info in getattr(cfg, 'AVAILABLE_MODELS', {}).values():
                if model_info['name'] == cfg.SENTENCE_BERT_MODEL:
                    model_size = model_info.get('size', '未知大小')
                    # 根据大小估算下载时间
                    if 'GB' in model_size or 'gb' in model_size:
                        size_num = float(model_size.replace('~', '').replace('GB', '').replace('gb', '').strip())
                        if size_num >= 2:
                            download_time = "10-20分钟"
                        elif size_num >= 1:
                            download_time = "5-10分钟"
                        else:
                            download_time = "3-5分钟"
                    elif 'MB' in model_size or 'mb' in model_size:
                        download_time = "1-3分钟"
                    break
            
            print(f"💡 首次使用此模型，需要下载模型文件（{model_size}，预计{download_time}）")
            print(f"📥 下载模型: {cfg.SENTENCE_BERT_MODEL}")
            print("⏳ 请耐心等待，模型将自动缓存到本地...")
    
    try:
        # 只要 USE_LOCAL_SENTENCE_BERT=1 或本地模型目录存在，强制只用本地路径加载，彻底断网
        use_local = getattr(cfg, 'USE_LOCAL_SENTENCE_BERT', False)
        local_path = getattr(cfg, 'LOCAL_SENTENCE_BERT_PATH', None)
        local_path_exists = local_path and os.path.exists(local_path)
        for _k in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']:
            os.environ.pop(_k, None)
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        if use_local and local_path_exists:
            print(f"📱 强制仅用本地目录加载 Sentence-BERT: {local_path}")
            try:
                model = SentenceTransformer(local_path, device=device, use_auth_token=False)
            except Exception as e:
                if 'cuda' in str(e).lower() or 'gpu' in str(e).lower():
                    print(f"⚠️ GPU模式加载失败，切换到CPU: {e}")
                    device = 'cpu'
                    model = SentenceTransformer(local_path, device=device, use_auth_token=False)
                else:
                    raise e
        elif model_exists:
            # 打包环境：直接使用 get_local_model_path() 获取内置模型路径
            # 开发环境：从 huggingface 缓存加载
            if getattr(sys, 'frozen', False):
                # 打包环境：使用内置模型
                print("📱 使用打包的内置模型加载 Sentence-BERT...")
                bundled_model_path = get_local_model_path(cfg.SENTENCE_BERT_MODEL)
                try:
                    model = SentenceTransformer(bundled_model_path, device=device, use_auth_token=False)
                except Exception as e:
                    if 'cuda' in str(e).lower() or 'gpu' in str(e).lower():
                        print(f"⚠️ GPU模式加载失败，切换到CPU: {e}")
                        device = 'cpu'
                        model = SentenceTransformer(bundled_model_path, device=device, use_auth_token=False)
                    else:
                        raise e
            else:
                # 开发环境：从 huggingface 缓存加载
                print("📱 强制仅用本地缓存加载 Sentence-BERT...")
                from pathlib import Path
                # 自动定位 huggingface hub 缓存下的 snapshots 子目录
                hub_cache = Path.home() / ".cache" / "huggingface" / "hub" / f"models--sentence-transformers--{cfg.SENTENCE_BERT_MODEL}" / "snapshots"
                if hub_cache.exists():
                    # 取最新的快照目录
                    latest = sorted(hub_cache.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[0]
                    try:
                        model = SentenceTransformer(str(latest), device=device, use_auth_token=False)
                    except Exception as e:
                        if 'cuda' in str(e).lower() or 'gpu' in str(e).lower():
                            print(f"⚠️ GPU模式加载失败，切换到CPU: {e}")
                            device = 'cpu'
                            model = SentenceTransformer(str(latest), device=device, use_auth_token=False)
                        else:
                            raise e
                else:
                    raise RuntimeError("未找到本地缓存快照目录")
        else:
            # 开发环境：首次使用需要下载模型（保留在线下载功能）
            # 打包环境：直接使用内置模型（不应该走到这里）
            if getattr(sys, 'frozen', False):
                # 打包环境但模型不存在 - 打包异常
                error_msg = (
                    "❌ 打包模型缺失\n\n"
                    f"未找到模型: {cfg.SENTENCE_BERT_MODEL}\n\n"
                    "这可能是打包异常导致的，请联系管理员重新获取完整的安装包。"
                )
                if os.environ.get('GUI_MODE') == '1':
                    try:
                        import tkinter as tk
                        from tkinter import messagebox
                        root = tk.Tk()
                        root.withdraw()
                        messagebox.showerror("模型缺失", error_msg)
                        root.destroy()
                    except:
                        print(error_msg)
                else:
                    print(error_msg)
                sys.exit(1)
            
            # 开发环境下载模型
            print("📥 首次使用，正在下载模型...")
            print("💡 提示：如需加速，可设置镜像源: $env:HF_ENDPOINT='https://hf-mirror.com'")
            
            # 使用本地路径（开发环境仍会触发下载）
            model_path = get_local_model_path(cfg.SENTENCE_BERT_MODEL)
            
            try:
                model = SentenceTransformer(model_path, device=device, use_auth_token=False)
            except Exception as e:
                if 'cuda' in str(e).lower() or 'gpu' in str(e).lower():
                    print(f"⚠️ GPU模式加载失败，切换到CPU: {e}")
                    device = 'cpu'
                    model = SentenceTransformer(model_path, device=device, use_auth_token=False)
                else:
                    raise e
            print("✅ 模型下载并加载成功！下次运行将直接使用缓存。")

        model.encode(["测试"], show_progress_bar=False)  # 测试模型是否可用
        print("✅ Sentence-BERT 模型加载成功！")

        # 尝试加载Cross-Encoder模型
        cross_encoder = None
        try:
            # 允许通过环境变量强制禁用 Cross-Encoder（避免联网或潜在卡顿）
            if os.environ.get('DISABLE_CROSS_ENCODER', '0') == '1':
                print("⚙️ 已根据环境变量禁用 Cross-Encoder 精排（DISABLE_CROSS_ENCODER=1）")
                cross_encoder = None
            elif getattr(cfg, 'USE_LOCAL_CROSS_ENCODER', False):
                cross_encoder_path = cfg.LOCAL_CROSS_ENCODER_PATH
                if os.path.exists(cross_encoder_path):
                    cross_encoder = CrossEncoder(cross_encoder_path, device=device) if CrossEncoder else None
                    print("✅ 本地Cross-Encoder模型加载成功！")
                else:
                    print("⚠️ 本地Cross-Encoder模型路径不存在，将使用在线模型")
                    cross_encoder = CrossEncoder(cfg.ONLINE_CROSS_ENCODER, device=device) if CrossEncoder else None
            else:
                print("⏳ 正在加载Cross-Encoder模型...")
                
                # 使用本地路径（打包环境直接用内置模型，开发环境用缓存）
                cross_encoder_model_path = get_local_model_path(cfg.ONLINE_CROSS_ENCODER)
                print(f"📁 使用打包的本地模型: {cross_encoder_model_path}")
                
                # 尝试多种加载方式以提高兼容性
                cross_encoder = None
                if CrossEncoder:
                    try:
                        # 方式1：标准加载
                        cross_encoder = CrossEncoder(cross_encoder_model_path, device=device)
                        print("✅ Cross-Encoder模型加载成功！")
                    except Exception as e1:
                        if "metaclip" in str(e1).lower() or "No module named" in str(e1):
                            # 方式2：使用 trust_remote_code（解决模块导入问题）
                            try:
                                print(f"   ⚙️  检测到模块导入问题，尝试使用兼容模式...")
                                cross_encoder = CrossEncoder(
                                    cross_encoder_model_path, 
                                    device=device,
                                    trust_remote_code=True  # 信任远程代码，绕过模块检查
                                )
                                print("✅ Cross-Encoder模型加载成功（兼容模式）！")
                            except Exception as e2:
                                # 方式3：降级到AutoModelForSequenceClassification
                                try:
                                    print(f"   ⚙️  尝试使用 AutoModel 直接加载...")
                                    from transformers import AutoModelForSequenceClassification, AutoTokenizer
                                    tokenizer = AutoTokenizer.from_pretrained(cross_encoder_model_path)
                                    model = AutoModelForSequenceClassification.from_pretrained(
                                        cross_encoder_model_path,
                                        trust_remote_code=True
                                    ).to(device)
                                    # 手动包装成 CrossEncoder 兼容对象
                                    class ManualCrossEncoder:
                                        def __init__(self, model, tokenizer, device):
                                            self.model = model
                                            self.tokenizer = tokenizer
                                            self.device = device
                                        
                                        def predict(self, sentences, batch_size=32, show_progress_bar=False):
                                            import torch
                                            scores = []
                                            for i in range(0, len(sentences), batch_size):
                                                batch = sentences[i:i+batch_size]
                                                inputs = self.tokenizer(
                                                    batch, 
                                                    padding=True, 
                                                    truncation=True, 
                                                    return_tensors="pt",
                                                    max_length=512
                                                ).to(self.device)
                                                with torch.no_grad():
                                                    outputs = self.model(**inputs)
                                                    batch_scores = outputs.logits[:, 0].cpu().numpy()
                                                scores.extend(batch_scores)
                                            return scores
                                    
                                    cross_encoder = ManualCrossEncoder(model, tokenizer, device)
                                    print("✅ Cross-Encoder模型加载成功（AutoModel模式）！")
                                except Exception as e3:
                                    raise e1  # 抛出最初的错误
                        else:
                            raise e1
        except Exception as ce_error:
            error_msg = str(ce_error)
            print(f"\n❌ Cross-Encoder模型加载失败（严重错误）:")
            print(f"   错误: {error_msg}")
            
            # 判断错误类型并给出针对性建议
            if "couldn't connect" in error_msg or "Connection" in error_msg:
                if getattr(sys, 'frozen', False):
                    # 打包环境不应该有网络问题（模型已内置）
                    print(f"\n❌ 意外的网络错误（打包版本不应联网）")
                    print(f"   这可能是打包异常或文件损坏")
                    print(f"   请联系管理员重新获取安装包")
                else:
                    # 开发环境提供网络解决方案
                    print(f"\n🌐 网络连接问题检测到！")
                    print(f"   当前尝试下载的模型: {cfg.ONLINE_CROSS_ENCODER}")
                    print(f"\n💡 快速解决方案:")
                    print(f"   1. ⚡ 使用镜像源（推荐）:")
                    print(f"      在终端执行: $env:HF_ENDPOINT='https://hf-mirror.com'")
                    print(f"   2. � 手动下载模型并放到缓存目录")
            elif "metaclip" in error_msg.lower():
                print(f"\n🔧 模型兼容性问题:")
                print(f"   transformers 库可能缺少必要的模型组件")
                print(f"\n💡 解决方案:")
                print(f"   1. 更新 transformers: pip install --upgrade transformers")
                print(f"   2. 重新安装依赖: pip install -r requirements.txt")
            
            # ❌ 不接受降级，直接退出
            print(f"\n❌ Cross-Encoder 是核心组件，程序无法在降级模式下运行")
            print(f"   请修复上述问题后重新启动")
            sys.exit(1)

    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        
        if getattr(sys, 'frozen', False):
            # 打包环境模型加载失败 - 严重错误
            print("\n❌ 打包环境模型加载失败")
            print("   这可能是打包异常或文件损坏，请联系管理员重新获取安装包")
            sys.exit(1)
        else:
            # 开发环境提供详细解决方案
            print("\n🔧 可能的解决方案:")
            print("1. 网络问题解决:")
            print("   - 检查网络连接是否稳定")
            print("   - 设置镜像源: $env:HF_ENDPOINT='https://hf-mirror.com'")
            print("\n2. 依赖库更新:")
            print("   pip install --upgrade sentence-transformers torch transformers")
            print("\n3. 强制离线模式:")
            print("   - 设置: $env:TRANSFORMERS_OFFLINE='1'")
            
            print("\n正在尝试使用备用方案...")
            
            if SIMPLE_FALLBACK:
                # 仅在明确允许时才降级
                SIMPLE_FALLBACK = True
                model = None
                cross_encoder = None
                print("⚡ 已切换到简化兜底模式：使用轻量文本相似度完成匹配")
            else:
                print("🚫 已禁止降级兜底模式。为保证准确率，程序将退出。")
                sys.exit(1)

    print("\n" + "="*50)
    print("⏳ [步骤 3/7] 正在查找本地文件...")
    
    # 优先级：环境变量 > 上传目录 > 配置文件
    store_a_file = None
    store_b_file = None
    
    try:
        # 1. 优先使用环境变量指定的文件
        if env_a_file and os.path.exists(env_a_file) and env_b_file and os.path.exists(env_b_file):
            store_a_file = env_a_file
            store_b_file = env_b_file
            print(f"✅ 通过环境变量指定文件:")
            print(f"  本店: {store_a_file}")
            print(f"  竞对: {store_b_file}")
        
        # 2. 尝试从上传目录检测文件（如果启用）
        elif getattr(cfg, 'USE_UPLOAD_DIRS', True):
            store_a_file, store_b_file, auto_name_a, auto_name_b = detect_files_from_upload_dirs(cfg)
            
            print(f"\n🔍 调试信息:")
            print(f"  检测到的文件A: {store_a_file}")
            print(f"  检测到的文件B: {store_b_file}")
            print(f"  店铺名A: {auto_name_a}")
            print(f"  店铺名B: {auto_name_b}")
            
            # 如果检测到文件，更新店铺名称
            if store_a_file and store_b_file:
                cfg.STORE_A_NAME = auto_name_a
                cfg.STORE_B_NAME = auto_name_b
                print(f"\n📝 已自动识别店铺名称:")
                print(f"  🏪 本店: {cfg.STORE_A_NAME}")
                print(f"  🏬 竞对: {cfg.STORE_B_NAME}")
            else:
                print(f"\n⚠️ 文件检测失败，将回退到配置文件模式")
        
        # 3. 回退到配置文件指定的文件名
        if not store_a_file or not store_b_file:
            print("\n🔄 使用配置文件中指定的文件名...")
            if not store_a_file:
                store_a_file = get_local_filepath(cfg.STORE_A_FILENAME)
            if not store_b_file:
                store_b_file = get_local_filepath(cfg.STORE_B_FILENAME)
        
    except Exception as e:
        print(f"[错误] 文件查找失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if not all([store_a_file, store_b_file]):
        print("\n❌ Missing required store files. Please ensure:")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        upload_a = os.path.join(base_dir, getattr(cfg, 'UPLOAD_DIR_STORE_A', 'upload/store_a'))
        upload_b = os.path.join(base_dir, getattr(cfg, 'UPLOAD_DIR_STORE_B', 'upload/store_b'))
        print(f"  1. Put your store Excel file in: {upload_a}")
        print(f"  2. Put competitor Excel file in: {upload_b}")
        print(f"  OR")
        print(f"  3. Set correct filenames in config, OR")
        print(f"  4. Use environment variables COMPARE_STORE_* to specify absolute paths")
        print(f"\nCurrent script directory: {base_dir}")
        sys.exit(1)

    print("\n" + "="*50)
    print(f"⏳ [步骤 4/7] 正在处理「{cfg.STORE_A_NAME}」的数据...")
    try:
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), cfg.EMBEDDING_CACHE_FILE)
        print(f"💾 启用向量缓存: {os.path.basename(cache_path)}")
        df_a_barcode, df_a_no_barcode = load_and_process_store_data(store_a_file, model, cache_path, role='A')
    except Exception as e:
        print(f"[错误] 处理A店数据失败: {e}")
        sys.exit(1)

    print(f"\n⏳ [步骤 4/7] 正在处理「{cfg.STORE_B_NAME}」的数据...")
    try:
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), cfg.EMBEDDING_CACHE_FILE)
        print(f"💾 启用向量缓存: {os.path.basename(cache_path)}")
        df_b_barcode, df_b_no_barcode = load_and_process_store_data(store_b_file, model, cache_path, role='B')
    except Exception as e:
        print(f"[错误] 处理B店数据失败: {e}")
        sys.exit(1)

    print("\n" + "="*50)
    print("⏳ [步骤 5/7] 正在进行商品匹配...")
    try:
        # --- 阶段1: 条码精确匹配 ---
        # 🔧 使用简短后缀 A/B 替代店铺名，确保ABAB排列生效
        barcode_matches_df = match_by_barcode(df_a_barcode, df_b_barcode, "A", "B")
        logging.info(f"【阶段1/3】条码精确匹配找到 {len(barcode_matches_df)} 个商品。")

        # --- 准备模糊匹配池 ---
        # 找出在条码匹配中未成功的商品
        if not barcode_matches_df.empty:
            # 正确的逻辑：合并后的条码列就叫'条码'，直接用它来获取已匹配的条码列表
            matched_barcodes = barcode_matches_df['条码'].unique()
            
            unmatched_a_with_barcode = df_a_barcode[~df_a_barcode['条码'].isin(matched_barcodes)]
            unmatched_b_with_barcode = df_b_barcode[~df_b_barcode['条码'].isin(matched_barcodes)]
        else:
            unmatched_a_with_barcode = df_a_barcode
            unmatched_b_with_barcode = df_b_barcode

        # 合并【有条码但未匹配上的】和【无条码的】商品，形成完整的模糊匹配池
        fuzzy_pool_a = pd.concat([unmatched_a_with_barcode, df_a_no_barcode], ignore_index=True)
        fuzzy_pool_b = pd.concat([unmatched_b_with_barcode, df_b_no_barcode], ignore_index=True)

        logging.info(f"【准备模糊匹配】A店进入模糊匹配池的商品数: {len(fuzzy_pool_a)} (有码未匹配: {len(unmatched_a_with_barcode)}, 无码: {len(df_a_no_barcode)})")
        logging.info(f"【准备模糊匹配】B店进入模糊匹配池的商品数: {len(fuzzy_pool_b)} (有码未匹配: {len(unmatched_b_with_barcode)}, 无码: {len(df_b_no_barcode)})")

        # === 可选：按B侧分类自动限域（减少A侧搜索空间，提高速度且不降准确率） ===
        try:
            auto_scope_cat1 = os.environ.get('AUTO_SCOPE_BY_B_CAT1', '1') == '1'
            auto_scope_cat3 = os.environ.get('AUTO_SCOPE_BY_B_CAT3', '0') == '1'
            max_cat1 = int(os.environ.get('SCOPE_CAT1_MAX', '3'))
            max_cat3 = int(os.environ.get('SCOPE_CAT3_MAX', '6'))

            a_before = len(fuzzy_pool_a)
            scope_msgs = []
            if auto_scope_cat1 and '一级分类' in fuzzy_pool_b.columns and '一级分类' in fuzzy_pool_a.columns:
                cats1 = sorted(set(str(x) for x in fuzzy_pool_b['一级分类'].dropna().unique()))
                if 0 < len(cats1) <= max_cat1:
                    fuzzy_pool_a = fuzzy_pool_a[fuzzy_pool_a['一级分类'].astype(str).isin(cats1)]
                    scope_msgs.append(f"按B的一级分类限域({len(cats1)}类) → A: {a_before} -> {len(fuzzy_pool_a)}")
                    a_before = len(fuzzy_pool_a)

            if auto_scope_cat3 and '三级分类' in fuzzy_pool_b.columns and '三级分类' in fuzzy_pool_a.columns:
                cats3 = sorted(set(str(x) for x in fuzzy_pool_b['三级分类'].dropna().unique()))
                if 0 < len(cats3) <= max_cat3:
                    fuzzy_pool_a = fuzzy_pool_a[fuzzy_pool_a['三级分类'].astype(str).isin(cats3)]
                    scope_msgs.append(f"按B的三级分类限域({len(cats3)}类) → A: {a_before} -> {len(fuzzy_pool_a)}")

            for m in scope_msgs:
                logging.info(f"【自动限域】{m}")
            if not scope_msgs:
                logging.info("【自动限域】未生效（B分类数量超过阈值或未启用）")
        except Exception as _:
            logging.info("【自动限域】执行出错，已忽略")
        # 额外提示：可能的耗时与模式
        try:
            use_simple = SIMPLE_FALLBACK or (len(fuzzy_pool_a) == 0 or len(fuzzy_pool_b) == 0 or (hasattr(fuzzy_pool_a['vector'].iloc[0], 'shape') and fuzzy_pool_a['vector'].iloc[0].shape == (1,)))
        except Exception:
            use_simple = SIMPLE_FALLBACK
        k_hard = int(os.environ.get('MATCH_TOPK_HARD', '20'))
        k_soft = int(os.environ.get('MATCH_TOPK_SOFT', '100'))
        gpu_sim = (os.environ.get('USE_TORCH_SIM','0')=='1' and torch.cuda.is_available())
        mode_text = '简化兜底(无向量/无CE)' if use_simple else f"向量+可选CE精排{' + GPU相似度' if gpu_sim else ''}"
        print(f"ℹ️ 匹配模式: {mode_text}，Top-K: 硬{k_hard}/软{k_soft}；样本规模 A={len(fuzzy_pool_a)} / B={len(fuzzy_pool_b)}")
        # 提醒任何过滤或采样配置
        if os.environ.get('COMPARE_CAT1_LIST') or os.environ.get('COMPARE_CAT1_REGEX'):
            print("🔎 已按一级分类进行预过滤 (COMPARE_CAT1_LIST/COMPARE_CAT1_REGEX)")
        if os.environ.get('COMPARE_MAX_A') or os.environ.get('COMPARE_MAX_B'):
            print(f"🧪 采样限制: A={os.environ.get('COMPARE_MAX_A') or '不限'} / B={os.environ.get('COMPARE_MAX_B') or '不限'}")
        if len(fuzzy_pool_a) * len(fuzzy_pool_b) > 200000:
            print("⏱️ 数据量较大，匹配可能需要几分钟，请耐心等待...（期间会有进度条）")


        # --- 阶段2: 硬分类优先匹配 (针对完整的模糊匹配池) ---
        logging.info(f"【阶段2/3】正在对所有未匹配商品进行“硬分类优先”匹配...")
        # 🔧 使用简短后缀 A/B 替代店铺名，确保ABAB排列生效
        hard_matches_df, unmatched_a_df, unmatched_b_df = perform_hard_category_matching(
            fuzzy_pool_a, fuzzy_pool_b, "A", "B", cross_encoder, cfg
        )
        logging.info(f"✅ 硬分类匹配找到 {len(hard_matches_df)} 个匹配。")
        logging.info(f"   - 剩余A店商品: {len(unmatched_a_df)}, B店商品: {len(unmatched_b_df)} 进入下一阶段。")

        # --- 阶段3: 软分类兜底匹配 (针对剩余商品) ---
        logging.info(f"【阶段3/3】正在对剩余商品进行“软分类兜底”匹配...")
        # 🔧 使用简短后缀 A/B 替代店铺名，确保ABAB排列生效
        soft_matches_df = perform_soft_fuzzy_matching(
            unmatched_a_df, unmatched_b_df, "A", "B", cross_encoder, cfg
        )
        logging.info(f"✅ 软分类兜底匹配找到 {len(soft_matches_df)} 个额外匹配。")

        # --- 合并所有模糊匹配结果 ---
        fuzzy_matches_df = pd.concat([hard_matches_df, soft_matches_df], ignore_index=True)
        
        # 🔧 【新增】跨阶段去重：确保同一个竞对商品不被硬匹配和软匹配重复
        if not fuzzy_matches_df.empty:
            # 找到竞对商品名称列（包含"_B"的列）
            b_cols = [col for col in fuzzy_matches_df.columns if '商品名称' in col and '_B' in col]
            if b_cols:
                b_name_col = b_cols[0]
                before_count = len(fuzzy_matches_df)
                fuzzy_matches_df = fuzzy_matches_df.sort_values('composite_similarity_score', ascending=False)
                fuzzy_matches_df = fuzzy_matches_df.drop_duplicates(subset=[b_name_col], keep='first')
                removed = before_count - len(fuzzy_matches_df)
                if removed > 0:
                    print(f"   🔧 跨阶段去重: 移除 {removed} 个硬匹配+软匹配的重复商品（保留得分最高）")
        
        print(f"✅ 名称模糊匹配总共找到 {len(fuzzy_matches_df)} 个匹配 (硬分类: {len(hard_matches_df)}, 软兜底: {len(soft_matches_df)})")
        print("✅ [步骤 5/7] 商品匹配完成！")
    except Exception as e:
        print(f"[错误] 商品匹配失败: {e}")
        sys.exit(1)

    print("\n" + "="*50)
    print("⏳ [步骤 6/7] 正在生成最终报告...")
    try:
        df_all_a = pd.concat([df_a_barcode, df_a_no_barcode], ignore_index=True)
        df_all_b = pd.concat([df_b_barcode, df_b_no_barcode], ignore_index=True)
        (df_a_unique, df_b_unique, df_sales_comp, df_discount_filter,
         df_a_unique_dedup, df_b_unique_dedup, df_differential, df_category_gaps, cost_sheets) = generate_final_reports(
            df_all_a, df_all_b, barcode_matches_df, fuzzy_matches_df, "A", "B", cfg
        )
        
    # 按需求变更：不再统计/导出“有条码但未匹配”信息
        
        print("✅ [步骤 6/7] 报告生成完毕！")
    except Exception as e:
        import traceback
        print(f"[错误] 生成报告失败: {e}")
        print("\n完整错误堆栈:")
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "="*50)
    
    # 生成带时间戳的文件名，避免文件被占用；统一导出到 reports/ 目录
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file_name = f'matched_products_comparison_final_{timestamp}.xlsx'
    # 构造输出目录并确保存在
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(script_dir, getattr(cfg, 'OUTPUT_DIR', 'reports'))
    os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, output_file_name)

    print(f"⏳ [步骤 7/7] 正在将所有结果导出到 Excel 文件: {output_path}...")
    
    try:
        
        # 检查并删除可能存在的同名文件
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                import time
                time.sleep(0.5)  # 短暂等待确保文件被释放
            except Exception as e:
                print(f"⚠️ 警告：无法删除现有文件 {output_path}: {e}")
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # === 核心匹配结果（条码匹配和名称匹配严格分离）===
            export_to_excel(writer, barcode_matches_df, '1-条码精确匹配', cfg)
            
            # 📋 2-名称模糊匹配：对齐手动比价，空表也要生成一个空白Sheet，便于结构一致
            print(f"📋 2-名称模糊匹配(无条码): 匹配条数 {len(fuzzy_matches_df)}（空表也会导出）")
            export_to_excel(writer, fuzzy_matches_df, '2-名称模糊匹配(无条码)', cfg)
            
            # === 新增：差异品对比 ===
            if not df_differential.empty:
                print(f"📊 差异品对比: {len(df_differential)} 对差异品匹配")
                export_to_excel(writer, df_differential, '3-差异品对比', cfg)
            
            # === 独有商品（原始+去重版本） ===
            export_to_excel(writer, df_a_unique, f'4-{cfg.STORE_A_NAME}-独有商品(全部)', cfg)
            export_to_excel(writer, df_b_unique, f'5-{cfg.STORE_B_NAME}-独有商品(全部)', cfg)
            # 按需求变更：不再导出“6-销量对比(B店畅销且我店有优势)”
            # 新增：A折扣>=B折扣且双方库存>0、B月售>0（简化命名）
            export_to_excel(writer, df_discount_filter, '9-库存>0&A折扣≥B折扣', cfg)
            
            # 导出去重后的独有商品
            if not df_a_unique_dedup.empty:
                print(f"  [去重A] {cfg.STORE_A_NAME}-独有商品(去重): {len(df_a_unique_dedup)} 种商品")
                export_to_excel(writer, df_a_unique_dedup, f'6-{cfg.STORE_A_NAME}-独有商品(去重)', cfg)
            if not df_b_unique_dedup.empty:
                print(f"  [去重B] {cfg.STORE_B_NAME}-独有商品(去重): {len(df_b_unique_dedup)} 种商品")
                export_to_excel(writer, df_b_unique_dedup, f'7-{cfg.STORE_B_NAME}-独有商品(去重)', cfg)
            
            # 导出品类缺口分析
            if not df_category_gaps.empty:
                print(f"  [缺口] 品类缺口分析: {len(df_category_gaps)} 个缺失品类")
                export_to_excel(writer, df_category_gaps, '8-品类缺口分析', cfg)
            
            # 🆕 导出成本分析 Sheet（第一阶段功能）
            print(f"\n🔍 成本分析导出检查:")
            print(f"   ENABLE_COST_PREDICTION = {cfg.ENABLE_COST_PREDICTION}")
            print(f"   EXPORT_COST_SHEETS = {cfg.EXPORT_COST_SHEETS}")
            print(f"   cost_sheets 是否为空 = {not cost_sheets}")
            print(f"   cost_sheets 键 = {list(cost_sheets.keys()) if cost_sheets else '无'}")
            
            if cfg.ENABLE_COST_PREDICTION and cfg.EXPORT_COST_SHEETS and cost_sheets:
                print(f"\n💰 正在导出成本分析报表...")
                sheet_num = 10  # 从10号开始编号，避免与现有Sheet冲突
                for sheet_name, sheet_df in cost_sheets.items():
                    if not sheet_df.empty:
                        print(f"  [成本] {sheet_name}: {len(sheet_df)} 条记录")
                        export_to_excel(writer, sheet_df, f'{sheet_num}-{sheet_name}')
                        sheet_num += 1
                print(f"✅ 成本分析报表已导出（共 {len(cost_sheets)} 个Sheet）")
            else:
                print(f"   ⚠️  成本分析未导出，原因:")
                if not cfg.ENABLE_COST_PREDICTION:
                    print(f"      - ENABLE_COST_PREDICTION = False")
                if not cfg.EXPORT_COST_SHEETS:
                    print(f"      - EXPORT_COST_SHEETS = False")
                if not cost_sheets:
                    print(f"      - cost_sheets 为空（可能成本预测失败或无数据）")
            
            # 清洗数据导出：可配置开关
            if getattr(cfg, 'EXPORT_CLEANED_SHEETS', True):
                print(f"✅ 正在导出清洗后的数据...")

                # 合并A店和B店的所有数据（包括有条码和无条码的）
                df_a_all = pd.concat([df_a_barcode, df_a_no_barcode], ignore_index=True) if not df_a_no_barcode.empty else df_a_barcode
                df_b_all = pd.concat([df_b_barcode, df_b_no_barcode], ignore_index=True) if not df_b_no_barcode.empty else df_b_barcode

                # 提取清洗后的列（包含所有处理过的字段和分类对比）
                cleaned_cols = [
                    '商品名称', 'cleaned_商品名称',
                    '美团一级分类', '一级分类', 'cleaned_一级分类',
                    '美团三级分类', '三级分类', 'cleaned_三级分类',
                    'standardized_brand', 'specs',
                    '商家分类', '条码', '店内码', '原价', '售价', '月售', '库存'
                ]

                # A店清洗数据
                cleaned_cols_a = [col for col in cleaned_cols if col in df_a_all.columns]
                if len(cleaned_cols_a) > 0:
                    df_a_cleaned = df_a_all[cleaned_cols_a].copy()
                    df_a_cleaned['数据源'] = cfg.STORE_A_NAME
                    export_to_excel(writer, df_a_cleaned, f'6-{cfg.STORE_A_NAME}-清洗数据')

                # B店清洗数据
                cleaned_cols_b = [col for col in cleaned_cols if col in df_b_all.columns]
                if len(cleaned_cols_b) > 0:
                    df_b_cleaned = df_b_all[cleaned_cols_b].copy()
                    df_b_cleaned['数据源'] = cfg.STORE_B_NAME
                    export_to_excel(writer, df_b_cleaned, f'7-{cfg.STORE_B_NAME}-清洗数据')

                # 合并清洗数据对比（只包含两店都有的列）
                common_cleaned_cols = list(set(cleaned_cols_a) & set(cleaned_cols_b))
                if len(common_cleaned_cols) > 0:
                    try:
                        df_combined_cleaned = pd.concat([
                            df_a_all[common_cleaned_cols].assign(数据源=cfg.STORE_A_NAME),
                            df_b_all[common_cleaned_cols].assign(数据源=cfg.STORE_B_NAME)
                        ], ignore_index=True)
                        export_to_excel(writer, df_combined_cleaned, '8-合并清洗数据对比')
                        print(f"✅ 清洗数据已导出到独立Sheet中，便于查阅对比")
                    except Exception as e:
                        print(f"⚠️ 合并清洗数据时出错: {e}")
            else:
                print("ℹ️ 已根据配置关闭清洗数据 Sheet 的导出（6/7/8 号表）。")
        
        print(f"✅ [步骤 7/7] Excel 文件导出成功！已保存至: {output_path}")
    except Exception as e:
        print(f"[错误] Excel导出失败: {e}")
        sys.exit(1)

    # 🚀 保存所有缓存并打印统计信息
    print("\n" + "="*50)
    print("💾 正在保存缓存...")
    print("="*50)
    cache_manager.save_all()
    cache_manager.print_stats()

    print("\n" + "="*50)
    print(f"🎉 全部流程完成！")
    print("="*50)

if __name__ == '__main__':
    # 授权检查（仅在打包环境下执行）
    if not check_authorization():
        sys.exit(1)
    
    main()

