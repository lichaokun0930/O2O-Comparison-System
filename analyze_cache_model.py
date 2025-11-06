"""分析缓存中是否区分了不同模型"""
import joblib
import hashlib
from pathlib import Path

# 测试不同模型的同一文本是否生成不同的缓存键
test_text = "可口可乐500ml"

models = [
    "BAAI/bge-base-zh-v1.5",
    "moka-ai/m3e-base",
    "shibing624/text2vec-base-chinese"
]

print("=" * 80)
print("缓存键生成测试 - 不同模型相同文本")
print("=" * 80)

print(f"\n测试文本: {test_text}")
print("\n生成的缓存键:")

cache_keys = []
for i, model in enumerate(models, 1):
    cache_text = f"{model}||{test_text}"
    cache_key = hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
    cache_keys.append(cache_key)
    print(f"{i}. 模型: {model}")
    print(f"   缓存键: {cache_key}")
    print()

# 检查是否所有键都不同
if len(cache_keys) == len(set(cache_keys)):
    print("✅ 结论: 不同模型的相同文本会生成**不同的缓存键**")
    print("   → 理论上应该区分模型")
else:
    print("❌ 结论: 不同模型的相同文本生成**相同的缓存键**")
    print("   → 缓存会混用不同模型的结果")

print("\n" + "=" * 80)
print("检查实际缓存中的情况")
print("=" * 80)

# 检查实际缓存
cache_file = Path('embedding_cache.joblib')
if cache_file.exists():
    cache = joblib.load(cache_file)
    
    print(f"\n向量缓存总键数: {len(cache)}")
    
    # 尝试反向匹配：看看缓存键是否包含模型信息
    # 由于是哈希，我们无法直接解密，但可以测试是否命中
    
    print("\n测试: 检查缓存中是否存在上述测试键")
    for i, (model, key) in enumerate(zip(models, cache_keys), 1):
        exists = key in cache
        print(f"{i}. {model}: {'✅ 存在' if exists else '❌ 不存在'}")
    
    # 关键问题：检查程序实际使用的model_identifier
    print("\n" + "=" * 80)
    print("关键发现：检查程序代码中model_identifier的传递")
    print("=" * 80)
    
    print("\n需要检查:")
    print("1. Config类中的model_name是否正确传递到缓存系统")
    print("2. 缓存键生成时是否使用了实际的model_identifier")
    print("3. 向量编码时传递的model_identifier参数")
    
else:
    print("\n缓存文件不存在")

# 再进行一个关键测试：模拟不同的model_identifier
print("\n" + "=" * 80)
print("模拟测试：如果model_identifier为空或固定值")
print("=" * 80)

empty_model_key = hashlib.sha256(f"||{test_text}".encode('utf-8')).hexdigest()
print(f"\nmodel_identifier为空时的缓存键: {empty_model_key}")

fixed_model_key = hashlib.sha256(f"default||{test_text}".encode('utf-8')).hexdigest()
print(f"model_identifier为固定值'default'时的缓存键: {fixed_model_key}")

if cache_file.exists():
    print(f"\n是否在缓存中:")
    print(f"  空值键: {'✅ 存在' if empty_model_key in cache else '❌ 不存在'}")
    print(f"  固定值键: {'✅ 存在' if fixed_model_key in cache else '❌ 不存在'}")
