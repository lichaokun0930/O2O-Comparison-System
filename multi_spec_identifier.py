"""
完整版多规格商品识别工具
基于三信号检测机制（规格列 + 名称解析 + 条码多值）

参考文档: 多规格商品识别逻辑说明.md
实现: identify_multi_spec_products() 完整版
"""
import pandas as pd
import numpy as np
import re
from typing import Tuple, List, Set


def _extract_inferred_spec(name: str) -> str:
    """
    从商品名称中提取规格信息
    
    参数:
        name: 商品名称
    
    返回:
        空格分隔的规格标记字符串 (如 "500ml 无糖")
    """
    if not isinstance(name, str) or not name.strip():
        return ''
    
    specs = []
    
    # === 规格模式：数量×规格 ===
    # 示例: 12*50g, 6×500ml, 3x1.5L
    pattern_qty_spec = r'(\d+\s*[x×*]\s*\d+(?:\.\d+)?\s*(?:g|kg|ml|l|片|包|袋|支|枚|瓶|听|卷)?)'
    matches = re.findall(pattern_qty_spec, name, re.IGNORECASE)
    for match in matches:
        specs.append(match.replace(' ', '').lower())
    
    # === 规格模式：容量/重量 ===
    # 示例: 500ml, 1.5l, 300g, 2kg
    pattern_volume_weight = r'(\d+(?:\.\d+)?\s*(?:ml|l|g|kg))'
    matches = re.findall(pattern_volume_weight, name, re.IGNORECASE)
    for match in matches:
        specs.append(match.replace(' ', '').lower())
    
    # === 规格模式：数量单位 ===
    # 示例: 12片, 6包, 24支
    pattern_count = r'(\d+\s*(?:片|包|袋|支|枚|瓶|听|盒|卷|块|片装|袋装|支装))'
    matches = re.findall(pattern_count, name, re.IGNORECASE)
    for match in matches:
        specs.append(match.replace(' ', ''))
    
    # === 口味/变体关键词 ===
    flavor_keywords = [
        '原味', '草莓', '香草', '巧克力', '柠檬', '芒果', '蓝莓', '葡萄',
        '微辣', '中辣', '特辣', '麻辣', '香辣',
        '无糖', '低糖', '0糖', '零糖', '减糖',
        '家庭装', '分享装', '量贩', '迷你', 'mini', 'MINI',
        '大瓶', '中瓶', '小瓶', '大包', '中包', '小包',
        '大', '中', '小', '特大', '加大',
        '原味型', '清爽型', '浓郁型',
    ]
    
    for keyword in flavor_keywords:
        if keyword in name:
            specs.append(keyword)
    
    # 去重并保持顺序
    unique_specs = []
    seen = set()
    for spec in specs:
        if spec not in seen:
            unique_specs.append(spec)
            seen.add(spec)
    
    return ' '.join(unique_specs)


def _normalize_base_name(name: str) -> str:
    """
    标准化商品名称，移除规格信息生成基础名称
    
    参数:
        name: 商品名称
    
    返回:
        标准化后的基础名称 (如 "可口可乐")
    """
    if not isinstance(name, str) or not name.strip():
        return ''
    
    s = name.lower()
    
    # 1. 移除括号内容
    s = re.sub(r'[\(（\[][^\)）\]]*[\)）\]]', '', s)
    
    # 2. 移除数量×规格模式
    s = re.sub(r'\d+\s*[x×*]\s*\d+(?:\.\d+)?\s*(?:g|kg|ml|l|片|包|袋|支|枚|瓶|听|卷)?', '', s, flags=re.IGNORECASE)
    
    # 3. 移除容量/重量模式
    s = re.sub(r'\d+(?:\.\d+)?\s*(?:ml|l|g|kg)', '', s, flags=re.IGNORECASE)
    
    # 4. 移除数量单位模式
    s = re.sub(r'\d+\s*(?:片|包|袋|支|枚|瓶|听|盒|卷|块|片装|袋装|支装)', '', s)
    
    # 5. 移除口味/变体关键词
    variant_keywords = [
        '原味', '草莓', '香草', '巧克力', '柠檬', '芒果', '蓝莓', '葡萄',
        '微辣', '中辣', '特辣', '麻辣', '香辣',
        '无糖', '低糖', '0糖', '零糖', '减糖',
        '家庭装', '分享装', '量贩', '迷你', 'mini', 'MINI',
        '大瓶', '中瓶', '小瓶', '大包', '中包', '小包',
        '大', '中', '小', '特大', '加大',
        '原味型', '清爽型', '浓郁型',
    ]
    
    for keyword in variant_keywords:
        s = s.replace(keyword.lower(), '')
    
    # 6. 清理标点符号和多余空格
    s = re.sub(r'[^\u4e00-\u9fff0-9a-zA-Z]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    
    return s


def identify_multi_spec_products(df: pd.DataFrame, 
                                  product_name_col: str = 'product_name',
                                  spec_col: str = '规格名称',
                                  barcode_col: str = 'barcode',
                                  store_col: str = None) -> pd.DataFrame:
    """
    识别多规格商品（三信号检测机制）
    
    检测逻辑：
    - Signal 1: 规格列多值（最可靠）- 同一商品名下有多个不同规格值
    - Signal 2: 名称解析多值（智能推断）- 同一基础名称下有多个不同规格
    - Signal 3: 条码多值（兜底机制）- 同一基础名称下有多个不同条码
    
    参数:
        df: 原始商品DataFrame
        product_name_col: 商品名称列名
        spec_col: 规格列名（可选，如不存在则跳过Signal 1）
        barcode_col: 条码列名（可选，如不存在则跳过Signal 3）
        store_col: 门店列名（可选，支持多门店数据）
    
    返回:
        多规格商品DataFrame，包含以下列：
        - product_name: 原始商品名称
        - base_name: 标准化基础名称
        - 规格名称: 原始规格列（如存在）
        - inferred_spec: 从名称解析的规格
        - variant_key: 唯一规格标识（优先级：规格列 > inferred_spec > barcode）
        - 规格种类数: 该商品的规格变体数量
        - 多规格依据: 触发的信号源（规格列/名称解析/条码多值）
    """
    print("🔍 开始识别多规格商品...")
    
    # === Step 1: 数据预处理 ===
    work = df.copy()
    
    # 确保商品名称列存在
    if product_name_col not in work.columns:
        print(f"❌ 错误: 找不到商品名称列 '{product_name_col}'")
        return pd.DataFrame()
    
    # 标准化规格列（处理None、空字符串）
    if spec_col in work.columns:
        work[spec_col] = work[spec_col].where(~work[spec_col].isna(), None)
        work[spec_col] = work[spec_col].apply(lambda x: x.strip() if isinstance(x, str) else x)
        work.loc[work[spec_col] == '', spec_col] = None
    else:
        work[spec_col] = None
        print(f"  ⚠️ 未找到规格列 '{spec_col}'，跳过Signal 1")
    
    # === Step 2: 生成辅助列 ===
    print("  📝 生成辅助列...")
    work['inferred_spec'] = work[product_name_col].apply(_extract_inferred_spec)
    work['base_name'] = work[product_name_col].apply(_normalize_base_name)
    
    # === Step 3: 定义分组键（支持多门店）===
    has_store = store_col is not None and store_col in work.columns
    key_pn = [store_col, product_name_col] if has_store else [product_name_col]
    key_base = [store_col, 'base_name'] if has_store else ['base_name']
    
    if has_store:
        print(f"  🏪 检测到多门店数据，按 '{store_col}' 分组")
    
    # === Step 4: 三信号检测 ===
    print("  🎯 执行三信号检测...")
    
    # Signal 1: 规格列多值
    if spec_col in work.columns and work[spec_col].notna().any():
        sig1 = work.dropna(subset=[spec_col]).groupby(key_pn)[spec_col].nunique(dropna=True)
        sig1_keys = sig1[sig1 > 1].index
        print(f"     ✅ Signal 1 (规格列): {len(sig1_keys)} 个商品")
    else:
        sig1_keys = pd.Index([]) if not has_store else pd.MultiIndex.from_tuples([])
        print(f"     ⚠️ Signal 1 (规格列): 跳过")
    
    # Signal 2: 名称解析多值
    sig2 = work[work['inferred_spec'] != ''].groupby(key_base)['inferred_spec'].nunique()
    sig2_keys = sig2[sig2 > 1].index
    print(f"     ✅ Signal 2 (名称解析): {len(sig2_keys)} 个基础名称")
    
    # Signal 3: 条码多值
    if barcode_col in work.columns:
        tmp = work.copy()
        tmp[barcode_col] = tmp[barcode_col].astype(str)
        # 过滤掉空值和nan
        tmp = tmp[tmp[barcode_col].notna() & (tmp[barcode_col] != '') & (tmp[barcode_col] != 'nan')]
        if len(tmp) > 0:
            sig3 = tmp.groupby(key_base)[barcode_col].nunique()
            sig3_keys = sig3[sig3 > 1].index
            print(f"     ✅ Signal 3 (条码多值): {len(sig3_keys)} 个基础名称")
        else:
            sig3_keys = pd.Index([]) if not has_store else pd.MultiIndex.from_tuples([])
            print(f"     ⚠️ Signal 3 (条码多值): 无有效条码数据")
    else:
        sig3_keys = pd.Index([]) if not has_store else pd.MultiIndex.from_tuples([])
        print(f"     ⚠️ Signal 3 (条码多值): 跳过")
    
    # === Step 5: 合并信号源，收集所有多规格base_names ===
    print("  🔗 合并信号源...")
    
    def idx_to_df(keys, cols):
        """将Index/MultiIndex转换为DataFrame"""
        if len(keys) == 0:
            return pd.DataFrame(columns=cols)
        
        if isinstance(keys, pd.MultiIndex):
            df = keys.to_frame(index=False)
            df.columns = cols
            return df
        else:
            return pd.DataFrame({cols[0]: list(keys)})
    
    # 转换信号键为DataFrame
    key_pn_df = idx_to_df(sig1_keys, key_pn)
    key_base_df_2 = idx_to_df(sig2_keys, key_base)
    key_base_df_3 = idx_to_df(sig3_keys, key_base)
    
    # 收集所有多规格base_names
    all_multi_base_names = set()
    
    # 从Signal 1: product_name → base_name映射
    if not key_pn_df.empty:
        if has_store:
            pn_to_base_map = work.set_index([store_col, product_name_col])['base_name'].to_dict()
            for _, row in key_pn_df.iterrows():
                key = (row[store_col], row[product_name_col])
                if key in pn_to_base_map:
                    all_multi_base_names.add((row[store_col], pn_to_base_map[key]))
        else:
            pn_to_base_map = work.set_index(product_name_col)['base_name'].to_dict()
            for _, row in key_pn_df.iterrows():
                if row[product_name_col] in pn_to_base_map:
                    all_multi_base_names.add(pn_to_base_map[row[product_name_col]])
    
    # 从Signal 2: 直接使用base_name
    if not key_base_df_2.empty:
        for _, row in key_base_df_2.iterrows():
            if has_store:
                all_multi_base_names.add((row[store_col], row['base_name']))
            else:
                all_multi_base_names.add(row['base_name'])
    
    # 从Signal 3: 直接使用base_name
    if not key_base_df_3.empty:
        for _, row in key_base_df_3.iterrows():
            if has_store:
                all_multi_base_names.add((row[store_col], row['base_name']))
            else:
                all_multi_base_names.add(row['base_name'])
    
    print(f"  📊 合并后唯一多规格基础名称: {len(all_multi_base_names)} 个")
    
    # === Step 6: 向量化过滤（避免逐行循环）===
    if has_store:
        work['is_multi_spec'] = work.apply(
            lambda row: (row[store_col], row['base_name']) in all_multi_base_names,
            axis=1
        )
    else:
        work['is_multi_spec'] = work['base_name'].isin(all_multi_base_names)
    
    result = work[work['is_multi_spec']].copy()
    result = result.drop('is_multi_spec', axis=1)
    
    if result.empty:
        print("  ✅ 未识别到多规格商品")
        return pd.DataFrame()
    
    print(f"  ✅ 筛选后多规格SKU: {len(result)} 个")
    
    # === Step 7: 计算规格种类数 ===
    print("  🔢 计算规格种类数...")
    
    def _coalesce_variant(row):
        """优先级合并：规格列 > inferred_spec > barcode"""
        for c in [spec_col, 'inferred_spec', barcode_col]:
            if c not in row.index:
                continue
            v = row.get(c, None)
            if isinstance(v, str):
                v = v.strip()
            if v not in (None, '', 'nan') and not (isinstance(v, float) and np.isnan(v)):
                return v
        return None
    
    result['variant_key'] = result.apply(_coalesce_variant, axis=1)
    
    # 按base_name统计unique variant_keys
    if has_store:
        vk_cnt = result.dropna(subset=['variant_key']).groupby(
            [store_col, 'base_name']
        )['variant_key'].nunique().reset_index()
        vk_cnt.columns = [store_col, 'base_name', '规格种类数']
        result = result.merge(vk_cnt, on=[store_col, 'base_name'], how='left')
    else:
        vk_cnt = result.dropna(subset=['variant_key']).groupby(
            'base_name'
        )['variant_key'].nunique().reset_index()
        vk_cnt.columns = ['base_name', '规格种类数']
        result = result.merge(vk_cnt, on='base_name', how='left')
    
    # 填充缺失值（假设至少2个规格）
    result['规格种类数'] = result['规格种类数'].fillna(2).astype(int)
    
    # === Step 8: 标注信号源（多规格依据）===
    print("  🏷️ 标注触发信号源...")
    
    def get_trigger_for_row(row):
        """获取触发该行的信号源"""
        triggers = []
        
        if has_store:
            store_name = row[store_col]
            base_name = row['base_name']
            product_name = row[product_name_col]
            
            # 检查Signal 1
            if not key_pn_df.empty:
                match = key_pn_df[
                    (key_pn_df[store_col] == store_name) & 
                    (key_pn_df[product_name_col] == product_name)
                ]
                if not match.empty:
                    triggers.append('规格列')
            
            # 检查Signal 2
            if not key_base_df_2.empty:
                match = key_base_df_2[
                    (key_base_df_2[store_col] == store_name) & 
                    (key_base_df_2['base_name'] == base_name)
                ]
                if not match.empty:
                    triggers.append('名称解析')
            
            # 检查Signal 3
            if not key_base_df_3.empty:
                match = key_base_df_3[
                    (key_base_df_3[store_col] == store_name) & 
                    (key_base_df_3['base_name'] == base_name)
                ]
                if not match.empty:
                    triggers.append('条码多值')
        else:
            base_name = row['base_name']
            product_name = row[product_name_col]
            
            # 检查Signal 1
            if not key_pn_df.empty and product_name in key_pn_df[product_name_col].values:
                triggers.append('规格列')
            
            # 检查Signal 2
            if not key_base_df_2.empty and base_name in key_base_df_2['base_name'].values:
                triggers.append('名称解析')
            
            # 检查Signal 3
            if not key_base_df_3.empty and base_name in key_base_df_3['base_name'].values:
                triggers.append('条码多值')
        
        return ', '.join(triggers) if triggers else '未知'
    
    # 性能优化：大数据集使用批量标注
    if len(result) > 1000:
        result['多规格依据'] = '批量识别'
        print(f"     ⚠️ 数据集较大 ({len(result)} 行)，使用简化标注")
    else:
        result['多规格依据'] = result.apply(get_trigger_for_row, axis=1)
        print(f"     ✅ 完成逐行标注")
    
    # === 输出统计 ===
    print("\n" + "="*60)
    print("📋 【多规格识别结果统计】")
    print("="*60)
    print(f"多规格SKU总数: {len(result)}")
    print(f"唯一多规格商品数: {result['base_name'].nunique()}")
    print(f"平均规格种类数: {result['规格种类数'].mean():.1f}")
    print(f"最多规格商品: {result['规格种类数'].max()} 种")
    
    if '多规格依据' in result.columns and result['多规格依据'].iloc[0] != '批量识别':
        print("\n信号源分布:")
        for source, count in result['多规格依据'].value_counts().head(5).items():
            print(f"  - {source}: {count} 个SKU")
    
    return result


def analyze_competitor_multi_spec_from_original(excel_file: str, 
                                                 sheet_name: str = None,
                                                 product_name_col: str = '商品名称',
                                                 spec_col: str = '规格名称', 
                                                 barcode_col: str = '条码') -> pd.DataFrame:
    """
    从竞对原始数据中识别多规格商品
    
    参数:
        excel_file: 竞对原始数据Excel文件路径
        sheet_name: Sheet名称（默认读取第一个Sheet）
        product_name_col: 商品名称列名
        spec_col: 规格列名
        barcode_col: 条码列名
    
    返回:
        多规格商品详情DataFrame
    """
    print(f"\n{'='*60}")
    print(f"📂 读取竞对原始数据: {excel_file}")
    print(f"{'='*60}")
    
    try:
        if sheet_name:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
        else:
            df = pd.read_excel(excel_file)
        
        print(f"✅ 成功读取，共 {len(df)} 行数据")
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        return pd.DataFrame()
    
    # 调用主识别函数
    result = identify_multi_spec_products(
        df,
        product_name_col=product_name_col,
        spec_col=spec_col,
        barcode_col=barcode_col
    )
    
    return result


if __name__ == '__main__':
    """
    测试脚本：读取竞对原始数据并识别多规格商品
    """
    import sys
    from pathlib import Path
    
    # 默认路径
    upload_dir = Path('upload/竞对')
    
    if not upload_dir.exists():
        print(f"❌ 上传目录不存在: {upload_dir}")
        sys.exit(1)
    
    # 查找Excel文件
    excel_files = list(upload_dir.glob('*.xlsx'))
    
    if not excel_files:
        print(f"❌ 未找到Excel文件: {upload_dir}")
        sys.exit(1)
    
    print(f"找到 {len(excel_files)} 个Excel文件:")
    for i, f in enumerate(excel_files, 1):
        print(f"  {i}. {f.name}")
    
    # 使用第一个文件
    excel_file = excel_files[0]
    
    print(f"\n使用文件: {excel_file.name}")
    
    # 执行识别
    result = analyze_competitor_multi_spec_from_original(
        str(excel_file),
        product_name_col='商品名称',
        spec_col='规格名称',
        barcode_col='条码'
    )
    
    if not result.empty:
        # 保存结果
        output_file = Path('reports') / f'竞对多规格商品_{pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        output_file.parent.mkdir(exist_ok=True)
        
        # 按base_name分组统计
        summary = result.groupby('base_name').agg({
            'product_name': 'count',
            '规格种类数': 'first',
            '多规格依据': 'first'
        }).rename(columns={'product_name': 'SKU数'}).reset_index()
        summary = summary.rename(columns={'base_name': '商品基础名称'})
        summary = summary.sort_values('SKU数', ascending=False)
        
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            # Sheet 1: 汇总
            summary.to_excel(writer, sheet_name='多规格商品汇总', index=False)
            
            # Sheet 2: 详细列表
            result.to_excel(writer, sheet_name='多规格SKU详细', index=False)
        
        print(f"\n✅ 结果已保存: {output_file}")
        print(f"   - Sheet 1: 多规格商品汇总 ({len(summary)} 个商品)")
        print(f"   - Sheet 2: 多规格SKU详细 ({len(result)} 个SKU)")
    else:
        print("\n⚠️ 未识别到多规格商品")
