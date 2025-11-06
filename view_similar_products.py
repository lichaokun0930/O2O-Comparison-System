"""查看差异品对比数据"""
import pandas as pd
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

df = pd.read_excel('reports/matched_products_comparison_final_20251106_142519.xlsx', 
                   sheet_name='3-差异品对比')

print("=" * 80)
print("📊 差异品对比 - 类似但不完全相同的商品")
print("=" * 80)
print(f"\n总数: {len(df)} 条")
print(f"\n💡 这个Sheet就是您想要的'类似但不完全相同'的商品！")

# 得分分布
if 'similarity_score' in df.columns:
    print(f"\n相似度分布:")
    print(f"  平均分: {df['similarity_score'].mean():.3f}")
    print(f"  最高分: {df['similarity_score'].max():.3f}")
    print(f"  最低分: {df['similarity_score'].min():.3f}")
    print(f"  中位数: {df['similarity_score'].median():.3f}")
    
    # 分数段
    print(f"\n相似度段分布:")
    print(f"  0.5-0.55: {len(df[(df['similarity_score'] >= 0.5) & (df['similarity_score'] < 0.55)])} 条")
    print(f"  0.45-0.5: {len(df[(df['similarity_score'] >= 0.45) & (df['similarity_score'] < 0.5)])} 条")
    print(f"  0.4-0.45: {len(df[(df['similarity_score'] >= 0.4) & (df['similarity_score'] < 0.45)])} 条")
    print(f"  0.35-0.4: {len(df[(df['similarity_score'] >= 0.35) & (df['similarity_score'] < 0.4)])} 条")
    print(f"  <0.35: {len(df[df['similarity_score'] < 0.35])} 条")

# 价格差异分布
if 'price_diff_pct' in df.columns:
    print(f"\n价格差异分布:")
    print(f"  平均价差: {df['price_diff_pct'].abs().mean():.1f}%")
    print(f"  最大价差: {df['price_diff_pct'].abs().max():.1f}%")

print(f"\n前10条示例:")
print("=" * 80)

for i, row in df.head(10).iterrows():
    store_a_col = [c for c in df.columns if '商品名称_' in c and '海门海亮' in c][0]
    store_b_col = [c for c in df.columns if '商品名称_' in c and '京东' in c][0]
    price_a_col = [c for c in df.columns if '售价_' in c and '海门海亮' in c][0]
    price_b_col = [c for c in df.columns if '售价_' in c and '京东' in c][0]
    cat_a_col = [c for c in df.columns if '美团一级分类_' in c and '海门海亮' in c][0]
    cat_b_col = [c for c in df.columns if '美团一级分类_' in c and '京东' in c][0]
    
    name_a = row[store_a_col]
    name_b = row[store_b_col]
    price_a = row[price_a_col]
    price_b = row[price_b_col]
    cat_a = row[cat_a_col]
    cat_b = row[cat_b_col]
    score = row.get('similarity_score', 0)
    price_diff = row.get('price_diff_pct', 0)
    
    print(f"\n{i+1}.")
    print(f"  店A: {name_a[:50]}")
    print(f"  店B: {name_b[:50]}")
    print(f"  价格: ¥{price_a:.2f} vs ¥{price_b:.2f} (差{abs(price_diff):.1f}%)")
    print(f"  分类: {cat_a} vs {cat_b}")
    print(f"  相似度: {score:.3f}")

print("\n" + "=" * 80)
print("💡 分析:")
print("  - 这些商品在同一品类，价格相近")
print("  - 但名称不完全相同（相似度0.3-0.55）")
print("  - 可能是：")
print("    1. 同品类不同品牌的商品")
print("    2. 同品牌不同规格的商品")
print("    3. 功能类似的替代品")
print("\n💼 业务价值:")
print("  - 了解竞对的同类商品定价策略")
print("  - 发现可以引进的替代品")
print("  - 优化自己的商品结构")
print("=" * 80)
