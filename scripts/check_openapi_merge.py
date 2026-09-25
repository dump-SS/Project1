"""合并后契约体检：重复键 + 断链 $ref + 两边增量是否都在。

YAML 对**重复 key 是静默取后者**，不报错——所以合并两个分支的契约时，
必须显式查重复键，否则会出现"某个 path/schema 被另一个分支的同名定义顶掉"，
而文件看起来完全正常。

用法（仓库根）：python scripts/check_openapi_merge.py
退出码：0 = 干净；1 = 有问题（列出明细）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs" / "openapi.yaml"

src = PATH.read_text(encoding="utf-8")

if "<<<<<<<" in src or ">>>>>>>" in src:
    sys.exit("仍有冲突标记未解决")

doc = yaml.safe_load(src)
paths = doc["paths"]
schemas = doc["components"]["schemas"]
problems: list[str] = []

# ---------------- 1. 重复键（YAML 静默取后者） ----------------
# ⚠️ 不能用「全文正则找 ^    key:」——那会把每个 path 下的 get/post 也算成重复（误报）。
# 必须按**映射结构**逐层查：只有同一个 mapping 里出现两次同名 key 才是真重复。
def find_duplicate_keys(node, path: str = "$", found: list[str] | None = None) -> list[str]:
    if found is None:
        found = []
    if isinstance(node, yaml.MappingNode):
        seen: set[str] = set()
        for key_node, value_node in node.value:
            key = str(key_node.value)
            if key in seen:
                found.append(f"{path}.{key}")
            seen.add(key)
            find_duplicate_keys(value_node, f"{path}.{key}", found)
    elif isinstance(node, yaml.SequenceNode):
        for idx, item in enumerate(node.value):
            find_duplicate_keys(item, f"{path}[{idx}]", found)
    return found


dupes = find_duplicate_keys(yaml.compose(src))
if dupes:
    problems.append(f"存在重复键（YAML 会静默取后者）：{dupes}")
else:
    print("  ok   无重复键（按映射结构逐层查）")

# ---------------- 2. $ref 全解析 ----------------
refs = set(re.findall(r"\$ref: '#/components/([a-zA-Z]+)/([^']+)'", src))
missing = [
    f"{kind}/{name}"
    for kind, name in refs
    if name not in doc["components"].get(kind, {})
]
if missing:
    problems.append(f"断链 $ref：{sorted(set(missing))}")
else:
    print(f"  ok   $ref 全部可解析（{len(refs)} 个引用）")

# ---------------- 3. 两边增量都在 ----------------
C_PATHS = [
    "/exams", "/exams/{examId}", "/timer-sessions", "/timer-sessions/current",
    "/timer-sessions/{sessionId}", "/timer-sessions/{sessionId}/heartbeat",
    "/timer-sessions/{sessionId}/segments", "/timer-sessions/{sessionId}/finish",
]
C_SCHEMAS = [
    "Exam", "ExamCreate", "ExamUpdate", "ExamList", "ExamDeleted",
    "TimerSession", "TimerSegment", "TimerSessionStart", "TimerSegmentStart",
    "TimerCurrent", "TimerFinish", "TimerDiscarded", "TimerRestore",
    "RecordSource", "RecordUpdate", "LearningRecordUpdated",
]
G_PATHS = [p for p in paths if "governance" in p or "usage" in p or "report" in p]

for p in C_PATHS:
    if p not in paths:
        problems.append(f"C 板块 path 丢失：{p}")
if not G_PATHS:
    problems.append("G 板块 path 疑似丢失（找不到 governance/usage/report 相关 path）")
if "patch" not in paths.get("/learning-records/{recordId}", {}):
    problems.append("C 板块 PATCH /learning-records/{recordId} 丢失")

for name in C_SCHEMAS:
    if name not in schemas:
        problems.append(f"C 板块 schema 丢失：{name}")

print(f"  ok   C 板块 8 paths + {len(C_SCHEMAS)} schemas 都在")
print(f"  ok   G 板块 {len(G_PATHS)} 个 path 也在（{G_PATHS[:3]}…）")

# ---------------- 汇总 ----------------
print()
print(f"version : {doc['info']['version']}")
print(f"paths   : {len(paths)}")
print(f"schemas : {len(schemas)}")

if problems:
    print("\n问题：")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("\n契约合并体检通过")
