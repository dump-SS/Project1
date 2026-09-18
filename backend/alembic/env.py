"""Alembic 迁移环境：接入 EpochX 后端自己的 metadata 与 database_url。

与 alembic.ini 的关系：
- sqlalchemy.url 不在 ini 里写死，统一走 backend/config.py 的 settings.database_url
  （已由 config 的 _normalize_sqlite_path 锚定到 backend 目录，消除 cwd 依赖）。
- target_metadata = backend 所有 ORM 模型的 Base.metadata，autogenerate 依赖它。

迁移定位（2026-09-15 squash 后）：
- **Alembic 是 schema 的唯一真相源**：空库建表走 `alembic upgrade head`，
  upgrade / downgrade 均可反复执行。
- 基线 `1a6f0c6bb285` 是 autogenerate 产出的**显式 DDL**（29 张表），不再引用
  `Base.metadata`，因此不会随模型变化而改变语义。
- 历史遗留：squash 之前的 14 个 revision 已归档到 `alembic/versions_archive/`。
  其中原基线 `ee1d7e6e893c` 的 upgrade 是 `Base.metadata.create_all`，读的是当前
  metadata（含全部模型），于是建出 30 张表——后续增量迁移的 14 处 create_table 与
  14 处 add_column 全部冲突（table already exists / duplicate column），
  整条链从第二个 revision 起无法从空库跑通。**这是本次 squash 的直接原因。**
  归档目录不参与 alembic 扫描，仅作历史留痕。
- `create_all` 仍保留两处：`main.py`（应用启动）与 `tests/conftest.py`（测试重建）。
  `models/__init__.py` 里「import 即建表」的副作用已移除——它会让 autogenerate
  永远看不到差异（对着空库也只生成空迁移），是迁移无法自举的另一半原因。
- 新增模型/列时：改 ORM 模型 → `alembic revision --autogenerate -m "..."` →
  **人工 review 产物**（autogenerate 对 server_default、索引命名未必还原到位）→ 提交。
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
