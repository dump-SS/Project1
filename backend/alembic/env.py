"""Alembic 迁移环境：接入 EpochX 后端自己的 metadata 与 database_url。

与 alembic.ini 的关系：
- sqlalchemy.url 不在 ini 里写死，统一走 backend/config.py 的 settings.database_url
  （已由 config 的 _normalize_sqlite_path 锚定到 backend 目录，消除 cwd 依赖）。
- target_metadata = backend 所有 ORM 模型的 Base.metadata，autogenerate 依赖它。

⚠️ 迁移定位（2026-08-31 团队决议）：
- **运行时 schema 的唯一真相源是 `Base.metadata.create_all`**（见 `database.py:8`、
  `main.py:32`、`tests/conftest.py:75`），app 启动与测试重建都走它。
- `versions/` 下的迁移文件**仅作历史留痕 / 契约记录**，不作为建库手段。
- **不要运行 `alembic upgrade head`**：基线 `ee1d7e6e893c` 的 upgrade 是
  `Base.metadata.create_all`，它读的是当前 metadata（已包含后续 kb_*/community_* 等全部表），
  与后面的增量迁移冲突（会报「table already exists」）。从空库跑整条链并不成立。
- 需要变更 schema 时：改 ORM 模型后，靠 create_all（开发机）/ 迁移留痕（留档）即可，
  不依赖 alembic 执行。
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# 项目自身的配置与模型（backend/ 目录，运行 alembic 时 cwd 在 backend）
import models  # noqa: F401  触发所有 ORM 类注册
from config import settings
from database import Base

config = context.config

# 迁移连接串从 config.py 注入（不写死在 alembic.ini）
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：不建 Engine，直接生成 SQL。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：走 Engine + 连接执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
