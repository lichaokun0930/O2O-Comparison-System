"""
分析去重对匹配结果的影响

问题：本店ABCD匹配到竞对AAAA，去重后保留AB，CD去哪了？
答案：CD被认为是"未匹配"，会进入后续的软匹配或差异品匹配
"""

import pandas as pd
from pathlib import Path

def analyze_dedup_impact(excel_file):
    """分析去重对商品匹配的影响"""
    
    print(f"📊 分析去重影响: {Path(excel_file).name}")
    print("="*80)
    
    # 读取模糊匹配Sheet
    df_fuzzy = pd.read_excel(excel_file, sheet_name='2-名称模糊匹配(无条码)')
    
    # 识别列名
    a_name_col = [col for col in df_fuzzy.columns if '商品名称' in col and col.endswith('_高港店')][0]
    b_name_col = [col for col in df_fuzzy.columns if '商品名称' in col and col.endswith('_好惠来店')][0]
    score_col = 'composite_similarity_score' if 'composite_similarity_score' in df_fuzzy.columns else 'text_similarity'
    
    print(f"\n📌 分析维度:")
    print(f"   本店列: {a_name_col}")
    print(f"   竞对列: {b_name_col}")
    print(f"   得分列: {score_col}")
    
    # 统计竞对侧的匹配情况
    b_match_counts = df_fuzzy[b_name_col].value_counts()
    duplicated_b = b_match_counts[b_match_counts > 1]
    
    print(f"\n{'='*80}")
    print(f"📋 【竞对侧匹配统计】")
    print(f"{'='*80}")
    print(f"总匹配记录数: {len(df_fuzzy)}")
    print(f"唯一竞对商品: {len(b_match_counts)}")
    print(f"重复的竞对商品: {len(duplicated_b)} 个")
    print(f"重复匹配总数: {duplicated_b.sum()} 条")
    print(f"去重后将保留: {len(duplicated_b)} 条（每个竞对商品1条）")
    print(f"去重后将删除: {duplicated_b.sum() - len(duplicated_b)} 条")
    
    # 分析被删除的本店商品的去向
    print(f"\n{'='*80}")
    print(f"🔍 【被删除匹配的本店商品去向分析】")
    print(f"{'='*80}")
    
    # 找出会被删除的记录
    deleted_records = []
    for b_name in duplicated_b.index:
        b_matches = df_fuzzy[df_fuzzy[b_name_col] == b_name].copy()
        b_matches = b_matches.sort_values(score_col, ascending=False)
        
        # 第一条保留，其余删除
        kept_record = b_matches.iloc[0]
        deleted = b_matches.iloc[1:]
        
        for idx, row in deleted.iterrows():
            deleted_records.append({
                '被删除的本店商品': row[a_name_col],
                '原匹配的竞对商品': b_name,
                '得分': row[score_col],
                '排名': list(b_matches.index).index(idx) + 1,
                '总竞争者': len(b_matches)
            })
    
    deleted_df = pd.DataFrame(deleted_records)
    
    print(f"✅ 被删除的匹配总数: {len(deleted_df)} 条")
    print(f"\n这些本店商品的可能去向:")
    print(f"   1️⃣ 进入软匹配阶段 → 可能匹配到其他竞对商品")
    print(f"   2️⃣ 进入差异品匹配 → 跨分类匹配到相似商品")
    print(f"   3️⃣ 成为独有商品 → 如果找不到任何匹配")
    
    # 读取独有商品Sheet，查看有多少"被删除"的商品成为了独有商品
    try:
        df_unique_a = pd.read_excel(excel_file, sheet_name='4-高港店-独有商品(全部)')
        
        # 检查有多少被删除的商品出现在独有商品中
        deleted_in_unique = deleted_df[deleted_df['被删除的本店商品'].isin(df_unique_a['商品名称'])]
        
        print(f"\n📊 实际去向统计:")
        print(f"   ❌ 成为独有商品: {len(deleted_in_unique)} 个 ({len(deleted_in_unique)/len(deleted_df)*100:.1f}%)")
        print(f"   ✅ 找到其他匹配: {len(deleted_df) - len(deleted_in_unique)} 个 ({(len(deleted_df)-len(deleted_in_unique))/len(deleted_df)*100:.1f}%)")
        
        if len(deleted_in_unique) > 0:
            print(f"\n⚠️ 【成为独有商品的被删除匹配】（前10个）:")
            for i, row in deleted_in_unique.head(10).iterrows():
                print(f"   {i+1}. {row['被删除的本店商品'][:70]}")
                print(f"      原匹配: {row['原匹配的竞对商品'][:70]}")
                print(f"      得分: {row['得分']:.3f} (排名 {row['排名']}/{row['总竞争者']})")
                print()
    
    except Exception as e:
        print(f"\n⚠️ 无法读取独有商品Sheet: {e}")
    
    # 展示典型案例
    print(f"\n{'='*80}")
    print(f"📋 【典型案例：多对一匹配】（前5个）")
    print(f"{'='*80}")
    
    for i, (b_name, count) in enumerate(duplicated_b.head(5).items(), 1):
        b_matches = df_fuzzy[df_fuzzy[b_name_col] == b_name].copy()
        b_matches = b_matches.sort_values(score_col, ascending=False)
        
        print(f"\n{i}. 竞对商品: {b_name[:80]}")
        print(f"   匹配到 {count} 个本店商品:")
        
        for idx, row in b_matches.iterrows():
            status = "✅ 保留" if idx == b_matches.index[0] else "❌ 删除"
            print(f"      {status} 本店: {row[a_name_col][:70]}")
            print(f"           得分: {row[score_col]:.3f}")
    
    # 生成去向分析报告
    output_file = str(Path(excel_file).parent / f"{Path(excel_file).stem}_去向分析.xlsx")
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Sheet 1: 被删除的匹配
        deleted_df.to_excel(writer, sheet_name='被删除的匹配', index=False)
        
        # Sheet 2: 重复匹配详情
        dup_details = []
        for b_name in duplicated_b.index:
            b_matches = df_fuzzy[df_fuzzy[b_name_col] == b_name].copy()
            b_matches = b_matches.sort_values(score_col, ascending=False)
            
            for idx, row in b_matches.iterrows():
                dup_details.append({
                    '竞对商品': b_name,
                    '本店商品': row[a_name_col],
                    '得分': row[score_col],
                    '是否保留': '保留' if idx == b_matches.index[0] else '删除',
                    '匹配排名': list(b_matches.index).index(idx) + 1,
                    '总匹配数': len(b_matches)
                })
        
        pd.DataFrame(dup_details).to_excel(writer, sheet_name='重复匹配详情', index=False)
    
    print(f"\n{'='*80}")
    print(f"✅ 去向分析报告已保存: {output_file}")
    print(f"{'='*80}")
    
    return deleted_df

def main():
    """主函数"""
    reports_dir = Path('reports')
    
    # 查找最新的比价报告
    excel_files = [f for f in reports_dir.glob('matched_products_comparison_final_*.xlsx') 
                   if '诊断' not in f.name and '去向' not in f.name]
    
    if not excel_files:
        print("❌ 找不到比价报告")
        return
    
    latest_file = max(excel_files, key=lambda x: x.stat().st_mtime)
    
    print(f"🎯 分析最新报告: {latest_file.name}")
    print(f"📅 修改时间: {pd.Timestamp.fromtimestamp(latest_file.stat().st_mtime)}")
    print()
    
    analyze_dedup_impact(str(latest_file))

if __name__ == '__main__':
    main()
