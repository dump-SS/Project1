"""openapi.yaml 结构完整性测试（X0 · 契约守门）。

docs/openapi.yaml 是唯一契约真相源——但它此前没有被任何测试守护：
一次 YAML 缩进错误或失效的 $ref（改契约时很容易发生）不会让任何业务测试变红，
问题会一直潜伏到前端/QA 按契约对接时才爆。本测试补上这层：

1. 文件可被 YAML 解析，且是 OpenAPI 3.x 文档；
2. 所有本地 $ref（#/components/...）都能解析到真实 schema/response/parameter；
3. 每个 path 至少有一个 operation，operationId 不重复（FastAPI 按 operationId 生成
   客户端方法名，重复会让 codegen 歧义——真实事故：重复挂载时报 Duplicate Operation ID）；
4. info.version 与 docs/README.md「唯一契约真相源」行内标注的版本一致（两个文件
   手工同步，防漂移——漂移了这里红，提醒改的人同步文档地图）。

刻意不做的事：不校验 schema 数量/paths 数量（每次契约变更都要改测试，摩擦大于收益）；
不校验字段级语义（那是 X0 评审的职责，测试守不住）。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover — pyyaml 由 fastapi 依赖链带入，缺失即环境问题
    yaml = None  # type: ignore[assignment]

DOCS = Path(__file__).resolve().parents[2] / "docs"
OPENAPI_PATH = DOCS / "openapi.yaml"


@pytest.fixture(scope="module")
def spec() -> dict:
    if yaml is None:
        pytest.fail("pyyaml 不可用，无法校验契约")
    with OPENAPI_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _iter_local_refs(node, prefix=""):
    """递归产出所有本地 $ref（#/ 开头）。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith("#/"):
                yield prefix, value
            else:
                yield from _iter_local_refs(value, prefix=f"{prefix}/{key}" if prefix else key)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _iter_local_refs(item, prefix=f"{prefix}[{i}]")


def _resolve_ref(spec: dict, ref: str):
    target = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or part not in target:
            return None
        target = target[part]
    return target


def test_openapi_parses_as_3x_document(spec):
    assert spec.get("openapi", "").startswith("3."), "必须是 OpenAPI 3.x"
    assert spec.get("info", {}).get("version"), "info.version 缺失"
    assert isinstance(spec.get("paths"), dict) and spec["paths"], "paths 缺失或为空"
    components = spec.get("components", {})
    assert isinstance(components.get("schemas"), dict), "components.schemas 缺失"


def test_all_local_refs_resolve(spec):
    broken = [
        (where, ref)
        for where, ref in _iter_local_refs(spec)
        if _resolve_ref(spec, ref) is None
    ]
    assert not broken, f"{len(broken)} 个失效的本地 $ref：\n" + "\n".join(
        f"  {ref}（位于 {where}）" for where, ref in broken[:10]
    )


def test_paths_have_operations_and_unique_operation_ids(spec):
    http_methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
    dup: dict[str, str] = {}
    problems: list[str] = []

    for path, item in spec["paths"].items():
        ops = {k: v for k, v in item.items() if k in http_methods}
        if not ops:
            problems.append(f"{path} 没有任何 operation")
            continue
        for method, op in ops.items():
            op_id = op.get("operationId")
            if not op_id:
                problems.append(f"{path} {method} 缺 operationId")
            elif op_id in dup:
                problems.append(f"operationId 重复：{op_id}（{dup[op_id]} 与 {path} {method}）")
            else:
                dup[op_id] = f"{path} {method}"

    assert not problems, "契约结构问题：\n" + "\n".join(f"  {p}" for p in problems[:10])


def test_version_synced_with_docs_readme(spec):
    """契约版本与 docs/README.md 文档地图标注的版本一致（两处手工同步，防漂移）。"""
    contract_version = spec["info"]["version"]
    readme = (DOCS / "README.md").read_text(encoding="utf-8")
    m = re.search(r"openapi\.yaml`?\s*\|?\s*\*\*[^*]*\*\*（?v([0-9.]+)", readme)
    assert m, "docs/README.md 中未找到契约版本标注（格式约定：openapi.yaml …（vX.Y.Z …））"
    assert m.group(1) == contract_version, (
        f"契约版本漂移：openapi.yaml={contract_version}，docs/README.md=v{m.group(1)}。"
        "改契约时请同步文档地图的「唯一契约真相源」行。"
    )
