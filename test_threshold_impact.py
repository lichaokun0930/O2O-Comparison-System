"""
测试不同阈值对匹配结果的影响

对比三种阈值配置：
1. 当前阈值（0.2/0.42/0.38）
2. 宽松阈值（0.15/0.35/0.30）
3. 严格阈值（0.25/0.50/0.45）
"""
import pandas as pd
import subprocess
import os
import sys
import time
from pathlib import Path
from datetime import datetime

print("=" * 80)
print("🔍 阈值差异测试 - 对比不同阈值配置的匹配效果")
print("=" * 80)

# 测试配置
test_configs = [
    {
        'name': '当前阈值（平衡）',
        'composite_threshold': 0.2,
        'hard_threshold': 0.42,
        'soft_threshold': 0.38,
        'description': '当前使用的阈值，精准度和召回率平衡'
    },
    {
        'name': '宽松阈值（召回优先）',
        'composite_threshold': 0.15,
        'hard_threshold': 0.35,
        'soft_threshold': 0.30,
        'description': '降低阈值，增加匹配数量，可能引入一些不太准确的匹配'
    },
    {
        'name': '严格阈值（精准优先）',
        'composite_threshold': 0.25,
        'hard_threshold': 0.50,
        'soft_threshold': 0.45,
        'description': '提高阈值，只保留高置信度匹配，匹配数量会减少'
    }
]

# 检查是否有最新的比价数据
reports_dir = Path('reports')
latest_report = sorted(reports_dir.glob('matched_products_comparison_final_*.xlsx'), 
                       key=lambda x: x.stat().st_mtime, reverse=True)

if not latest_report:
    print("\n❌ 未找到比价报告，请先运行比价程序")
    sys.exit(1)

latest_report = latest_report[0]
print(f"\n📊 当前报告: {latest_report.name}")
print(f"   生成时间: {datetime.fromtimestamp(latest_report.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")

# 读取当前结果作为基准
print("\n📈 读取当前匹配结果...")
xl = pd.ExcelFile(latest_report)

current_results = {}
for sheet in xl.sheet_names:
    df = pd.read_excel(latest_report, sheet_name=sheet)
    current_results[sheet] = len(df)

print("\n当前结果统计:")
print("-" * 80)
for sheet, count in current_results.items():
    print(f"  {sheet}: {count:,} 条")

# 提取关键指标
barcode_match = current_results.get('1-条码精确匹配', 0)
fuzzy_match = 0
for key in current_results.keys():
    if '模糊' in key or '名称' in key or '2-' in key:
        fuzzy_match = current_results[key]
        break

unique_a = 0
unique_b = 0
for key in current_results.keys():
    if '独有商品(全部)' in key:
        if '4-' in key or any(word in key for word in ['海门海亮', '店A', '本店']):
            unique_a = current_results[key]
        elif '5-' in key or any(word in key for word in ['京东', '店B', '竞对']):
            unique_b = current_results[key]

total_products = barcode_match + fuzzy_match + unique_a + unique_b

print(f"\n核心指标:")
print(f"  总商品数: {total_products:,}")
print(f"  条码匹配: {barcode_match:,} ({barcode_match/total_products*100:.1f}%)")
print(f"  模糊匹配: {fuzzy_match:,} ({fuzzy_match/total_products*100:.1f}%)")
print(f"  独有商品: {unique_a + unique_b:,} ({(unique_a + unique_b)/total_products*100:.1f}%)")

# 询问是否继续测试
print("\n" + "=" * 80)
print("⚠️  注意：完整测试需要运行3次比价程序，每次约2-5分钟")
print("=" * 80)

choice = input("\n是否继续完整测试？(y/n，默认n): ").strip().lower()

if choice != 'y':
    print("\n✅ 已取消完整测试")
    print("\n💡 简化版测试：基于当前数据模拟不同阈值的效果")
    print("-" * 80)
    
    # 读取模糊匹配数据
    fuzzy_sheet = None
    for key in xl.sheet_names:
        if '模糊' in key or '名称' in key or '2-' in key:
            fuzzy_sheet = key
            break
    
    if fuzzy_sheet:
        df_fuzzy = pd.read_excel(latest_report, sheet_name=fuzzy_sheet)
        
        # 找到得分列
        score_col = None
        for col in ['composite_similarity_score', '综合相似度', '综合得分']:
            if col in df_fuzzy.columns:
                score_col = col
                break
        
        if score_col and len(df_fuzzy) > 0:
            print(f"\n📊 模糊匹配得分分布 (共{len(df_fuzzy)}条):")
            print(f"   平均分: {df_fuzzy[score_col].mean():.3f}")
            print(f"   最高分: {df_fuzzy[score_col].max():.3f}")
            print(f"   最低分: {df_fuzzy[score_col].min():.3f}")
            print(f"   中位数: {df_fuzzy[score_col].median():.3f}")
            
            # 模拟不同阈值的效果
            print(f"\n🔍 不同阈值下的预估匹配数:")
            print("-" * 80)
            
            thresholds = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
            for thr in thresholds:
                matches = len(df_fuzzy[df_fuzzy[score_col] >= thr])
                change = matches - fuzzy_match
                change_pct = (change / fuzzy_match * 100) if fuzzy_match > 0 else 0
                
                status = ""
                if thr == 0.20:
                    status = " ← 当前"
                elif matches > fuzzy_match:
                    status = f" (+{change}, +{change_pct:.1f}%)"
                elif matches < fuzzy_match:
                    status = f" ({change}, {change_pct:.1f}%)"
                
                print(f"  阈值 {thr:.2f}: {matches:,} 条{status}")
            
            # 详细分析
            print(f"\n💡 分析与建议:")
            print("-" * 80)
            
            # 计算不同阈值段的数量
            low_quality = len(df_fuzzy[df_fuzzy[score_col] < 0.3])
            medium_quality = len(df_fuzzy[(df_fuzzy[score_col] >= 0.3) & (df_fuzzy[score_col] < 0.5)])
            high_quality = len(df_fuzzy[df_fuzzy[score_col] >= 0.5])
            
            print(f"\n质量分布:")
            print(f"  高质量 (≥0.5): {high_quality:,} 条 ({high_quality/len(df_fuzzy)*100:.1f}%)")
            print(f"  中等质量 (0.3-0.5): {medium_quality:,} 条 ({medium_quality/len(df_fuzzy)*100:.1f}%)")
            print(f"  低质量 (<0.3): {low_quality:,} 条 ({low_quality/len(df_fuzzy)*100:.1f}%)")
            
            # 建议
            if low_quality > fuzzy_match * 0.3:
                print(f"\n  ⚠️  发现较多低质量匹配 ({low_quality}条)")
                print(f"     当前阈值0.2可能已经比较宽松")
                print(f"     不建议进一步降低阈值")
            
            if high_quality > fuzzy_match * 0.5:
                print(f"\n  ✅ 超过一半是高质量匹配 ({high_quality}条)")
                print(f"     当前阈值设置合理")
            
            # 降低阈值的潜在收益
            potential_gain_015 = len(df_fuzzy[df_fuzzy[score_col] >= 0.15]) - fuzzy_match
            potential_gain_025 = fuzzy_match - len(df_fuzzy[df_fuzzy[score_col] >= 0.25])
            
            print(f"\n  📈 阈值调整的潜在影响:")
            if potential_gain_015 > 0:
                print(f"     降至0.15: 增加约{potential_gain_015}条匹配 (+{potential_gain_015/fuzzy_match*100:.1f}%)")
            if potential_gain_025 > 0:
                print(f"     升至0.25: 减少约{potential_gain_025}条匹配 (-{potential_gain_025/fuzzy_match*100:.1f}%)")
            
            # 查看边界案例
            print(f"\n  🔍 边界案例分析:")
            
            # 0.15-0.20之间的商品（降低阈值会新增的）
            borderline_low = df_fuzzy[(df_fuzzy[score_col] >= 0.15) & (df_fuzzy[score_col] < 0.20)]
            if len(borderline_low) > 0:
                print(f"\n     如果降至0.15，会新增{len(borderline_low)}条匹配:")
                print(f"     示例（前3条）:")
                for idx, row in borderline_low.head(3).iterrows():
                    score = row[score_col]
                    name_a = row.get('商品名称_A', row.get('商品名称', 'N/A'))
                    name_b = row.get('商品名称_B', row.get('匹配商品名称', 'N/A'))
                    print(f"       得分{score:.3f}: {name_a[:30]} ↔ {name_b[:30]}")
            
            # 0.20-0.25之间的商品（升高阈值会失去的）
            borderline_high = df_fuzzy[(df_fuzzy[score_col] >= 0.20) & (df_fuzzy[score_col] < 0.25)]
            if len(borderline_high) > 0:
                print(f"\n     如果升至0.25，会失去{len(borderline_high)}条匹配:")
                print(f"     示例（前3条）:")
                for idx, row in borderline_high.head(3).iterrows():
                    score = row[score_col]
                    name_a = row.get('商品名称_A', row.get('商品名称', 'N/A'))
                    name_b = row.get('商品名称_B', row.get('匹配商品名称', 'N/A'))
                    print(f"       得分{score:.3f}: {name_a[:30]} ↔ {name_b[:30]}")
        else:
            print(f"\n⚠️  未找到得分列，无法进行详细分析")
    else:
        print(f"\n⚠️  未找到模糊匹配Sheet，无法进行详细分析")
    
    print("\n" + "=" * 80)
    print("✅ 简化测试完成")
    print("\n💡 建议:")
    print("  1. 如果当前匹配结果符合预期，保持现有阈值")
    print("  2. 如果需要更多匹配，可以尝试降至0.15")
    print("  3. 如果发现太多错误匹配，可以升至0.25")
    print("=" * 80)
    
else:
    print("\n🚀 开始完整测试...")
    print("=" * 80)
    
    # TODO: 实现完整的三次运行测试
    # 这需要修改product_comparison_tool_local.py中的阈值参数
    print("\n⚠️  完整测试功能正在开发中...")
    print("   当前版本仅支持简化模拟测试")
    print("\n💡 如需完整测试，请手动修改阈值后重新运行比价程序")
