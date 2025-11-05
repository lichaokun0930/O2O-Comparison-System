"""
模糊匹配重复问题诊断工具
自动分析Excel报告，识别重复匹配和多规格商品
"""
import pandas as pd
import re
from collections import Counter
from pathlib import Path
import difflib

def extract_spec_info(product_name):
    """
    从商品名称中提取规格信息
    返回: (基础名称, 规格列表)
    """
    specs = []
    base_name = product_name
    
    # 规格模式：容量、重量、数量、包装
    patterns = [
        r'(\d+\.?\d*)(ml|ML|毫升|L|升)',           # 容量
        r'(\d+\.?\d*)(g|G|克|kg|KG|公斤|斤)',      # 重量
        r'(\d+)(瓶|罐|盒|袋|包|箱|桶|支|条|片|块|只|个|粒|枚)', # 数量+单位
        r'(\d+)x(\d+)(ml|g|ML|G|毫升|克)',         # 组合装 (如 6x500ml)
        r'(大瓶|中瓶|小瓶|大包|中包|小包|迷你装|家庭装|分享装|便携装)', # 描述性规格
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, product_name, re.IGNORECASE)
        if matches:
            for match in matches:
                if isinstance(match, tuple):
                    spec = ''.join(match)
                else:
                    spec = match
                specs.append(spec)
                # 从基础名称中移除规格
                base_name = base_name.replace(spec, '')
    
    # 清理基础名称
    base_name = re.sub(r'\s+', ' ', base_name).strip()
    base_name = re.sub(r'[（(].*?[)）]', '', base_name)  # 移除括号内容
    
    return base_name, specs

def calculate_name_similarity(name1, name2):
    """计算两个商品名的文本相似度（0-1）"""
    return difflib.SequenceMatcher(None, name1, name2).ratio()

def identify_unique_multi_spec(df, name_col, side_name):
    """
    识别独有商品中的多规格商品
    
    逻辑：
    - 按商品名称分组（去除规格描述后）
    - 如果同一基础名称有多个不同规格或条码，则为多规格
    
    参数:
        df: 独有商品DataFrame
        name_col: 商品名称列名
        side_name: '本店'或'竞对'，用于识别规格列和条码列
    
    返回:
        多规格商品列表
    """
    multi_spec_products = []
    
    # 获取规格列和条码列
    # 独有商品Sheet中的列名不带店名后缀
    spec_cols = [col for col in df.columns if '规格' in col]
    barcode_cols = [col for col in df.columns if '条码' in col]
    sales_col = '月售' if '月售' in df.columns else None
    
    # 按商品名称分组（简单分组，可以优化为去除规格后的基础名称分组）
    for product_name in df[name_col].unique():
        product_rows = df[df[name_col] == product_name]
        
        if len(product_rows) <= 1:
            continue
        
        # 方式1：基于规格列
        if spec_cols:
            specs = product_rows[spec_cols[0]].astype(str).str.strip()
            specs = specs[(specs != '') & (specs != 'nan') & (specs.notna())]
            unique_specs = specs.unique()
            
            if len(unique_specs) > 1:
                multi_spec_products.append({
                    '商品名称': product_name,
                    '规格数': len(unique_specs),
                    '规格列表': ', '.join(unique_specs[:5]),
                    'SKU数': len(product_rows),
                    '月售合计': product_rows[sales_col].sum() if sales_col else 0,
                    '判定依据': f'规格列有{len(unique_specs)}种不同规格'
                })
                continue
        
        # 方式2：基于条码列
        if barcode_cols:
            barcodes = product_rows[barcode_cols[0]].astype(str).str.strip()
            barcodes = barcodes[(barcodes != '') & (barcodes != 'nan') & (barcodes.notna())]
            unique_barcodes = barcodes.unique()
            
            if len(unique_barcodes) > 1:
                multi_spec_products.append({
                    '商品名称': product_name,
                    '规格数': len(unique_barcodes),
                    '规格列表': f'{len(unique_barcodes)}个不同条码',
                    'SKU数': len(product_rows),
                    '月售合计': product_rows[sales_col].sum() if sales_col else 0,
                    '判定依据': f'条码有{len(unique_barcodes)}种'
                })
    
    return multi_spec_products

def identify_competitor_multi_spec(matched_rows, b_name_col):
    """
    识别竞对的多规格商品（只看竞对侧）
    
    核心逻辑：
    - 如果同一个竞对商品名，匹配到我们多个不同的商品
    - 且这些匹配有不同的规格或条码
    - 说明竞对有多规格，而我们可能只有单规格
    
    竞对多规格判定条件（满足任意一组）：
    
    【方式1：基于竞对规格列】
    - 同一商品名的多次匹配中，竞对规格列有多个不同值
    
    【方式2：基于竞对条码】
    - 同一商品名的多次匹配中，竞对条码有多个不同值
    
    【方式3：基于竞对名称规格】
    - 从竞对商品名称中提取规格，有多个不同规格
    
    参数：
        matched_rows: 同一竞对商品名的所有匹配行
        b_name_col: 竞对商品名称列名
    
    返回：
        (is_multi_spec, spec_count, spec_list, reason)
    """
    if len(matched_rows) <= 1:
        return False, 1, [], "单次匹配"
    
    # 获取竞对规格列和条码列
    spec_b_cols = [col for col in matched_rows.columns if '规格' in col and b_name_col.split('_')[1] in col]
    barcode_b_cols = [col for col in matched_rows.columns if '条码' in col and b_name_col.split('_')[1] in col]
    
    # === 方式1：基于竞对规格列 ===
    if spec_b_cols:
        specs = matched_rows[spec_b_cols[0]].astype(str).str.strip()
        specs = specs[(specs != '') & (specs != 'nan') & (specs.notna())]
        unique_specs = specs.unique()
        
        if len(unique_specs) > 1:
            return True, len(unique_specs), list(unique_specs), f"竞对规格列有{len(unique_specs)}种: {', '.join(unique_specs[:3])}"
    
    # === 方式2：基于竞对条码 ===
    if barcode_b_cols:
        barcodes = matched_rows[barcode_b_cols[0]].astype(str).str.strip()
        barcodes = barcodes[(barcodes != '') & (barcodes != 'nan') & (barcodes.notna())]
        unique_barcodes = barcodes.unique()
        
        if len(unique_barcodes) > 1:
            return True, len(unique_barcodes), list(unique_barcodes), f"竞对条码有{len(unique_barcodes)}种不同条码"
    
    # === 方式3：基于竞对名称规格解析 ===
    b_name = matched_rows[b_name_col].iloc[0]
    _, specs_from_name = extract_spec_info(b_name)
    
    if len(specs_from_name) > 0:
        # 如果商品名称中包含"规格可选"、"多规格"等关键词
        if any(keyword in b_name for keyword in ['规格可选', '多规格', '尺码可选', '颜色可选']):
            return True, 2, specs_from_name, f"竞对商品名含'规格可选'等关键词"
    
    return False, 1, [], "非多规格"

def analyze_match_duplicates(excel_file):
    """
    分析模糊匹配结果中的重复问题
    
    返回：诊断报告字典
    """
    print(f"📊 正在分析: {excel_file}")
    
    # 读取模糊匹配Sheet
    try:
        df = pd.read_excel(excel_file, sheet_name='2-名称模糊匹配(无条码)')
    except Exception as e:
        print(f"❌ 无法读取Excel: {e}")
        return None
    
    print(f"✅ 模糊匹配总记录数: {len(df)}")
    
    # 提取竞对商品名列（动态识别列名）
    b_name_col = None
    a_name_col = None
    name_cols = [col for col in df.columns if '商品名称' in col]
    
    if len(name_cols) >= 2:
        a_name_col = name_cols[0]  # 第一个商品名称列作为本店
        b_name_col = name_cols[1]  # 第二个商品名称列作为竞对
    else:
        print(f"❌ 找不到足够的商品名称列，可用列: {df.columns.tolist()}")
        return None
    
    print(f"📌 本店列: {a_name_col}")
    print(f"📌 竞对列: {b_name_col}")
    
    # === 1. 竞对侧重复分析 ===
    b_duplicates = df[b_name_col].value_counts()
    duplicate_b = b_duplicates[b_duplicates > 1]
    
    print(f"\n{'='*60}")
    print(f"📋 【竞对侧重复统计】")
    print(f"{'='*60}")
    print(f"总匹配数: {len(df)}")
    print(f"唯一竞对商品数: {df[b_name_col].nunique()}")
    print(f"重复的竞对商品数: {len(duplicate_b)}")
    print(f"重复匹配占比: {len(duplicate_b) * duplicate_b.mean() / len(df) * 100:.1f}%")
    
    # === 2. TOP 10 重复商品 ===
    print(f"\n{'='*60}")
    print(f"🔥 【TOP 10 最多重复的竞对商品】")
    print(f"{'='*60}")
    top_duplicates = []
    for b_name, count in duplicate_b.head(10).items():
        matched_a_names = df[df[b_name_col] == b_name][a_name_col].tolist()
        top_duplicates.append({
            '竞对商品': b_name,
            '匹配次数': count,
            '本店商品': matched_a_names
        })
        print(f"\n竞对: {b_name}")
        print(f"   匹配次数: {count}")
        print(f"   匹配的本店商品:")
        for i, a_name in enumerate(matched_a_names, 1):
            print(f"      {i}. {a_name}")
    
    # === 3. 多规格 vs 真重复分类 ===
    print(f"\n{'='*60}")
    print(f"🔬 【多规格商品识别】（基于规格列+条码+名称）")
    print(f"{'='*60}")
    
    # 🔍 统计：检查数据中规格列和条码列的覆盖率
    spec_cols = [col for col in df.columns if '规格' in col]
    barcode_cols = [col for col in df.columns if '条码' in col]
    
    if spec_cols:
        spec_coverage_a = df[spec_cols[0]].notna().sum() if len(spec_cols) > 0 else 0
        spec_coverage_b = df[spec_cols[1]].notna().sum() if len(spec_cols) > 1 else 0
        print(f"📏 规格列覆盖: 本店 {spec_coverage_a}/{len(df)} ({spec_coverage_a/len(df)*100:.1f}%), "
              f"竞对 {spec_coverage_b}/{len(df)} ({spec_coverage_b/len(df)*100:.1f}%)")
    else:
        print(f"⚠️  未找到规格列")
    
    if barcode_cols:
        barcode_coverage_a = df[barcode_cols[0]].notna().sum() if len(barcode_cols) > 0 else 0
        barcode_coverage_b = df[barcode_cols[1]].notna().sum() if len(barcode_cols) > 1 else 0
        print(f"📊 条码列覆盖: 本店 {barcode_coverage_a}/{len(df)} ({barcode_coverage_a/len(df)*100:.1f}%), "
              f"竞对 {barcode_coverage_b}/{len(df)} ({barcode_coverage_b/len(df)*100:.1f}%)")
    else:
        print(f"⚠️  未找到条码列")
    
    print()
    
    multi_spec_cases = []
    true_duplicate_cases = []
    
    # 🔍 统计判断路径
    spec_based = 0
    barcode_based = 0
    name_based = 0
    
    for b_name, count in duplicate_b.items():
        if count <= 1:
            continue
            
        matched_rows = df[df[b_name_col] == b_name]
        
        # 🔍 使用新逻辑：只看竞对侧的多规格
        is_multi, spec_count, spec_list, reason = identify_competitor_multi_spec(matched_rows, b_name_col)
        
        # 🔍 统计判断路径
        if is_multi:
            if '规格列' in reason:
                spec_based += 1
            elif '条码' in reason:
                barcode_based += 1
            else:
                name_based += 1
        
        if is_multi:
            # 竞对有多规格，记录为多规格案例
            # 获取竞对的规格列和条码列信息
            spec_b_cols = [col for col in matched_rows.columns if '规格' in col and b_name_col.split('_')[1] in col]
            barcode_b_cols = [col for col in matched_rows.columns if '条码' in col and b_name_col.split('_')[1] in col]
            
            # 展示竞对的所有规格
            if spec_b_cols:
                competitor_specs = matched_rows[spec_b_cols[0]].dropna().unique()
            else:
                competitor_specs = []
            
            if barcode_b_cols:
                competitor_barcodes = matched_rows[barcode_b_cols[0]].dropna().unique()
            else:
                competitor_barcodes = []
            
            # 获取我们匹配到的商品列表
            our_products = matched_rows[a_name_col].tolist()
            
            multi_spec_cases.append({
                '竞对商品': b_name,
                '竞对规格数': spec_count,
                '竞对规格列表': ', '.join([str(s) for s in spec_list[:5]]) if spec_list else '无',
                '我们商品数': len(our_products),
                '我们商品列表': '\n'.join([f"{i}. {p}" for i, p in enumerate(our_products[:5], 1)]),
                '判定依据': reason
            })
        else:
            # 真重复：多个我们的商品匹配到同一个竞对商品（且竞对不是多规格）
            for idx, row_a in matched_rows.iterrows():
                # 提取名称中的规格信息（用于展示）
                base_a, specs_a = extract_spec_info(row_a[a_name_col])
                base_b, specs_b = extract_spec_info(b_name)
                
                true_duplicate_cases.append({
                    '本店商品': row_a[a_name_col],
                    '竞对商品': b_name,
                    '本店基础名': base_a,
                    '竞对基础名': base_b,
                    '判定依据': '非多规格的重复匹配'
                })
    
    print(f"✅ 多规格商品对: {len(multi_spec_cases)}")
    print(f"❌ 真重复商品对: {len(true_duplicate_cases)}")
    if len(multi_spec_cases) + len(true_duplicate_cases) > 0:
        print(f"📊 多规格占比: {len(multi_spec_cases) / (len(multi_spec_cases) + len(true_duplicate_cases)) * 100:.1f}%")
    
    # 🔍 显示判断路径统计
    if multi_spec_cases:
        print(f"\n📋 多规格判定路径统计:")
        print(f"   - 基于规格列: {spec_based} 对")
        print(f"   - 基于条码: {barcode_based} 对")
        print(f"   - 基于名称解析: {name_based} 对")
    
    # 展示多规格识别详情
    if multi_spec_cases:
        print(f"\n🔍 【竞对多规格商品示例】（前5个）")
        for i, case in enumerate(multi_spec_cases[:5], 1):
            print(f"\n  {i}. 竞对: {case['竞对商品'][:80]}")
            print(f"     ⚠️  竞对有 {case['竞对规格数']} 种规格: {case['竞对规格列表']}")
            print(f"     📊 我们只有 {case['我们商品数']} 个商品匹配")
            print(f"     ✅ {case['判定依据']}")
            print(f"     我们的商品:")
            print(f"     {case['我们商品列表']}")
    
    # === 4. 独有商品的多规格分析 ===
    print(f"\n{'='*60}")
    print(f"🔬 【独有商品多规格分析】")
    print(f"{'='*60}")
    
    # 尝试读取独有商品Sheet
    competitor_unique_multi = []
    our_unique_multi = []
    
    try:
        # 读取所有Sheet名称
        xl = pd.ExcelFile(excel_file)
        sheet_names = xl.sheet_names
        
        # 动态识别独有商品Sheet（格式：店名-独有商品(全部)）
        competitor_sheet = None
        our_sheet = None
        
        for sheet in sheet_names:
            if '独有商品(全部)' in sheet:
                # 根据列名判断是竞对还是本店
                # 竞对Sheet包含b_name_col，本店Sheet包含a_name_col
                if b_name_col.split('_')[1] in sheet:
                    competitor_sheet = sheet
                elif a_name_col.split('_')[1] in sheet:
                    our_sheet = sheet
        
        # 读取竞对独有商品
        if competitor_sheet:
            df_competitor_unique = pd.read_excel(excel_file, sheet_name=competitor_sheet)
            print(f"📊 竞对独有商品总数: {len(df_competitor_unique)} (Sheet: {competitor_sheet})")
            
            # 独有商品Sheet使用简单的"商品名称"列（不带店名后缀）
            name_col = '商品名称'
            if name_col not in df_competitor_unique.columns:
                print(f"⚠️  列名错误: 竞对独有商品Sheet中找不到'商品名称'列")
                print(f"   实际列名: {list(df_competitor_unique.columns)[:10]}")
            else:
                # 识别竞对独有商品中的多规格
                competitor_unique_multi = identify_unique_multi_spec(df_competitor_unique, name_col, '竞对')
                print(f"✅ 竞对独有多规格商品: {len(competitor_unique_multi)} 个")
                
                if competitor_unique_multi:
                    # 按月售排序
                    competitor_unique_multi_df = pd.DataFrame(competitor_unique_multi)
                    competitor_unique_multi_df = competitor_unique_multi_df.sort_values('月售合计', ascending=False)
                    competitor_unique_multi = competitor_unique_multi_df.to_dict('records')
                    
                    print(f"\n🔥 TOP 5 高销量竞对独有多规格商品:")
                    for i, item in enumerate(competitor_unique_multi[:5], 1):
                        print(f"  {i}. {item['商品名称'][:60]}")
                        print(f"     规格数: {item['规格数']}, SKU数: {item['SKU数']}, 月售: {item['月售合计']}")
        else:
            print(f"⚠️  未找到竞对独有商品Sheet")
    except Exception as e:
        print(f"⚠️  读取竞对独有商品错误: {e}")
    
    try:
        # 读取我们独有商品
        if our_sheet:
            df_our_unique = pd.read_excel(excel_file, sheet_name=our_sheet)
            print(f"\n📊 本店独有商品总数: {len(df_our_unique)} (Sheet: {our_sheet})")
            
            # 独有商品Sheet使用简单的"商品名称"列（不带店名后缀）
            name_col = '商品名称'
            if name_col not in df_our_unique.columns:
                print(f"⚠️  列名错误: 本店独有商品Sheet中找不到'商品名称'列")
                print(f"   实际列名: {list(df_our_unique.columns)[:10]}")
            else:
                # 识别我们独有商品中的多规格
                our_unique_multi = identify_unique_multi_spec(df_our_unique, name_col, '本店')
                print(f"✅ 本店独有多规格商品: {len(our_unique_multi)} 个")
                
                if our_unique_multi:
                    # 按月售排序
                    our_unique_multi_df = pd.DataFrame(our_unique_multi)
                    our_unique_multi_df = our_unique_multi_df.sort_values('月售合计', ascending=False)
                    our_unique_multi = our_unique_multi_df.to_dict('records')
                    
                    print(f"\n✨ TOP 5 高销量本店独有多规格商品:")
                    for i, item in enumerate(our_unique_multi[:5], 1):
                        print(f"  {i}. {item['商品名称'][:60]}")
                        print(f"     规格数: {item['规格数']}, SKU数: {item['SKU数']}, 月售: {item['月售合计']}")
        else:
            print(f"⚠️  未找到本店独有商品Sheet")
    except Exception as e:
        print(f"⚠️  读取本店独有商品错误: {e}")
    
    # === 5. 导出详细报告 ===
    output_file = excel_file.replace('.xlsx', '_重复诊断报告.xlsx')
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Sheet 1: 概览
        summary_data = {
            '指标': [
                '总匹配数',
                '唯一竞对商品数',
                '重复的竞对商品数',
                '重复匹配总数',
                '多规格商品对',
                '真重复商品对',
                '多规格占比(%)'
            ],
            '数值': [
                len(df),
                df[b_name_col].nunique(),
                len(duplicate_b),
                duplicate_b.sum() - len(duplicate_b),
                len(multi_spec_cases),
                len(true_duplicate_cases),
                f"{len(multi_spec_cases) / max(len(multi_spec_cases) + len(true_duplicate_cases), 1) * 100:.1f}"
            ]
        }
        pd.DataFrame(summary_data).to_excel(writer, sheet_name='诊断概览', index=False)
        
        # Sheet 2: TOP重复商品
        top_df_data = []
        for item in top_duplicates:
            for i, a_name in enumerate(item['本店商品']):
                top_df_data.append({
                    '竞对商品': item['竞对商品'],
                    '匹配次数': item['匹配次数'] if i == 0 else '',
                    '本店商品': a_name
                })
        pd.DataFrame(top_df_data).to_excel(writer, sheet_name='TOP10重复商品', index=False)
        
        # Sheet 3: 多规格商品
        if multi_spec_cases:
            pd.DataFrame(multi_spec_cases).to_excel(writer, sheet_name='多规格商品', index=False)
        
        # Sheet 4: 真重复商品
        if true_duplicate_cases:
            pd.DataFrame(true_duplicate_cases).to_excel(writer, sheet_name='真重复商品', index=False)
        
        # Sheet 5: 完整重复列表
        duplicate_df = df[df[b_name_col].isin(duplicate_b.index)].copy()
        duplicate_df = duplicate_df.sort_values(b_name_col)
        duplicate_df.to_excel(writer, sheet_name='完整重复列表', index=False)
        
        # Sheet 6: 竞对独有多规格分析
        if competitor_unique_multi:
            competitor_unique_df = pd.DataFrame(competitor_unique_multi)
            # 按月售降序排列
            competitor_unique_df = competitor_unique_df.sort_values('月售合计', ascending=False)
            competitor_unique_df.to_excel(writer, sheet_name='竞对独有多规格商品', index=False)
            print(f"✅ Sheet 6: 竞对独有多规格商品 ({len(competitor_unique_multi)}个)")
        else:
            # 创建空Sheet
            pd.DataFrame({'说明': ['无竞对独有多规格商品或未找到独有商品数据']}).to_excel(
                writer, sheet_name='竞对独有多规格商品', index=False)
            print(f"⚠️  Sheet 6: 竞对独有多规格商品 (未找到数据)")
        
        # Sheet 7: 我们独有多规格分析
        if our_unique_multi:
            our_unique_df = pd.DataFrame(our_unique_multi)
            # 按月售降序排列
            our_unique_df = our_unique_df.sort_values('月售合计', ascending=False)
            our_unique_df.to_excel(writer, sheet_name='本店独有多规格商品', index=False)
            print(f"✅ Sheet 7: 本店独有多规格商品 ({len(our_unique_multi)}个)")
        else:
            # 创建空Sheet
            pd.DataFrame({'说明': ['无本店独有多规格商品或未找到独有商品数据']}).to_excel(
                writer, sheet_name='本店独有多规格商品', index=False)
            print(f"⚠️  Sheet 7: 本店独有多规格商品 (未找到数据)")
        
        # Sheet 8: 多规格战略总览
        strategy_data = {
            '维度': [
                '【已匹配】竞对多规格商品',
                '【已匹配】真重复商品',
                '【竞对独有】多规格商品',
                '【本店独有】多规格商品',
                '',
                '优先级P0',
                '优先级P1',
                '优先级P2'
            ],
            '数量': [
                len(multi_spec_cases),
                len(true_duplicate_cases),
                len(competitor_unique_multi),
                len(our_unique_multi),
                '',
                f"{len(multi_spec_cases)} 对",
                f"{len(competitor_unique_multi)} 个",
                f"{len(our_unique_multi)} 个"
            ],
            '业务含义': [
                '竞对规格更全，我们需补齐',
                '非多规格的重复匹配',
                '我们没有的品类',
                '我们的差异化商品',
                '',
                '补齐已匹配的多规格',
                '引进高销量竞对独有多规格',
                '强化推广本店独有多规格'
            ],
            '操作建议': [
                '见Sheet 3，逐一补齐规格',
                '启用竞对侧去重（已修复主程序）',
                '见Sheet 6，按月售评估引进价值',
                '见Sheet 7，加强营销突出优势',
                '',
                '快速提升竞争力，立即执行',
                '战略品类扩张，按销量优先',
                '巩固差异化优势，持续推广'
            ]
        }
        strategy_df = pd.DataFrame(strategy_data)
        strategy_df.to_excel(writer, sheet_name='多规格战略总览', index=False)
        print(f"✅ Sheet 8: 多规格战略总览")
    
    print(f"\n{'='*60}")
    print(f"✅ 诊断报告已保存: {output_file}")
    print(f"{'='*60}")
    
    return {
        'total_matches': len(df),
        'unique_b': df[b_name_col].nunique(),
        'duplicate_b_count': len(duplicate_b),
        'multi_spec_count': len(multi_spec_cases),
        'true_duplicate_count': len(true_duplicate_cases),
        'competitor_unique_multi_count': len(competitor_unique_multi),
        'our_unique_multi_count': len(our_unique_multi),
        'output_file': output_file
    }

def main():
    """主函数：查找最新的比价报告并分析"""
    # 查找reports目录下最新的比价报告
    reports_dir = Path('reports')
    
    if not reports_dir.exists():
        print("❌ 找不到 reports 目录")
        return
    
    # 查找所有比价报告（排除诊断报告）
    excel_files = [f for f in reports_dir.glob('matched_products_comparison_final_*.xlsx') 
                   if '诊断' not in f.name]
    
    if not excel_files:
        print("❌ 找不到比价报告文件")
        return
    
    # 选择最新的文件
    latest_file = max(excel_files, key=lambda x: x.stat().st_mtime)
    
    print(f"🎯 找到最新报告: {latest_file.name}")
    print(f"📅 修改时间: {pd.Timestamp.fromtimestamp(latest_file.stat().st_mtime)}")
    print()
    
    # 执行分析
    result = analyze_match_duplicates(str(latest_file))
    
    if result:
        print(f"\n{'='*60}")
        print(f"🎉 分析完成！")
        print(f"{'='*60}")
        print(f"建议：")
        
        duplicate_ratio = result['duplicate_b_count'] / result['unique_b'] * 100
        multi_spec_ratio = result['multi_spec_count'] / max(result['multi_spec_count'] + result['true_duplicate_count'], 1) * 100
        
        if duplicate_ratio > 30:
            print(f"⚠️  重复商品占比 {duplicate_ratio:.1f}% 较高，建议优化匹配逻辑")
        
        if multi_spec_ratio > 70:
            print(f"✅ 多规格商品占比 {multi_spec_ratio:.1f}%，可单独Sheet展示")
        elif multi_spec_ratio < 30:
            print(f"⚠️  真重复商品占比 {100-multi_spec_ratio:.1f}%，建议启用竞对侧去重")
        else:
            print(f"📊 多规格({multi_spec_ratio:.1f}%) 和真重复 混合，建议分别处理")

if __name__ == '__main__':
    main()
