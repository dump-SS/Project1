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

### 5xx 率（主查询，**带非法 JSON 守卫**）

```sql
SELECT
  ROUND(100.0 * COUNT(*) FILTER (WHERE event_type = 'http_5xx')
        / NULLIF(SUM(
            CASE WHEN event_type = 'http_request_total' THEN
              CASE
                WHEN payload_json IS NULL              THEN 0
                WHEN json_valid(payload_json)          THEN COALESCE((payload_json::jsonb ->> 'count')::int, 0)
                ELSE 0
              END
            ELSE 0 END), 0), 3)
        AS rate_pct
FROM analytics_events
WHERE category = 'ai_quality'
  AND event_type IN ('http_5xx', 'http_request_total')
  AND created_at >= now() - interval '28 days';
```

> **为什么必须带守卫**：`payload_json::jsonb` 遇到非法 JSON 会**直接抛错中断整个查询**（不是返回 NULL，是整条查询失败）。
> `json_valid()` 必须在 `::jsonb` **之前**判断——`CASE WHEN` 是短路的，只有校验通过才执行 cast。
> ⚠️ 若 Neon 上的 PG 版本 **< 16**，`json_valid()` 不存在（见下方「兼容 PG < 16」）。

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

### 兼容 PG < 16（`json_valid()` 不存在时）

先建一次守卫函数，之后写法完全相同：

```sql
CREATE OR REPLACE FUNCTION is_json(t text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  RETURN (t::jsonb IS NOT NULL);
EXCEPTION WHEN others THEN RETURN false;
END $$;
```

然后把上面主查询里的 `json_valid(payload_json)` 换成 `is_json(payload_json)`。

> ⚠️ **性能提醒**：pl/pgSQL 异常捕获比原生函数慢，**只在脏数据确实存在时才需要**。
> 正常情况下所有 `http_request_total` 行都由 `track_event` 写入、必为合法 JSON，
> 裸 cast 就够（快得多）。**守卫是为"有人手工插了脏数据"兜底**，不是常态路径。

### ⚠️ Neon 验证时必须覆盖的三个点

1. **上面那条带守卫的 SQL 能跑通**——先造一条 `payload_json` 为 NULL 的行、再造一条非法 JSON（如 `not-json`）的行，确认**查询仍返回结果而不是报错**。这是本条验证的核心。
2. **确认 Neon 的 PG 版本**：≥16 可直接用 `json_valid()`；<16 需先建 `is_json()` 函数（见上）。用 `SELECT version();` 确认。
3. **`round(numeric, 3)` 合法**——`100.0` 是 numeric、`numeric / bigint → numeric`，两参 round 成立。⚠️ 若算出 `double precision`，PG 会直接报 `function round(double precision, integer) does not exist`。

---

## ⚠️ 关于 SQLite 侧的 `json_valid`

实现侧已在 `http_error_tracking.py` 里对 SQLite 查询加了 `json_valid` 护栏。
**但 `json_valid()` 是 SQLite 的函数，PG 没有同名函数**（PG 16+ 才有内置版本，名字恰好相同）。
两侧机制不同，验的时候别混用。

---

## 口径变更时的处置

X0 裁定若要改分母口径（是否含 4xx），**两个版本都要同步**：
- 口径文档：`pilot-metrics-and-admission.md` §2.2
- 本文件的 SQL
- 实现侧常量（SQLite 版的对应常量在 `backend/http_error_tracking.py` 底部）
