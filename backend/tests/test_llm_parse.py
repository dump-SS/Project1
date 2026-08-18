"""LLM 输出解析容错测试：markdown 围栏提取、混合文本、非法输入。"""

from __future__ import annotations

from ai_suggestion import _extract_json_block, _parse_llm_items, _parse_llm_summary


def test_extract_plain_json_untouched():
    """纯 JSON 输入，围栏提取应原样返回（两层容错第 1 层不干预）。"""
    text = '{"items": [{"title": "A", "content": "a"}]}'
    assert _extract_json_block(text) == text


def test_extract_markdown_fenced_json():
    """模型常见输出：```json ... ``` 包裹。"""
    text = '以下是建议：\n```json\n{"items": [{"title": "A", "content": "a"}]}\n```\n希望有帮助。'
    extracted = _extract_json_block(text)
    assert extracted.startswith("{")
    assert extracted.endswith("}")


def test_extract_bare_fence():
    """不带 json 标记的围栏也应提取。"""
    text = "```\n{\"items\": []}\n```"
    assert _extract_json_block(text) == '{"items": []}'


def test_parse_llm_items_pure_json():
    text = '{"items": [{"title": "A", "content": "a"}, {"title": "B", "content": "b"}]}'
    items = _parse_llm_items(text)
    assert items is not None and len(items) == 2
    assert items[0]["title"] == "A"


def test_parse_llm_items_markdown_wrapped():
    """围栏 + 前后说明文字——真实模型最常见的'不守规矩'输出。"""
    text = (
        "好的，根据状态生成如下：\n"
        "```json\n"
        '{"items": [{"title": "保持节奏", "content": "状态不错，继续保持"}]}\n'
        "```\n"
        "如果需要调整请告诉我。"
    )
    items = _parse_llm_items(text)
    assert items is not None and len(items) == 1
    assert items[0]["title"] == "保持节奏"


def test_parse_llm_items_bare_list():
    """直接返回顶层数组（不带 items 包装）。"""
    items = _parse_llm_items('[{"title": "A", "content": "a"}]')
    assert items is not None and len(items) == 1


def test_parse_llm_items_garbage_returns_none():
    """完全不是 JSON 的输出返回 None，由上层走模板兜底。"""
    assert _parse_llm_items("这是一段纯文本建议，保持节奏即可。") is None
    assert _parse_llm_items("") is None


def test_parse_llm_items_empty_items_list():
    """items 空数组视为无效（不允许'成功但 0 条建议'，应走兜底）。"""
    assert _parse_llm_items('{"items": []}') is None


def test_parse_llm_summary_markdown_wrapped():
    text = (
        "```json\n"
        '{"overview": "本周状态稳定", "patterns": ["x"], "suggestions": ["y"], "encouragement": "z"}\n'
        "```"
    )
    data = _parse_llm_summary(text)
    assert data is not None
    assert data["overview"] == "本周状态稳定"


def test_parse_llm_summary_invalid():
    assert _parse_llm_summary("纯文本") is None
