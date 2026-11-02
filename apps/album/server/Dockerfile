# 多架构支持：基础镜像 python:3.12-slim 同时提供 amd64 与 arm64 变体，
# psycopg2-binary / Pillow 等预编译轮子在两种架构上均有，无需源码编译。
# 默认在本机架构构建即可；如需一次产出两种架构并推送镜像仓库，见 scripts/build.sh（docker buildx）。
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
# 本应用无进程内单例状态（状态全部在数据库），多 worker 安全
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "--timeout", "60", "app:app"]
