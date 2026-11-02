# MyHome 家庭应用中心 · 部署与运维指南

> 本仓库是一个**家庭应用中心**总枢纽：门户仪表盘（`portal/`）+ 19 个应用（`apps/<name>/`）+ nginx 路径路由 + 共享 PostgreSQL + docker-compose 一键编排。
> 本文档覆盖：环境要求、快速开始、改强密码、数据持久化、备份、恢复、外部访问安全、更新、日常运维、故障排查、应用清单。

---

## 1. 环境要求

- 一台 **Linux 主机**（x86_64 或 ARM/aarch64 均可：树莓派、ARM NAS、Apple Silicon 都支持）。
- 已安装 **Docker Engine + Docker Compose v2**（命令是 `docker compose`，不是旧版 `docker-compose`）。
- 端口占用：
  - 宿主 **8080** → 容器 80：门户与反向代理统一入口（所有应用都走这里）。
  - 宿主 **5432** → 容器 5432：**PostgreSQL**，仅供内网/本机使用，切勿对公网开放。
- 磁盘：预留约 2 GB（镜像 + 初始数据）。

---

## 2. 快速开始

```bash
git clone <你的仓库地址> MyHome
cd MyHome
docker compose up -d --build
```

- 首次构建会编译 **18 个后端镜像 + portal + nginx**，第一次较慢（几分钟到十几分钟，取决于机器与网络）。
- 构建完成后，`postgres-init` 脚本会自动建库；各 api 首次启动写入示例数据。
- 等待约 10~30 秒让数据库就绪，然后浏览器访问 `http://<主机IP>:8080/`。
- 门户应显示 **19 个应用卡片**，点进去即可使用。

> 所有应用都依赖后端 API（除 `home` 是纯静态）。直接双击打开某个 `index.html` 会因连不上后端而在页面顶部报错——**必须走 `docker compose` 集成模式**。

---

## 3. 改强密码（务必做）

数据库口令已抽离到仓库根目录的 **`.env`** 文件（已被 `.gitignore` 忽略，**绝不进 git**），`docker-compose.yml` 通过 `${POSTGRES_PASSWORD}` 引用它。默认口令仅用于本地测试，任何真实部署请改为强密码：

- `.env` 内容示例：
  ```ini
  POSTGRES_USER=myhome
  POSTGRES_PASSWORD=你的强密码
  POSTGRES_DB=postgres
  ```
- `docker-compose.yml` 中所有口令均走 `${POSTGRES_PASSWORD}`（**共 29 处**：1 处 `postgres` 服务的 `POSTGRES_PASSWORD` + 28 处各 `*-api` 服务的 `DATABASE_URL`，格式 `postgresql://myhome:${POSTGRES_PASSWORD}@postgres:5432/<app>`），docker compose 自动读取 `.env` 完成替换。
- **改密码只需改 `.env` 一处**：把 `POSTGRES_PASSWORD` 改为你的强密码，再 `docker compose up -d` 让 postgres 与所有 api 用新密码重连。**务必保证 postgres 与各 api 的口令一致**，否则 api 连不上库。
- 改密码属于破坏性变更，建议**先备份**再改（见第 5 节）。

---

## 4. 数据持久化

所有运行时数据集中在仓库 `./data/`（不进 git，需自行备份）：

```
data/
├── postgres/   # 共享 PostgreSQL 实例的全部数据（19 个应用的库都在这里）
├── music/      # 本地音乐默认存放处（容器 /music/local）
├── wiki/       # 家用手册附件（容器 /data/wiki）
├── album/      # 家庭相册（原图 photos/ + 缩略图 thumbs/，容器 /data/album）
├── docs/       # 家庭文档归档（容器 /data/docs）
├── vault/      # ⚠️ 家庭密码箱：含加密密钥 vault.key（容器 /data/vault）
└── <app>/      # 其余仅用数据库的应用无文件卷
```

`data/` 与 `backups/` 已被 `.gitignore` 忽略。

---

## 5. 备份（一键）

```bash
bash scripts/backup.sh
# 产出：
#   backups/db-<时间戳>.sql        数据库逻辑备份（pg_dumpall，最可靠）
#   backups/data-<时间戳>.tar.gz   data/ 下所有应用数据（含 vault.key）
```

- 建议加入 crontab 每日凌晨执行，并保留最近 N 份：
  ```bash
  # 每天 03:10 备份；保留最近 14 天（find 清理）
  10 3 * * *  cd /path/to/MyHome && bash scripts/backup.sh && find backups -name '*.tar.gz' -mtime +14 -delete
  ```
- ⚠️ **vault 的 `data/vault/vault.key` 是解密唯一凭证**，备份一定要包含它；丢失则密码箱数据无法解密。

---

## 6. 恢复

两种恢复方式，可按需选择或组合：

**A. 整盘恢复（最快，推荐用于整机迁移/回滚）**
```bash
docker compose down
tar -xzf backups/data-<时间戳>.tar.gz -C .
docker compose up -d
```
> 这会整体覆盖 `./data/`（含 postgres 数据目录与各应用数据）。

**B. 仅数据库恢复（用逻辑备份）**
```bash
docker compose up -d postgres
cat backups/db-<时间戳>.sql \
  | docker compose exec -T -e PGPASSWORD="$MYHOME_DB_PASSWORD" postgres psql -U myhome -d postgres
```
- 若你**没改过密码**，把上面的 `PGPASSWORD="$MYHOME_DB_PASSWORD"` 去掉即可（默认口令）。
- B 会按备份重建所有库与表，覆盖现有数据；只恢复单库时先 `DROP DATABASE <app>` 再导入对应片段。

---

## 7. 外部 / 公网访问（安全）

- 内网访问直接用 `http://<IP>:8080`（确保 8080 在家庭网络可达）。
- **如需从外网访问，务必套一层 HTTPS 反向代理**（Caddy / Nginx Proxy Manager / Traefik 均可），并启用认证（Basic Auth、客户端证书，或前置一个 SSO）。
- 🔒 **强烈建议：家庭密码箱（vault）不要暴露在公网**；即便内网也只在受信任设备访问。vault 页面本身也带安全提示。
- 防火墙：**5432（PostgreSQL）只对内网开放**，不要对公网放行。

---

## 8. 更新应用

```bash
git pull
docker compose up -d --build     # 重新构建变更过的服务镜像并重启
```
- 数据在 `./data/`，更新不会丢失。
- 即便只改了前端静态文件，`--build` 也最稳妥（portal/nginx 镜像会重新打包静态资源）。

---

## 9. 日常运维命令

| 目的 | 命令 |
|------|------|
| 看所有服务状态 | `docker compose ps` |
| 看某服务日志 | `docker compose logs -f <service>`（如 `vault-api`、`postgres`） |
| 重启单服务 | `docker compose restart <service>` |
| 进数据库交互 | `docker compose exec postgres psql -U myhome` |
| 停止（保留数据） | `docker compose down` |
| 彻底清盘（**含数据！**） | `docker compose down -v` |

---

## 10. 故障排查

- **门户打不开 / 应用提示连不上 API**：多半是 postgres 未就绪或某 api 崩溃。看 `docker compose logs postgres` 与 `docker compose logs <app>-api`；确认 `docker compose ps` 中相关服务为 `running`。
- **首次建库失败**：`postgres-init/01-create-dbs.sql` 用条件写法（`SELECT 'CREATE DATABASE ...'` + `\gexec`），可重复执行、库已存在会跳过。改过密码后须保证 `DATABASE_URL` 与 `POSTGRES_PASSWORD` 一致。
- **音乐播放器服务器出声无设备**：compose 给 `music-api` 透传了 `/dev/snd`；无音频设备时会报错，可删除该 `devices` 行（仅用"此设备"播放即可）。
- **上传大文件失败（docs/album）**：nginx 已设 `client_max_body_size 200m`；仍失败检查磁盘空间与文件类型白名单/大小上限（docs 50MB、album 100MB）。
- **vault 页面红色告警**：本机没装 `cryptography` 库，已退化为 base64 混淆（仅调试用）。生产环境镜像内已含该依赖，告警即消失。
- **改密码后旧备份/旧容器不兼容**：改密码是破坏性变更，建议先 `bash scripts/backup.sh` 再改；改完 `docker compose up -d` 让 postgres 与所有 api 用新密码重连。

---

## 11. 应用清单与路径

| 应用 | 路径 | 数据库 | 备注 |
|------|------|--------|------|
| 家庭主页 | `/` | — | 纯静态门户/信息中心 |
| 音乐播放器 | `/apps/music/` | music | 网络电台 + 本地/NAS 音乐库 + 收藏 |
| 家用手册 Wiki | `/apps/wiki/` | wiki | 纯文本知识库，支持附件 |
| 家庭相册 | `/apps/album/` | album | 照片/相册，EXIF 自动读取 |
| 纪念日/日历 | `/apps/calendar/` | calendar | 倒计时 |
| 车辆保养 | `/apps/carlog/` | carlog | 保养记录 |
| 购物/冰箱 | `/apps/pantry/` | pantry | 购物清单 + 冰箱库存 |
| 家庭公告板 | `/apps/board/` | board | 置顶公告 |
| 文档归档 | `/apps/docs/` | docs | 合同/证件扫描，`data/docs` 卷 |
| 订阅管理 | `/apps/subs/` | subs | 续费摊销 |
| 任务看板 | `/apps/tasks/` | tasks | 三列看板 |
| 健康档案 | `/apps/health/` | health | 就诊/用药/体征 |
| 菜谱大全 | `/apps/recipes/` | recipes | 食材/步骤 |
| 每周菜单 | `/apps/menu/` | menu | 联动写入购物清单 |
| 家庭账本 | `/apps/ledger/` | ledger | 收支汇总 |
| 家电资产 | `/apps/assets/` | assets | 保修到期提醒 |
| 藏书馆 | `/apps/books/` | books | 想读/在读/已读 |
| 宠物照护 | `/apps/pets/` | pets | 宠物档案 + 照护记录 |
| 家庭密码箱 | `/apps/vault/` | vault | 🔐 敏感字段 Fernet 加密，`data/vault` 卷 |

> 注：`home` 为静态应用，其余 18 个均连同一个共享 PostgreSQL 实例的独立库。
> 移动端 Android 客户端（PWA：manifest + Service Worker + 音乐锁屏控制）为已规划待做项。
