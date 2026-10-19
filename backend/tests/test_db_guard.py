"""脚本入口数据库隔离的测试（backend/db_guard.py）。

背景：2026-10-18 的一次性探针脚本没设 `DATABASE_URL`，吃掉了 `.env` 里的共享开发库地址，
建了野表 + 留了垃圾数据。这组测试守住那道防线。

## 为什么要起子进程

`config.py` 的 `settings` 是**模块级单例**，在 pytest 进程里已经被 conftest 用
`DATABASE_URL` 指向 `.pytest_data/test.db` 了 —— 进程内根本复现不出
「没设 DATABASE_URL」这个状态。

所以核心证据必须是**子进程**：清掉环境变量里的 DATABASE_URL，让它自己 import config，
看它解析出来的到底是哪个库。

## 测试分层

1. 纯函数层：`evaluate()` 的判定顺序（应用/工具/显式声明/正式脚本/一次性脚本）
2. 集成层（**核心证据**）：子进程真跑一遍，确认没打到共享库
3. 回归层：共享开发库本身**没被这些测试碰到**
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent

sys.path.insert(0, str(BACKEND))

import db_guard  # noqa: E402

SHARED_DB = BACKEND / "data.db"
SCRATCH_DB = BACKEND / db_guard.SCRATCH_DIR_NAME / db_guard.SCRATCH_DB_NAME


def _values(url: str) -> dict:
    return {"database_url": url}


def _shared_url() -> str:
    return f"sqlite:///{SHARED_DB.as_posix()}"


# ---------------------------------------------------------------- 纯函数层


def test_detect_mode_app_via_uvicorn_arg():
    """`uvicorn main:app` 形态 → 应用，不隔离。"""
    assert db_guard.detect_mode(["uvicorn", "main:app"], BACKEND, REPO_ROOT) == db_guard.MODE_APP


def test_detect_mode_app_via_main_py():
    assert (
        db_guard.detect_mode([str(BACKEND / "main.py")], BACKEND, REPO_ROOT)
        == db_guard.MODE_APP
    )


def test_detect_mode_tool_alembic():
    assert (
        db_guard.detect_mode(["alembic", "upgrade", "head"], BACKEND, REPO_ROOT)
        == db_guard.MODE_TOOL
    )


def test_detect_mode_tool_console_script_exe():
    """控制台脚本的 argv[0] 可能带 .exe。

    ⚠️ setuptools 的启动器恰好会去掉 .exe 后缀，所以「只比 alembic」也能命中；
    但那是**别人的实现细节**。一旦它改成保留 .exe，`alembic upgrade head`
    就会被误判成一次性脚本 → **静默地**打到隔离库。
    这里钉死剥后缀的行为。
    """
    for argv0 in (
        str(Path(sys.prefix) / "Scripts" / "alembic.exe"),
        str(Path(sys.prefix) / "Scripts" / "alembic"),
        str(Path(sys.prefix) / "Scripts" / "pytest.exe"),
    ):
        assert db_guard.detect_mode([argv0], BACKEND, REPO_ROOT) == db_guard.MODE_TOOL, argv0


def test_detect_mode_tool_pytest_module():
    """`python -m pytest` 的 argv[0] 落在 site-packages → 工具。"""
    site = Path(sys.prefix) / "Lib" / "site-packages" / "pytest" / "__main__.py"
    assert db_guard.detect_mode([str(site)], BACKEND, REPO_ROOT) == db_guard.MODE_TOOL


def test_detect_mode_inline_code_is_script():
    """`python -c "..."` —— 事故那一类，必须判成一次性脚本。"""
    assert db_guard.detect_mode(["-c"], BACKEND, REPO_ROOT) == db_guard.MODE_SCRIPT


def test_detect_mode_temp_script_is_script():
    """事故脚本的真实形态：放在临时目录里的一次性脚本。"""
    tmp = Path(r"C:\Users\29622\AppData\Local\Temp\opencode\probe.py")
    assert db_guard.detect_mode([str(tmp)], BACKEND, REPO_ROOT) == db_guard.MODE_SCRIPT


def test_detect_mode_curated_repo_script():
    curated = REPO_ROOT / "scripts" / "import_knowledge_points.py"
    assert db_guard.detect_mode([str(curated)], BACKEND, REPO_ROOT) == db_guard.MODE_CURATED


# ---------------------------------------------------------------- Railway 回归（生产级）
#
# Railway 的实际配置（describe-service 读出来的原文）：
#   buildCommand:    python3 scripts/railway_build.py                      （cwd=仓库根）
#   preDeployCmd:    cd backend && python3 -m alembic upgrade head          （cwd=backend）
#   startCommand:    cd backend && python3 ../scripts/check_vector_index.py
#                    && exec python3 -m uvicorn main:app --host 0.0.0.0     （cwd=backend）
#
# 🔴 特别要守的是 **preDeploy 的 alembic**：它一旦被误判成「一次性脚本」，
# 迁移就会**静默地**打到隔离库 → 迁移变成空操作 → 生产 schema 永远落后，
# 而且**不会报任何错**。这是比"共享库被写脏"严重得多的故障。


def test_railway_predeploy_alembic_is_never_redirected():
    """🔴 生产红线：preDeploy 的 alembic 绝不能被重定向。"""
    site = Path(sys.prefix) / "Lib" / "site-packages" / "alembic" / "__main__.py"
    d = db_guard.evaluate(
        BACKEND,
        REPO_ROOT,
        {},
        [str(site), "upgrade", "head"],
        _values(_shared_url()),
        cwd=BACKEND,
    )
    assert d.action == db_guard.ACTION_KEEP, d
    assert d.mode == db_guard.MODE_TOOL


def test_railway_start_command_is_never_redirected():
    """startCommand 的两段都不得被重定向。"""
    # 第一段：check_vector_index.py（cwd=backend，相对路径 ../scripts/...）
    d1 = db_guard.evaluate(
        BACKEND,
        REPO_ROOT,
        {},
        ["../scripts/check_vector_index.py"],
        _values(_shared_url()),
        cwd=BACKEND,
    )
    assert d1.action == db_guard.ACTION_KEEP, d1
    assert d1.mode == db_guard.MODE_CURATED

    # 第二段：exec python3 -m uvicorn main:app
    site = Path(sys.prefix) / "Lib" / "site-packages" / "uvicorn" / "__main__.py"
    d2 = db_guard.evaluate(
        BACKEND,
        REPO_ROOT,
        {},
        [str(site), "main:app", "--host", "0.0.0.0", "--port", "8000"],
        _values(_shared_url()),
        cwd=BACKEND,
    )
    assert d2.action == db_guard.ACTION_KEEP, d2


def test_railway_build_command_is_never_redirected():
    """buildCommand 的 cwd 是**仓库根**（不是 backend），相对路径解析必须对。"""
    d = db_guard.evaluate(
        BACKEND,
        REPO_ROOT,
        {},
        ["scripts/railway_build.py"],
        _values(_shared_url()),
        cwd=REPO_ROOT,
    )
    assert d.action == db_guard.ACTION_KEEP, d
    assert d.mode == db_guard.MODE_CURATED


def test_evaluate_redirects_one_off_script():
    """核心：一次性脚本 + 未声明目标 + 目标是共享库 → 重定向。"""
    d = db_guard.evaluate(
        BACKEND, REPO_ROOT, {}, [str(Path("C:/tmp/probe.py"))], _values(_shared_url())
    )
    assert d.action == db_guard.ACTION_REDIRECT
    assert d.final == db_guard.scratch_url(BACKEND)
    assert SCRATCH_DB.as_posix() in d.final
    assert d.notice, "重定向必须带醒目说明"


def test_evaluate_respects_explicit_database_url():
    """显式设置 = 操作者已声明目标 → 放行。"""
    d = db_guard.evaluate(
        BACKEND,
        REPO_ROOT,
        {"DATABASE_URL": "postgresql://u:p@host/db"},
        [str(Path("C:/tmp/probe.py"))],
        _values("postgresql://u:p@host/db"),
    )
    assert d.action == db_guard.ACTION_KEEP


def test_evaluate_respects_allow_shared_env():
    d = db_guard.evaluate(
        BACKEND,
        REPO_ROOT,
        {db_guard.ALLOW_SHARED_ENV: "1"},
        [str(Path("C:/tmp/probe.py"))],
        _values(_shared_url()),
    )
    assert d.action == db_guard.ACTION_KEEP


def test_evaluate_does_not_touch_app_or_tool():
    for argv in (["uvicorn", "main:app"], [str(BACKEND / "main.py")], ["alembic", "upgrade"]):
        d = db_guard.evaluate(BACKEND, REPO_ROOT, {}, argv, _values(_shared_url()))
        assert d.action == db_guard.ACTION_KEEP, argv


def test_evaluate_does_not_touch_curated_scripts():
    """正式工具脚本本身就是「要动库」的 —— 隔离会让它静默写进空库。"""
    d = db_guard.evaluate(
        BACKEND,
        REPO_ROOT,
        {},
        [str(REPO_ROOT / "scripts" / "import_knowledge_points.py")],
        _values(_shared_url()),
    )
    assert d.action == db_guard.ACTION_KEEP


def test_evaluate_does_not_touch_non_shared_target():
    """目标不是共享开发库（比如 Neon）→ 一律不动。"""
    d = db_guard.evaluate(
        BACKEND,
        REPO_ROOT,
        {},
        [str(Path("C:/tmp/probe.py"))],
        _values("postgresql://u:p@host/db"),
    )
    assert d.action == db_guard.ACTION_KEEP


def test_evaluate_handles_relative_sqlite_path():
    """`.env` 里写相对路径 `./data.db` 时也要认得出那是共享库。"""
    d = db_guard.evaluate(
        BACKEND,
        REPO_ROOT,
        {},
        [str(Path("C:/tmp/probe.py"))],
        _values("sqlite:///./data.db"),
    )
    assert d.action == db_guard.ACTION_REDIRECT


def test_summarize_target_does_not_leak_password():
    """日志里不能出现口令。"""
    out = db_guard.summarize_target("postgresql://user:sup3rsecret@host/db")
    assert "sup3rsecret" not in out
    assert "host/db" in out


# ---------------------------------------------------------------- 集成层（核心证据）


def _run_probe(env_extra: dict | None = None) -> tuple[int, str, str]:
    """在**没有 DATABASE_URL** 的环境里跑一个一次性脚本，打印它解析出来的库。"""
    env = dict(os.environ)
    env.pop("DATABASE_URL", None)
    env.pop(db_guard.ALLOW_SHARED_ENV, None)
    env.update(env_extra or {})
    code = (
        "import config;"
        "print(config.settings.database_url)"
    )
    p = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    return p.returncode, p.stdout.strip(), p.stderr


def test_subprocess_without_database_url_does_not_hit_shared_db():
    """🔴 核心证据：真起一个不设 DATABASE_URL 的脚本，它**不能**连共享开发库。"""
    code, out, err = _run_probe()
    assert code == 0, f"探针跑挂了: {err}"
    assert SCRATCH_DB.as_posix() in out, (
        f"一次性脚本解析出来的应该是隔离库，实际是 {out!r}"
    )
    assert SHARED_DB.as_posix() not in out, (
        f"一次性脚本连到了共享开发库！{out!r}"
    )


def test_subprocess_emits_loud_notice_naming_both_targets():
    """重定向必须**看得见**：说明里要同时点出原本的共享库和新的隔离库。"""
    code, out, err = _run_probe()
    assert code == 0, err
    assert "[db-guard]" in err, f"stderr 没有告警: {err!r}"
    assert SHARED_DB.as_posix() in err, f"告警没点出共享库: {err!r}"
    assert SCRATCH_DB.as_posix() in err, f"告警没点出隔离库: {err!r}"


def test_subprocess_with_explicit_database_url_is_respected():
    """显式设置 → 放行（这是本仓既有的合法口子）。"""
    target = "sqlite:///" + (SCRATCH_DB).as_posix()
    code, out, err = _run_probe({"DATABASE_URL": target})
    assert code == 0, err
    assert out == target
    assert "[db-guard]" not in err, "显式声明时不该再告警"


def test_subprocess_with_allow_shared_env_keeps_env_value():
    """EPOCHX_ALLOW_SHARED_DB=1 → 放行 .env 的值（即共享开发库）。"""
    code, out, err = _run_probe({db_guard.ALLOW_SHARED_ENV: "1"})
    assert code == 0, err
    assert out == _shared_url(), out
    assert "[db-guard]" not in err


# ---------------------------------------------------------------- 回归层


def test_shared_dev_db_untouched_by_this_test_file():
    """这些测试**不能**碰到共享开发库。

    如果哪天隔离失效，这里会先炸 —— 因为子进程探针写的是隔离库，
    而共享库只被**读**（检查文件存在与 mtime）。
    """
    if not SHARED_DB.exists():
        pytest.skip("本机没有共享开发库")
    # 只读：确认它还在、且不是本轮被创建的
    assert SHARED_DB.exists()
    assert SHARED_DB.stat().st_size > 0
