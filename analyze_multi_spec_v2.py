"""
优化版多规格识别 - 适配去重后的比价报告

核心变化：
1. 不再依赖"重复匹配"识别多规格
2. 直接基于竞对商品的规格列识别多规格
3. 对比本店和竞对的规格覆盖情况
"""

import pandas as pd
from pathlib import Path
import re

def extract_spec_info(text):
    """从商品名称或规格列提取规格信息"""
    if pd.isna(text) or text == '':
        return set()
    
    text = str(text)
    specs = set()
    
    # 提取容量/重量规格
    patterns = [
        r'(\d+(?:\.\d+)?)\s*ml',
        r'(\d+(?:\.\d+)?)\s*g',
        r'(\d+(?:\.\d+)?)\s*kg',
        r'(\d+(?:\.\d+)?)\s*L',
        r'(\d+(?:\.\d+)?)\s*片',
        r'(\d+(?:\.\d+)?)\s*条',
        r'(\d+(?:\.\d+)?)\s*包',
        r'(\d+(?:\.\d+)?)\s*盒',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        specs.update(matches)
    
    # 提取尺码
    size_patterns = [
        r'[SMLX]{1,3}码',
        r'\d+码',
        r'\d+-\d+码',
    ]
    
    for pattern in size_patterns:
        matches = re.findall(pattern, text)
        specs.update(matches)
    
    return specs

def analyze_multi_spec_products(excel_file):
    """分析多规格商品（优化版）"""
    
    print(f"{'='*80}")
    print(f"🔍 多规格商品识别（优化版 - 适配去重后报告）")
    print(f"{'='*80}")
    print(f"报告文件: {Path(excel_file).name}\n")
    
    # 读取模糊匹配Sheet
    df = pd.read_excel(excel_file, sheet_name='2-名称模糊匹配(无条码)')
    
    # 识别列名
    a_name_col = [col for col in df.columns if '商品名称' in col and '高港店' in col][0]
    b_name_col = [col for col in df.columns if '商品名称' in col and '好惠来店' in col][0]
    
    # 规格列（可能不存在）
    a_spec_col = [col for col in df.columns if '规格' in col and '高港店' in col]
    b_spec_col = [col for col in df.columns if '规格' in col and '好惠来店' in col]
    a_spec_col = a_spec_col[0] if a_spec_col else None
    b_spec_col = b_spec_col[0] if b_spec_col else None
    
    print(f"📊 基础统计:")
    print(f"总匹配数: {len(df)}")
    print(f"唯一竞对商品: {df[b_name_col].nunique()}")
    print(f"唯一本店商品: {df[a_name_col].nunique()}")
    
    # === 方法1: 基于规格列识别 ===
    multi_spec_by_column = []
    
    if b_spec_col:
        print(f"\n{'='*80}")
        print(f"📋 方法1: 基于竞对规格列识别")
        print(f"{'='*80}")
        
        for b_name in df[b_name_col].unique():
            b_rows = df[df[b_name_col] == b_name]
            
            # 检查竞对规格列
            b_specs = b_rows[b_spec_col].dropna().unique()
            
            # 如果规格列包含明显的多规格标识
            if len(b_specs) == 1:
                spec_text = str(b_specs[0])
                # 检查是否包含"多规格"、"可选"等关键词
                if any(keyword in spec_text for keyword in ['可选', '多规格', '/', '或', '|']):
                    multi_spec_by_column.append({
                        '竞对商品': b_name,
                        '规格信息': spec_text,
                        '本店匹配数': len(b_rows),
                        '识别依据': '规格列包含多规格标识'
                    })
        
        print(f"✅ 通过规格列识别: {len(multi_spec_by_column)} 个多规格商品")
    
    # === 方法2: 基于商品名称解析 ===
    print(f"\n{'='*80}")
    print(f"📋 方法2: 基于商品名称规格解析")
    print(f"{'='*80}")
    
    multi_spec_by_name = []
    
    for b_name in df[b_name_col].unique():
        b_rows = df[df[b_name_col] == b_name]
        
        # 从竞对商品名称提取规格
        b_specs = extract_spec_info(b_name)
        
        # 检查是否包含多规格关键词
        multi_spec_keywords = ['多规格', '可选', '任选', '随机', '多色', '多款']
        has_multi_spec_keyword = any(keyword in b_name for keyword in multi_spec_keywords)
        
        if has_multi_spec_keyword or len(b_specs) > 2:  # 包含2个以上规格信息
            # 检查本店匹配的商品是否有不同规格
            a_specs_list = []
            for _, row in b_rows.iterrows():
                a_name = row[a_name_col]
                a_spec_text = row[a_spec_col] if a_spec_col else ''
                a_specs = extract_spec_info(f"{a_name} {a_spec_text}")
                a_specs_list.append(a_specs)
            
            # 本店是否有多个不同规格
            unique_a_specs = set()
            for specs in a_specs_list:
                if specs:
                    unique_a_specs.update(specs)
            
            multi_spec_by_name.append({
                '竞对商品': b_name[:80],
                '竞对规格': ', '.join(b_specs) if b_specs else '名称包含多规格关键词',
                '本店匹配数': len(b_rows),
                '本店规格数': len(unique_a_specs) if unique_a_specs else '未解析',
                '识别依据': '名称解析' if b_specs else '多规格关键词'
            })
    
    print(f"✅ 通过名称解析识别: {len(multi_spec_by_name)} 个多规格商品")
    
    # === 方法3: 基于本店商品规格差异 ===
    print(f"\n{'='*80}")
    print(f"📋 方法3: 基于本店商品规格差异推断")
    print(f"{'='*80}")
    
    # 注意：去重后每个竞对商品只匹配1个本店商品
    # 但我们可以读取优化前的报告来对比
    
    print(f"⚠️ 去重后无法通过此方法识别（需要对比优化前报告）")
    
    # === 汇总结果 ===
    print(f"\n{'='*80}")
    print(f"📊 汇总结果")
    print(f"{'='*80}")
    
    all_multi_spec = {}
    
    # 合并方法1和方法2的结果
    for item in multi_spec_by_column:
        all_multi_spec[item['竞对商品']] = item
    
    for item in multi_spec_by_name:
        b_name = item['竞对商品']
        if b_name not in all_multi_spec:
            all_multi_spec[b_name] = item
    
    print(f"总计识别多规格商品: {len(all_multi_spec)} 个")
    
    if len(all_multi_spec) > 0:
        print(f"\n示例（前10个）:")
        for i, (b_name, item) in enumerate(list(all_multi_spec.items())[:10], 1):
            print(f"\n{i}. {b_name[:70]}")
            print(f"   识别依据: {item['识别依据']}")
            print(f"   本店匹配数: {item['本店匹配数']}")
    
    # === 建议 ===
    print(f"\n{'='*80}")
    print(f"💡 优化建议")
    print(f"{'='*80}")
    
    print(f"""
1. 【数据源优化】确保竞对商品有完整的规格列数据
   - 当前识别依赖规格列和名称解析
   - 规格列越完整，识别越准确

2. 【对比优化前报告】识别被去重的多规格
   - 去重前：同一竞对商品匹配多个本店商品
   - 检查这些本店商品是否有不同规格
   - 如果有→竞对可能是多规格商品

3. 【独立数据源】直接从竞对原始数据识别
   - 不依赖匹配结果
   - 基于竞对自己的SKU数据判断多规格
   
4. 【手动标注】对于关键品类
   - 建立多规格商品清单
   - 定期更新维护
    """)
    
    # 保存结果
    output_file = str(Path(excel_file).parent / f"多规格分析_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    
    if all_multi_spec:
        df_result = pd.DataFrame(list(all_multi_spec.values()))
        df_result.to_excel(output_file, index=False)
        print(f"\n✅ 分析结果已保存: {output_file}")
    
    return all_multi_spec

def main():
    """主函数"""
    reports_dir = Path('reports')
    
    # 查找最新报告
    excel_files = sorted([f for f in reports_dir.glob('matched_products_comparison_final_*.xlsx') 
                         if '诊断' not in f.name and '去向' not in f.name],
                        key=lambda x: x.stat().st_mtime)
    
    if not excel_files:
        print("❌ 找不到比价报告")
        return
    
    latest_file = excel_files[-1]
    print(f"🎯 分析最新报告: {latest_file.name}\n")
    
    analyze_multi_spec_products(str(latest_file))

if __name__ == '__main__':
    main()
