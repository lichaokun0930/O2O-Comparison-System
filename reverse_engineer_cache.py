"""反向推断缓存中实际使用的model_identifier"""
import joblib
import hashlib
from pathlib import Path

# 已知商品文本样本（从之前的测试数据中）
sample_texts = [
    "可口可乐 饮料 碳酸饮料",
    "百事可乐 饮料 碳酸饮料",
    "雪碧 饮料 碳酸饮料",
]

# 可能的model_identifier（根据代码逻辑推断）
possible_identifiers = [
    # 原始模型名称
    "BAAI/bge-base-zh-v1.5",
    "moka-ai/m3e-base",
    "shibing624/text2vec-base-chinese",
    "BAAI/bge-large-zh-v1.5",
    "BAAI/bge-m3",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    
    # 替换后的标识符（代码Line 2687: model_name.replace('/', '_').replace('\\', '_')）
    "BAAI_bge-base-zh-v1.5",
    "moka-ai_m3e-base",
    "shibing624_text2vec-base-chinese",
    "BAAI_bge-large-zh-v1.5",
    "BAAI_bge-m3",
    "sentence-transformers_paraphrase-multilingual-mpnet-base-v2",
    
    # 可能的默认值
    "unknown",
    "",
    "default",
]

# 加载缓存
cache_file = Path('embedding_cache.joblib')
if not cache_file.exists():
    print("❌ 缓存文件不存在")
    exit(1)

cache = joblib.load(cache_file)
print(f"向量缓存总键数: {len(cache)}")
print("\n" + "=" * 80)
print("反向推断实际使用的model_identifier")
print("=" * 80)

# 方法：尝试所有可能的identifier，看哪个能命中缓存
found_identifiers = set()

for identifier in possible_identifiers:
    hits = 0
    for text in sample_texts:
        cache_text = f"{identifier}||{text}"
        cache_key = hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
        if cache_key in cache:
            hits += 1
    
    if hits > 0:
        print(f"\n✅ 找到匹配: {identifier}")
        print(f"   命中率: {hits}/{len(sample_texts)}")
        found_identifiers.add(identifier)

if not found_identifiers:
    print("\n❌ 未找到匹配的model_identifier")
    print("\n可能原因:")
    print("1. 样本文本不在缓存中")
    print("2. model_identifier是其他值")
    print("3. 缓存键生成逻辑不同")
    
    # 尝试从缓存中随机取一个键，看看能否反推
    print("\n" + "=" * 80)
    print("尝试从缓存中随机取样分析")
    print("=" * 80)
    
    sample_keys = list(cache.keys())[:10]
    print(f"\n随机10个缓存键:")
    for i, key in enumerate(sample_keys, 1):
        print(f"{i}. {key}")
    
    # 尝试暴力匹配一些常见的商品名
    common_products = [
        "可口可乐",
        "百事可乐",
        "农夫山泉",
        "怡宝",
        "康师傅",
        "统一",
        "雪碧",
        "芬达",
    ]
    
    print("\n尝试匹配常见商品名（不带分类）:")
    for identifier in possible_identifiers:
        for product in common_products:
            cache_text = f"{identifier}||{product}"
            cache_key = hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
            if cache_key in cache:
                print(f"✅ 匹配: identifier={identifier}, text={product}")
                found_identifiers.add(identifier)
                break
        if found_identifiers:
            break

else:
    print("\n" + "=" * 80)
    print("结论")
    print("=" * 80)
    print(f"\n实际使用的model_identifier: {', '.join(found_identifiers)}")
    
    if len(found_identifiers) == 1:
        print("\n✅ 所有缓存使用同一个model_identifier")
        print("   → 这就是为什么不同模型会得到相同结果的原因！")
    else:
        print("\n⚠️ 缓存中混用了多个model_identifier")
        print("   → 这是正常的，说明您曾经使用过多个模型")
