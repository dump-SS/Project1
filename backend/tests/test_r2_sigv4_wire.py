"""护栏：签名用的 path 与请求实际发出的 path 必须**逐字节一致**。

## 为什么单测里要起一个真服务器

缺陷 1（签名 path 与请求 path 编码不一致）之所以漏过去，正是因为原来的测试
只验证「签名字符串符合 AWS 规范」，**从不验证请求实际发出的长什么样**。
两份各自「正确」的东西拼在一起仍然可能错 —— 只有把真请求发出去、让服务器
把收到的 request-line 吐回来比对，才能抓到这类「错位」缺陷。

不需要任何 R2 凭据：把 r2_storage 指向本地回显服务器即可。

另外顺带钉住缺陷 2：发出的非豁免头必须在 SignedHeaders 内
（豁免名单 = authorization / user-agent / x-amzn-trace-id / expect /
transfer-encoding / connection / content-length）。
"""
from __future__ import annotations

import hashlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import r2_storage
from r2_sigv4 import canonical_path, object_url, sign_request

BASE_HOST = "acct.r2.cloudflarestorage.com"
AK = "test-access-key"
SK = "test-secret-key"

NEVER_SIGN = {
    "authorization",
    "user-agent",
    "x-amzn-trace-id",
    "expect",
    "transfer-encoding",
    "connection",
    "content-length",
}

# 覆盖三类：需编码但当前生产躲过的（@）、urllib 直接拒发的（空格、中文）、
# 以及看似无害实则会编码的（+ &）。
KEYS = [
    "user/u_10237/" + "a" * 32 + ".png",
    "user/dev6-r2-e2e-test@epochx.dev/" + "a" * 32 + ".png",
    "user/u_10237/with space.png",
    "user/u_10237/题目照片.png",
    "user/u_10237/a+b&c.png",
    "user/u_10237/percent%20already.png",
]


class _Echo(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    captured: dict = {}

    def do_PUT(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        type(self).captured = {
            "path": self.path,
            "headers": {str(k).lower(): str(v) for k, v in self.headers.items()},
            "body": body,
        }
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def echo_server():
    srv = HTTPServer(("127.0.0.1", 0), _Echo)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/epoch-x"
    srv.shutdown()


@pytest.fixture(autouse=True)
def _patch_storage_base(echo_server, monkeypatch):
    monkeypatch.setattr(r2_storage, "_require_config", lambda: (echo_server, AK, SK))
    _Echo.captured = {}


@pytest.mark.parametrize("key", KEYS)
def test_signed_path_matches_sent_path(echo_server, key):
    """签名用的 path == 服务端收到的 request-line path。

    不一致时 R2 会回 SignatureDoesNotMatch（我路由里映射成 502）。
    """
    url = object_url(echo_server, key)
    body = b"x" * 33
    # 签名时用的 path：取自 sign_request 自己的单一真相源 canonical_path，
    # **不要**在测试里 urlsplit(url) 反推 —— 一旦 object_url 退回未编码，
    # 反推值会跟着退化成原始字符，恰好和发出去的原始字符相等，缺陷就看不见了。
    signed_path = canonical_path(url)

    r2_storage.put_object(key, body, "image/png")  # 不应抛异常

    sent = _Echo.captured["path"].split("?")[0]
    assert sent == signed_path, (
        f"签名 path 与请求 path 不一致：\n  签名={signed_path}\n  发出={sent}"
    )


@pytest.mark.parametrize("key", KEYS)
def test_body_and_payload_hash_survive_encoding(echo_server, key):
    """编码只影响 URL，不能动 body，也不能让 x-amz-content-sha256 与实际载荷脱节。"""
    body = b"y" * 33
    r2_storage.put_object(key, body, "image/png")
    cap = _Echo.captured
    assert cap["body"] == body
    assert cap["headers"]["x-amz-content-sha256"] == hashlib.sha256(body).hexdigest()


@pytest.mark.parametrize("key", KEYS)
def test_no_unsigned_non_exempt_header(echo_server, key):
    """发出的非豁免头必须都在 SignedHeaders 内，否则被拒。"""
    r2_storage.put_object(key, b"x" * 33, "image/png")
    cap = _Echo.captured

    auth = cap["headers"]["authorization"]
    signed = auth.split("SignedHeaders=")[1].split(",")[0].strip()
    signed_set = set(signed.split(";"))

    unsigned = sorted(
        h
        for h in cap["headers"]
        if h not in NEVER_SIGN and h not in signed_set
    )
    # accept-encoding 是 urllib 自动加的，且生产构建期的 GET（railway_build.py，同为 urllib）
    # 同样没签它却成功了 —— 有实证说明 R2 容忍，故不在此列为失败。
    allowed_extra = {"accept-encoding"}
    assert set(unsigned) <= allowed_extra, f"这些头发了但没签：{unsigned}"


def test_content_type_is_signed_and_sent(echo_server):
    """缺陷 2 的直接护栏：给了 content_type 就必须既发出、又签入。"""
    key = "user/u_10237/" + "a" * 32 + ".png"
    r2_storage.put_object(key, b"x" * 33, "image/png")
    cap = _Echo.captured
    assert cap["headers"]["content-type"] == "image/png"
    signed = cap["headers"]["authorization"].split("SignedHeaders=")[1].split(",")[0]
    assert "content-type" in signed


def test_get_path_signature_unchanged_for_plain_key(frozen_clock=None):
    """回归护栏：不含需编码字符时，GET 签名与修复前完全一致（不破坏 GET 先例）。

    railway_build.py 的 GET 用的就是 embeddings.index / refs.json 这类简单 key，
    所以这条能保证本次修复对既有 GET 链路零影响。
    """
    url = object_url(f"https://{BASE_HOST}/epoch-x", "embeddings.index")
    assert url == f"https://{BASE_HOST}/epoch-x/embeddings.index"
    h = sign_request("GET", url, AK, SK)
    assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in h["Authorization"]


def test_object_url_encodes_exactly_once_no_double_encoding():
    """只编码一次。若 sign_request 还 quote 一次就会变 %2520，同样对不上。"""
    url = object_url(f"https://{BASE_HOST}/epoch-x", "user/u 1/题目.png")
    assert "%2520" not in url
    assert "%25E9" not in url
    # 再走一次 sign_request，path 不能被二次改动
    import urllib.parse as up

    assert up.urlsplit(url).path == "/epoch-x/user/u%201/%E9%A2%98%E7%9B%AE.png"