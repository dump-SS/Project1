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

只签 `host` / `x-amz-content-sha256` / `x-amz-date` 三个头（与 `railway_build.py` 先例一致）。
`Content-Type` 会随请求发出但**不参与签名** —— S3 规范允许这样做，S3 只强制要求
`x-amz-content-sha256` 在签名内。

## 未实测的部分

⚠️ **PUT 路径未对真实 R2 验证过**（本机无 R2 凭据，Railway 上那两个变量读不到值）。
`backend/tests/test_r2_sigv4.py` 只验证了签名字符串的构造是否符合 AWS 规范
（用 AWS 官方文档的算法逐步展开比对），**没有**验证 R2 是否接受 PUT 的签名。
真实验证要等 F 板块部署到 Railway 之后 —— 那时用 CF MCP 读桶对象列表确认。
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
    # key 可能含非 ASCII 与分隔符，必须 encode；先例同样用 quote 而非 quote_plus
    path = urllib.parse.quote(parsed.path or "/")

    now = _dt.datetime.now(_dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    ph = payload_hash(body)

    # 顺序必须与 AWS 规范一致：header 名小写、值去首尾空白、字典序、末尾换行
    canonical_headers = f"host:{host}\nx-amz-content-sha256:{ph}\nx-amz-date:{amz_date}\n"
    signed_headers = "host;x-amz-content-sha256;x-amz-date"

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
    """由桶基址与对象 key 拼出完整 URL。

    ``base_url`` 形如 ``https://<account>.r2.cloudflarestorage.com/epoch-x``（可带尾斜杠）。
    ``key`` 是**未编码**的对象名——编码由 :func:`sign_request` 负责，这里不重复编码，
    否则会出现「编码两次」（``%2520``）。加斜杠统一处理尾部 ``/``。
    """
    base = (base_url or "").rstrip("/")
    if not base:
        raise SigV4Error("桶基址为空（KB_VECTOR_URL 未设置？）")
    if not key:
        raise SigV4Error("对象 key 为空")
    return f"{base}/{key.lstrip('/')}"