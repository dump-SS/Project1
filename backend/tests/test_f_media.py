"""F 板块媒体端点的测试。

## 隔离方式

**不真调 R2**：`r2_storage.put_object` / `get_object` 全部 monkeypatch 成记录调用的假实现。
理由：本机没有 R2 凭据（Railway 上那两个变量读不到值），真调必然失败；
且真调也不该进单元测试。

## 测试重心

**安全断言占多数**，因为这个端点唯一的风险面就是「让用户碰到别人的数据或生产向量索引」：

1. 上传的 key **由服务端生成**，不能被请求方指定 → 覆盖 ``embeddings.index`` 不可能；
2. 取回别人的 key → 403；
3. 路径穿越（``..``）→ 403；
4. 拿非图片冒充图片 → 400（魔数校验，不是只信 Content-Type 头）；
5. 空 body / 超限 → 400 / 413；
6. R2 未配置 → **503**（部署问题），不是 500；R2 上游 5xx → 502。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import r2_storage
from config import settings

# 1x1 像素 PNG（魔数 + 合法 IHDR）
PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 8


@pytest.fixture
def r2_calls(monkeypatch):
    """把 R2 读写换成记录调用的假实现，返回记录列表。"""
    calls: list[tuple] = []

    def fake_put(key, data, content_type):
        calls.append(("PUT", key, data, content_type))
        return {"ETag": '"fake-etag"'}

    def fake_get(key):
        calls.append(("GET", key, None, None))
        return PNG, "image/png"

    monkeypatch.setattr(r2_storage, "put_object", fake_put)
    monkeypatch.setattr(r2_storage, "get_object", fake_get)
    return calls


@pytest.fixture
def r2_offline(monkeypatch):
    """模拟 R2 未配置。"""

    def boom(key, data=None, content_type=None):
        raise r2_storage.R2NotConfigured("no creds")

    monkeypatch.setattr(r2_storage, "put_object", boom)
    monkeypatch.setattr(r2_storage, "get_object", boom)


@pytest.fixture
def r2_upstream_fail(monkeypatch):
    """模拟 R2 上游 5xx。"""

    def boom(key, data=None, content_type=None):
        raise r2_storage.R2Error("R2 PUT 失败：HTTP 500", status=500)

    monkeypatch.setattr(r2_storage, "put_object", boom)
    monkeypatch.setattr(r2_storage, "get_object", boom)


@pytest.fixture
def client(monkeypatch):
    """TestClient + 放开测试身份回落（deps.py 的第 2-4 层）。"""
    monkeypatch.setattr(settings, "allow_insecure_user_header", True, raising=False)
    from main import app

    return TestClient(app)


HEADERS = {"X-User-ID": "u_test1"}


# ---------------------------------------------------------------- 上传


def test_upload_png_returns_key_under_user_prefix(client, r2_calls):
    r = client.post("/api/v1/f/media", content=PNG, headers={**HEADERS, "Content-Type": "image/png"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["key"].startswith("user/u_test1/")
    assert body["contentType"] == "image/png"
    assert body["size"] == len(PNG)
    assert body["mediaId"] and body["getUrl"].startswith("/f/media/")
    # 确实落了 R2，且 key 与回执一致
    assert [c[0] for c in r2_calls] == ["PUT"]
    assert r2_calls[0][1] == body["key"]


def test_upload_key_is_server_generated_not_client_controlled(client, r2_calls):
    """**最重要的一条**：key 不能被请求方指定，否则能覆盖 embeddings.index。"""
    # 即使客户端在 query / 头里试图指定 key，也必须被忽略
    r = client.post(
        "/api/v1/f/media",
        content=PNG,
        headers={**HEADERS, "Content-Type": "image/png"},
        params={"key": "embeddings.index"},
    )
    assert r.status_code == 201
    assert "embeddings.index" not in r.json()["key"]
    assert r2_calls[0][1] != "embeddings.index"


def test_upload_rejects_empty_body(client, r2_calls):
    r = client.post("/api/v1/f/media", content=b"", headers={**HEADERS, "Content-Type": "image/png"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"
    assert not r2_calls, "空 body 不应触达 R2"


def test_upload_rejects_non_image_even_if_content_type_says_image(client, r2_calls):
    """魔数校验：声明 image/png 但内容是任意字节 -> 400，且不落 R2。"""
    r = client.post(
        "/api/v1/f/media",
        content=b"#!/bin/sh\nrm -rf /",
        headers={**HEADERS, "Content-Type": "image/png"},
    )
    assert r.status_code == 400
    assert not r2_calls, "非图片不该落 R2"


def test_upload_rejects_content_type_mismatch(client, r2_calls):
    """内容是 PNG 但声明 image/jpeg -> 400（防伪装）。"""
    r = client.post("/api/v1/f/media", content=PNG, headers={**HEADERS, "Content-Type": "image/jpeg"})
    assert r.status_code == 400
    assert not r2_calls


def test_upload_rejects_oversize(client, r2_calls):
    from routes import f_media

    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (f_media.MAX_UPLOAD_BYTES + 10)
    r = client.post("/api/v1/f/media", content=big, headers={**HEADERS, "Content-Type": "image/png"})
    assert r.status_code == 413
    assert not r2_calls


def test_upload_requires_auth(client, r2_calls):
    """未登录（无 sid、且回落链关闭）-> 401。"""
    from config import settings as s

    old = s.allow_insecure_user_header
    s.allow_insecure_user_header = False
    try:
        r = client.post("/api/v1/f/media", content=PNG, headers={"Content-Type": "image/png"})
        assert r.status_code == 401
    finally:
        s.allow_insecure_user_header = old


# ------------------------------------------------- 魔数校验的边界（自查补的）


def test_rejects_riff_container_that_is_not_webp(client, r2_calls):
    """`RIFF` 是容器魔数：WAV/AVI 也能通过。只查前缀会放行任意 RIFF 文件。

    真实 WebP 的判定字样 `WEBP` 在第 8 字节，所以这里构造一个 WAV 冒充 webp。
    """
    wav = b"RIFF" + b"\x24\x00\x00\x00" + b"WAVEfmt "
    r = client.post("/api/v1/f/media", content=wav, headers={**HEADERS, "Content-Type": "image/webp"})
    assert r.status_code == 400, r.text
    assert not r2_calls, "非 WebP 的 RIFF 文件不该落 R2"


def test_accepts_real_webp(client, r2_calls):
    """反过来守住：合法 WebP 不能被这个收紧误伤。"""
    webp = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBPVP8 " + b"\x00" * 8
    r = client.post("/api/v1/f/media", content=webp, headers={**HEADERS, "Content-Type": "image/webp"})
    assert r.status_code == 201, r.text
    assert r.json()["contentType"] == "image/webp"


def test_accepts_gif(client, r2_calls):
    gif = b"GIF89a" + b"\x00" * 8
    r = client.post("/api/v1/f/media", content=gif, headers={**HEADERS, "Content-Type": "image/gif"})
    assert r.status_code == 201, r.text
    assert r.json()["key"].endswith(".gif")


# ------------------------------------------------- 错误包装（自查补的）


def test_signature_failure_is_wrapped_into_r2error(monkeypatch):
    """签名失败必须变成 R2Error，不能裸抛 SigV4Error。

    回归背景：`r2_storage._call` 里 `sign_request()` 一度写在 `try` 外面，
    导致 `except SigV4Error` 变死代码、签名缺陷裸抛，破坏「失败一律 R2Error」的约定。
    """
    import r2_storage
    from r2_sigv4 import SigV4Error

    monkeypatch.setattr(
        r2_storage,
        "_require_config",
        lambda: ("https://example.r2.cloudflarestorage.com/bucket", "AK", "SK"),
    )

    def boom(*a, **k):
        raise SigV4Error("签名炸了")

    monkeypatch.setattr(r2_storage, "sign_request", boom)
    with pytest.raises(r2_storage.R2Error) as exc:
        r2_storage.get_object("user/u/a.png")
    assert "签名构造失败" in str(exc.value)


def test_upload_returns_503_when_r2_not_configured(client, r2_offline):
    r = client.post("/api/v1/f/media", content=PNG, headers={**HEADERS, "Content-Type": "image/png"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "R2_NOT_CONFIGURED"


def test_upload_returns_502_on_upstream_failure(client, r2_upstream_fail):
    r = client.post("/api/v1/f/media", content=PNG, headers={**HEADERS, "Content-Type": "image/png"})
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "STORAGE_FAILED"


# ---------------------------------------------------------------- 取回


def test_get_returns_image_bytes(client, r2_calls):
    r = client.get("/api/v1/f/media/user/u_test1/abc.png", headers=HEADERS)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == PNG
    # 私有用户数据：不得被缓存复用
    assert "no-store" in r.headers.get("cache-control", "")


def test_get_rejects_other_users_key(client, r2_calls):
    """**越权**：读别人的图片 -> 403，且不触达 R2。"""
    r = client.get("/api/v1/f/media/user/u_someone_else/abc.png", headers=HEADERS)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"
    assert not r2_calls, "越权请求不该触达 R2"


def test_get_rejects_vector_index_key(client, r2_calls):
    """即使 key 前缀合法，也要确保拿不到生产向量索引。"""
    r = client.get("/api/v1/f/media/embeddings.index", headers=HEADERS)
    assert r.status_code == 403
    assert not r2_calls


def test_get_rejects_path_traversal(client, r2_calls):
    r = client.get("/api/v1/f/media/user/u_test1/../../embeddings.index", headers=HEADERS)
    assert r.status_code in (403, 404)
    assert not r2_calls, "路径穿越不该触达 R2"


def test_get_maps_upstream_404_to_404(client, monkeypatch):
    def missing(key):
        raise r2_storage.R2Error("R2 GET 失败：HTTP 404", status=404)

    monkeypatch.setattr(r2_storage, "get_object", missing)
    r = client.get("/api/v1/f/media/user/u_test1/gone.png", headers=HEADERS)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_get_returns_503_when_not_configured(client, r2_offline):
    r = client.get("/api/v1/f/media/user/u_test1/a.png", headers=HEADERS)
    assert r.status_code == 503