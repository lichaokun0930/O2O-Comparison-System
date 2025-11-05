"""
追踪CD商品的完整去向

对比优化前后的报告，精确追踪被删除的CD商品去了哪里
"""

import pandas as pd
from pathlib import Path

def compare_reports(old_file, new_file):
    """对比优化前后的两份报告，追踪CD商品去向"""
    
    print(f"{'='*80}")
    print(f"📊 对比分析：优化前 vs 优化后")
    print(f"{'='*80}")
    print(f"优化前报告: {Path(old_file).name}")
    print(f"优化后报告: {Path(new_file).name}")
    print()
    
    # 读取模糊匹配Sheet
    df_old = pd.read_excel(old_file, sheet_name='2-名称模糊匹配(无条码)')
    df_new = pd.read_excel(new_file, sheet_name='2-名称模糊匹配(无条码)')
    
    # 识别列名
    a_name_col = [col for col in df_old.columns if '商品名称' in col and '_高港店' in col][0]
    b_name_col = [col for col in df_old.columns if '商品名称' in col and '_好惠来店' in col][0]
    
    print(f"{'='*80}")
    print(f"📋 【模糊匹配数量对比】")
    print(f"{'='*80}")
    print(f"优化前总匹配数: {len(df_old)}")
    print(f"优化后总匹配数: {len(df_new)}")
    print(f"减少匹配数: {len(df_old) - len(df_new)} 条 ({(len(df_old)-len(df_new))/len(df_old)*100:.1f}%)")
    
    # 找出被删除的匹配
    old_pairs = set(zip(df_old[a_name_col], df_old[b_name_col]))
    new_pairs = set(zip(df_new[a_name_col], df_new[b_name_col]))
    deleted_pairs = old_pairs - new_pairs
    
    print(f"\n❌ 被删除的匹配对: {len(deleted_pairs)} 对")
    
    # 提取被删除的本店商品
    deleted_a_products = set([pair[0] for pair in deleted_pairs])
    deleted_b_products = set([pair[1] for pair in deleted_pairs])
    
    print(f"   涉及本店商品: {len(deleted_a_products)} 个")
    print(f"   涉及竞对商品: {len(deleted_b_products)} 个")
    
    # === 追踪CD商品的去向 ===
    print(f"\n{'='*80}")
    print(f"🔍 【追踪被删除的本店商品去向】")
    print(f"{'='*80}")
    
    # 读取所有可能的去向Sheet
    sheets_to_check = {
        '条码精确匹配': '1-条码精确匹配',
        '差异品对比': '3-差异品对比',
        '本店独有商品': '4-高港店-独有商品(全部)',
    }
    
    cd_destinations = {
        '新的模糊匹配': 0,
        '条码精确匹配': 0,
        '差异品对比': 0,
        '本店独有商品': 0,
        '完全消失': 0
    }
    
    cd_details = []
    
    for cd_product in deleted_a_products:
        found_in = []
        
        # 1. 检查是否在新报告的模糊匹配中（新的匹配）
        if cd_product in df_new[a_name_col].values:
            new_match = df_new[df_new[a_name_col] == cd_product]
            new_competitor = new_match[b_name_col].iloc[0]
            found_in.append(f"新的模糊匹配 → {new_competitor[:60]}")
            cd_destinations['新的模糊匹配'] += 1
        
        # 2. 检查条码精确匹配
        try:
            df_barcode = pd.read_excel(new_file, sheet_name='1-条码精确匹配')
            if cd_product in df_barcode[a_name_col].values:
                match = df_barcode[df_barcode[a_name_col] == cd_product]
                competitor = match[b_name_col].iloc[0]
                found_in.append(f"条码精确匹配 → {competitor[:60]}")
                cd_destinations['条码精确匹配'] += 1
        except:
            pass
        
        # 3. 检查差异品对比
        try:
            df_diff = pd.read_excel(new_file, sheet_name='3-差异品对比')
            if cd_product in df_diff[a_name_col].values:
                match = df_diff[df_diff[a_name_col] == cd_product]
                competitor = match[b_name_col].iloc[0]
                found_in.append(f"差异品对比 → {competitor[:60]}")
                cd_destinations['差异品对比'] += 1
        except:
            pass
        
        # 4. 检查本店独有商品
        try:
            df_unique = pd.read_excel(new_file, sheet_name='4-高港店-独有商品(全部)')
            if cd_product in df_unique['商品名称'].values:
                found_in.append(f"本店独有商品")
                cd_destinations['本店独有商品'] += 1
        except:
            pass
        
        # 5. 如果哪里都没找到
        if not found_in:
            found_in.append("⚠️ 完全消失（可能是数据源问题）")
            cd_destinations['完全消失'] += 1
        
        # 获取原始匹配信息
        old_match = df_old[df_old[a_name_col] == cd_product]
        old_competitor = old_match[b_name_col].iloc[0] if not old_match.empty else "未知"
        old_score = old_match['composite_similarity_score'].iloc[0] if 'composite_similarity_score' in old_match.columns else 0
        
        cd_details.append({
            '本店商品': cd_product,
            '原匹配的竞对商品': old_competitor,
            '原得分': old_score,
            '新去向': ' | '.join(found_in)
        })
    
    # 显示统计结果
    print(f"\n📊 去向统计:")
    for destination, count in cd_destinations.items():
        if count > 0:
            percentage = count / len(deleted_a_products) * 100
            print(f"   {destination}: {count} 个 ({percentage:.1f}%)")
    
    # 展示详细案例
    print(f"\n{'='*80}")
    print(f"📋 【CD商品去向详情】（前20个）")
    print(f"{'='*80}")
    
    for i, detail in enumerate(cd_details[:20], 1):
        print(f"\n{i}. 本店: {detail['本店商品'][:70]}")
        print(f"   原匹配: {detail['原匹配的竞对商品'][:70]} (得分: {detail['原得分']:.3f})")
        print(f"   新去向: {detail['新去向']}")
    
    # 生成详细报告
    output_file = str(Path(new_file).parent / f"CD商品追踪报告_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Sheet 1: CD商品去向汇总
        pd.DataFrame(cd_details).to_excel(writer, sheet_name='CD商品去向汇总', index=False)
        
        # Sheet 2: 去向统计
        stats_data = {
            '去向': list(cd_destinations.keys()),
            '数量': list(cd_destinations.values()),
            '占比(%)': [v/len(deleted_a_products)*100 for v in cd_destinations.values()]
        }
        pd.DataFrame(stats_data).to_excel(writer, sheet_name='去向统计', index=False)
        
        # Sheet 3: 被删除的匹配对
        deleted_pairs_df = pd.DataFrame([
            {'本店商品': pair[0], '竞对商品': pair[1]} 
            for pair in list(deleted_pairs)[:1000]  # 限制1000条
        ])
        deleted_pairs_df.to_excel(writer, sheet_name='被删除的匹配对', index=False)
    
    print(f"\n{'='*80}")
    print(f"✅ CD商品追踪报告已保存: {output_file}")
    print(f"{'='*80}")
    
    return cd_details, cd_destinations

def find_latest_reports():
    """查找最新的两份报告（优化前和优化后）"""
    reports_dir = Path('reports')
    
    excel_files = [f for f in reports_dir.glob('matched_products_comparison_final_*.xlsx') 
                   if '诊断' not in f.name and '去向' not in f.name and 'CD商品追踪' not in f.name]
    
    if len(excel_files) < 2:
        print("❌ 需要至少2份比价报告才能对比")
        return None, None
    
    # 按修改时间排序
    excel_files.sort(key=lambda x: x.stat().st_mtime)
    
    old_file = excel_files[-2]  # 倒数第二新的（优化前）
    new_file = excel_files[-1]  # 最新的（优化后）
    
    return str(old_file), str(new_file)

def main():
    """主函数"""
    
    # 方式1: 自动查找最新的两份报告
    old_file, new_file = find_latest_reports()
    
    if not old_file or not new_file:
        # 方式2: 手动指定文件
        reports_dir = Path('reports')
        excel_files = sorted([f for f in reports_dir.glob('matched_products_comparison_final_*.xlsx') 
                             if '诊断' not in f.name and '去向' not in f.name and 'CD商品追踪' not in f.name],
                            key=lambda x: x.stat().st_mtime)
        
        if len(excel_files) < 2:
            print("❌ 找不到足够的报告文件进行对比")
            print(f"   当前reports目录下只有 {len(excel_files)} 个报告")
            return
        
        print("\n📁 可用的报告文件:")
        for i, f in enumerate(excel_files, 1):
            mod_time = pd.Timestamp.fromtimestamp(f.stat().st_mtime)
            print(f"   {i}. {f.name} ({mod_time})")
        
        print("\n请选择要对比的两份报告:")
        try:
            old_idx = int(input("优化前报告编号: ")) - 1
            new_idx = int(input("优化后报告编号: ")) - 1
            old_file = str(excel_files[old_idx])
            new_file = str(excel_files[new_idx])
        except:
            print("❌ 输入错误")
            return
    
    print(f"\n🎯 即将对比:")
    print(f"   优化前: {Path(old_file).name}")
    print(f"   优化后: {Path(new_file).name}")
    print()
    
    compare_reports(old_file, new_file)

if __name__ == '__main__':
    main()
