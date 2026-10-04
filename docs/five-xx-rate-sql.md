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
                WHEN payload_json IS JSON               THEN COALESCE((payload_json::jsonb ->> 'count')::int, 0)
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
> `IS JSON` 必须在 `::jsonb` **之前**判断——`CASE WHEN` 是短路的，只有校验通过才执行 cast。
> `IS JSON` 是 **SQL/JSON 标准谓词、PG 16 起可用**（实测 Neon 为 PG 18.6，直接可用）。
> ⚠️ 它**不是** `json_valid()`——后者是 MySQL/SQLite 的函数，PG 从来没有过（见文末修正记录）。

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

### 若将来要支持 PG 16 以下（`IS JSON` 不存在时）

先建一次守卫函数，之后写法完全相同：

```sql
CREATE OR REPLACE FUNCTION is_json(t text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  RETURN (t::jsonb IS NOT NULL);
EXCEPTION WHEN others THEN RETURN false;
END $$;
```

然后把主查询里的 `payload_json IS JSON` 换成 `is_json(payload_json)`。

> ⚠️ **性能提醒**：pl/pgSQL 异常捕获比原生函数慢，**只在脏数据确实存在时才需要**。
> 正常情况下所有 `http_request_total` 行都由 `track_event` 写入、必为合法 JSON，
> 裸 cast 就够（快得多）。**守卫是为"有人手工插了脏数据"兜底**，不是常态路径。

### ⚠️ Neon 验证时必须覆盖的三个点（2026-10-04 已实测通过）

**实测结论**（dev-4 在 Neon PG 18.6 上跑的）：
- ✅ 守卫生效：造 `payload_json` 为 NULL 与 `'not-json'` 两行脏数据后，主查询**返回 `rate_pct=25.000`、未报错**
- ✅ **Neon 是 PG 18.6**（`server_version_num=180006`）
- ✅ `round(numeric, 3)` 合法，实测返回三位小数，未出现 `round(double precision) does not exist`
- ✅ 「`payload_json::jsonb` 遇非法 JSON 抛错中断整条查询」描述准确（实测复现 `invalid input syntax for type json`）
- ✅ CASE 短路语义成立，守卫放在 cast 之前是对的
- ✅ 分子查询验过：`err_5xx=5 / err_5xx_anonymous=2`，与造数意图一致
- ✅ 清理到位：`analytics_events` 0→0、残留探针行 0、`kb_points` 3391、关系 3127、`kb_subjects` 9、`alembic_version` 未动

**⚠️ 本条曾被我写错（2026-10-04 修正）**：本文早先写「PG 16+ 才有内置 `json_valid()`」——
**这是事实错误。`json_valid()` 是 MySQL / SQLite 的函数，PostgreSQL 从来没有过，任何版本都没有。**
dev-4 实测 `SELECT json_valid('not-json')` 直接报 `function json_valid(text) does not exist`，
穷举非系统 schema 与 129 个 `json%` 内置函数均无此项。

**正确的做法是上面主查询用的 `IS JSON`** —— SQL/JSON 标准谓词，**PG 16 起可用**（Neon 18.6 直接可用），
无需自建函数，也就不存在「函数不在迁移里、新库没有」的问题。

### 若将来要支持 PG 16 以下（当前 Neon 不需要）

`IS JSON` 在 PG 16 以下不存在，才需要自建 `is_json()`：

```sql
CREATE OR REPLACE FUNCTION is_json(t text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  RETURN (t::jsonb IS NOT NULL);
EXCEPTION WHEN others THEN RETURN false;
END $$;
```

> ⚠️ **自建函数必须走 Alembic 迁移，不能手建。**（dev-4 2026-10-04 指出）
> 手建的话它是**不受迁移管理**的 schema 对象：从迁移链建出来的新库（新分支 / 新环境 / CI /
> 灾备恢复）不会有它，那里跑 5xx 查询就 `function is_json does not exist`——
> 而 5xx 率是 §2.2「连续 4 周 5xx ≤ 1%」的验收门，**读不出来就判不了**。
> 也就是说手建会让这条验收门**只在「手工建过函数的那个库」上成立**。
> 当前用 `IS JSON` 就没有这个问题；若将来真要自建，务必配一条迁移 + 一个「函数是否存在」的断言测试。
>
> ⚠️ 性能提醒：`IS JSON` 是原生谓词，比 pl/pgSQL 异常捕获快得多。
> 即便如此，守卫仍是**为「有人手工插了脏数据」兜底**，不是常态路径——
> 正常情况下所有 `http_request_total` 行都由 `track_event` 写入、必为合法 JSON。

---

## 两库守卫机制不同，别混用

| 库 | 守卫写法 | 出处 |
|---|---|---|
| **SQLite** | `json_valid(payload_json)` | 实现侧 `http_error_tracking.py` 已内置（SQLite 的 JSON1 扩展提供该函数） |
| **Postgres / Neon** | `payload_json IS JSON`（SQL/JSON 标准谓词，PG 16+） | 本文档主查询 |

**`json_valid()` 是 SQLite / MySQL 的函数，PostgreSQL 从来没有过。** 实现侧的 SQLite 查询注释里
也已写明这一点（"PG 无 json_valid，需用 CASE 判空"）——**是本文档早先写错，实现侧一直是对的。**

---

## 口径变更时的处置

X0 裁定若要改分母口径（是否含 4xx），**两个版本都要同步**：
- 口径文档：`pilot-metrics-and-admission.md` §2.2
- 本文件的 SQL
- 实现侧常量（SQLite 版的对应常量在 `backend/http_error_tracking.py` 底部）
