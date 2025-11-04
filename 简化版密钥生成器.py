#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
O2O 比价工具 - 简化版密钥生成器
纯时间密钥，无硬件绑定

使用方法:
  python 简化版密钥生成器.py
"""

import hashlib
from datetime import datetime, timedelta

# 🔐 主密钥盐值（与主程序保持一致）
MASTER_SALT = "O2O_COMPARISON_TOOL_2025_SECRET_SALT_V1"

def generate_time_key(days: int) -> tuple[str, str]:
    """
    生成纯时间密钥（无硬件绑定）
    
    Args:
        days: 有效天数
    
    Returns:
        (密钥, 到期日期)
    """
    expire_date = datetime.now() + timedelta(days=days)
    expire_str = expire_date.strftime("%Y%m%d")
    
    # 简化版：不使用硬件指纹，只用日期
    raw_data = f"{expire_str}-{MASTER_SALT}"
    hash_obj = hashlib.sha256(raw_data.encode('utf-8'))
    license_key = hash_obj.hexdigest()[:12].upper()
    
    return license_key, expire_str

def main():
    print("=" * 65)
    print("  🔑 O2O比价工具 - 简化版密钥生成器（无硬件绑定）")
    print("=" * 65)
    print()
    print("📋 特点：")
    print("  - 纯时间密钥，任何电脑都可以用")
    print("  - 到期后自动失效")
    print("  - 无需用户提供硬件指纹")
    print()
    print("=" * 65)
    print()
    
    while True:
        print("━━━ 选择有效期 ━━━")
        print("  1. 30天  - 月度授权")
        print("  2. 90天  - 季度授权")
        print("  3. 180天 - 半年授权")
        print("  4. 365天 - 年度授权")
        print("  5. 自定义天数")
        print("  0. 退出")
        print()
        
        choice = input("请选择 [0-5]: ").strip()
        
        if choice == "0":
            print("\n✅ 退出")
            break
        elif choice == "1":
            days = 30
        elif choice == "2":
            days = 90
        elif choice == "3":
            days = 180
        elif choice == "4":
            days = 365
        elif choice == "5":
            try:
                days = int(input("\n请输入天数: ").strip())
                if days <= 0:
                    print("❌ 天数必须大于0")
                    continue
            except ValueError:
                print("❌ 无效输入")
                continue
        else:
            print("❌ 无效选择")
            continue
        
        # 生成密钥
        license_key, expire_str = generate_time_key(days)
        expire_date = datetime.strptime(expire_str, "%Y%m%d")
        
        print()
        print("=" * 65)
        print("  ✅ 密钥生成成功")
        print("=" * 65)
        print()
        print(f"  授权密钥: {license_key}")
        print(f"  有效期至: {expire_date.strftime('%Y年%m月%d日')} ({days}天)")
        print()
        print("=" * 65)
        print()
        print("📧 发送给用户:")
        print()
        print("─" * 65)
        print(f"授权密钥：{license_key}")
        print(f"有效期至：{expire_date.strftime('%Y年%m月%d日')}")
        print()
        print("使用方法：")
        print("  1. 启动 O2O比价工具")
        print(f"  2. 输入密钥：{license_key}")
        print("  3. 开始使用")
        print("─" * 65)
        print()
        
        # 保存到文件
        filename = f"license_{expire_str}.txt"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"O2O 比价工具 - 授权密钥\n\n")
                f.write(f"授权密钥: {license_key}\n")
                f.write(f"有效期至: {expire_date.strftime('%Y年%m月%d日')} ({days}天)\n")
                f.write(f"\n使用方法:\n")
                f.write(f"  1. 启动 O2O比价工具\n")
                f.write(f"  2. 输入密钥: {license_key}\n")
                f.write(f"  3. 开始使用\n")
            print(f"✅ 密钥信息已保存到: {filename}\n")
        except Exception as e:
            print(f"⚠️  保存文件失败: {e}\n")
        
        # 询问是否继续
        continue_choice = input("是否继续生成其他密钥？(y/n): ").strip().lower()
        if continue_choice != 'y':
            break
        print()
    
    print("\n✅ 完成！")

if __name__ == "__main__":
    main()
