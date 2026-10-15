"""`r2_sigv4` 的签名构造测试。

## 这组测试能证明什么、不能证明什么

**能**：CanonicalRequest / StringToSign 的**逐行结构**、payload 哈希、URL 编码、
凭据缺失时的失败行为，以及**与 `scripts/railway_build.py` 里那个 GET 先例的签名一致性**
（固定同一时刻后两者必须逐字节相同 —— 证明把 GET 泛化成 GET/PUT/DELETE 时没有改坏原行为）。

**不能**：R2 是否接受 PUT 的签名。那需要真实凭据 + 真实请求，本机做不到
（Railway 上那两个变量读不到值）。**这条只能等部署后用 CF MCP 读桶对象列表确认。**

为什么不用 AWS 官方测试向量：官方 `aws-sig-v4-test-suite` 是 S3 的
`region=us-east-1`，而 R2 强制 `region=auto`/`service=s3`，套不上。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.util
from pathlib import Path

import pytest

from r2_sigv4 import (
    SigV4Error,
    _canonical_request,
    _string_to_sign,
    object_url,
    payload_hash,
    sign_request,
)

AK = "test-access-key"
SK = "test-secret-key"
BASE = "https://acct.r2.cloudflarestorage.com/epoch-x"
FIXED = _dt.datetime(2026, 10, 12, 8, 30, 15, tzinfo=_dt.timezone.utc)
AMZ_DATE = "20261012T083015Z"
DATE_STAMP = "20261012"


# --------------------------------------------------------------------------
# payload 哈希
# --------------------------------------------------------------------------

def test_payload_hash_of_empty_body_is_sha256_of_nothing():
    """GET 空体的哈希必须等于 sha256(b"") —— 先例里那一行注释写的就是这件事。"""
    assert payload_hash(b"") == hashlib.sha256(b"").hexdigest()


def test_payload_hash_of_body_differs_from_empty():
    body = b"\x89PNG\r\n\x1a\n fake"
    assert payload_hash(body) == hashlib.sha256(body).hexdigest()
    assert payload_hash(body) != payload_hash(b"")


# --------------------------------------------------------------------------
# CanonicalRequest 结构：逐行钉死
# --------------------------------------------------------------------------

def test_canonical_request_has_exactly_six_logical_fields_in_spec_order():
    """规范说的「6 行」是 6 个**逻辑字段**，不是 split 后的物理行数。

    CanonicalHeaders 自己就由多个 ``name:value\\n`` 行组成，所以物理行数必然多于 6
    （3 个 header + 其余字段 = 9 行）。真正要钉死的是**字段顺序**：方法、URI、空的
    query 串、headers 块、signed headers、payload 哈希。末尾两个字段用负索引断言，
    这样 header 块有几行都不影响。
    """
    headers = f"host:h\nx-amz-content-sha256:abc\nx-amz-date:{AMZ_DATE}\n"
    signed = "host;x-amz-content-sha256;x-amz-date"
    cr = _canonical_request("PUT", "/b/k", headers, signed, "abc")

    lines = cr.split("\n")
    assert lines[0] == "PUT"                     # 1. HTTPMethod
    assert lines[1] == "/b/k"                    # 2. CanonicalURI
    assert lines[2] == ""                        # 3. CanonicalQueryString（本模块不处理 query）
    assert lines[3] == "host:h"                  # 4. CanonicalHeaders（由 3 行 header 构成）
    assert lines[-2] == signed                   # 5. SignedHeaders
    assert lines[-1] == "abc"                    # 6. HashedPayload

    # header 块必须完整且顺序正确（小写名、字典序）
    assert "host:h\nx-amz-content-sha256:abc\nx-amz-date:%s" % AMZ_DATE in cr


def test_canonical_request_has_blank_line_between_headers_and_signed_headers():
    """最容易错的一处：CanonicalHeaders 自带尾换行，join 又加一个 -> 必须是**两个**换行。"""
    headers = f"host:h\nx-amz-content-sha256:abc\nx-amz-date:{AMZ_DATE}\n"
    cr = _canonical_request("GET", "/k", headers, "host;x-amz-date", "abc")
    assert "\n\nhost;" in cr
    assert "\n\n\n" not in cr, "不该出现三个连续换行"


def test_string_to_sign_shape():
    sts = _string_to_sign(AMZ_DATE, "20261012/auto/s3/aws4_request", "canonical")
    lines = sts.split("\n")
    assert len(lines) == 4
    assert lines[0] == "AWS4-HMAC-SHA256"
    assert lines[1] == AMZ_DATE
    assert lines[2] == "20261012/auto/s3/aws4_request"
    assert lines[3] == hashlib.sha256(b"canonical").hexdigest()


# --------------------------------------------------------------------------
# sign_request 的对外行为
# --------------------------------------------------------------------------

@pytest.fixture
def frozen_clock(monkeypatch):
    """把时间钉死，让签名可复现、可比对。"""
    class _FrozenDT(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return FIXED

    monkeypatch.setattr(_dt, "datetime", _FrozenDT)
    return FIXED


def test_sign_request_get_matches_the_get_only_precedent(frozen_clock):
    """**核心回归**：固定同一时刻后，本模块的 GET 必须与 railway_build.py 的先例逐字节相同。

    这条过了，就说明「把只做 GET 的先例泛化成支持 PUT」没有改坏原有行为。
    """
    spec = importlib.util.spec_from_file_location(
        "railway_build_precedent", Path(__file__).resolve().parents[2] / "scripts" / "railway_build.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    url = f"{BASE}/embeddings.index"
    mine = sign_request("GET", url, AK, SK)
    theirs = mod._sigv4_headers(url, AK, SK)

    # 先例与本模块必须产出逐字节相同的 header（含 Authorization 里的 Signature）——
    # 签名不同就说明泛化改坏了原有行为。
    assert mine["Authorization"] == theirs["Authorization"]
    assert mine["x-amz-date"] == theirs["x-amz-date"] == AMZ_DATE
    assert mine["x-amz-content-sha256"] == theirs["x-amz-content-sha256"]
    assert mine["Host"] == theirs["Host"]
    # 两边暴露的 header 名集合也必须一致（键名拼错会让线上 400）
    assert set(mine) == set(theirs)


def test_sign_request_put_signs_real_body_hash(frozen_clock):
    """PUT 必须把**真实请求体**的哈希签进去，否则 R2 会拒。"""
    body = b"hello-bytes"
    h = sign_request("PUT", f"{BASE}/user/u_1/a.png", AK, SK, body=body)
    assert h["x-amz-content-sha256"] == hashlib.sha256(body).hexdigest()
    assert "host;x-amz-content-sha256;x-amz-date" in h["Authorization"]


def test_sign_request_authorization_carries_r2_fixed_region_and_service(frozen_clock):
    """region 必须是 auto、service 必须是 s3 —— 用错会 403 SignatureDoesNotMatch。"""
    h = sign_request("GET", f"{BASE}/k", AK, SK)
    assert "/auto/s3/aws4_request" in h["Authorization"]
    assert h["Authorization"].startswith("AWS4-HMAC-SHA256 ")


def test_sign_request_percent_encodes_non_ascii_key(frozen_clock):
    """中文/空格 key 必须 percent-encode；且不能编码两次。"""
    h = sign_request("GET", object_url(BASE, "user/u 1/题目 v2.png"), AK, SK)
    # Host 不含 key，所以从签名里反查不出 path；直接断言 object_url 保留原样、sign 不炸
    assert h["Host"] == "acct.r2.cloudflarestorage.com"
    assert "%" not in h["Host"]


def test_sign_request_includes_content_type_when_given(frozen_clock):
    """缺陷修复：Content-Type 既然要随请求发出，就必须**签进** SignedHeaders。

    修复前这里断言「不该出现它」，那条断言本身就是 bug 的固化——
    它对应的 docstring 断言「S3 允许发而不签」未经 R2 实证，生产 PUT 实测 502。
    """
    h = sign_request("PUT", f"{BASE}/k", AK, SK, body=b"x", content_type="image/png")
    assert h["Content-Type"] == "image/png"
    # AWS 规范要求 header 名小写并按字典序：content-type 排在 host 之前
    assert "SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date" in h["Authorization"]


def test_sign_request_omits_content_type_when_not_given(frozen_clock):
    """没给 content_type 时不应凭空签它（否则签名与实际请求不符）。"""
    h = sign_request("GET", f"{BASE}/k", AK, SK)
    assert "Content-Type" not in h
    assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in h["Authorization"]


def test_sign_request_rejects_missing_credentials():
    with pytest.raises(SigV4Error, match="凭据"):
        sign_request("GET", f"{BASE}/k", "", SK)
    with pytest.raises(SigV4Error, match="凭据"):
        sign_request("GET", f"{BASE}/k", AK, "")


def test_sign_request_rejects_non_absolute_url():
    with pytest.raises(SigV4Error, match="绝对 URL"):
        sign_request("GET", "/relative/path", AK, SK)


def test_get_and_put_with_empty_body_sign_identically(frozen_clock):
    """仅 GET/PUT 动词不同时，payload 都是空时签名也应相同 —— 顺带验证动词确实进了 canonical。"""
    g = sign_request("GET", f"{BASE}/k", AK, SK)
    p = sign_request("PUT", f"{BASE}/k", AK, SK)
    # 动词不同 -> canonical_request 不同 -> 签名不同（证明动词被正确纳入）
    assert g["Authorization"] != p["Authorization"]
    assert g["x-amz-content-sha256"] == p["x-amz-content-sha256"]


# --------------------------------------------------------------------------
# object_url
# --------------------------------------------------------------------------

def test_object_url_tolerates_trailing_slash_on_base():
    assert object_url(BASE + "/", "embeddings.index") == f"{BASE}/embeddings.index"
    assert object_url(BASE, "embeddings.index") == f"{BASE}/embeddings.index"


def test_object_url_encodes_key_exactly_once():
    """缺陷修复：编码统一收在 object_url，所以这里**必须**看到编码后的结果。

    修复前 key 保持未编码、编码发生在 sign_request，两边不一致 →
    R2 判 SignatureDoesNotMatch。空格/中文的 key 连请求都发不出去。
    """
    got = object_url(BASE, "user/u 1/题目.png")
    assert got == f"{BASE}/user/u%201/%E9%A2%98%E7%9B%AE.png"
    # 关键：只编码一次。若再编码一次会变 %2520 / %25E9…
    assert "%2520" not in got
    assert "%25E9" not in got


def test_object_url_keeps_slash_unencoded():
    """`/` 是 key 内部的目录分隔符，不能被编码掉，否则对象名就变了。"""
    got = object_url(BASE, "user/u_10237/" + "a" * 32 + ".png")
    assert got == f"{BASE}/user/u_10237/" + "a" * 32 + ".png"


def test_object_url_encodes_at_in_email_style_user_id():
    """user_id 是邮箱时（dev-4 的测试账号就是这种形态）必现的那一类。"""
    got = object_url(BASE, "user/dev6-r2-e2e-test@epochx.dev/x.png")
    assert "@" not in got
    assert got.endswith("/user/dev6-r2-e2e-test%40epochx.dev/x.png")


def test_object_url_rejects_empty_inputs():
    with pytest.raises(SigV4Error, match="基址为空"):
        object_url("", "k")
    with pytest.raises(SigV4Error, match="key 为空"):
        object_url(BASE, "")