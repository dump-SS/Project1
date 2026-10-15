"""R2（S3 兼容）SigV4 签名 —— 零依赖，仅用标准库。

## 为什么需要这个模块

R2 的**对象**读写走 S3 兼容端点（`<account>.r2.cloudflarestorage.com/<bucket>/<key>`），
**只认 AWS SigV4**；`Authorization: Bearer <R2 API token>` 只能打 Cloudflare 的管理接口。

`scripts/railway_build.py` 里已有一个手写先例（`_sigv4_headers`），但它只做 **GET**
（`payload_hash = sha256(b"")`）。F 板块要**上传**（PUT，带请求体），所以这里把它泛化。

## 为什么不直接用 boto3

`backend/pyproject.toml` 没有 boto3，`python-multipart` 也没装（写了 `File(...)` 会让
FastAPI 启动直接报错）。F 板块的最小链路要**零新依赖**，所以手写。

## 与先例一致、不可改的三个点

1. **region 固定 `auto`、service 固定 `s3`** —— R2 的要求。用错会 `403 SignatureDoesNotMatch`。
2. **`x-amz-content-sha256` 必须签进 canonical headers** —— 少了会被 400
   `Missing x-amz-content-sha256`（这是先例里踩过的坑，见 `_sigv4_headers` 的 docstring）。
3. **`x-amz-content-sha256` 的值是请求体的 sha256**（不是字面量 `UNSIGNED-PAYLOAD`）——
   所以 GET 空体时它等于 `sha256(b"")`。

## 签名范围说明

默认只签 `host` / `x-amz-content-sha256` / `x-amz-date` 三个头（与 `railway_build.py` 先例一致）。

**⚠️ 缺陷修复（2026-10-15）**：本模块原先写着「`Content-Type` 会随请求发出但不参与签名
—— S3 规范允许这样做」。**那是未经 R2 实证的错误假设**，生产 PUT 实际返回 502
（`SignatureDoesNotMatch` 被路由映射成 502）。AWS SigV4 的豁免名单是
`authorization / user-agent / x-amzn-trace-id / expect / transfer-encoding /
connection / content-length` —— **不含 `content-type`**，所以凡发非豁免头就应签入。
现在给了 `content_type` 就把它签进去（并按字典序插到 `host` 之前）。

**⚠️ 缺陷修复（2026-10-15）**：原先 path 由本模块 `quote()`、而请求 URL 用未编码的 key，
两边不一致 → 含 `@`/空格/中文的 key 必然 `SignatureDoesNotMatch`。
现在**编码统一收在 :func:`object_url`**，本模块假定传入的 URL 已编码、不再重复 quote
（重复 quote 会变 `%2520`）。这就是为什么 ``railway_build.py`` 的 GET 先例一直没暴露它 ——
那两个 key（`embeddings.index` / `refs.json`）**不含任何需要编码的字符**，
「先例看起来对」只是输入简单。

## 仍未对真实 R2 验证的部分

⚠️ 修完之后，本地回显服务器可验证「请求 path == 签名 path」「发出的非豁免头都在签名内」，
但**签名是否被 R2 接受**，仍要等 redeploy 后补跑生产实测才算最终确认。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import urllib.parse

# R2 的固定值，不是随便填的（见模块 docstring 第 1 点）
_R2_REGION = "auto"
_R2_SERVICE = "s3"
_ALGORITHM = "AWS4-HMAC-SHA256"


class SigV4Error(ValueError):
    """签名输入不合法（如空凭据、非 http(s) URL）。"""


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def payload_hash(body: bytes) -> str:
    """请求体的 sha256（十六进制）。GET 空体时等于 sha256(b"")。"""
    return hashlib.sha256(body or b"").hexdigest()


def canonical_path(url: str) -> str:
    """返回**签名实际使用**的 canonical path。

    单独抽出来只有一个理由：让测试能观察到 :func:`sign_request` 真正签的那个值。
    早期版本的回归测试是自己在测试里从 URL 反推 path 来比对，结果**测不出缺陷** ——
    一旦 ``object_url`` 退回返回未编码 key，反推出来的值也跟着变成原始字符，
    于是「签名 %40 / 发出 @」这种错位在测试里看起来是**一致**的。
    护栏必须观测被测代码自己用的值，而不是复刻一份逻辑。

    ⚠️ 这里**不做任何 encode/decode**（缺陷修复）。编码的唯一职责在 :func:`object_url`，
    否则会编码两次（``%2520``），与请求行同样对不上。
    """
    return urllib.parse.urlsplit(url).path or "/"


def sign_request(
    method: str,
    url: str,
    access_key: str,
    secret_key: str,
    body: bytes = b"",
    *,
    content_type: str | None = None,
) -> dict[str, str]:
    """为一次 R2 对象操作生成 SigV4 请求头。

    参数
    ----
    method
        HTTP 方法，大小写不敏感。R2 对象操作实际用到 ``GET`` / ``PUT`` / ``DELETE``。
    url
        完整 URL，形如 ``https://<account>.r2.cloudflarestorage.com/<bucket>/<key>``。
        key 里的特殊字符由本函数负责 percent-encode（先例也这么做）。
    access_key / secret_key
        R2 的 S3 API 凭据（对应 ``KB_VECTOR_ACCESS_KEY_ID`` /
        ``KB_VECTOR_SECRET_ACCESS_KEY``）。空值直接抛错——**不静默降级成匿名请求**，
        因为匿名对私有桶必然 403，失败得更难查。
    body
        请求体。``PUT`` 上传时必须传真实字节，否则 ``x-amz-content-sha256`` 与实际
        载荷不符，R2 会拒。
    content_type
        给了就随请求发出，但**不参与签名**（见模块 docstring「签名范围说明」）。

    返回
    ----
    可直接展开进 HTTP 请求头的 dict（含 ``Host``）。
    """
    if not access_key or not secret_key:
        raise SigV4Error("缺少 R2 S3 凭据（access_key / secret_key 为空）")

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SigV4Error(f"不是可签名的绝对 URL: {url!r}")

    m = method.upper()
    host = parsed.netloc
    # ⚠️ 这里**不再 quote**（缺陷修复）：编码已由 object_url 统一完成。
    # 签名用的 path 必须与请求行实际发出的 path **逐字节一致**，否则 SignatureDoesNotMatch。
    # 取值走 canonical_path —— 它是签名 path 的单一真相源，测试也用它来观测。
    # 重复 quote 会把 `%40` 变成 `%2540`、空格变成 `%2520`，同样对不上。
    path = canonical_path(url)

    now = _dt.datetime.now(_dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    ph = payload_hash(body)

    # 顺序必须与 AWS 规范一致：header 名小写、值去首尾空白、**字典序**、末尾换行。
    # content-type 在字典序里排在 host 之前，别按书写顺序拼。
    signed_names = ["host", "x-amz-content-sha256", "x-amz-date"]
    hdr_pairs = {"host": host, "x-amz-content-sha256": ph, "x-amz-date": amz_date}

    if content_type:
        # 缺陷修复：Content-Type 既然要随请求发出，就必须签进去。
        # AWS SigV4 的豁免名单只有
        # authorization / user-agent / x-amzn-trace-id / expect /
        # transfer-encoding / connection / content-length —— **不含 content-type**。
        # 之前「发了不签」是我未经 R2 实证写进 docstring 的错误假设，
        # 很可能就是生产 PUT 返回 502 的直接原因（未签的非豁免头 → SignatureDoesNotMatch）。
        ct = content_type.strip()
        if ct:
            hdr_pairs["content-type"] = ct
            signed_names.append("content-type")
            signed_names.sort()

    canonical_headers = "".join(f"{n}:{hdr_pairs[n]}\n" for n in signed_names)
    signed_headers = ";".join(signed_names)

    canonical_request = _canonical_request(m, path, canonical_headers, signed_headers, ph)

    scope = f"{date_stamp}/{_R2_REGION}/{_R2_SERVICE}/aws4_request"
    string_to_sign = _string_to_sign(amz_date, scope, canonical_request)

    k_date = _sign(("AWS4" + secret_key).encode(), date_stamp)
    k_region = _sign(k_date, _R2_REGION)
    k_service = _sign(k_region, _R2_SERVICE)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(
        k_signing, string_to_sign.encode(), hashlib.sha256
    ).hexdigest()

    headers = {
        "Authorization": (
            f"{_ALGORITHM} Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "x-amz-date": amz_date,
        "x-amz-content-sha256": ph,
        "Host": host,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _canonical_request(
    method: str, path: str, canonical_headers: str, signed_headers: str, ph: str
) -> str:
    """拼 AWS 规范里的 CanonicalRequest。

    单独抽出来是为了让测试能**逐行断言它的结构**——签名算错绝大多数时候不是 HMAC 的问题，
    而是这个字符串某一行多了空格、少了换行、或顺序错了。抽出来后这些都能被钉死。

    规范要求恰好 6 行、顺序固定：
    ``HTTPMethod / CanonicalURI / CanonicalQueryString / CanonicalHeaders /
    SignedHeaders / HashedPayload``
    注意第 3 行是**空的**（本模块不处理 query string，调用方应把 query 直接拼进 path）。
    ``canonical_headers`` 自身**已带结尾换行**，所以第 5 行前面还要再加一个换行。
    """
    return "\n".join([method, path, "", canonical_headers, signed_headers, ph])


def _string_to_sign(amz_date: str, scope: str, canonical_request: str) -> str:
    """拼 AWS 规范里的 StringToSign（4 行）。同样为可断言而抽出。"""
    return "\n".join(
        [
            _ALGORITHM,
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )


def object_url(base_url: str, key: str) -> str:
    """由桶基址与对象 key 拼出完整 URL（**已 percent-encode**）。

    ``base_url`` 形如 ``https://<account>.r2.cloudflarestorage.com/epoch-x``（可带尾斜杠）。
    ``key`` 是**未编码**的对象名。

    ## 为什么编码收在这里（缺陷修复）

    之前编码放在 :func:`sign_request` 里（``quote(parsed.path)``），而**请求 URL 用的却是
    未编码的 key**，两边不一致 → R2 判 ``SignatureDoesNotMatch``。
    该缺陷靠本地回显服务器复现：key 含 ``@`` 时签名算的是 ``%40``、请求发的是 ``@``；
    key 含空格时 urllib 直接 ``InvalidURL`` 拒发；含中文时 ``UnicodeEncodeError``。

    **编码必须只发生一次**，所以收在这里；:func:`sign_request` 改为「假定 URL 已编码」，
    不再重复 quote —— 否则会编码两次，空格变 ``%2520``，同样对不上。

    ``safe='/'`` 是必须的：key 自身含 ``/`` 作目录分隔（``user/{userId}/{uuid}.png``），
    不能被编码掉，否则对象名就变了。
    """
    base = (base_url or "").rstrip("/")
    if not base:
        raise SigV4Error("桶基址为空（KB_VECTOR_URL 未设置？）")
    if not key:
        raise SigV4Error("对象 key 为空")
    return f"{base}/{urllib.parse.quote(key.lstrip('/'), safe='/')}"