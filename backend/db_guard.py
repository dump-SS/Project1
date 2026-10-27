"""脚本入口的 DATABASE_URL 隔离（防「随手跑个脚本」误改共享开发库）。

## 这条防护是为了修什么

2026-10-18 出过一次真事故：我在 pytest 之外跑了一个一次性探针脚本，脚本里
`import database` 然后 `db.add(...)` 插了一行探针数据。**脚本没设 `DATABASE_URL`**，
于是 pydantic-settings 读了 `backend/.env`，落到了**共享开发库** `backend/data.db`：
建了一张野表 `chat_jobs` + 留了 1 行垃圾数据。

那次靠人工发现 + 人工清理（备份 → DROP → `alembic upgrade head`）收掉了。
**清理是补救，不是防护** —— 下一个人跑脚本还会再踩一次。

更糟的是那类脚本**自己不会知道**：它会以为自己在写某个库，安静地写进共享库。

## 拦截点为什么在 config.py 的 `mode="before"` 校验器

1. 它是**唯一**能同时看到「.env 解析结果」与「环境变量是否被显式设置」的地方；
   `database.py` 拿到的已经是 `settings.database_url`，那时再判断就晚了。
2. 它跑在 engine 创建**之前** —— `database.py` 一 import 就 `create_engine`，
   没有任何「先连上再改」的余地。
3. 实测确认：pydantic-settings 的 before 校验器拿得到 env+.env 合并后的值，且能改写。

## 判定顺序（先命中先算）

| # | 情形 | 结果 | 理由 |
|---|---|---|---|
| 1 | 应用 / 工具进程（uvicorn、gunicorn、alembic、pytest…） | **不保护** | 这些进程本来就不该被脚本隔离影响；alembic 必须连它该连的库 |
| 2 | 显式设了 `DATABASE_URL` | **不保护** | 本仓既有的合法口子：`scripts/verify_frontend_contract.py` 早就在 import config 前把它指向临时库；`backup_neon.py` / `r2_sweep.py` 从环境变量/stdin 取。**「显式设置」本身就是「我知道我要连哪个库」的声明** |
| 3 | 显式设了 `EPOCHX_ALLOW_SHARED_DB=1` | **不保护** | 同上，但更显眼、更易 grep |
| 4 | `<repo>/scripts/` 下的正式工具脚本 | **不保护** | 它们在版本控制里、经过 review，而且**本身就是「要动库」的工具**（`import_knowledge_points` / `seed_*` / `migrate_subject_codes` / `gen_invite_codes`）。给它们套隔离层会让它们**静默写进一个空库**（比不改更糟） |
| 5 | 其余一次性脚本 / 探针 / 临时脚本 | **重定向** | 若解析出来指向共享开发库 `backend/data.db`，改指向隔离库 `backend/.scratch_data/scratch.db`，并打印一行醒目说明 |

第 5 条的「重定向」而不是「直接报错」，理由是**响亮的失败比安静的错误更安全**：
隔离库没有表，脚本会撞 `no such table` —— 它**知道自己没连上想要的库**；
而如果改成「悄悄连另一个库」，脚本会读到空数据、得出错误结论且毫无察觉。
第 4 条的存在保证了正式工作流不会被拦死。

## 怎么表达「我真的要连共享库」

```powershell
# 方式一：显式给 URL（推荐，最直白）
$env:DATABASE_URL = "sqlite:///D:/Projects/Project1/backend/data.db"
python scripts/your_script.py

# 方式二：放行 .env 里的值（脚本自己知道 .env 配的是什么）
$env:EPOCHX_ALLOW_SHARED_DB = "1"
python scripts/your_script.py
```

## 已知边界（不隐瞒）

- 第 4 条是**路径约定**而不是逐脚本声明：正式工具脚本默认就能连共享库。
  代价是「把一个误写的脚本放进 `scripts/`」仍然会连共享库。
  换来的是正式工具不用为每一行脚本改动 CLI 语义。
- 本模块只拦**解析出来的目标是共享开发库**这一种情况。
  指向 Neon / 别的 SQLite / 别的路径，一律不动。
- 隔离库**没有表**。需要表结构请对该库单独建（或先 `alembic upgrade head` 打过去）。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

#: 共享开发库的库名（本机的 backend/data.db，多个 agent / worktree 共用）
SHARED_DEV_DB_NAME = "data.db"

#: 隔离库的位置：backend/.scratch_data/scratch.db
SCRATCH_DIR_NAME = ".scratch_data"
SCRATCH_DB_NAME = "scratch.db"

#: 显式放行共享开发库的环境变量
ALLOW_SHARED_ENV = "EPOCHX_ALLOW_SHARED_DB"

#: 仓库里「正式工具脚本」的目录名（相对仓库根）
CURATED_SCRIPTS_DIR_NAME = "scripts"

#: 已知工具入口：这些进程本来就不该被脚本隔离影响
_TOOL_ARGV0 = frozenset(
    {
        "alembic",
        "pytest",
        "py.test",
        "uvicorn",
        "gunicorn",
        "hypercorn",
        "ipython",
        "pip",
        "pip.exe",
        "python",
        "pythonw",
        "python.exe",
    }
)

#: 进程模式
MODE_APP = "app"        # 应用服务（uvicorn/gunicorn main:app）
MODE_TOOL = "tool"      # 工具（alembic/pytest…）
MODE_CURATED = "curated"  # 仓库内正式脚本 scripts/*.py
MODE_SCRIPT = "script"  # 一次性脚本 / 探针

ACTION_KEEP = "keep"
ACTION_REDIRECT = "redirect"


@dataclass(frozen=True)
class GuardDecision:
    """一次判定的结果。`notice` 非空时应当打印给操作者看。"""

    mode: str
    action: str
    original: str
    final: str
    reason: str
    notice: str = ""


def _looks_like_app_arg(arg: str) -> bool:
    """uvicorn/gunicorn 的应用参数形如 `main:app`（module:attr）。"""
    return ":" in arg and not arg.startswith("-")


def detect_mode(
    argv: list[str],
    backend_dir: Path,
    repo_root: Path,
    cwd: Path | None = None,
) -> str:
    """判断当前进程是「应用 / 工具 / 正式脚本 / 一次性脚本」。

    判据刻意保守：宁可漏判成 script（多一层保护），也不要把应用误判成 script
    （那会让本地起服务连到空库）。

    `cwd` 显式传入而不是读环境里的当前目录：相对路径 argv[0]（比如
    `../scripts/check_vector_index.py`）必须按**它实际运行时的 cwd** 解析，
    而 Railway 的 build 命令（cwd=仓库根）与 start 命令（cwd=backend）cwd 就不同。
    做成参数，行为才是确定的、可测的 —— 见 tests/test_db_guard.py 的 Railway 回归用例。
    """
    argv = list(argv or [])
    argv0 = argv[0] if argv else ""
    cwd = Path.cwd() if cwd is None else Path(cwd)

    # 应用：uvicorn main:app / gunicorn main:app
    if any(_looks_like_app_arg(a) for a in argv[1:]):
        return MODE_APP

    if not argv0:
        return MODE_SCRIPT

    # python -c "..."：一次性代码，正是事故那一类
    if argv0 in ("-c", "-"):
        return MODE_SCRIPT

    base = os.path.basename(argv0).lower()
    # 控制台脚本的 argv[0] 可能是 `.../Scripts/alembic.exe`。
    # ⚠️ setuptools 生成的启动器**恰好**会把 .exe 后缀去掉（argv[0] 变成 `.../Scripts/alembic`），
    # 所以只比 "alembic" 恰好能命中。但那是**别人的实现细节**，不能依赖 ——
    # 一旦它改成保留 .exe，alembic 就会被误判成「一次性脚本」，
    # 于是 `alembic upgrade head` 会**静默地**打到隔离库。
    # 这里主动剥掉可执行后缀，不赌别人的实现。
    for ext in (".exe", ".cmd", ".bat", ".ps1", ".pyw"):
        if base.endswith(ext):
            base = base[: -len(ext)]
            break
    if base in _TOOL_ARGV0:
        # `uvicorn` / `gunicorn` 作为可执行文件 → 应用；其余 → 工具
        return MODE_APP if base in ("uvicorn", "gunicorn", "hypercorn") else MODE_TOOL

    if base.endswith(".py"):
        try:
            resolved = Path(argv0)
            if not resolved.is_absolute():
                resolved = cwd / resolved
            resolved = resolved.resolve()
        except OSError:
            return MODE_SCRIPT
        parts = {p.lower() for p in resolved.parts}
        # 第三方库自带的 __main__（python -m pytest 之类）
        if "site-packages" in parts or "dist-packages" in parts:
            return MODE_TOOL
        # 应用入口：python main.py
        if resolved.parent == backend_dir.resolve() and base == "main.py":
            return MODE_APP
        # 仓库内正式脚本
        curated = (repo_root / CURATED_SCRIPTS_DIR_NAME).resolve()
        if curated in resolved.parents:
            return MODE_CURATED
        return MODE_SCRIPT

    return MODE_SCRIPT


def sqlite_target(url: str, backend_dir: Path) -> Path | None:
    """把 sqlite URL 解析成绝对路径；不是 sqlite 就返回 None。

    与 `Settings._normalize_sqlite_path` 同一套锚定规则：相对路径按 backend 目录解析。
    """
    if not url.startswith("sqlite:///"):
        return None
    raw = url[len("sqlite:///"):]
    if not raw:
        return None
    # sqlite:////abs/path 形式（四个斜杠）表示 POSIX 绝对路径
    if raw.startswith("/") and not raw.startswith("//"):
        return Path(raw).resolve()
    if raw.startswith("//"):
        return Path(raw[1:]).resolve()
    p = Path(raw)
    if not p.is_absolute():
        p = (backend_dir / raw).resolve()
    return p.resolve()


def scratch_url(backend_dir: Path) -> str:
    """隔离库 URL。"""
    return f"sqlite:///{(backend_dir / SCRATCH_DIR_NAME / SCRATCH_DB_NAME).as_posix()}"


def summarize_target(url: str) -> str:
    """给日志用的目标摘要：**不打印口令**。"""
    if url.startswith("sqlite:///"):
        return url
    try:
        # postgresql://user:pass@host/db → 只留 host/db
        scheme, _, rest = url.partition("://")
        if "@" in rest:
            rest = rest.split("@", 1)[1]
        return f"{scheme}://{rest}"
    except Exception:
        return "<无法解析的 DATABASE_URL>"


def evaluate(
    backend_dir: Path,
    repo_root: Path,
    env: dict[str, str],
    argv: list[str],
    values: dict,
    cwd: Path | None = None,
) -> GuardDecision:
    """核心判定。纯函数，不碰环境变量，方便单测。"""
    mode = detect_mode(argv, backend_dir, repo_root, cwd)
    current = str(values.get("database_url") or "")

    # mode="before" 校验器在字段默认值应用前运行：若 values 里没有 database_url
    #（没写 .env、也没设 DATABASE_URL 环境变量），pydantic 之后会用字段默认
    # 值 "sqlite:///./data.db"，它解析后正好是共享开发库。不把默认值算进来
    # 就会漏判成「不动」→ 一次性脚本静默写进共享库（fail-open）。
    if not current:
        current = "sqlite:///./data.db"

    if mode in (MODE_APP, MODE_TOOL):
        return GuardDecision(mode, ACTION_KEEP, current, current, "应用/工具进程，不隔离")

    if (env.get("DATABASE_URL") or "").strip():
        return GuardDecision(
            mode, ACTION_KEEP, current, current,
            "显式设置了 DATABASE_URL —— 操作者已声明目标库",
        )

    if (env.get(ALLOW_SHARED_ENV) or "").strip() == "1":
        return GuardDecision(
            mode, ACTION_KEEP, current, current,
            f"显式设置了 {ALLOW_SHARED_ENV}=1 —— 放行 .env 的值",
        )

    if mode == MODE_CURATED:
        return GuardDecision(
            mode, ACTION_KEEP, current, current,
            "仓库内正式工具脚本：本身就是「要动库」的工具，不隔离",
        )

    # 到这里 = 一次性脚本，且没显式声明目标库
    target = sqlite_target(current, backend_dir)
    shared = (backend_dir / SHARED_DEV_DB_NAME).resolve()
    if target is None or target != shared:
        return GuardDecision(
            mode, ACTION_KEEP, current, current,
            "目标不是共享开发库（可能是 Neon / 别的库），不动",
        )

    new_url = scratch_url(backend_dir)
    try:
        (backend_dir / SCRATCH_DIR_NAME).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    example_url = f"sqlite:///{shared.as_posix()}"
    notice = (
        "[db-guard] 一次性脚本且未显式设置 DATABASE_URL ——\n"
        f"[db-guard]   原本会连到共享开发库：{current}\n"
        f"[db-guard]   已重定向到隔离库      ：{new_url}\n"
        "[db-guard]   ⚠️ 隔离库**没有表**，脚本会撞 no such table"
        "（这是故意的：响亮的失败好过安静地连错库）。\n"
        "[db-guard]   确实要写共享开发库/生产库，请显式声明目标：\n"
        f'[db-guard]     $env:DATABASE_URL = "{example_url}"\n'
        f'[db-guard]     或 $env:{ALLOW_SHARED_ENV} = "1"（放行 .env 的值）'
    )
    return GuardDecision(
        mode, ACTION_REDIRECT, current, new_url,
        "一次性脚本未声明目标库 → 重定向到隔离库", notice,
    )


def apply_db_guard(
    backend_dir: Path,
    repo_root: Path,
    values: dict,
    env: dict[str, str] | None = None,
    argv: list[str] | None = None,
    cwd: Path | None = None,
) -> tuple[dict, GuardDecision]:
    """给 `Settings` 的 before 校验器用。返回 (改写后的 values, 判定结果)。"""
    env = os.environ if env is None else env
    argv = sys.argv if argv is None else argv
    if not isinstance(values, dict):
        return values, GuardDecision(MODE_SCRIPT, ACTION_KEEP, "", "", "非字典输入，跳过")

    decision = evaluate(backend_dir, repo_root, env, argv, values, cwd)
    if decision.action == ACTION_REDIRECT:
        values = {**values, "database_url": decision.final}
        # 说明打 stderr：不少脚本把结构化结果打到 stdout，混进去会污染输出
        print(decision.notice, file=sys.stderr, flush=True)
    return values, decision
