"""诊断模糊匹配结果偏少的原因"""
import pandas as pd
import sys
import io
from pathlib import Path

# 设置输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 找到最新报告
reports_dir = Path('reports')
latest_report = sorted(reports_dir.glob('matched_products_comparison_final_*.xlsx'), 
                       key=lambda x: x.stat().st_mtime, reverse=True)[0]

print("=" * 80)
print(f"📊 诊断报告: {latest_report.name}")
print("=" * 80)

# 读取所有Sheet
xl = pd.ExcelFile(latest_report)

print("\n1️⃣ 各Sheet数据量统计:")
print("-" * 80)
sheet_stats = {}
for sheet in xl.sheet_names:
    df = pd.read_excel(latest_report, sheet_name=sheet)
    sheet_stats[sheet] = len(df)
    print(f"  {sheet}: {len(df):,} 条")

print(f"\n  总计: {sum(sheet_stats.values()):,} 条记录")

# 详细分析
print("\n2️⃣ 匹配结果分析:")
print("-" * 80)

# Sheet 1: 条码精确匹配
barcode_match = 0
for key in sheet_stats.keys():
    if '条码' in key or '1-' in key:
        barcode_match = sheet_stats[key]
        print(f"  ✅ 条码精确匹配: {barcode_match:,} 条")
        break

# Sheet 2: 模糊匹配
fuzzy_match = 0
fuzzy_sheet_name = None
for key in sheet_stats.keys():
    if '模糊' in key or '名称' in key or '2-' in key:
        fuzzy_match = sheet_stats[key]
        fuzzy_sheet_name = key
        print(f"  🔍 模糊匹配: {fuzzy_match:,} 条 {'⚠️ 偏少' if fuzzy_match < 1000 else '✅'}")
        break
    
    # 读取模糊匹配详情
    if fuzzy_sheet_name and fuzzy_match > 0:
        df_fuzzy = pd.read_excel(latest_report, sheet_name=fuzzy_sheet_name)
        if len(df_fuzzy) > 0:
            print(f"\n  模糊匹配得分分布:")
            if 'composite_similarity_score' in df_fuzzy.columns:
                score_col = 'composite_similarity_score'
            elif '综合相似度' in df_fuzzy.columns:
                score_col = '综合相似度'
            else:
                score_col = None
            
            if score_col:
                print(f"    平均分: {df_fuzzy[score_col].mean():.3f}")
                print(f"    最高分: {df_fuzzy[score_col].max():.3f}")
                print(f"    最低分: {df_fuzzy[score_col].min():.3f}")
                print(f"    中位数: {df_fuzzy[score_col].median():.3f}")
                
                # 分数段统计
                print(f"\n  得分段分布:")
                print(f"    ≥0.8 (优秀): {len(df_fuzzy[df_fuzzy[score_col] >= 0.8]):,} 条")
                print(f"    0.6-0.8 (良好): {len(df_fuzzy[(df_fuzzy[score_col] >= 0.6) & (df_fuzzy[score_col] < 0.8)]):,} 条")
                print(f"    0.4-0.6 (一般): {len(df_fuzzy[(df_fuzzy[score_col] >= 0.4) & (df_fuzzy[score_col] < 0.6)]):,} 条")
                print(f"    <0.4 (较低): {len(df_fuzzy[df_fuzzy[score_col] < 0.4]):,} 条")

# Sheet 4-5: 独有商品
unique_a = 0
unique_b = 0
for key in sheet_stats.keys():
    if '独有商品(全部)' in key:
        if '4-' in key or ('海门海亮' in key and '全部' in key):
            unique_a = sheet_stats[key]
        elif '5-' in key or ('京东' in key and '全部' in key):
            unique_b = sheet_stats[key]

if unique_a > 0 or unique_b > 0:
    print(f"\n  📦 独有商品:")
    print(f"    店A独有: {unique_a:,} 条")
    print(f"    店B独有: {unique_b:,} 条")
    print(f"    独有商品占比: {(unique_a + unique_b) / (sum(sheet_stats.values()) - sheet_stats.get('8-品类缺口分析', 0) - sheet_stats.get('9-库存>0&A折扣≥B折扣', 0)) * 100:.1f}%")

print("\n3️⃣ 可能原因分析:")
print("-" * 80)

# 分析可能原因
total_products = barcode_match + fuzzy_match + unique_a + unique_b
matched_products = barcode_match + fuzzy_match
match_rate = matched_products / total_products * 100 if total_products > 0 else 0

print(f"  总商品数: {total_products:,}")
print(f"  匹配商品数: {matched_products:,} ({match_rate:.1f}%)")
print(f"  独有商品数: {unique_a + unique_b:,} ({(unique_a + unique_b) / total_products * 100:.1f}%)")

if fuzzy_match < 1000:
    print(f"\n  ⚠️ 模糊匹配结果偏少的可能原因:")
    
    if unique_a + unique_b > matched_products:
        print(f"    1. ❌ 独有商品过多 ({(unique_a + unique_b) / total_products * 100:.1f}%)")
        print(f"       → 说明两店商品差异很大，很多商品找不到对应")
        print(f"       → 建议：检查两店是否同类型/同品类")
    
    if barcode_match > fuzzy_match * 5:
        print(f"    2. ✅ 条码匹配占比过高 ({barcode_match / matched_products * 100:.1f}%)")
        print(f"       → 说明大部分商品都是相同的（有条码）")
        print(f"       → 这是正常情况，条码匹配优先级更高")
    
    print(f"    3. 🔍 可能的匹配阈值过高")
    print(f"       → 检查配置文件中的相似度阈值设置")
    
    print(f"    4. 📊 商品名称差异大")
    print(f"       → 检查商品名称格式是否统一")

# 读取原始数据文件
print("\n4️⃣ 原始数据检查:")
print("-" * 80)

upload_dir = Path('upload')
store_a_files = list(upload_dir.glob('本店/*.xlsx'))
store_b_files = list(upload_dir.glob('竞对/*.xlsx'))

if store_a_files:
    df_a = pd.read_excel(store_a_files[0])
    print(f"  店A: {store_a_files[0].name}")
    print(f"    总商品: {len(df_a):,} 条")
    if '条码' in df_a.columns:
        has_barcode = df_a['条码'].notna().sum()
        print(f"    有条码: {has_barcode:,} 条 ({has_barcode/len(df_a)*100:.1f}%)")

if store_b_files:
    df_b = pd.read_excel(store_b_files[0])
    print(f"\n  店B: {store_b_files[0].name}")
    print(f"    总商品: {len(df_b):,} 条")
    if '条码' in df_b.columns:
        has_barcode = df_b['条码'].notna().sum()
        print(f"    有条码: {has_barcode:,} 条 ({has_barcode/len(df_b)*100:.1f}%)")

print("\n5️⃣ 建议:")
print("-" * 80)
print("  1. 检查独有商品列表，看是否真的没有对应商品")
print("  2. 降低相似度阈值（如从0.42降到0.35），增加召回率")
print("  3. 检查商品名称格式是否一致（如品牌、规格写法）")
print("  4. 查看日志文件，确认匹配过程是否有异常")
print("\n" + "=" * 80)
