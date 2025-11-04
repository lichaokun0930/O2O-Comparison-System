"""
密钥生成助手 - 为管理员快速生成硬件绑定密钥配置（方案A优化版）

优化内容：
- 直接生成 JSON 格式配置，可追加到 authorized_keys.json
- 无需修改 Python 代码，无需重新打包
- 支持导出为 JSON 片段或完整 JSON 文件
"""
from datetime import datetime, timedelta
import json
import os

def generate_key_config():
    """交互式生成密钥配置"""
    print("\n" + "="*70)
    print("  🔑 密钥生成助手")
    print("="*70)
    print()
    
    # 获取用户硬件指纹
    print("📋 步骤1: 获取用户硬件指纹")
    print("   用户需要运行 generate_fingerprint.py 获取指纹")
    print()
    fingerprint = input("请输入用户的硬件指纹（16位）: ").strip()
    
    if not fingerprint:
        print("❌ 硬件指纹不能为空")
        return
    
    if len(fingerprint) != 16:
        print(f"⚠️  警告：指纹长度 {len(fingerprint)} 位（标准为16位）")
    
    # 生成密钥名称（建议包含指纹前缀）
    print()
    print("📋 步骤2: 生成密钥名称")
    print(f"   建议格式: DEMO-{fingerprint[:8]}")
    print()
    key_name_suggestion = f"DEMO-{fingerprint[:8]}"
    key_name = input(f"请输入密钥名称（回车使用默认）[{key_name_suggestion}]: ").strip()
    
    if not key_name:
        key_name = key_name_suggestion
    
    # 设置有效期
    print()
    print("📋 步骤3: 设置有效期")
    print("   1. 30天（试用）")
    print("   2. 90天（季度）")
    print("   3. 365天（年度）")
    print("   4. 自定义")
    print()
    
    expire_choice = input("请选择有效期 [1-4]: ").strip()
    
    if expire_choice == "1":
        days = 30
    elif expire_choice == "2":
        days = 90
    elif expire_choice == "3":
        days = 365
    elif expire_choice == "4":
        try:
            days = int(input("请输入天数: "))
        except:
            print("❌ 输入无效，使用默认30天")
            days = 30
    else:
        days = 30
    
    expire_date = datetime.now() + timedelta(days=days)
    expire_str = expire_date.strftime("%Y%m%d")
    
    # 是否绑定硬件
    print()
    print("📋 步骤4: 硬件绑定设置")
    print("   1. 绑定硬件（推荐，防止分发）")
    print("   2. 不绑定（通用密钥，可以分发）")
    print()
    
    bind_choice = input("请选择 [1-2，默认1]: ").strip()
    bind_hardware = bind_choice != "2"
    
    # 生成配置代码
    print()
    print("="*70)
    print("  ✅ 密钥配置已生成")
    print("="*70)
    print()
    print("📄 方案A优化：直接追加到 authorized_keys.json")
    print()
    print("-" * 70)
    
    # 构建 JSON 配置
    key_config = {
        key_name: {
            "expire": expire_str,
            "fingerprint": fingerprint if bind_hardware else None,
            "note": f"{'硬件绑定' if bind_hardware else '通用密钥'} - 有效期{days}天 - 生成于{datetime.now().strftime('%Y-%m-%d')}"
        }
    }
    
    # 显示 JSON 格式配置
    json_config = json.dumps(key_config, indent=2, ensure_ascii=False)
    print(json_config)
    print("-" * 70)
    print()
    
    # 尝试自动追加到 authorized_keys.json
    json_file = "authorized_keys.json"
    if os.path.exists(json_file):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                existing_keys = json.load(f)
            
            # 追加新密钥
            existing_keys.update(key_config)
            
            # 保存回文件
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(existing_keys, f, indent=2, ensure_ascii=False)
            
            print(f"✅ 已自动追加到 {json_file}")
            print(f"   当前共有 {len(existing_keys)} 个密钥")
            print()
        except Exception as e:
            print(f"⚠️  自动追加失败: {e}")
            print(f"   请手动将上述 JSON 配置添加到 {json_file}")
            print()
    else:
        print(f"⚠️  未找到 {json_file}，将创建新文件")
        try:
            # 创建新的 JSON 文件
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(key_config, f, indent=2, ensure_ascii=False)
            print(f"✅ 已创建 {json_file} 并添加密钥")
            print()
        except Exception as e:
            print(f"❌ 创建文件失败: {e}")
            print()
    
    # 生成用户通知模板
    print("📧 发送给用户的通知：")
    print()
    print("-" * 70)
    print(f"您的授权密钥已生成：")
    print()
    print(f"  密钥: {key_name}")
    print(f"  有效期: {expire_date.strftime('%Y年%m月%d日')} ({days}天)")
    if bind_hardware:
        print(f"  绑定设备: {fingerprint[:8]}****（仅限您的电脑使用）")
    else:
        print(f"  通用密钥（可在任意电脑使用）")
    print()
    print(f"使用方法：")
    print(f"  1. 启动 O2O_Comparison_Tool.exe")
    print(f"  2. 输入密钥: {key_name}")
    print(f"  3. 开始使用")
    print()
    if bind_hardware:
        print(f"注意：此密钥仅限您的电脑使用，无法在其他设备上运行。")
    print("-" * 70)
    print()
    
    # 保存配置到文件
    try:
        with open(f"key_config_{key_name}.txt", "w", encoding="utf-8") as f:
            f.write("=== 密钥配置（方案A - JSON格式）===\n\n")
            f.write("已自动追加到 authorized_keys.json：\n\n")
            f.write(json_config + "\n\n")
            f.write("=== 用户通知 ===\n\n")
            f.write(f"密钥: {key_name}\n")
            f.write(f"有效期: {expire_date.strftime('%Y年%m月%d日')} ({days}天)\n")
            f.write(f"硬件绑定: {'是' if bind_hardware else '否'}\n")
            if bind_hardware:
                f.write(f"硬件指纹: {fingerprint}\n")
        
        print(f"✅ 配置已保存到: key_config_{key_name}.txt")
    except Exception as e:
        print(f"⚠️  保存文件失败: {e}")
    
    print()
    print("🔄 是否继续生成其他密钥？")

if __name__ == '__main__':
    print("\n🎯 密钥生成助手（方案A优化版）- 自动更新 authorized_keys.json")
    print("   优势：无需修改代码，无需重新打包！")
    
    while True:
        generate_key_config()
        
        choice = input("\n是否继续生成？(y/n): ").strip().lower()
        if choice != 'y':
            break
    
    print("\n✅ 完成！方案A优化流程：")
    print("  1. ✅ 密钥已自动追加到 authorized_keys.json")
    print("  2. 📤 发送 authorized_keys.json 给用户（覆盖程序目录中的同名文件）")
    print("  3. ⚡ 用户重启程序即可使用新密钥（无需重新打包）")
    print()
    print("📋 或者首次打包时：")
    print("  1. 运行 .\\打包完整版_优化.ps1 （会自动包含 authorized_keys.json）")
    print("  2. 发送整个程序包给用户")
    print()
