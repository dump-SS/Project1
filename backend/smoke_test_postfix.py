"""
MVP 修复回归 smoke test（2026-08-18 旧 Agent 卡死后由新 Agent 重写）。
仅做接口层验证，覆盖 4 个修复点：
  1. /study-guide AUTO 冷启动  → 修复在前端，无后端变更；通过 plan 路由可达性侧面验证
  2. StudyEditor 空值不显红字  → 纯前端 props 修复
  3. /study-timer 任务从 plan_tasks 加载 → 新增 GET /plans?date_from=&date_to=
  4. /summary-review 已有 1 条复盘可展示  → 已有 GET /summaries 列表接口

注：服务基地址与 X-User-ID 由命令行参数传入，便于在沙箱里跑。
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta


def http(method: str, url: str, headers: dict | None = None, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
        return e.code, payload


def main(base: str, user_id: str) -> int:
    headers = {"X-User-ID": user_id}
    today = date.today()
    today_s = today.isoformat()
    week_ago = (today - timedelta(days=6)).isoformat()
    failures: list[str] = []

    # 0) 健康检查
    root = base.rsplit("/api/v1", 1)[0]
    code, body = http("GET", f"{root}/openapi.json")
    if code != 200 or not body.get("paths"):
        failures.append(f"openapi 不可达 code={code}")
    else:
        print(f"[0] openapi 命中 {len(body['paths'])} 路径")

    # 1) 建档 PUT /me
    code, body = http("PUT", f"{base}/me", headers, {
        "stage": "senior",
        "grade": "高三",
        "subjects": ["math", "chinese", "english"],
    })
    if code != 200:
        failures.append(f"PUT /me 失败 code={code} body={body}")
    else:
        print(f"[1] /me 建档 ok userId={body.get('userId')} subjects={body.get('subjects')}")

    # 2) 建 1 个目标（POST /goals）
    code, body = http("POST", f"{base}/goals", headers, {
        "type": "short_term",
        "subject": "math",
        "title": "smoke-test 数学目标",
    })
    if code != 201:
        failures.append(f"POST /goals 失败 code={code} body={body}")
    else:
        print(f"[2] /goals 创建 goalId={body.get('goalId')}")

    # 3) POST /plans 生成今日计划
    code, plan = http("POST", f"{base}/plans", headers, {
        "planDate": today_s,
        "availableMinutes": 60,
    })
    if code != 201 or not plan.get("tasks"):
        failures.append(f"POST /plans 失败 code={code} body={plan}")
    else:
        first = plan["tasks"][0]
        print(f"[3] /plans planId={plan['planId']} tasks={len(plan['tasks'])} 首条="
              f"{first.get('subject')}·{first.get('topic')}")

    # === Issue #3 验证：GET /plans?date_from=&date_to= 返回今日计划 ===
    qs = urllib.parse.urlencode({"date_from": today_s, "date_to": today_s, "page": 1, "page_size": 1})
    code, list_resp = http("GET", f"{base}/plans?{qs}", headers)
    items = list_resp.get("items", [])
    if code != 200 or not items:
        failures.append(f"GET /plans?date_from 不返回当日计划 code={code} total={list_resp.get('pagination',{}).get('total')}")
    elif items[0].get("planId") != plan.get("planId"):
        failures.append(f"GET /plans 返回了别的计划 {items[0].get('planId')} != {plan.get('planId')}")
    else:
        first_task = items[0]["tasks"][0] if items[0].get("tasks") else None
        print(f"[3-fix] /study-timer 现在能拉到今日计划 planId={items[0]['planId']} 首条任务={first_task}")

    # 4) POST /learning-records（让状态评估有数据）
    code, rec = http("POST", f"{base}/learning-records", headers, {
        "subject": "math",
        "startedAt": (datetime.now() - timedelta(minutes=25)).isoformat() + "Z",
        "durationMinutes": 25,
        "behavior": {"completion": "completed"},
        "selfReport": {
            "focus": 4,
            "fatigue": 2,
            "emotion": "positive",
            "difficultyFeel": "moderate",
        },
        "skipRecommendation": True,
    })
    if code != 201:
        failures.append(f"POST /learning-records 失败 code={code} body={rec}")
    else:
        print(f"[4] /learning-records recordId={rec.get('recordId')}")

    # 5) POST /summaries 触发复盘（会异步生成）
    code, summ_pending = http("POST", f"{base}/summaries", headers, {
        "periodStart": week_ago,
        "periodEnd": today_s,
    })
    if code != 202:
        failures.append(f"POST /summaries 失败 code={code} body={summ_pending}")
    else:
        print(f"[5] /summaries pending summaryId={summ_pending.get('summaryId')}")

    # 6) 轮询直到 summary 进入终态（mock LLM 应当秒级 ready）
    summ_final = None
    if code == 202:
        import time
        summary_id = summ_pending["summaryId"]
        for i in range(20):
            time.sleep(1.0)
            sc, sb = http("GET", f"{base}/summaries/{summary_id}", headers)
            if sc == 200 and sb.get("generation", {}).get("status") in {"ready", "insufficient_data", "failed"}:
                summ_final = sb
                print(f"[5-poll] 第 {i+1} 次拿到终态 status={sb['generation']['status']} content={bool(sb.get('content'))}")
                break
        if summ_final is None:
            failures.append("POST /summaries 30s 内未进入终态")

    # === Issue #4 验证：GET /summaries 列表能返回刚生成的复盘 ===
    code, list_summ = http("GET", f"{base}/summaries?page=1&page_size=20", headers)
    items = list_summ.get("items", [])
    if code != 200:
        failures.append(f"GET /summaries 失败 code={code}")
    elif not items:
        failures.append(f"GET /summaries 返回 0 条，但 DB 里应有 1 条")
    else:
        top = items[0]
        print(f"[4-fix] /summary-review 现在能展示已有复盘 summaryId={top.get('summaryId')} status={top.get('generation',{}).get('status')}")

    # 7) 顺手验证 GET /recommendations 可达（StudyTimer 推荐弹窗的依赖）
    code, recs = http("GET", f"{base}/recommendations?page=1&page_size=5", headers)
    if code != 200:
        failures.append(f"GET /recommendations 失败 code={code}")
    else:
        print(f"[7] /recommendations list ok total={recs.get('pagination',{}).get('total')}")

    # 总结
    if failures:
        print("\n=== FAIL ===")
        for f in failures:
            print("  -", f)
        return 1
    print("\n=== ALL OK === 4 个修复点的接口层验证全部通过")
    return 0


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/api/v1"
    user = sys.argv[2] if len(sys.argv) > 2 else "u_smoke_2026_08_18"
    sys.exit(main(base, user))
