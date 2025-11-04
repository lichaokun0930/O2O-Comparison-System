"""
硬件指纹生成工具
用于生成当前机器的唯一标识，提交给管理员授权
"""
import hashlib
import platform
import subprocess
import uuid

def get_machine_fingerprint():
    """获取机器硬件指纹"""
    components = []
    
    # 1. CPU 信息
    try:
        if platform.system() == 'Windows':
            cmd = 'wmic cpu get ProcessorId'
            cpu_id = subprocess.check_output(cmd, shell=True).decode().split('\n')[1].strip()
        else:
            cpu_id = subprocess.check_output(['cat', '/proc/cpuinfo']).decode()
        components.append(cpu_id)
    except:
        pass
    
    # 2. 主板序列号
    try:
        if platform.system() == 'Windows':
            cmd = 'wmic baseboard get SerialNumber'
            board_sn = subprocess.check_output(cmd, shell=True).decode().split('\n')[1].strip()
        else:
            board_sn = subprocess.check_output(['dmidecode', '-s', 'baseboard-serial-number']).decode().strip()
        components.append(board_sn)
    except:
        pass
    
    # 3. MAC 地址（第一个网卡）
    try:
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                       for elements in range(0,2*6,2)][::-1])
        components.append(mac)
    except:
        pass
    
    # 4. 系统盘序列号
    try:
        if platform.system() == 'Windows':
            cmd = 'wmic diskdrive get SerialNumber'
            disk_sn = subprocess.check_output(cmd, shell=True).decode().split('\n')[1].strip()
            components.append(disk_sn)
    except:
        pass
    
    # 生成唯一哈希
    fingerprint_str = '|'.join(components)
    fingerprint = hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]
    
    return fingerprint, components

if __name__ == '__main__':
    print("=" * 60)
    print("  O2O 比价工具 - 硬件指纹生成器")
    print("=" * 60)
    print()
    
    fingerprint, components = get_machine_fingerprint()
    
    print("📋 机器信息：")
    print(f"   操作系统: {platform.system()} {platform.release()}")
    print(f"   计算机名: {platform.node()}")
    print(f"   用户名: {platform.os.getenv('USERNAME', 'Unknown')}")
    print()
    
    print("🔑 硬件指纹（请提供此代码给管理员）：")
    print()
    print(f"   {fingerprint}")
    print()
    print("=" * 60)
    
    # 写入文件方便复制
    with open('my_fingerprint.txt', 'w', encoding='utf-8') as f:
        f.write(f"硬件指纹: {fingerprint}\n")
        f.write(f"计算机名: {platform.node()}\n")
        f.write(f"生成时间: {platform.os.getenv('DATE', 'N/A')}\n")
        f.write(f"\n请将此指纹发送给管理员申请授权\n")
    
    print("✅ 指纹已保存到 my_fingerprint.txt")
    print()
    input("按回车键退出...")
