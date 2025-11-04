"""
下载额外的Base和Small模型
用于支持模型可选功能的3档模式
"""

import os
from sentence_transformers import SentenceTransformer, CrossEncoder

def download_models():
    """下载Base和Small模型"""
    
    models_to_download = [
        {
            'type': 'embedding',
            'name': 'BAAI/bge-base-zh-v1.5',
            'display': 'BGE-Base 嵌入模型',
            'size': '~400MB'
        },
        {
            'type': 'embedding',
            'name': 'BAAI/bge-small-zh-v1.5',
            'display': 'BGE-Small 嵌入模型',
            'size': '~200MB'
        },
        {
            'type': 'reranker',
            'name': 'BAAI/bge-reranker-base',
            'display': 'BGE-Reranker-Base 精排模型',
            'size': '~400MB'
        }
    ]
    
    print("="*70)
    print("📥 下载额外模型以支持3档模式选择")
    print("="*70)
    print("\n将下载以下模型:")
    for model in models_to_download:
        print(f"  • {model['display']} ({model['size']})")
    print(f"\n总大小: ~1GB")
    print("="*70)
    
    for i, model in enumerate(models_to_download, 1):
        print(f"\n[{i}/{len(models_to_download)}] 下载 {model['display']}...")
        print(f"模型ID: {model['name']}")
        
        try:
            if model['type'] == 'embedding':
                # 下载嵌入模型
                print("⏳ 正在下载嵌入模型...")
                model_obj = SentenceTransformer(model['name'])
                print(f"✅ 嵌入模型下载成功")
                
            elif model['type'] == 'reranker':
                # 下载精排模型
                print("⏳ 正在下载精排模型...")
                model_obj = CrossEncoder(model['name'])
                print(f"✅ 精排模型下载成功")
            
            # 显示缓存位置
            cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
            print(f"📁 缓存位置: {cache_dir}")
            
        except Exception as e:
            print(f"❌ 下载失败: {e}")
            print("请检查网络连接，或稍后重试")
            return False
    
    print("\n" + "="*70)
    print("✅ 所有模型下载完成！")
    print("="*70)
    print("\n现在可以在GUI中选择以下模式:")
    print("  • 高精度模式 (Large模型)")
    print("  • 平衡模式 (Base模型) ⭐ 推荐")
    print("  • 快速模式 (Small模型)")
    print("\n下次打包时这些模型会自动包含在内")
    
    return True

if __name__ == "__main__":
    # 检查是否有Large模型（之前应该已下载）
    print("检查现有模型...")
    try:
        from sentence_transformers import SentenceTransformer
        large_model = SentenceTransformer('BAAI/bge-large-zh-v1.5')
        print("✅ 检测到Large模型已存在")
    except:
        print("⚠️  未检测到Large模型，建议先运行一次比价分析下载Large模型")
    
    print()
    input("按回车键开始下载Base和Small模型...")
    
    success = download_models()
    
    if success:
        print("\n🎉 所有准备工作完成！")
    else:
        print("\n⚠️  部分模型下载失败，请检查错误信息")
    
    input("\n按回车键退出...")
