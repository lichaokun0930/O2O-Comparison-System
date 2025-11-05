"""
增强版诊断工具 - 集成完整多规格识别
结合优化后的比价报告 + 竞对原始数据，生成完整分析
"""
import pandas as pd
from pathlib import Path
import sys

# 导入完整版多规格识别
from multi_spec_identifier import identify_multi_spec_products


def find_latest_report(reports_dir='reports'):
    """查找最新的比价报告"""
    reports_path = Path(reports_dir)
    if not reports_path.exists():
        return None
    
    excel_files = list(reports_path.glob('matched_products_comparison_final_*.xlsx'))
    if not excel_files:
        return None
    
    # 按修改时间排序
    excel_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return excel_files[0]


def find_competitor_original_data(upload_dir='upload/竞对'):
    """查找竞对原始数据"""
    upload_path = Path(upload_dir)
    if not upload_path.exists():
        return None
    
    excel_files = list(upload_path.glob('*.xlsx'))
    if not excel_files:
        return None
    
    return excel_files[0]


def find_our_original_data(upload_dir='upload/本店'):
    """查找本店原始数据"""
    upload_path = Path(upload_dir)
    if not upload_path.exists():
        return None
    
    excel_files = list(upload_path.glob('*.xlsx'))
    if not excel_files:
        return None
    
    return excel_files[0]


def analyze_enhanced(report_file, competitor_file=None, our_file=None):
    """
    增强版分析，结合比价报告和双方原始数据
    
    参数:
        report_file: 优化后的比价报告
        competitor_file: 竞对原始数据（可选）
        our_file: 本店原始数据（可选）
    """
    print("="*70)
    print("📊 增强版多规格诊断分析")
    print("="*70)
    
    # === Part 1: 读取比价报告 ===
    print(f"\n📂 读取比价报告: {Path(report_file).name}")
    
    try:
        # 读取模糊匹配Sheet
        df_matched = pd.read_excel(report_file, sheet_name='2-名称模糊匹配(无条码)')
        print(f"✅ 模糊匹配记录: {len(df_matched)} 条")
        
        # 读取独有商品
        sheets_dict = pd.read_excel(report_file, sheet_name=None)
        
        # 查找独有商品Sheet（优先使用全部版本，数据更完整）
        competitor_unique_sheet = None
        our_unique_sheet = None
        
        for sheet_name in sheets_dict.keys():
            # 竞对独有：支持多种命名格式
            if any(x in sheet_name for x in ['竞对独有', '店B独有', '好惠来店-独有']):
                if '全部' in sheet_name or competitor_unique_sheet is None:
                    competitor_unique_sheet = sheet_name
            # 本店独有：支持多种命名格式
            elif any(x in sheet_name for x in ['本店独有', '店A独有', '高港店-独有']):
                if '全部' in sheet_name or our_unique_sheet is None:
                    our_unique_sheet = sheet_name
        
        df_competitor_unique = sheets_dict.get(competitor_unique_sheet, pd.DataFrame())
        df_our_unique = sheets_dict.get(our_unique_sheet, pd.DataFrame())
        
        print(f"📋 识别到竞对独有Sheet: {competitor_unique_sheet}")
        print(f"📋 识别到本店独有Sheet: {our_unique_sheet}")
        
        print(f"✅ 竞对独有商品: {len(df_competitor_unique)} 个")
        print(f"✅ 本店独有商品: {len(df_our_unique)} 个")
        
    except Exception as e:
        print(f"❌ 读取比价报告失败: {e}")
        return None
    
    # === Part 2: 竞对原始数据多规格识别 ===
    competitor_multi_spec_full = pd.DataFrame()
    
    if competitor_file and Path(competitor_file).exists():
        print(f"\n🔍 分析竞对原始数据...")
        print(f"文件: {Path(competitor_file).name}")
        
        try:
            # 读取竞对原始数据
            df_competitor_raw = pd.read_excel(competitor_file)
            print(f"✅ 竞对原始数据: {len(df_competitor_raw)} 个SKU")
            
            # 执行完整的三信号检测
            competitor_multi_spec_full = identify_multi_spec_products(
                df_competitor_raw,
                product_name_col='商品名称',
                spec_col='规格名称',
                barcode_col='条码'
            )
            
            print(f"✅ 识别到多规格商品: {competitor_multi_spec_full['base_name'].nunique()} 个")
            print(f"✅ 多规格SKU总数: {len(competitor_multi_spec_full)} 个")
            
        except Exception as e:
            print(f"⚠️ 竞对原始数据分析失败: {e}")
    else:
        print(f"\n⚠️ 未提供竞对原始数据，跳过完整多规格识别")
    
    # === Part 2.5: 本店原始数据多规格识别 ===
    our_multi_spec_full = pd.DataFrame()
    
    if our_file and Path(our_file).exists():
        print(f"\n🔍 分析本店原始数据...")
        print(f"文件: {Path(our_file).name}")
        
        try:
            # 读取本店原始数据
            df_our_raw = pd.read_excel(our_file)
            print(f"✅ 本店原始数据: {len(df_our_raw)} 个SKU")
            
            # 执行完整的三信号检测
            our_multi_spec_full = identify_multi_spec_products(
                df_our_raw,
                product_name_col='商品名称',
                spec_col='规格名称',
                barcode_col='条码'
            )
            
            print(f"✅ 识别到多规格商品: {our_multi_spec_full['base_name'].nunique()} 个")
            print(f"✅ 多规格SKU总数: {len(our_multi_spec_full)} 个")
            
        except Exception as e:
            print(f"⚠️ 本店原始数据分析失败: {e}")
    else:
        print(f"\n⚠️ 未提供本店原始数据，跳过完整多规格识别")
    
    # === Part 3: 匹配结果中的多规格分析 ===
    print(f"\n🔍 分析匹配结果中的多规格...")
    
    # 获取列名
    name_cols = [col for col in df_matched.columns if '商品名称' in col]
    if len(name_cols) < 2:
        print("❌ 找不到商品名称列")
        return None
    
    a_name_col = name_cols[0]  # 本店
    b_name_col = name_cols[1]  # 竞对
    
    # 双侧分组统计
    a_duplicates = df_matched[a_name_col].value_counts()
    b_duplicates = df_matched[b_name_col].value_counts()
    duplicate_a = a_duplicates[a_duplicates > 1]
    duplicate_b = b_duplicates[b_duplicates > 1]
    
    print(f"多规格匹配情况:")
    print(f"  - 总匹配记录: {len(df_matched)}")
    print(f"  - 本店侧重复商品: {len(duplicate_a)} 个（一对多匹配）")
    print(f"  - 竞对侧重复商品: {len(duplicate_b)} 个（一对多匹配）")
    
    # 识别匹配结果中的多规格（双向检查）
    matched_multi_spec = []
    
    # 1. 本店侧：一个本店商品匹配多个竞对商品
    for a_name, count in duplicate_a.items():
        if count <= 1:
            continue
        
        matched_rows = df_matched[df_matched[a_name_col] == a_name]
        
        # 检查本店是否是真多规格
        is_our_multi_spec = False
        our_spec_details = ''
        
        if not our_multi_spec_full.empty:
            match = our_multi_spec_full[
                our_multi_spec_full['商品名称'] == a_name
            ]
            if not match.empty:
                is_our_multi_spec = True
                spec_count = match['规格种类数'].iloc[0]
                spec_basis = match['多规格依据'].iloc[0]
                our_spec_details = f"{spec_count}种规格 ({spec_basis})"
        
        matched_multi_spec.append({
            '匹配类型': '本店→竞对（一对多）',
            '本店商品': a_name,
            '本店验证': '✅ 确认多规格' if is_our_multi_spec else '⚠️ 待确认',
            '本店规格详情': our_spec_details if our_spec_details else '未识别',
            '匹配数量': count,
            '竞对商品': ', '.join(matched_rows[b_name_col].tolist()[:5])
        })
    
    # 2. 竞对侧：一个竞对商品匹配多个本店商品
    for b_name, count in duplicate_b.items():
        if count <= 1:
            continue
        
        matched_rows = df_matched[df_matched[b_name_col] == b_name]
        
        # 检查竞对是否是真多规格
        is_competitor_multi_spec = False
        competitor_spec_details = ''
        
        if not competitor_multi_spec_full.empty:
            match = competitor_multi_spec_full[
                competitor_multi_spec_full['商品名称'] == b_name
            ]
            if not match.empty:
                is_competitor_multi_spec = True
                spec_count = match['规格种类数'].iloc[0]
                spec_basis = match['多规格依据'].iloc[0]
                competitor_spec_details = f"{spec_count}种规格 ({spec_basis})"
        
        matched_multi_spec.append({
            '匹配类型': '竞对→本店（一对多）',
            '竞对商品': b_name,
            '竞对验证': '✅ 确认多规格' if is_competitor_multi_spec else '⚠️ 待确认',
            '竞对规格详情': competitor_spec_details if competitor_spec_details else '未识别',
            '匹配数量': count,
            '本店商品': ', '.join(matched_rows[a_name_col].tolist()[:5])
        })
    
    print(f"✅ 识别到匹配结果中的多规格: {len(matched_multi_spec)} 个")
    
    # === Part 4: 独有商品多规格分析 ===
    print(f"\n🔍 分析独有商品中的多规格...")
    
    # 竞对独有（从原始数据识别）
    competitor_unique_multi_enhanced = []
    if not competitor_multi_spec_full.empty and not df_competitor_unique.empty:
        # 获取竞对独有商品的商品名列
        unique_name_cols = [col for col in df_competitor_unique.columns if '商品名称' in col]
        if unique_name_cols:
            unique_name_col = unique_name_cols[0]
            
            for _, row in df_competitor_unique.iterrows():
                product_name = row[unique_name_col]
                
                # 在完整多规格数据中查找（使用实际列名）
                match = competitor_multi_spec_full[
                    competitor_multi_spec_full['商品名称'] == product_name
                ]
                
                if not match.empty:
                    base_name = match['base_name'].iloc[0]
                    spec_count = match['规格种类数'].iloc[0]
                    spec_basis = match['多规格依据'].iloc[0]
                    
                    # 统计该base_name的所有SKU
                    all_skus = competitor_multi_spec_full[
                        competitor_multi_spec_full['base_name'] == base_name
                    ]
                    
                    competitor_unique_multi_enhanced.append({
                        '商品基础名称': base_name,
                        '规格种类数': spec_count,
                        'SKU数': len(all_skus),
                        '识别依据': spec_basis,
                        '示例商品名': product_name
                    })
            
            # 去重（按base_name）
            if competitor_unique_multi_enhanced:
                competitor_unique_df = pd.DataFrame(competitor_unique_multi_enhanced)
                competitor_unique_df = competitor_unique_df.drop_duplicates(subset=['商品基础名称'])
                competitor_unique_multi_enhanced = competitor_unique_df.to_dict('records')
        
        print(f"✅ 竞对独有多规格: {len(competitor_unique_multi_enhanced)} 个")
    else:
        print(f"⚠️ 无法分析竞对独有多规格（缺少数据）")
    
    # 本店独有（完整三信号检测）
    our_unique_multi_enhanced = []
    if not our_multi_spec_full.empty and not df_our_unique.empty:
        # 获取本店独有商品的商品名列
        unique_name_cols = [col for col in df_our_unique.columns if '商品名称' in col]
        if unique_name_cols:
            unique_name_col = unique_name_cols[0]
            
            for _, row in df_our_unique.iterrows():
                product_name = row[unique_name_col]
                
                # 在完整多规格数据中查找（使用实际列名）
                match = our_multi_spec_full[
                    our_multi_spec_full['商品名称'] == product_name
                ]
                
                if not match.empty:
                    base_name = match['base_name'].iloc[0]
                    spec_count = match['规格种类数'].iloc[0]
                    spec_basis = match['多规格依据'].iloc[0]
                    
                    # 统计该base_name的所有SKU
                    all_skus = our_multi_spec_full[
                        our_multi_spec_full['base_name'] == base_name
                    ]
                    
                    our_unique_multi_enhanced.append({
                        '商品基础名称': base_name,
                        '规格种类数': spec_count,
                        'SKU数': len(all_skus),
                        '识别依据': spec_basis,
                        '示例商品名': product_name
                    })
            
            # 去重（按base_name）
            if our_unique_multi_enhanced:
                our_unique_df = pd.DataFrame(our_unique_multi_enhanced)
                our_unique_df = our_unique_df.drop_duplicates(subset=['商品基础名称'])
                our_unique_multi_enhanced = our_unique_df.to_dict('records')
        
        print(f"✅ 本店独有多规格（完整识别）: {len(our_unique_multi_enhanced)} 个")
    elif not df_our_unique.empty:
        # 降级为简化识别
        print(f"⚠️ 未提供本店原始数据，使用简化识别...")
        our_unique_multi = []
        unique_name_cols = [col for col in df_our_unique.columns if '商品名称' in col]
        if unique_name_cols:
            unique_name_col = unique_name_cols[0]
            
            # 按商品名分组
            for product_name, group in df_our_unique.groupby(unique_name_col):
                if len(group) > 1:
                    our_unique_multi.append({
                        '商品名称': product_name,
                        'SKU数': len(group),
                        '识别依据': '同名多SKU（简化）'
                    })
            
            our_unique_multi_enhanced = our_unique_multi
        
        print(f"✅ 本店独有多规格（简化识别）: {len(our_unique_multi_enhanced)} 个")
    else:
        our_unique_multi_enhanced = []
        print(f"⚠️ 无法分析本店独有多规格（缺少数据）")
    
    # === Part 5: 生成增强报告 ===
    output_file = Path('reports') / f'enhanced_diagnosis_{pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    output_file.parent.mkdir(exist_ok=True)
    
    print(f"\n💾 生成增强诊断报告...")
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Sheet 1: 概览
        overview_data = {
            '指标': [
                '总匹配记录数',
                '唯一竞对商品数',
                '重复的竞对商品数',
                '竞对独有商品数',
                '本店独有商品数',
                '',
                '【多规格识别】',
                '匹配结果中的多规格',
                '竞对独有多规格（完整识别）',
                '本店独有多规格（完整识别）',
                '',
                '【原始数据多规格】',
                '竞对多规格商品总数',
                '竞对多规格SKU总数',
                '本店多规格商品总数',
                '本店多规格SKU总数'
            ],
            '数值': [
                len(df_matched),
                df_matched[b_name_col].nunique(),
                len(duplicate_b),
                len(df_competitor_unique),
                len(df_our_unique),
                '',
                '',
                len(matched_multi_spec),
                len(competitor_unique_multi_enhanced),
                len(our_unique_multi_enhanced),
                '',
                '',
                competitor_multi_spec_full['base_name'].nunique() if not competitor_multi_spec_full.empty else 0,
                len(competitor_multi_spec_full) if not competitor_multi_spec_full.empty else 0,
                our_multi_spec_full['base_name'].nunique() if not our_multi_spec_full.empty else 0,
                len(our_multi_spec_full) if not our_multi_spec_full.empty else 0
            ],
            '说明': [
                '模糊匹配总记录',
                '去重后竞对商品数',
                f'重复率 {len(duplicate_b) / df_matched[b_name_col].nunique() * 100:.1f}%',
                '我们没有的商品',
                '竞对没有的商品',
                '',
                '',
                '基于优化后报告识别',
                '基于竞对原始数据三信号检测',
                '基于本店原始数据三信号检测',
                '',
                '',
                '竞对完整多规格商品数',
                '竞对完整多规格SKU数',
                '本店完整多规格商品数',
                '本店完整多规格SKU数'
            ]
        }
        pd.DataFrame(overview_data).to_excel(writer, sheet_name='1-分析概览', index=False)
        
        # Sheet 2: 匹配结果多规格
        if matched_multi_spec:
            pd.DataFrame(matched_multi_spec).to_excel(writer, sheet_name='2-匹配多规格商品', index=False)
        else:
            pd.DataFrame({'说明': ['未识别到多规格商品']}).to_excel(writer, sheet_name='2-匹配多规格商品', index=False)
        
        # Sheet 3: 竞对独有多规格（完整版）
        if competitor_unique_multi_enhanced:
            df_comp = pd.DataFrame(competitor_unique_multi_enhanced)
            df_comp = df_comp.sort_values('SKU数', ascending=False)
            df_comp.to_excel(writer, sheet_name='3-竞对独有多规格(完整)', index=False)
        else:
            pd.DataFrame({'说明': ['未识别到竞对独有多规格或缺少原始数据']}).to_excel(
                writer, sheet_name='3-竞对独有多规格(完整)', index=False)
        
        # Sheet 4: 本店独有多规格（完整版）
        if our_unique_multi_enhanced:
            df_our = pd.DataFrame(our_unique_multi_enhanced)
            df_our = df_our.sort_values('SKU数', ascending=False)
            df_our.to_excel(writer, sheet_name='4-本店独有多规格(完整)', index=False)
        else:
            pd.DataFrame({'说明': ['未识别到本店独有多规格或缺少原始数据']}).to_excel(
                writer, sheet_name='4-本店独有多规格(完整)', index=False)
        
        # Sheet 5: 竞对完整多规格清单（原始数据）
        if not competitor_multi_spec_full.empty:
            # 汇总视图
            summary = competitor_multi_spec_full.groupby('base_name').agg({
                '商品名称': 'count',  # 修复：使用实际列名
                '规格种类数': 'first',
                '多规格依据': 'first'
            }).rename(columns={'商品名称': 'SKU数'}).reset_index()
            summary = summary.rename(columns={'base_name': '商品基础名称'})
            summary = summary.sort_values('SKU数', ascending=False)
            
            summary.to_excel(writer, sheet_name='5-竞对多规格汇总', index=False)
            
            # 详细视图
            competitor_multi_spec_full.to_excel(writer, sheet_name='6-竞对多规格详细', index=False)
        else:
            pd.DataFrame({'说明': ['未提供竞对原始数据']}).to_excel(writer, sheet_name='5-竞对多规格汇总', index=False)
        
        # Sheet 7-8: 本店完整多规格清单（原始数据）
        if not our_multi_spec_full.empty:
            # 汇总视图
            our_summary = our_multi_spec_full.groupby('base_name').agg({
                '商品名称': 'count',
                '规格种类数': 'first',
                '多规格依据': 'first'
            }).rename(columns={'商品名称': 'SKU数'}).reset_index()
            our_summary = our_summary.rename(columns={'base_name': '商品基础名称'})
            our_summary = our_summary.sort_values('SKU数', ascending=False)
            
            our_summary.to_excel(writer, sheet_name='7-本店多规格汇总', index=False)
            
            # 详细视图
            our_multi_spec_full.to_excel(writer, sheet_name='8-本店多规格详细', index=False)
        else:
            pd.DataFrame({'说明': ['未提供本店原始数据']}).to_excel(writer, sheet_name='7-本店多规格汇总', index=False)
        
        # Sheet 9: 战略总览
        strategy_data = {
            '维度': [
                '【已匹配】多规格商品',
                '【竞对独有】多规格商品',
                '【本店独有】多规格商品',
                '',
                '优先级P0',
                '优先级P1', 
                '优先级P2'
            ],
            '数量': [
                f"{len(matched_multi_spec)} 个",
                f"{len(competitor_unique_multi_enhanced)} 个",
                f"{len(our_unique_multi_enhanced)} 个",
                '',
                f"{len(matched_multi_spec)} 对",
                f"{len(competitor_unique_multi_enhanced)} 个",
                f"{len(our_unique_multi_enhanced)} 个"
            ],
            '业务含义': [
                '竞对规格更全，我们需补齐',
                '我们没有的品类（多规格商品）',
                '我们的差异化商品',
                '',
                '补齐已匹配的多规格',
                '引进高价值竞对独有多规格',
                '强化推广本店独有多规格'
            ],
            '操作建议': [
                '见Sheet 2，逐一补齐规格',
                '见Sheet 3，评估引进价值',
                '见Sheet 4，加强营销推广',
                '',
                '快速提升竞争力，立即执行',
                '战略品类扩张，优先高SKU商品',
                '巩固差异化优势，持续推广'
            ],
            '数据来源': [
                '优化后比价报告 + 原始数据验证',
                '竞对原始数据三信号检测',
                '本店独有数据分析',
                '',
                '',
                '',
                ''
            ]
        }
        pd.DataFrame(strategy_data).to_excel(writer, sheet_name='9-战略总览', index=False)
    
    print(f"\n{'='*70}")
    print(f"✅ 增强诊断报告已保存: {output_file.name}")
    print(f"{'='*70}")
    print(f"\n📋 报告内容:")
    print(f"  - Sheet 1: 分析概览")
    print(f"  - Sheet 2: 匹配多规格商品 ({len(matched_multi_spec)} 个)")
    print(f"  - Sheet 3: 竞对独有多规格(完整) ({len(competitor_unique_multi_enhanced)} 个)")
    print(f"  - Sheet 4: 本店独有多规格(完整) ({len(our_unique_multi_enhanced)} 个)")
    
    if not competitor_multi_spec_full.empty:
        print(f"  - Sheet 5: 竞对多规格汇总 ({competitor_multi_spec_full['base_name'].nunique()} 个)")
        print(f"  - Sheet 6: 竞对多规格详细 ({len(competitor_multi_spec_full)} SKU)")
    
    if not our_multi_spec_full.empty:
        print(f"  - Sheet 7: 本店多规格汇总 ({our_multi_spec_full['base_name'].nunique()} 个)")
        print(f"  - Sheet 8: 本店多规格详细 ({len(our_multi_spec_full)} SKU)")
    
    print(f"  - Sheet 9: 战略总览")
    
    return output_file


if __name__ == '__main__':
    """
    自动查找最新报告和双方原始数据，执行增强分析
    """
    print("🔍 查找最新比价报告...")
    report_file = find_latest_report()
    
    if not report_file:
        print("❌ 未找到比价报告，请先运行主程序生成报告")
        sys.exit(1)
    
    print(f"✅ 找到报告: {report_file.name}")
    
    print("\n🔍 查找竞对原始数据...")
    competitor_file = find_competitor_original_data()
    
    if competitor_file:
        print(f"✅ 找到竞对数据: {competitor_file.name}")
    else:
        print("⚠️ 未找到竞对原始数据，将使用简化分析")
    
    print("\n🔍 查找本店原始数据...")
    our_file = find_our_original_data()
    
    if our_file:
        print(f"✅ 找到本店数据: {our_file.name}")
    else:
        print("⚠️ 未找到本店原始数据，将使用简化分析")
    
    # 执行增强分析
    result = analyze_enhanced(
        report_file=str(report_file),
        competitor_file=str(competitor_file) if competitor_file else None,
        our_file=str(our_file) if our_file else None
    )
    
    if result:
        print(f"\n🎉 分析完成！")
    else:
        print(f"\n❌ 分析失败")
        sys.exit(1)
