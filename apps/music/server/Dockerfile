# 多架构支持：基础镜像 python:3.12-slim 同时提供 amd64 与 arm64 变体；
# 其下的 apt 包（cifs-utils/nfs-common/mpv/alsa-utils）与 Python 轮子（psycopg2-binary 等）
# 在两种架构上均有预编译版本，无需源码编译，故本镜像可在 ARM 与 amd64 上直接构建运行。
# 默认在本机架构构建即可；如需一次产出两种架构并推送镜像仓库，见仓库 scripts/build.sh（docker buildx）。
FROM python:3.12-slim

# 安装 NAS 挂载所需的客户端工具（SMB/CIFS 与 NFS），以及服务器端播放所需的 mpv + ALSA 工具
# 注意：容器内挂载需要 docker-compose 给 music-api 加 SYS_ADMIN 权限（见 docker-compose.yml）
# 服务器端出声需要 docker-compose 把宿主 /dev/snd 透传进容器（见 docker-compose.yml）
RUN apt-get update \
    && apt-get install -y --no-install-recommends cifs-utils nfs-common mpv alsa-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
# 单 worker：服务器端播放的 mpv 进程与状态是进程内单例，多 worker 会导致状态不一致
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "--timeout", "120", "app:app"]
