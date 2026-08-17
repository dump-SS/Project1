"""
SQLAlchemy 2.0 异步同步双轨：MVP 用同步连接足够，省事且与 SQLite 配合稳定。

用法：
    from database import Base, engine, SessionLocal, get_db

    # 建表（启动时调一次）
    Base.metadata.create_all(bind=engine)

    # 在路由里拿 session
    def route(db: Session = Depends(get_db)):
        ...
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings


# SQLite 需要 check_same_thread=False，因为 FastAPI 跨线程复用连接
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=settings.app_debug,  # debug 模式打印 SQL，生产关掉
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个 session，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
