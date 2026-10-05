"""Railway 构建脚本：装依赖 → （可选）构建前端 → 下载并校验向量索引。

为什么要有这个脚本（而不是把命令堆在 Railway 配置里）
----------------------------------------------------
三条都是实测踩出来的，不是预防性写法：

1. **`pip install ./backend` 装不上。** `backend/pyproject.toml` 没有 `[build-system]`，
   而 `backend/` 是平铺布局且含多个顶层目录（`models/` `routes/` `tests/` `alembic/`），
   setuptools 自动发现直接失败：
   `error: Multiple top-level packages discovered in a flat-layout`。
   实测命令：`pip install --dry-run --no-deps ./backend` → exit 1。

   所以这里用 `tomllib`（Python 3.11+ 标准库）读出 `project.dependencies` 的精确 pin
   再喂给 pip。**好处：`backend/pyproject.toml` 仍是依赖的唯一真相源**，
   不新增一份会漂移的 requirements.txt。

2. **Railpack 在仓库根探测不到依赖。** `pyproject.toml` 在 `backend/` 下，
   而 Railway 从 `root_directory`（这里是仓库根）找依赖清单。依赖安装因此
   显式写在这里，不依赖平台的自动探测。

3. **向量索引进不了仓库。** `.gitignore` 含 `backend/kb_vectors/`，26.5MB 二进制
   不入库；而源 JSON 在仓库之外（`D:\\Projects\\knowledge base\\...`），
   所以 Railway 上**既拿不到也重建不了**——只能从外部 URL 拉。

   缺 `KB_VECTOR_URL` 时**故意让构建失败**：宁可部署失败，也不要「部署成功但
   检索静悄悄降级成 name_fuzzy」——那正是 pilot 要避免的情况，而且事后极难察觉。

用法（Railway build 命令）
------------------------
    python scripts/railway_build.py

环境变量
--------
KB_VECTOR_URL   必填（除非 SKIP_VECTOR_INDEX=1）。索引文件的下载 URL。
KB_VECTOR_DIR   索引落地目录，默认 /app/kb_vectors。
SKIP_VECTOR_INDEX=1   跳过索引下载（**仅限本地/CI 演练**，线上不要设）。
BUILD_FRONTEND  1=构建前端（默认） / 0=不构建（前端由 Vercel 等单独部署）。
EXPECTED_VECTOR_COUNT  期望条目数，默认读 KB_VECTOR_EXPECTED_COUNT（3391）。

⚠️ 本地能跑通 ≠ Railway 能跑通。本脚本在 Linux 容器里执行，
   而开发机是 Windows —— 见交付文档「哪些本地没事、上 Railway 会出问题」。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
VECTOR_FILE = "embeddings.index"
REFS_FILE = "refs.json"
# 仅用于挡住「下到一个 HTML 错误页 / 空文件」这类明显失败；
# 真正的判据是最后跑 check_vector_index.py（它会读 FAISS，截断必然读不出来）。
MIN_VECTOR_BYTES = 1_000_000
MIN_REFS_BYTES = 10_000


def log(msg: str) -> None:
    print(f"[railway-build] {msg}", flush=True)


def die(msg: str, hint: str = "") -> None:
    print(f"[railway-build][FATAL] {msg}", flush=True)
    if hint:
        print(f"[railway-build][HINT] {hint}", flush=True)
    sys.exit(1)


def truthy(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def run(cmd: list[str], cwd: Path, label: str) -> None:
    log(f"{label}: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(cwd))
    if proc.returncode != 0:
        die(f"{label} 失败（exit {proc.returncode}）", f"工作目录 {cwd}")


def step_install_python_deps() -> None:
    """从 backend/pyproject.toml 解析精确 pin 并安装。

    刻意不新增 requirements.txt：两份依赖清单必然漂移，而漂移会在
    「本地装的是 A、线上装的是 B」时变成极难查的问题。
    """
    pyproject = BACKEND_DIR / "pyproject.toml"
    if not pyproject.exists():
        die(f"找不到 {pyproject}", "确认 root_directory 是仓库根")

    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    deps = data.get("project", {}).get("dependencies") or []
    if not deps:
        die(f"{pyproject} 里没有 project.dependencies", "依赖清单被清空了？")

    log(f"从 pyproject 解析到 {len(deps)} 个依赖（含 extras 的原样传递）")
    run([sys.executable, "-m", "pip", "install", "--no-cache-dir", *deps], REPO_ROOT, "装 Python 依赖")


def step_build_frontend() -> None:
    """构建前端静态产物到 frontend/dist（main.py 的 SPA 回退读这里）。"""
    if truthy("BUILD_FRONTEND", "1") == "0":
        log("BUILD_FRONTEND=0 → 跳过前端构建")
        log("  注意：main.py 的 FRONTEND_DIR 找不到 index.html 时，"
            "对 / 与 SPA 路由会返回 FRONTEND_NOT_DEPLOYED（这是预期行为，不是故障）")
        return

    frontend = REPO_ROOT / "frontend"
    pkg = frontend / "package.json"
    if not pkg.exists():
        die(f"找不到 {pkg}", "BUILD_FRONTEND=1 但仓库里没有 frontend/package.json")

    lock = frontend / "package-lock.json"
    if lock.exists():
        run(["npm", "ci", "--no-audit", "--no-fund"], frontend, "装前端依赖")
    else:
        log("没有 package-lock.json → 用 npm install（不保证可复现）")
        run(["npm", "install", "--no-audit", "--no-fund"], frontend, "装前端依赖")
    run(["npm", "run", "build"], frontend, "构建前端")

    dist_index = frontend / "dist" / "index.html"
    if not dist_index.exists():
        die(f"构建结束但没有 {dist_index}", "看上面 npm run build 的输出")
    log(f"前端产物就位：{dist_index}")


def step_download_vector_index() -> None:
    """从 KB_VECTOR_URL 下载索引并校验，然后跑权威校验脚本。"""
    if truthy("SKIP_VECTOR_INDEX") == "1":
        log("SKIP_VECTOR_INDEX=1 → 跳过索引下载（**线上不要设**）")
        return

    url = truthy("KB_VECTOR_URL")
    if not url:
        die(
            "KB_VECTOR_URL 未设置，索引无法送达",
            "26.5MB 的 embeddings.index 不在 git 里（.gitignore 有 backend/kb_vectors/），"
            "源 JSON 也在仓库外，所以线上无法重建。请把索引传到对象存储，"
            "把下载 URL 配成 Railway 变量 KB_VECTOR_URL 后重新构建。",
        )

    target_dir = Path(truthy("KB_VECTOR_DIR", "/app/kb_vectors"))
    target_dir.mkdir(parents=True, exist_ok=True)

    base = url.rstrip("/")
    for name, min_bytes in ((VECTOR_FILE, MIN_VECTOR_BYTES), (REFS_FILE, MIN_REFS_BYTES)):
        src_url = f"{base}/{name}"
        dest = target_dir / name
        log(f"下载 {src_url} → {dest}")
        try:
            with urllib.request.urlopen(src_url, timeout=120) as resp:  # noqa: S310 - URL 来自 Railway 变量
                data = resp.read()
        except (urllib.error.URLError, OSError) as exc:
            die(f"下载 {name} 失败：{exc}", f"确认 KB_VECTOR_URL 可公开访问，且路径下确实有 {name}")

        if len(data) < min_bytes:
            die(
                f"{name} 只有 {len(data)} 字节（期望至少 {min_bytes}）—— 多半下到了错误页或空文件",
                "检查 URL 是否指向对象存储里的真实文件，而不是桶目录或登录页",
            )
        dest.write_bytes(data)
        log(f"  {name}: {len(data):,} bytes")

    # 权威判据：复用 check_vector_index.py（与 HTTP /health/vector-index 同一口径）。
    # 它会真正读取 FAISS，所以截断/损坏/条目数不对都会在这里暴露。
    log("跑 scripts/check_vector_index.py 做权威校验")
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_vector_index.py")],
        cwd=str(REPO_ROOT),
    )
    if proc.returncode != 0:
        die(
            "向量索引校验未通过（check_vector_index.py 退出非 0）",
            "部署已中止——这是有意的：宁可部署失败，也不要上线后检索静悄悄降级成 name_fuzzy。"
            "用 --json 看 problems 字段定位。",
        )
    log("索引校验通过")


def main() -> int:
    log(f"仓库根：{REPO_ROOT}")
    log(f"Python：{sys.version.split()[0]}（{sys.executable}）")

    step_install_python_deps()
    step_build_frontend()
    step_download_vector_index()

    log("构建步骤全部完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())