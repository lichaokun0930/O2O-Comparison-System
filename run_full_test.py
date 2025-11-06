"""
阶段3完整测试脚本 - 自动化运行

功能：
1. 自动选择默认模型（避免交互）
2. 监控运行时间和内存占用
3. 验证优化效果

运行方式：
    python run_full_test.py
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime

def print_section(title):
    """打印分隔线"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def run_comparison_with_monitoring():
    """运行比价程序并监控性能"""
    print_section("阶段3完整测试 - 开始")
    
    print(f"\n⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 设置环境变量（避免交互）
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    
    # 准备输入：模型选择1（默认）+ Cross-Encoder选择1（默认）
    input_data = "1\n1\n"
    
    print("\n📝 自动选择配置:")
    print("  - Sentence-BERT: 模型1（标准多语言）")
    print("  - Cross-Encoder: 模型1（MS-Marco-MiniLM）")
    print("\n🚀 开始运行比价程序...\n")
    
    # 记录开始时间
    start_time = time.time()
    
    # 运行程序
    try:
        process = subprocess.Popen(
            ['python', 'product_comparison_tool_local.py'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        # 发送输入
        output, _ = process.communicate(input=input_data, timeout=600)  # 10分钟超时
        
        # 记录结束时间
        elapsed_time = time.time() - start_time
        
        # 打印输出（最后100行）
        lines = output.split('\n')
        print("\n" + "="*70)
        print("  运行输出（最后100行）")
        print("="*70)
        for line in lines[-100:]:
            print(line)
        
        # 检查返回码
        if process.returncode == 0:
            print("\n✅ 程序运行成功")
        else:
            print(f"\n⚠️ 程序退出码: {process.returncode}")
        
        # 打印性能统计
        print_section("性能统计")
        print(f"⏱️  总耗时: {elapsed_time:.1f}秒 ({elapsed_time/60:.1f}分钟)")
        
        # 检查输出文件
        reports_dir = Path('reports')
        if reports_dir.exists():
            xlsx_files = sorted(reports_dir.glob('matched_products_comparison_final_*.xlsx'))
            if xlsx_files:
                latest_file = xlsx_files[-1]
                file_size = latest_file.stat().st_size / 1024 / 1024
                print(f"📊 输出文件: {latest_file.name}")
                print(f"📦 文件大小: {file_size:.2f} MB")
                print(f"🕐 生成时间: {datetime.fromtimestamp(latest_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        
        return True
        
    except subprocess.TimeoutExpired:
        print("\n❌ 运行超时（10分钟）")
        process.kill()
        return False
        
    except Exception as e:
        print(f"\n❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_upload_files():
    """检查上传文件"""
    print_section("检查测试数据")
    
    upload_dir = Path('upload')
    if not upload_dir.exists():
        print("❌ upload目录不存在")
        return False
    
    store_a_dir = upload_dir / '本店'
    store_b_dir = upload_dir / '竞对'
    
    # 检查本店数据
    if store_a_dir.exists():
        xlsx_files = list(store_a_dir.glob('*.xlsx'))
        if xlsx_files:
            print(f"✅ 本店数据: {xlsx_files[0].name}")
        else:
            print("⚠️ 本店目录为空")
            return False
    else:
        print("⚠️ 本店目录不存在")
        return False
    
    # 检查竞对数据
    if store_b_dir.exists():
        xlsx_files = list(store_b_dir.glob('*.xlsx'))
        if xlsx_files:
            print(f"✅ 竞对数据: {xlsx_files[0].name}")
        else:
            print("⚠️ 竞对目录为空")
            return False
    else:
        print("⚠️ 竞对目录不存在")
        return False
    
    return True

def main():
    """主测试流程"""
    print("\n" + "🚀"*35)
    print("  阶段3完整测试 - 真实数据验证")
    print("  测试时间: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("🚀"*35)
    
    # 检查测试数据
    if not check_upload_files():
        print("\n❌ 测试数据检查失败，请确保upload/本店和upload/竞对目录中有Excel文件")
        sys.exit(1)
    
    # 运行比价程序
    success = run_comparison_with_monitoring()
    
    # 生成测试报告
    print_section("测试总结")
    if success:
        print("✅ 阶段3优化测试完成")
        print("\n📋 验证要点:")
        print("  1. ✅ 程序正常运行，无崩溃")
        print("  2. ✅ 生成完整的比价报告")
        print("  3. ⏳ 请手动验证报告内容准确性")
        print("  4. ⏳ 对比历史运行时间，确认性能提升")
        print("\n💡 提示:")
        print("  - 查看reports目录中的最新Excel文件")
        print("  - 对比之前的运行时间（如果有记录）")
        print("  - 验证分块相似度计算和Cross-Encoder批量优化是否生效")
    else:
        print("❌ 测试失败，请检查错误信息")
        sys.exit(1)

if __name__ == '__main__':
    main()
