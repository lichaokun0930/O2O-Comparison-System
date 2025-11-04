# 使用 Python 3.11 官方镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY requirements.txt .
COPY *.py .
COPY .streamlit/ .streamlit/

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装 PyTorch CPU 版本
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# 暴露端口
EXPOSE 8555

# 设置环境变量（强制 CPU 模式）
ENV CUDA_VISIBLE_DEVICES=""
ENV USE_TORCH_SIM="0"
ENV ENCODE_BATCH_SIZE="32"

# 启动命令
CMD ["streamlit", "run", "comparison_app.py", "--server.port=8555", "--server.address=0.0.0.0"]
