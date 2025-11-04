# 服务器部署文件夹

此文件夹包含将比价工具部署到 **阿里云/远程服务器**所需的文件。

## 📁 文件说明

### 部署脚本
- **deploy_to_aliyun.ps1** - 本地打包脚本（Windows）⭐
- **server_setup.sh** - 服务器一键部署脚本（Linux）⭐
- **start_public.ps1** - 公网访问启动脚本

### Docker 部署
- **Dockerfile** - Docker 镜像配置
- **requirements.txt** - Python 依赖列表

### 部署包
- **o2o_tool.zip** - 打包好的部署文件

### 文档
- **部署指南.md** - 通用部署指南（含 ngrok/云服务器/Docker）
- **阿里云部署指南.md** - 阿里云专用部署指南⭐
- **最终用户使用指南.md** - 给最终用户看的使用说明

## 🚀 快速部署（推荐流程）

### 步骤1：本地打包

在 Windows 环境执行：

```powershell
.\deploy_to_aliyun.ps1
```

**自动完成**：
- ✅ 收集所有必需文件
- ✅ 创建目录结构
- ✅ 压缩成 ZIP 包
- ✅ 显示上传命令

### 步骤2：上传到服务器

**方式A：VS Code Remote SSH（推荐）**
1. 连接到阿里云服务器
2. 拖拽 `o2o_tool_deploy_*.zip` 到 `/root/`
3. 解压：`unzip o2o_tool_deploy_*.zip -d o2o_tool`

**方式B：SCP 命令**
```powershell
scp o2o_tool_deploy_*.zip root@您的IP:/root/
```

### 步骤3：服务器端部署

SSH 连接到服务器后：

```bash
cd /root/o2o_tool
chmod +x server_setup.sh
sudo ./server_setup.sh
```

**自动完成**：
- ✅ 更新系统
- ✅ 安装 Python 3.11+
- ✅ 安装所有依赖（torch CPU 版本）
- ✅ 创建 systemd 服务
- ✅ 配置防火墙
- ✅ 启动服务
- ✅ 显示访问地址

### 步骤4：配置安全组

在阿里云控制台：
1. ECS → 安全组 → 配置规则
2. 添加入方向规则：端口 8555
3. 授权对象：`0.0.0.0/0`（所有人）或公司 IP

### 步骤5：访问测试

浏览器打开：
```
http://您的阿里云IP:8555
```

## 📚 其他部署方式

### 方式1：内网穿透（快速测试，5分钟）

```powershell
.\start_public.ps1
```

然后下载 ngrok/NATAPP，运行：
```bash
ngrok http 8555
```

获得公网地址：`http://abc123.ngrok.io`

### 方式2：Docker 部署（专业容器化）

```bash
docker build -t o2o-tool .
docker run -d -p 8555:8555 o2o-tool
```

## ⚙️ 服务管理命令

部署完成后，使用以下命令管理服务：

```bash
# 启动服务
sudo systemctl start o2o-tool

# 停止服务
sudo systemctl stop o2o-tool

# 重启服务
sudo systemctl restart o2o-tool

# 查看状态
sudo systemctl status o2o-tool

# 查看日志
journalctl -u o2o-tool -f

# 开机自启
sudo systemctl enable o2o-tool
```

## 🔧 配置要求

### 最低配置
- **CPU**: 2核
- **内存**: 4GB
- **硬盘**: 10GB
- **系统**: Ubuntu 20.04+

### 推荐配置
- **CPU**: 4核
- **内存**: 8GB
- **硬盘**: 20GB
- **系统**: Ubuntu 22.04

## 📖 详细文档

- **完整部署步骤**：查看 `部署指南.md`
- **阿里云专用指南**：查看 `阿里云部署指南.md`（**推荐**）
- **用户使用说明**：分享 `最终用户使用指南.md` 给用户

## 🌐 访问地址

部署成功后：
- **内网**: `http://内网IP:8555`
- **公网**: `http://公网IP:8555`
- **域名**（可选）: `http://o2o.yourdomain.com`

## 🔙 返回根目录

```powershell
cd ..
```
