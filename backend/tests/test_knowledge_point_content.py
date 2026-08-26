"""知识点库内容字段测试（2026-08-25 建表）。

覆盖：
- 带全 7 个内容字段的知识点，GET /points/{id} 返回新字段，典型错误/关键词是数组
- 老行（无内容字段）detail 返回 null/空，不报错（向后兼容）
- 脏 JSON 文本降级为空数组，不 500
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models.knowledge import KnowledgePoint, KnowledgeSubject

client = TestClient(app)


def _ensure_subject():
    db = SessionLocal()
    try:
        if db.get(KnowledgeSubject, "ks_math") is None:
            db.add(KnowledgeSubject(id="ks_math", code="SX", name="数学", grade_band="senior", version="1.0"))
            db.commit()
    finally:
        db.close()


def test_detail_returns_content_fields():
    _ensure_subject()
    db = SessionLocal()
    try:
        db.add(KnowledgePoint(
            id="kp_full", subject_code="SX", code="math.func.mono",
            name="函数单调性", definition="函数值随自变量增减的性质",
            difficulty=3, exam_weight=0.1,
            explanation="用'你'字称呼的讲解……判断函数在区间上是增还是减。",
            frequency=4,
            typical_errors=json.dumps(["忽视定义域", "把导数符号看反", "端点取值遗漏"]),
            example="[仿题]已知f(x)=x²，求其单调区间。x<0减，x>0增。",
            keywords=json.dumps(["单调性", "增函数", "减函数"]),
            module_path="必修一/P3/函数的性质",
            source_version="人教A版2019",
        ))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/knowledge/points/kp_full")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "函数单调性"
    assert body["frequency"] == 4
    assert body["typicalErrors"] == ["忽视定义域", "把导数符号看反", "端点取值遗漏"]
    assert body["keywords"] == ["单调性", "增函数", "减函数"]
    assert body["example"].startswith("[仿题]")
    assert body["modulePath"] == "必修一/P3/函数的性质"
    assert body["sourceVersion"] == "人教A版2019"
    assert body["explanation"]


def test_detail_legacy_point_returns_nulls():
    _ensure_subject()
    db = SessionLocal()
    try:
        db.add(KnowledgePoint(
            id="kp_legacy", subject_code="SX", code="math.legacy",
            name="旧知识点", definition="无内容字段的旧行",
        ))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/knowledge/points/kp_legacy")
    assert r.status_code == 200
    body = r.json()
    assert body["typicalErrors"] == []  # None → 空数组
    assert body["keywords"] == []
    assert body["explanation"] is None
    assert body["frequency"] == 3  # 有列默认值（频次默认 3），非 None


def test_detail_dirty_json_falls_back_to_empty():
    _ensure_subject()
    db = SessionLocal()
    try:
        db.add(KnowledgePoint(
            id="kp_dirty", subject_code="SX", code="math.dirty",
            name="脏数据", definition="x",
            typical_errors="not-a-json",
            keywords="[broken",
        ))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/knowledge/points/kp_dirty")
    assert r.status_code == 200
    body = r.json()
    assert body["typicalErrors"] == []
    assert body["keywords"] == []
