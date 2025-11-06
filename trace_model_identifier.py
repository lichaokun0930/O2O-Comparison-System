"""
追踪程序实际使用的model_identifier

直接运行encode_batch函数，打印model_identifier
"""
import sys
import logging

logging.basicConfig(level=logging.INFO)

# 模拟导入主程序的Config
from product_comparison_tool_local import Config, CacheManager

# 创建缓存管理器实例
cache_manager = CacheManager()

print("=" * 80)
print("测试：追踪实际使用的model_identifier")
print("=" * 80)

# 模拟加载模型
print("\n1. 加载默认模型（模型1）...")
config = Config()
config.choose_model("1")  # 选择模型1

print(f"\n2. Config中的model_name: {config.model_name}")

# 模拟获取model_identifier（模仿Line 2687的逻辑）
model_name = config.model_name
model_identifier = model_name.replace('/', '_').replace('\\', '_')

print(f"3. 转换后的model_identifier: {model_identifier}")

# 生成测试缓存键
test_text = "可口可乐 饮料 碳酸饮料"
import hashlib
cache_text = f"{model_identifier}||{test_text}"
cache_key = hashlib.sha256(cache_text.encode('utf-8')).hexdigest()

print(f"\n4. 测试文本: {test_text}")
print(f"5. 缓存文本: {cache_text}")
print(f"6. 缓存键: {cache_key}")

# 检查是否在缓存中
import joblib
from pathlib import Path

cache_file = Path('embedding_cache.joblib')
if cache_file.exists():
    cache = joblib.load(cache_file)
    exists = cache_key in cache
    print(f"\n7. 是否在缓存中: {'✅ 是' if exists else '❌ 否'}")
    
    if not exists:
        print("\n提示: 这个键不在缓存中，可能原因:")
        print("   - 缓存是用其他模型生成的")
        print("   - 文本预处理不同（cleaned_商品名称）")
        print("   - model_identifier不同")
else:
    print("\n7. 缓存文件不存在")

print("\n" + "=" * 80)
print("尝试所有可用模型")
print("=" * 80)

# 测试所有模型
for i in range(1, 7):
    try:
        test_config = Config()
        test_config.choose_model(str(i))
        model_name = test_config.model_name
        model_id = model_name.replace('/', '_').replace('\\', '_')
        
        cache_text = f"{model_id}||{test_text}"
        cache_key = hashlib.sha256(cache_text.encode('utf-8')).hexdigest()
        
        if cache_file.exists():
            exists = cache_key in cache
            status = "✅" if exists else "❌"
        else:
            status = "?"
        
        print(f"\n模型 {i}: {model_name}")
        print(f"  标识符: {model_id}")
        print(f"  在缓存中: {status}")
        
    except Exception as e:
        print(f"\n模型 {i}: 加载失败 - {e}")
