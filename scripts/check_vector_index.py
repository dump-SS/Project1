"""向量索引部署前置校验：确认索引真的在磁盘上、且条目数与基准一致。

为什么需要（2026-10-04）：
索引读不到时应用**照常启动**，检索静悄悄降级 name_fuzzy——功能可用、接口形态
不变，但匹配质量下降，事先没有任何报错。所以「静默降级」必须变成「可观测 + 可拦」：
本脚本给部署流水线一个**退出码**，让「索引没带上」在 release 阶段就红，
而不是等用户说「搜不准」才发现。

判定口径与 :func:`vector_store.vector_index_status` 完全一致（单一真相源，
不在脚本里重复实现一遍判定逻辑——两处口径漂移正是这类校验最常见的失效原因）。

用法：
    python scripts/check_vector_index.py            # 期望 3391 条，不符则 exit 1
    python scripts/check_vector_index.py --expect 0# 允许空索引（首次建库前）
    python scripts/check_vector_index.py --json     # 机器可读输出

部署接法（三个候选平台都支持跑一次性命令）：
- Railway / Render：release command 或 healthcheck 调 `python scripts/check_vector_index.py`
- Fly.io：部署后 `fly ssh console -C "python scripts/check_vector_index.py"`
- 最小可用形态：把本脚本的退出码与 GET /health/vector-index 一起挂到监控。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import vector_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="向量索引部署前置校验")
    parser.add_argument(
        "--expect",
        type=int,
        default=None,
        help="期望的索引条目数；默认取 KB_VECTOR_EXPECTED_COUNT（3391）。传 0 表示允许空索引。",
    )
    parser.add_argument("--json", action="store_true", help="只输出 JSON")
    args = parser.parse_args()

    status = vector_store.vector_index_status()

    #显式覆盖基准（--expect 0 = 允许空索引，用于首次建库前）
    if args.expect is not None:
        status["expectedCount"] = args.expect
        if status["count"] != args.expect:
            status["problems"].append(
                f"索引条目数 {status['count']} != 期望 {args.expect}"
                "（先核对 refs.json 与库表是否同步，不要直接重建索引）"
            )
        status["status"] = "ok" if not status["problems"] else "degraded"
        status["searchable"] = bool(status["count"])
        status["searchMode"] = "vector" if status["count"] else "name_fuzzy"

    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status["status"] == "ok" else 1

    print("=== 向量索引部署前置校验 ===")
    print(f"  状态{status['status']}（ok / degraded）")
    print(f"  检索模式        {status['searchMode']}")
    print(f"  条目数          {status['count']}（基准 {status['expectedCount']}）")
    print(f"  维度            {status['dim']}")
    print(f"  refs 条目       {status['refs']}")
    print(f"  目录来源        {status['indexDirSource']}")
    print(f"  索引目录        {status['indexDir']}")
    print(f"  索引文件存在    {status['indexFileExists']}")
    print(f"  引用文件存在    {status['refsFileExists']}")
    print(f"  KB_EMBED_MODE   {status['embedMode']}")

    if status["problems"]:
        print("\n  未通过，原因：")
        for problem in status["problems"]:
            print(f"    - {problem}")
        print(
            "\n  处理：确认 KB_VECTOR_DIR 指向随部署带上来的索引目录，"
            "且该目录内有 embeddings.index 与 refs.json。"
        )
        print(
            "  ⚠️ 条目数不对时**先查 refs.json 与库表是否同步**——"
            "库里有而索引里没有才需要重建；反之重建会覆盖掉正确向量。"
        )
        return 1

    print("\n  通过：索引在位，检索走向量。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())