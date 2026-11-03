-- 共享 PostgreSQL 实例：所有需要持久化的应用都连这一个服务器，
-- 但每个应用使用【独立的 database】做数据隔离（便于单独备份/迁移）。
--
-- 新增一个需要数据库的应用时：
--   1) 在此文件追加一行 CREATE DATABASE <app>；（用下面的条件写法可重复执行不报错）
--   2) 在 docker-compose.yml 里把该应用的 DATABASE_URL 指向 postgresql://myhome:<密码>@postgres:5432/<app>
--   3) docker compose down && docker compose up -d --build  （仅首次建库需要重启；也可直接连库手动 CREATE DATABASE）

-- 网络收音机 / 音乐播放器（已合并为 music 应用）
SELECT 'CREATE DATABASE music'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'music')\gexec

-- 家用手册 Wiki（Markdown 知识库）
SELECT 'CREATE DATABASE wiki'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'wiki')\gexec

-- 家庭相册（照片 + 相册管理，含缩略图）
SELECT 'CREATE DATABASE album'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'album')\gexec

-- 纪念日 / 家庭日历
SELECT 'CREATE DATABASE calendar'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'calendar')\gexec

-- 车辆保养记录
SELECT 'CREATE DATABASE carlog'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'carlog')\gexec

-- 购物清单 / 冰箱库存
SELECT 'CREATE DATABASE pantry'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'pantry')\gexec

-- 家庭公告板
SELECT 'CREATE DATABASE board'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'board')\gexec

-- 家庭文档归档（合同/证件/保修卡/扫描件，含文件存储）
SELECT 'CREATE DATABASE docs'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'docs')\gexec

-- 订阅 / 会员续费管理
SELECT 'CREATE DATABASE subs'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'subs')\gexec

-- 家庭任务看板
SELECT 'CREATE DATABASE tasks'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'tasks')\gexec

-- 健康档案
SELECT 'CREATE DATABASE health'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'health')\gexec

-- 菜谱大全
SELECT 'CREATE DATABASE recipes'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'recipes')\gexec

-- 每周菜单
SELECT 'CREATE DATABASE menu'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'menu')\gexec

-- 家庭账本
SELECT 'CREATE DATABASE ledger'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ledger')\gexec

-- 家电 / 资产管理
SELECT 'CREATE DATABASE assets'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'assets')\gexec

-- 藏书馆
SELECT 'CREATE DATABASE books'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'books')\gexec

-- 宠物照护
SELECT 'CREATE DATABASE pets'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'pets')\gexec

-- 家庭密码箱（敏感字段加密存储，密钥在 ./data/vault）
SELECT 'CREATE DATABASE vault'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'vault')\gexec

-- 家庭药箱
SELECT 'CREATE DATABASE medkit'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'medkit')\gexec

-- 影视清单
SELECT 'CREATE DATABASE films'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'films')\gexec

-- 旅行游记
SELECT 'CREATE DATABASE travel'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'travel')\gexec

-- 绿植养护
SELECT 'CREATE DATABASE plants'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'plants')\gexec

-- 家庭环境记录
SELECT 'CREATE DATABASE homeenv'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'homeenv')\gexec

-- 房屋维修记录
SELECT 'CREATE DATABASE repair'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'repair')\gexec

-- 孩子成长日志
SELECT 'CREATE DATABASE growth'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'growth')\gexec

-- 家庭能耗记录
SELECT 'CREATE DATABASE energy'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'energy')\gexec

-- 家庭保险保单
SELECT 'CREATE DATABASE insurance'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'insurance')\gexec

-- 家庭证件档案
SELECT 'CREATE DATABASE certs'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'certs')\gexec

-- 服药提醒打卡
SELECT 'CREATE DATABASE meds'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'meds')\gexec

-- 家庭通讯录
SELECT 'CREATE DATABASE contacts'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'contacts')\gexec

-- 预留：未来需要数据库的应用，在此追加 CREATE DATABASE <app>;
