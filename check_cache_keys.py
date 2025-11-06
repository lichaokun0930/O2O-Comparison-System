"""检查缓存键格式，确认是否包含模型标识符"""
import joblib
from pathlib import Path

cache_file = Path('embedding_cache.joblib')
if cache_file.exists():
    cache = joblib.load(cache_file)
    print(f"缓存总键数: {len(cache)}")
    
    keys = list(cache.keys())
    if keys:
        print(f"\n前5个缓存键示例:")
        for i, key in enumerate(keys[:5], 1):
            print(f"{i}. {key[:80]}...")  # 只显示前80个字符
        
        # 分析键的组成
        print("\n分析键的格式:")
        sample_key = keys[0]
        print(f"键长度: {len(sample_key)}")
        print(f"是否为SHA256哈希: {len(sample_key) == 64 and all(c in '0123456789abcdef' for c in sample_key)}")
    else:
        print("缓存为空")
else:
    print("缓存文件不存在")

# 检查Cross-Encoder缓存
ce_cache_file = Path('cross_encoder_cache.joblib')
if ce_cache_file.exists():
    ce_cache = joblib.load(ce_cache_file)
    print(f"\n\nCross-Encoder缓存总键数: {len(ce_cache)}")
    
    ce_keys = list(ce_cache.keys())
    if ce_keys:
        print(f"\n前3个Cross-Encoder缓存键示例:")
        for i, key in enumerate(ce_keys[:3], 1):
            print(f"{i}. {key[:80]}...")
else:
    print("\n\nCross-Encoder缓存文件不存在")

# 检查相似度矩阵缓存
sim_cache_file = Path('similarity_matrix_cache.joblib')
if sim_cache_file.exists():
    sim_cache = joblib.load(sim_cache_file)
    print(f"\n\n相似度矩阵缓存总键数: {len(sim_cache)}")
    
    sim_keys = list(sim_cache.keys())
    if sim_keys:
        print(f"\n前3个相似度矩阵缓存键示例:")
        for i, key in enumerate(sim_keys[:3], 1):
            print(f"{i}. {key[:80]}...")
else:
    print("\n\n相似度矩阵缓存文件不存在")
