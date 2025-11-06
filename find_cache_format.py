"""
简化版本：直接测试缓存中存储的模型标识符
"""
import joblib
import hashlib
from pathlib import Path

# 加载缓存
cache_file = Path('embedding_cache.joblib')
if not cache_file.exists():
    print("❌ 缓存文件不存在")
    exit(1)

cache = joblib.load(cache_file)
print(f"向量缓存总键数: {len(cache)}")

# 所有可能的模型标识符（替换后的版本）
possible_models = [
    "paraphrase-multilingual-mpnet-base-v2",  # 模型1（无斜杠，不会被替换）
    "BAAI_bge-base-zh-v1.5",  # 模型2
    "moka-ai_m3e-base",  # 模型3
    "BAAI_bge-large-zh-v1.5",  # 模型4
    "BAAI_bge-m3",  # 模型5
    "BAAI_bge-small-zh-v1.5",  # 模型6
]

# 从Excel中读取一些实际商品名称
import pandas as pd

excel_file = Path('upload/本店/淮安生态新城.xlsx')
if not excel_file.exists():
    print(f"❌ Excel文件不存在: {excel_file}")
    exit(1)

df = pd.read_excel(excel_file)

# 尝试复现预处理逻辑（clean_text）
def simple_clean(text):
    """简化版clean_text"""
    import re
    if pd.isna(text):
        return ""
    text = str(text).strip()
    # 移除特殊字符
    text = re.sub(r'[【】《》<>（）()[\]\\【\\】]', ' ', text)
    # 压缩空格
    text = ' '.join(text.split())
    return text

# 准备测试文本
sample_products = df['商品名称'].dropna().head(50).tolist()

# 尝试匹配
print("\n" + "=" * 80)
print("测试: 使用不同的文本格式和模型标识符")
print("=" * 80)

# 方案1: 只用商品名称
print("\n方案1: 仅商品名称")
for model_id in possible_models:
    hits = 0
    for product in sample_products[:10]:
        cache_text = f"{model_id}||{product}"
        cache_key = hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
        if cache_key in cache:
            hits += 1
    if hits > 0:
        print(f"✅ {model_id}: {hits}/10 命中")

# 方案2: 清洗后的商品名称
print("\n方案2: 清洗后的商品名称")
for model_id in possible_models:
    hits = 0
    for product in sample_products[:10]:
        cleaned = simple_clean(product)
        cache_text = f"{model_id}||{cleaned}"
        cache_key = hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
        if cache_key in cache:
            hits += 1
            if hits == 1:  # 只打印第一个匹配示例
                print(f"✅ {model_id}: 命中!")
                print(f"   示例商品: {product}")
                print(f"   清洗后: {cleaned}")
                print(f"   缓存键: {cache_key}")
    if hits > 1:
        print(f"   总命中: {hits}/10")

# 方案3: 商品名称 + 分类（使用正确的列名）
cat1_col = '美团一级分类' if '美团一级分类' in df.columns else '一级分类'
cat3_col = '美团三级分类' if '美团三级分类' in df.columns else '三级分类'

if cat1_col in df.columns and cat3_col in df.columns:
    print(f"\n方案3: 商品名称 + 分类 (列名: {cat1_col}, {cat3_col})")
    for model_id in possible_models:
        hits = 0
        for i in range(min(10, len(df))):
            product = df.iloc[i]['商品名称']
            cat1 = df.iloc[i].get(cat1_col, '')
            cat3 = df.iloc[i].get(cat3_col, '')
            
            cleaned_product = simple_clean(product)
            cleaned_cat1 = simple_clean(str(cat1))
            cleaned_cat3 = simple_clean(str(cat3))
            
            text = f"{cleaned_product} {cleaned_cat1} {cleaned_cat3}"
            cache_text = f"{model_id}||{text}"
            cache_key = hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
            
            if cache_key in cache:
                hits += 1
                if hits == 1:
                    print(f"✅ {model_id}: 命中!")
                    print(f"   示例商品: {product}")
                    print(f"   一级分类: {cat1}")
                    print(f"   三级分类: {cat3}")
                    print(f"   组合文本: {text}")
                    print(f"   缓存键: {cache_key}")
        if hits > 1:
            print(f"   总命中: {hits}/10")
else:
    print("\n⚠️ 方案3跳过: Excel中没有分类列")

print("\n" + "=" * 80)
print("总结")
print("=" * 80)
