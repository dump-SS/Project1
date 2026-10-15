# 修 F 板块两个 SigV4 缺陷（path 编码 + Content-Type 未签）

- agent：dev-6（harness: opencode）
- 派单：lead-1，ref `修 F 板块两个 SigV4 缺陷（path 编码 + Content-Type 未签）`（2026-10-15 23:55:29）
- 状态：**代码已改 + 测试全绿；未 commit、未 push、未部署**（brief 明令禁止）

## 一、改了什么

只改两个缺陷，不重构。共 3 个文件：

| 文件 | 改动 |
|---|---|
| `backend/r2_sigv4.py` | 缺陷 1 + 缺陷 2 的修复；新增 `canonical_path()` 作为签名 path 的单一真相源 |
| `backend/tests/test_r2_sigv4.py` | 修正 2 条**固化了 bug 的旧断言**，补 4 条新单测 |
| `backend/tests/test_r2_sigv4_wire.py` | **新增**：21 条本地回显服务器护栏（真实 HTTP 请求层） |

### 缺陷 1：签名 path 与请求 path 编码不一致

**根因**：编码职责被拆成两半，且两半用的不是同一套规则。

- 旧 `object_url()`：返回**未编码**的 key（`f"{base}/{key}"`）
- 旧 `sign_request()`：`path = urllib.parse.quote(parsed.path)`

于是签名算的是 `%40`，请求发的是 `@`；key 含空格时 urllib 直接 `InvalidURL` 拒发；含中文时 `UnicodeEncodeError`。

**修法**（brief 指定方向）：编码只做一次，收在 `object_url()`；`sign_request()` 改为「假定 URL 已编码」。

```python
return f"{base}/{urllib.parse.quote(key.lstrip('/'), safe='/')}"   # object_url
path = canonical_path(url)                                          # sign_request，不再 quote
```

`safe='/'` 必须保留 —— key 内部含 `/` 作目录分隔（`user/{userId}/{uuid}.png`），编码掉对象名就变了。

**为什么 GET 先例一直没暴露它**：`railway_build.py` 用的两个 key 是 `embeddings.index` / `refs.json`，**不含任何需编码字符**，两份逻辑「看起来都对」。生产的 `user_id` 是 `u_10237` 这类数字 ID，同样躲过了；只有邮箱形态的 `user_id`（如 dev-4 测试账号）才必现。

### 缺陷 2：Content-Type 发出但未签

**根因**：`r2_sigv4.py` 的模块 docstring 写着「Content-Type 会随请求发出但不参与签名 —— S3 规范允许」。**那是未经 R2 实证的错误假设**，我把它当既成事实写进了代码和测试。

AWS SigV4 的强制豁免名单是 `authorization` / `user-agent` / `x-amzn-trace-id` / `expect` / `transfer-encoding` / `connection` / `content-length` —— **不含 `content-type`**。所以「发了不签」本身就是违规，生产 PUT 实测 502（`SignatureDoesNotMatch` 被我路由映射成 502）。

**修法**：给了 `content_type` 就签入，header 名小写并按字典序插入（`content-type` 排在 `host` 前）。

```python
hdr_pairs["content-type"] = ct
signed_names.append("content-type")
signed_names.sort()
```

### 附带修正：一条**测不出缺陷**的假护栏

新增的 wire 测试第一版在测试里自己 `urlsplit(url)` 反推 path 来比对。回退验证时发现它**看不见错位**：`object_url` 一旦退回未编码，反推值也跟着退化成原始 `@`，恰好和发出的 `@` 相等 —— 测试仍然绿。

护栏必须观测**被测代码自己用的值**，不能复刻一份逻辑。故把签名 path 抽成 `canonical_path()`，`sign_request()` 与测试共用同一个函数。

## 二、测试

brief 指定命令：

```
pytest tests/test_r2_sigv4.py tests/test_f_media.py -q --no-header -p no:cacheprovider
→ 38 passed, exit 0
```

含新增 wire 护栏：

```
pytest tests/test_r2_sigv4_wire.py tests/test_r2_sigv4.py tests/test_f_media.py
→ 59 passed, exit 0
```

全量（确认无回归）：

```
pytest -q --no-header -p no:cacheprovider
→ 657 passed, 1 skipped, 11 warnings, exit 0
```

（修前全量 621 passed → 现 657，多出的 36 条即新护栏。）

### 护栏有效性：回退验证

不验证「测试能变红」的测试等于没有测试。我逐项临时回退并确认失败，再还原：

| 回退项 | 结果 |
|---|---|
| `canonical_path` 退回 `quote()` | **5 failed**，含 `@` / 空格 / 中文 / `+&` / `%` |
| `object_url` 退回不编码 | 3 failed（空格、中文发不出） |
| `content_type` 不再签名 | **7 failed**（6 条未签头 + 1 条 content-type） |
| 两处同时回退 | 12 failed |

`@` 错位的具体实证（回退态）：

```
签名=/epoch-x/user/dev6-r2-e2e-test%2540epochx.dev/aaaa….png
发出=/epoch-x/user/dev6-r2-e2e-test%40epochx.dev/aaaa….png
```

即双重编码 `%40 → %2540`。还原后 `TEMP-REVERT` 残留检查 = 0。

### 覆盖的 key 形态

普通数字 ID、`@`（邮箱形态 user_id）、空格、中文、`+&`、已含 `%20` 的 key —— 6 类。

## 三、本地回显对照

`C:\Users\29622\AppData\Local\Temp\opencode\sigv4_diag.py`（本地 HTTP 服务器 + monkeypatch `_require_config`，**不需要任何 R2 凭据**）。

**改后**：path 不一致 **0/5**，`SignedHeaders` 全部为 `content-type;host;x-amz-content-sha256;x-amz-date`。

| key | 签名 path | 收到 path | 一致 |
|---|---|---|---|
| 普通 | `/epoch-x/user/u_10237/aaa….png` | 同 | ✓ |
| `@` | `…/dev6-r2-e2e-test%40epochx.dev/…` | 同 | ✓ |
| 空格 | `…/with%20space.png` | 同 | ✓ |
| 中文 | `…/%E9%A2%98%E7%9B%AE%E7%85%A7%E7%89%87.png` | 同 | ✓ |
| `+&` | `…/a%2Bb%26c.png` | 同 | ✓ |

**改前**：path 不一致 2/5（空格、中文连请求都发不出），且所有用例 `content-type` 均未签。

诊断脚本仍报「有签非豁免头 5/5」，但逐项核对后**只剩 `accept-encoding`** —— urllib 自动加的，且**生产构建期的 GET（`railway_build.py`，同为 urllib）同样没签它却成功了**，有实证说明 R2 容忍。故未纳入签名，也未列为失败。

## 四、不确定的地方（请 lead-1 拍板）

1. **签名是否真被 R2 接受，仍未实证。** 本地能证明「请求 path == 签名 path」「非豁免头都在签名内」，但 R2 的判定只有 redeploy 后补跑生产实测才算数。这是本次唯一无法本地闭环的部分。
2. **`accept-encoding` 未签是否安全** —— 我的依据是生产 GET 先例的实证推断，非 R2 文档明文。若你要求严格合规，我可以把它也显式签入（需在 headers 里显式设置 `identity`，覆盖 urllib 默认值）。
3. **`docs/openapi.yaml` 的 `{key:path}`** —— 生产自动 OpenAPI 归一为 `{key}`，严格 OpenAPI 合规性仍未裁定。**与本 brief 无关，未动。**
4. **`backend/routes/f_media.py:162` 注释错误**（写「类型放 query」，实际读 `Content-Type` header）—— brief 限定只改两处，**未动**。

## 五、约束遵守

- 未 push、未部署（brief 明令）。
- 未申请临时 R2 凭据（brief 明令）。
- 只用本地回显服务器复现。
- 只显式 `git add` 自己的文件，未用 `-A`，未 reset/clean/stash。
- 改动文件：`backend/r2_sigv4.py`（M）、`backend/tests/test_r2_sigv4.py`（M）、`backend/tests/test_r2_sigv4_wire.py`（新增）。工作区其余未追踪文件为他人所有，未触碰。