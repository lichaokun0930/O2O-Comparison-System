"""
快速测试脚本 - 测试完整版多规格识别
"""
from pathlib import Path
import sys

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from multi_spec_identifier import analyze_competitor_multi_spec_from_original


def main():
    """测试完整版多规格识别"""
    print("="*70)
    print("🧪 测试完整版多规格识别功能")
    print("="*70)
    
    # 查找竞对原始数据
    upload_dir = Path('upload/竞对')
    
    if not upload_dir.exists():
        print(f"\n❌ 错误: 上传目录不存在")
        print(f"   请创建目录: {upload_dir}")
        print(f"   并将竞对Excel文件放入该目录")
        return False
    
    excel_files = list(upload_dir.glob('*.xlsx'))
    
    if not excel_files:
        print(f"\n❌ 错误: 未找到Excel文件")
        print(f"   目录: {upload_dir}")
        return False
    
    print(f"\n✅ 找到 {len(excel_files)} 个Excel文件:")
    for i, f in enumerate(excel_files, 1):
        print(f"   {i}. {f.name}")
    
    # 使用第一个文件
    excel_file = excel_files[0]
    print(f"\n📂 使用文件: {excel_file.name}")
    
    # 执行识别
    result = analyze_competitor_multi_spec_from_original(
        str(excel_file),
        product_name_col='商品名称',
        spec_col='规格名称',
        barcode_col='条码'
    )
    
    if result.empty:
        print("\n⚠️ 未识别到多规格商品")
        return False
    
    print(f"\n{'='*70}")
    print("✅ 测试成功！")
    print(f"{'='*70}")
    
    # 显示前5个示例
    print("\n📋 示例商品（前5个）:")
    print("-"*70)
    
    for i, (base_name, group) in enumerate(result.groupby('base_name'), 1):
        if i > 5:
            break
        
        spec_count = group['规格种类数'].iloc[0]
        sku_count = len(group)
        basis = group['多规格依据'].iloc[0]
        
        print(f"\n{i}. {base_name}")
        print(f"   规格种类: {spec_count} 种")
        print(f"   SKU数量: {sku_count} 个")
        print(f"   识别依据: {basis}")
        print(f"   商品示例:")
        
        for j, product_name in enumerate(group['product_name'].head(3), 1):
            print(f"      - {product_name}")
    
    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
