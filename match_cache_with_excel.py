"""使用实际Excel数据反推model_identifier"""
import joblib
import hashlib
import pandas as pd
from pathlib import Path

# 加载缓存
cache_file = Path('embedding_cache.joblib')
if not cache_file.exists():
    print("❌ 缓存文件不存在")
    exit(1)

cache = joblib.load(cache_file)
print(f"向量缓存总键数: {len(cache)}")

# 尝试加载最近使用的Excel文件
excel_files = list(Path('upload/本店').glob('*.xlsx')) + list(Path('upload/竞对').glob('*.xlsx'))
if not excel_files:
    print("❌ 未找到Excel文件")
    exit(1)

excel_file = excel_files[0]
print(f"\n使用文件: {excel_file}")

try:
    df = pd.read_excel(excel_file)
    print(f"总行数: {len(df)}")
    
    # 假设预处理后的文本格式（根据代码Line 2691）
    # texts = (df['cleaned_商品名称'] + ' ' + df['cleaned_一级分类'] + ' ' + df['cleaned_三级分类'])
    
    # 尝试读取商品名称列
    possible_cols = ['商品名称', '商品', '名称', 'product_name', 'name']
    name_col = None
    for col in possible_cols:
        if col in df.columns:
            name_col = col
            break
    
    if name_col:
        print(f"商品名称列: {name_col}")
        sample_names = df[name_col].dropna().head(20).tolist()
        print(f"\n前20个商品名称:")
        for i, name in enumerate(sample_names[:10], 1):
            print(f"{i}. {name}")
    else:
        print("❌ 未找到商品名称列")
        print(f"可用列: {df.columns.tolist()}")
        exit(1)
    
    # 可能的model_identifier
    possible_identifiers = [
        "BAAI_bge-base-zh-v1.5",
        "moka-ai_m3e-base",
        "shibing624_text2vec-base-chinese",
        "BAAI_bge-large-zh-v1.5",
        "BAAI_bge-m3",
        "sentence-transformers_paraphrase-multilingual-mpnet-base-v2",
        "unknown",
    ]
    
    print("\n" + "=" * 80)
    print("尝试匹配缓存键")
    print("=" * 80)
    
    found = False
    for identifier in possible_identifiers:
        hits = 0
        for name in sample_names:
            # 只用商品名称
            cache_text = f"{identifier}||{name}"
            cache_key = hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
            if cache_key in cache:
                hits += 1
        
        if hits > 0:
            print(f"\n✅ 找到匹配: {identifier}")
            print(f"   命中数: {hits}/{len(sample_names)}")
            found = True
            
            # 显示匹配的详细信息
            print(f"\n   匹配的商品:")
            for i, name in enumerate(sample_names[:5], 1):
                cache_text = f"{identifier}||{name}"
                cache_key = hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
                status = "✅" if cache_key in cache else "❌"
                print(f"   {i}. {status} {name}")
            break
    
    if not found:
        print("\n❌ 未找到匹配")
        print("\n提示: 缓存键可能包含分类信息，或者使用了清洗后的文本")
        print("建议: 直接检查程序运行日志，查看实际使用的模型名称")

except Exception as e:
    print(f"❌ 读取Excel出错: {e}")
    import traceback
    traceback.print_exc()
