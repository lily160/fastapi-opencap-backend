# 1. 使用官方 Python 3.10 轻量级镜像作为基础镜像 (可根据你的实际 Python 版本修改)
FROM python:3.12-slim

# 2. 设置容器内的工作目录
WORKDIR /app

# 3. 设置环境变量：防止 Python 生成 .pyc 文件，并强制控制台无缓冲输出（方便查看日志）
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 4. 复制依赖清单到容器中
COPY requirements.txt .

# 5. 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 6. 将当前目录下的所有项目代码复制到容器的 /app 目录下
COPY . .

# 注意：这里没有写 CMD 指令。
# 因为你的 fastapi、celery-worker 和 celery-beat 将共用这个镜像，
# 它们的具体启动命令（如 uvicorn 或 celery -A...）应该在你的 docker-compose-celery.yml 中通过 `command:` 来分别指定。