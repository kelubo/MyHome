#!/usr/bin/env bash
# 多架构构建脚本：MyHome 的所有镜像均支持 ARM (aarch64) 与 amd64。
#
# 默认行为：在当前宿主机的架构上构建（docker compose build），开箱即用——
#   在 x86_64 机器上构建即产出 amd64 镜像；在树莓派/ARM NAS/Apple Silicon 上构建即产出 arm64 镜像。
#   官方基础镜像（python:3.12-slim / nginx:alpine / postgres:16-alpine）与 Python 轮子均为多架构，
#   无需任何额外处理。
#
# 跨平台一次性构建：若你想一次产出两种架构并推送到镜像仓库（供不同架构机器拉取同一个 tag），
#   使用 --push 指定仓库前缀。多架构镜像必须入库（manifest list）才能被 docker compose 拉取。
#
# 用法：
#   ./scripts/build.sh                         # 在当前架构构建（等同 docker compose build）
#   ./scripts/build.sh --push myregistry.com/myhome   # 构建 amd64+arm64 并推送
#   ./scripts/build.sh --platform linux/amd64,linux/arm64 --push ...

set -euo pipefail
cd "$(dirname "$0")/.."

PLATFORM="linux/amd64,linux/arm64"
REGISTRY=""
LOCAL_ONLY=1

usage() {
  echo "用法: $0 [--platform linux/amd64,linux/arm64] [--push <registry-prefix>]"
  echo "  (无参数)           在当前宿主架构上构建（docker compose build）"
  echo "  --push PREFIX      使用 buildx 跨平台构建并推送，PREFIX 形如 myregistry.com/myhome"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform) PLATFORM="$2"; shift 2;;
    --push)     REGISTRY="$2"; LOCAL_ONLY=0; shift 2;;
    -h|--help)  usage;;
    *)          echo "未知参数: $1"; usage;;
  esac
done

if [[ "$LOCAL_ONLY" -eq 1 ]]; then
  echo "🔧 在当前宿主架构上构建（docker compose build）"
  docker compose build
  echo "✅ 构建完成。运行: docker compose up -d"
  exit 0
fi

# ── 跨平台构建并推送（需 buildx + 可写镜像仓库）──
echo "🔧 使用 buildx 多架构构建 -> ${REGISTRY} (platforms=${PLATFORM})"
# 确保 buildx 构建器存在（支持 QEMU 模拟跨架构）
docker buildx create --name myhome-builder --use --bootstrap 2>/dev/null || docker buildx use myhome-builder

docker buildx build --platform "$PLATFORM" \
  -t "${REGISTRY}/myhome-music-api:latest" \
  ./apps/music/server \
  --push

echo "✅ 已推送多架构镜像 ${REGISTRY}/myhome-music-api:latest"
echo "   之后在 docker-compose.yml 里将 music-api 的 'build: ./apps/music/server' 改为："
echo "     image: ${REGISTRY}/myhome-music-api:latest"
echo "   即可让 ARM 与 amd64 主机拉取同一 tag 运行。"
