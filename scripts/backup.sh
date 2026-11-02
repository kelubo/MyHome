#!/usr/bin/env bash
# 一键备份家庭应用中心的数据（在仓库根目录下运行）
#   - 逻辑备份共享 PostgreSQL（pg_dumpall，最可靠）
#   - 打包 data/ 下所有应用的非数据库数据
# 恢复见 README「数据持久化与备份」一节。
set -e
cd "$(dirname "$0")/.."
mkdir -p backups
TS=$(date +%Y%m%d-%H%M%S)

# 若部署时已改密码，请先 export MYHOME_DB_PASSWORD=你的强密码，否则走无密码（默认口令）路径
DB_USER=myhome
pg_env=()
if [ -n "${MYHOME_DB_PASSWORD:-}" ]; then
  pg_env=(-e "PGPASSWORD=${MYHOME_DB_PASSWORD}")
fi

echo "[1/2] 逻辑备份 PostgreSQL（pg_dumpall）..."
docker compose exec -T "${pg_env[@]}" postgres pg_dumpall -U "$DB_USER" > "backups/db-${TS}.sql"
echo "       -> backups/db-${TS}.sql"

echo "[2/2] 打包 data/ 下所有应用数据（含 vault 的加密密钥 vault.key）..."
tar -czf "backups/data-${TS}.tar.gz" data/
echo "       -> backups/data-${TS}.tar.gz"

echo "备份完成：backups/db-${TS}.sql  +  backups/data-${TS}.tar.gz"
echo "⚠️  vault 的 data/vault/vault.key 已包含在 tar 包内；丢失该密钥将无法解密密码箱，请妥善保管备份。"
