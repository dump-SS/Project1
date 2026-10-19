"""R2 测试对象清理（幂等，可反复跑）。

## 它解决什么

2026-10-18 前后连续两轮出现同一类事故：**测试跑完了、报告也写了「已清干净」，
但 R2 里其实还留着对象**（一次 5 个对象 + 1 条会话行）。

根因不是「忘了清理」，而是**清理写在被测进程的 `finally` 里**：
进程被 shell 超时 / Ctrl-C / 断网杀掉时，`finally` 未必执行。
把清理放进被测进程，等于让「被测进程的生命周期」决定「清理是否发生」——
而那恰恰是我们控制不了的变量。

所以改成三段解耦：

1. 测试脚本**每上传一个 key 就立刻 append** 到 manifest（append-only，不截断）
2. 清理是**另一个进程**，读 manifest 逐个幂等 DELETE
3. 两者解耦：测试被杀 → manifest 仍在 → 随时重跑本脚本收干净

## 幂等性

`DELETE` 一个不存在的对象返回 **204**（契约 v1.11.0），所以**重复运行是安全的**，
不会因为「对象已经没了」而报错。

## 用法

```powershell
# 1) 取生产 DATABASE_URL（**不要写进文件**），管道进本脚本
$env:DATABASE_URL = (railway variables --service backend --json | ConvertFrom-Json).DATABASE_URL
$env:DATABASE_URL | python scripts/r2_sweep.py <manifest.json>
```

manifest 是一个 JSON 数组，形如：

```json
["user/u_10237/abc.png", "user/u_10237/def.png"]
```

不传参数时默认读 `%TEMP%/opencode/r2_manifest.json`。

## 边界

- 只删 manifest 里列出的 key，**不会**扫桶、不会碰 `embeddings.index` / `refs.json`
- 只处理**当前用户**（`UID`）名下的对象；别人的 key 会 403 并被记为失败项
- 临时会话（auth_sessions 行）在 `finally` 里删掉
"""
import hashlib
import json
import pathlib
import secrets
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

API = "https://api.epochx.net"
UID = "u_10237"
MANIFEST = pathlib.Path(
    sys.argv[1] if len(sys.argv) > 1
    else r"C:\Users\29622\AppData\Local\Temp\opencode\r2_manifest.json"
)

PG_URL = sys.stdin.read().strip()
if not PG_URL or "://" not in PG_URL:
    print("[sweep] stdin 没拿到 DATABASE_URL，退出")
    sys.exit(1)

# ⚠️ 说清「我要动哪个库」：让误连变成看得见的事（不打印口令）
_host = PG_URL.split("@")[-1].split("/")[0] if "@" in PG_URL else "?"
print(f"[sweep] 目标库 host={_host}")


def call(method, path, sid=None, data=None, ctype=None, body=None):
    h = {"User-Agent": "epochx-r2-sweep/1.0"}
    if sid:
        h["Cookie"] = f"sid={sid}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    elif ctype:
        h["Content-Type"] = ctype
    req = urllib.request.Request(API + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b""
    except Exception as e:
        return 0, f"TRANSPORT:{type(e).__name__}:{e}".encode()


# ---------- 读 manifest（append-only，允许不存在/为空） ----------
keys: list[str] = []
if MANIFEST.exists():
    try:
        raw = MANIFEST.read_text(encoding="utf-8").strip()
        if raw:
            data = json.loads(raw)
            keys = list(dict.fromkeys(data)) if isinstance(data, list) else list(data.keys())
    except Exception as e:
        print(f"[manifest] 解析失败 {MANIFEST.name}: {type(e).__name__}: {e}")

print(f"[manifest] {MANIFEST.name} 记录 {len(keys)} 个 key")
if not keys:
    print("[sweep] 无需清理，退出（幂等：重复运行安全）")
    sys.exit(0)

# ---------- 临时会话 ----------
sid = secrets.token_urlsafe(24)
tok = hashlib.sha256(sid.encode()).hexdigest()

import psycopg2  # noqa: E402

conn = psycopg2.connect(PG_URL)
conn.autocommit = True
cur = conn.cursor()
cur.execute(
    "INSERT INTO auth_sessions (token_hash, user_id, expires_at, created_at)"
    " VALUES (%s,%s,%s,%s)",
    (tok, UID, int((time.time() + 1800) * 1000),
     time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())),
)

deleted, already_gone, failed = 0, 0, []
try:
    for key in keys:
        s, b = call("DELETE", f"/api/v1/f/media/{key}", sid)
        if s == 204:
            deleted += 1
        elif s == 403:
            failed.append((key, f"403 {b[:80]!r}"))
        else:
            failed.append((key, f"HTTP {s} {b[:80]!r}"))

    # 复核：逐个 GET，必须全是 404
    still_there = []
    for key in keys:
        s, _ = call("GET", f"/api/v1/f/media/{key}", sid)
        if s != 404:
            still_there.append((key, s))
finally:
    cur.execute("DELETE FROM auth_sessions WHERE token_hash=%s", (tok,))
    sess_removed = cur.rowcount
    cur.close()
    conn.close()

print(f"[sweep] DELETE 成功 {deleted} / 共 {len(keys)}")
print(f"[sweep] 删后仍可 GET 到（非 404）: {still_there if still_there else '无'}")
print(f"[sweep] 失败项: {failed if failed else '无'}")
print(f"[sweep] 临时会话已删除 rowcount={sess_removed}")
if still_there or failed:
    sys.exit(2)
print("[sweep] 完成。manifest 保留以便下次重跑（幂等）。")
