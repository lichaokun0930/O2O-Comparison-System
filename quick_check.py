import pandas as pd
from pathlib import Path

# 指定两份报告
old_file = Path('reports/matched_products_comparison_final_20251104_172455.xlsx')
new_file = Path('reports/matched_products_comparison_final_20251105_094953.xlsx')

print("="*80)
print("� 深度分析：833个消失商品的本质")
print("="*80)

# 读取旧报告的模糊匹配
df_old_fuzzy = pd.read_excel(old_file, sheet_name='2-名称模糊匹配(无条码)')
a_col = [c for c in df_old_fuzzy.columns if '商品名称' in c and '高港店' in c][0]
b_col = [c for c in df_old_fuzzy.columns if '商品名称' in c and '好惠来店' in c][0]
score_col = 'composite_similarity_score'

# 读取新报告的模糊匹配和独有商品
df_new_fuzzy = pd.read_excel(new_file, sheet_name='2-名称模糊匹配(无条码)')
df_new_unique = pd.read_excel(new_file, sheet_name='4-高港店-独有商品(全部)')

# 找出消失的本店商品
old_a_products = set(df_old_fuzzy[a_col])
new_a_products = set(df_new_fuzzy[a_col])
deleted_a = old_a_products - new_a_products

print(f"\n📊 基本统计:")
print(f"消失的本店商品: {len(deleted_a)} 个")

# 分析这些商品在旧报告中的匹配情况
print(f"\n{'='*80}")
print(f"🔍 【关键问题】这833个商品真的是独有商品吗？")
print(f"{'='*80}")

# 对于每个消失的商品，查看它在旧报告中匹配到了哪个竞对商品
deleted_analysis = []
for product in list(deleted_a)[:20]:  # 分析前20个
    old_matches = df_old_fuzzy[df_old_fuzzy[a_col] == product]
    
    for _, match in old_matches.iterrows():
        competitor = match[b_col]
        score = match[score_col]
        
        # 检查同一个竞对商品有多少个本店商品匹配
        same_competitor_matches = df_old_fuzzy[df_old_fuzzy[b_col] == competitor]
        total_matches = len(same_competitor_matches)
        
        # 这个本店商品在所有匹配中的排名
        same_competitor_sorted = same_competitor_matches.sort_values(score_col, ascending=False)
        rank = list(same_competitor_sorted[a_col]).index(product) + 1
        
        # 检查这个竞对商品在新报告中是否还存在
        competitor_in_new = competitor in df_new_fuzzy[b_col].values
        
        deleted_analysis.append({
            '本店商品': product,
            '匹配的竞对商品': competitor,
            '得分': score,
            '该竞对的总匹配数': total_matches,
            '本店商品排名': rank,
            '竞对商品在新报告': '✅ 存在' if competitor_in_new else '❌ 不存在'
        })

print(f"\n示例分析（前10个）:")
print(f"{'序号':<4} {'排名':<6} {'总匹配':<8} {'得分':<8} {'竞对在新报告':<12}")
print("-"*80)

for i, item in enumerate(deleted_analysis[:10], 1):
    print(f"{i:<4} {item['本店商品排名']}/{item['该竞对的总匹配数']:<6} "
          f"{item['该竞对的总匹配数']:<8} {item['得分']:<8.3f} {item['竞对商品在新报告']:<12}")
    print(f"     本店: {item['本店商品'][:68]}")
    print(f"     竞对: {item['匹配的竞对商品'][:68]}")
    print()

# 统计分析
multi_match_count = sum(1 for item in deleted_analysis if item['该竞对的总匹配数'] > 1)
rank_not_first = sum(1 for item in deleted_analysis if item['本店商品排名'] > 1)

print(f"\n{'='*80}")
print(f"📊 【统计结论】（基于前20个样本）")
print(f"{'='*80}")
print(f"匹配到有多个本店商品的竞对: {multi_match_count}/{len(deleted_analysis)} ({multi_match_count/len(deleted_analysis)*100:.1f}%)")
print(f"排名不是第一的: {rank_not_first}/{len(deleted_analysis)} ({rank_not_first/len(deleted_analysis)*100:.1f}%)")

print(f"\n💡 【结论】")
if multi_match_count > len(deleted_analysis) * 0.8:
    print(f"✅ 这些商品大多数（{multi_match_count/len(deleted_analysis)*100:.1f}%）匹配到了\"一对多\"的竞对商品")
    print(f"   说明：它们不是真正的独有商品，而是被去重删除的低分匹配")
    print(f"   理由：竞对有对应商品，只是我们有多个类似商品而竞对只有一个")
    print(f"\n   例如：")
    print(f"   - 竞对1个\"女士内裤\" vs 我们15个不同款式的内裤")
    print(f"   - 保留得分最高的1个，删除其他14个")
    print(f"   - 被删除的14个不应该算独有商品（竞对有对应商品）")
else:
    print(f"⚠️ 这些商品大多数是真正的独有商品")

print(f"\n{'='*80}")
