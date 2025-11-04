#!/bin/bash
# O2O 比价工具 - 阿里云服务器一键部署脚本
# 使用方法：./server_setup.sh

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 打印函数
print_header() {
    echo -e "${CYAN}========================================"
    echo -e "  $1"
    echo -e "========================================${NC}"
}

print_step() {
    echo -e "${YELLOW}[$1] $2${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# 开始部署
clear
print_header "O2O 比价工具 - 服务器自动部署"
echo ""

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then 
    print_error "请使用 root 用户运行此脚本"
    echo "使用方法: sudo ./server_setup.sh"
    exit 1
fi

# 获取项目目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo -e "${CYAN}项目目录: ${SCRIPT_DIR}${NC}"
echo ""

# 步骤1: 更新系统
print_step "1/8" "更新系统包..."
apt update -qq && apt upgrade -y -qq
print_success "系统更新完成"

# 步骤2: 安装 Python
print_step "2/8" "检查 Python 版本..."
if command -v python3.11 &> /dev/null; then
    PYTHON_VERSION=$(python3.11 --version)
    print_success "已安装 $PYTHON_VERSION"
else
    print_info "安装 Python 3.11..."
    apt install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt update -qq
    apt install -y python3.11 python3.11-dev python3.11-venv
    print_success "Python 3.11 安装完成"
fi

# 安装 pip
if ! command -v pip3 &> /dev/null; then
    print_info "安装 pip..."
    apt install -y python3-pip
fi

# 步骤3: 安装系统依赖
print_step "3/8" "安装系统依赖..."
apt install -y build-essential libssl-dev libffi-dev unzip curl wget
print_success "系统依赖安装完成"

# 步骤4: 安装 Python 依赖
print_step "4/8" "安装 Python 依赖（使用清华源加速）..."
cd "$SCRIPT_DIR"

if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
else
    # 手动安装核心依赖
    print_info "requirements.txt 不存在，手动安装核心依赖..."
    pip3 install streamlit pandas numpy openpyxl jieba tqdm -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
    pip3 install torch --index-url https://download.pytorch.org/whl/cpu --quiet
    pip3 install sentence-transformers -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
fi

print_success "Python 依赖安装完成"

# 步骤5: 验证依赖
print_step "5/8" "验证依赖安装..."
python3 -c "import streamlit, torch, sentence_transformers, pandas, numpy" 2>/dev/null
if [ $? -eq 0 ]; then
    print_success "所有依赖验证通过"
else
    print_error "依赖验证失败，请检查安装日志"
    exit 1
fi

# 步骤6: 创建目录结构
print_step "6/8" "创建目录结构..."
mkdir -p "$SCRIPT_DIR/upload/本店"
mkdir -p "$SCRIPT_DIR/upload/竞对"
mkdir -p "$SCRIPT_DIR/reports"
mkdir -p "$SCRIPT_DIR/.streamlit"
print_success "目录结构创建完成"

# 检查配置文件
if [ ! -f "$SCRIPT_DIR/.streamlit/config.toml" ]; then
    print_info "创建 Streamlit 配置文件..."
    cat > "$SCRIPT_DIR/.streamlit/config.toml" << 'EOF'
[server]
address = "0.0.0.0"
port = 8555
headless = true
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false
EOF
    print_success "配置文件创建完成"
fi

# 步骤7: 配置 systemd 服务
print_step "7/8" "配置系统服务..."

PYTHON_BIN=$(which python3)
SERVICE_FILE="/etc/systemd/system/o2o-tool.service"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=O2O Comparison Tool - Streamlit
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${SCRIPT_DIR}
Environment="CUDA_VISIBLE_DEVICES="
Environment="USE_TORCH_SIM=0"
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecStart=${PYTHON_BIN} -m streamlit run comparison_app.py --server.port 8555 --server.address 0.0.0.0
Restart=always
RestartSec=10
StandardOutput=append:${SCRIPT_DIR}/streamlit.log
StandardError=append:${SCRIPT_DIR}/streamlit_error.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable o2o-tool
print_success "系统服务配置完成"

# 步骤8: 配置防火墙
print_step "8/8" "配置防火墙..."
if command -v ufw &> /dev/null; then
    ufw allow 8555/tcp
    print_success "UFW 防火墙规则已添加"
elif command -v firewall-cmd &> /dev/null; then
    firewall-cmd --permanent --add-port=8555/tcp
    firewall-cmd --reload
    print_success "firewalld 防火墙规则已添加"
else
    print_info "未检测到防火墙，请手动配置阿里云安全组"
fi

# 部署完成
echo ""
print_header "✅ 部署完成！"
echo ""

# 显示服务器信息
PUBLIC_IP=$(curl -s ifconfig.me)
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}服务器信息:${NC}"
echo -e "${CYAN}  公网 IP: ${PUBLIC_IP}${NC}"
echo -e "${CYAN}  内网 IP: ${LOCAL_IP}${NC}"
echo -e "${CYAN}  端口: 8555${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 启动服务
print_info "启动服务中..."
systemctl start o2o-tool
sleep 3

# 检查服务状态
if systemctl is-active --quiet o2o-tool; then
    print_success "服务启动成功！"
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}访问地址:${NC}"
    echo -e "${CYAN}  公网: http://${PUBLIC_IP}:8555${NC}"
    echo -e "${CYAN}  内网: http://${LOCAL_IP}:8555${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    print_error "服务启动失败！"
    echo ""
    echo "查看错误日志:"
    echo "  journalctl -u o2o-tool -n 50"
    exit 1
fi

echo ""
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}常用命令:${NC}"
echo -e "${YELLOW}========================================${NC}"
echo -e "启动服务: ${CYAN}systemctl start o2o-tool${NC}"
echo -e "停止服务: ${CYAN}systemctl stop o2o-tool${NC}"
echo -e "重启服务: ${CYAN}systemctl restart o2o-tool${NC}"
echo -e "查看状态: ${CYAN}systemctl status o2o-tool${NC}"
echo -e "查看日志: ${CYAN}journalctl -u o2o-tool -f${NC}"
echo -e "查看错误: ${CYAN}tail -f ${SCRIPT_DIR}/streamlit_error.log${NC}"
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}⚠️  重要提示:${NC}"
echo -e "${BLUE}========================================${NC}"
echo "1. 请在阿里云控制台开放安全组 8555 端口"
echo "2. 建议绑定域名以获得更好的使用体验"
echo "3. 如需 HTTPS，请安装并配置 nginx + certbot"
echo "4. 定期备份数据和日志文件"
echo ""

print_success "部署脚本执行完成！"
echo ""
