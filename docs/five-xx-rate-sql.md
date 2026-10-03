# 5xx 率查询 SQL（SQLite / Postgres）

> 用途：`docs/pilot-metrics-and-admission.md` §2.2「连续 4 周后端 5xx 率 ≤ 1%」的验收查询。
> **状态**：SQLite 版已实测（真 app 造数 100 次 → 率与手算一致）；**Postgres/Neon 版尚未实测**，见 §5 第 6 项。
> 来源：dev-2 实现（PR #47，`feat/5xx-tracking`），此处固化以免 SQL 文本只存在于本地分支的某个 commit 里。

## 口径（先读这个，否则会算错）

| 项 | 值 |
|---|---|
| 统计对象 | 仅 `/api/v1/**` 的 API 请求 |
| **分母** | `SUM(payload.count)`（该周期请求数 **− 4xx**，实现侧在累计时已扣除） |
| **分子** | `event_type='http_5xx'` 的事件条数（逐条实时落，非聚合） |
| 排除 | 4xx（计在 `payload.count4xx`，**仅供诊断，不作分母**）、`/health`、静态资源 |
| 周期 | 近 28 天（对应「放号起连续 4 周」的比对窗口，按需改） |
| 数据表 | `analytics_events`，`category='ai_quality'` |

**两类事件**：
- `eventType=http_5xx` —— 分子，5xx 逐条落，payload 含 `path` / `method` / `statusCode` / `durationMs` / `userScoped`
- `eventType=http_request_total` —— 分母，进程内累计后定时 flush 的汇总行，payload 含 `count`（= 分母）/ `count4xx`（诊断）/ `windowMinutes` / `userScoped`

---

## SQLite（本地开发库 `backend/data.db`）

### 5xx 率（主查询）

```sql
SELECT
  ROUND(100.0 * SUM(CASE WHEN event_type = 'http_5xx' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN event_type = 'http_request_total'
                         THEN CAST(json_extract(payload_json, '$.count') AS INTEGER)
                         ELSE 0 END), 0), 3) AS rate_pct
FROM analytics_events
WHERE category = 'ai_quality'
  AND event_type IN ('http_5xx', 'http_request_total')
  AND created_at >= datetime('now', '-28 days');
```

### 分子：5xx 按天拆分（含匿名占比）

```sql
SELECT date(created_at)                          AS day,
       COUNT(*)                                  AS err_5xx,
       SUM(CASE WHEN user_id = 'system' THEN 1 ELSE 0 END) AS err_5xx_anonymous
FROM analytics_events
WHERE category = 'ai_quality'
  AND event_type = 'http_5xx'
GROUP BY day
ORDER BY day;
```

> `user_id='system'` 是**系统级事件**（登录接口等无登录态请求——这类恰恰是重点盯的对象），
> **不参与任何用户维度指标**。本条查询的分母是请求数，不依赖 user_id 维度。

---

## Postgres / Neon（目标环境，⚠️ 尚未实测）

### 5xx 率（主查询）

```sql
SELECT
  ROUND(100.0 * COUNT(*) FILTER (WHERE event_type = 'http_5xx')
        / NULLIF(SUM(CASE WHEN event_type = 'http_request_total'
                          THEN (payload_json::jsonb ->> 'count')::int ELSE 0 END), 0), 3)
        AS rate_pct
FROM analytics_events
WHERE category = 'ai_quality'
  AND event_type IN ('http_5xx', 'http_request_total')
  AND created_at >= now() - interval '28 days';
```

### 分子：5xx 按天拆分（含匿名占比）

```sql
SELECT (occurred_at AT TIME ZONE 'UTC')::date      AS day,
       COUNT(*)                                    AS err_5xx,
       COUNT(*) FILTER (WHERE user_id = 'system')  AS err_5xx_anonymous
FROM analytics_events
WHERE category = 'ai_quality'
  AND event_type = 'http_5xx'
GROUP BY day
ORDER BY day;
```

### ⚠️ Neon 验证时必须覆盖的三个点

1. **`payload_json::jsonb` 遇非法 JSON 会直接抛错中断整个查询。** `http_request_total` 的行都由 `track_event` 写、必为合法 JSON，所以当前安全；但**若有人手工插过脏数据，查询就会炸**。验证时请专门造一条 `payload_json` 为 NULL 或非法 JSON 的行，确认查询仍能安全返回。
   （SQLite 版用 `json_extract`，同类风险；实现侧已加 `json_valid` 护栏规避。）
2. **`round(numeric, 3)` 合法**——`100.0` 是 numeric、`numeric / bigint → numeric`，两参 round 成立。⚠️ 若算出 `double precision`，PG 会直接报 `function round(double precision, integer) does not exist`。
3. **`COUNT(*) FILTER` 与 `interval '28 days'`** 均为标准 PG 写法，无需额外依赖。

---

## 口径变更时的处置

X0 裁定若要改分母口径（是否含 4xx），**两个版本都要同步**：
- 口径文档：`pilot-metrics-and-admission.md` §2.2
- 本文件的 SQL
- 实现侧常量（SQLite 版的对应常量在 `backend/http_error_tracking.py` 底部）
