"""R2 对象读写（零新依赖，只用标准库 ``urllib``）。

## 为什么用 urllib 而不是 httpx

`backend/pyproject.toml` 里 `httpx` 只在 ``[project.optional-dependencies].dev`` 下，
**不在生产依赖里**。F 板块要求零新依赖（且 `python-multipart` 也没装），所以这里用标准库
``urllib.request``。`scripts/railway_build.py` 的 SigV4 先例同样只用标准库，风格一致。

## 为什么签名放在 r2_sigv4

签名算法与 AWS 规范细节都收在 :mod:`r2_sigv4`，本模块只负责「带着签名发请求、
把 R2 的错误翻译成能上抛的类型」。

## 阻塞性与 FastAPI

本模块是**同步阻塞**的（``urllib`` 没有异步版本）。调用方在 async 路由里必须用
``asyncio.to_thread`` / ``run_in_threadpool`` 包起来，否则会阻塞事件循环。
同步路由（``def``）则由 Starlette 自动放进线程池，可以直接调用。
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.request

from config import settings
from r2_sigv4 import SigV4Error, object_url, sign_request

logger = logging.getLogger(__name__)

# R2 单次请求超时（秒）。图片不大，但跨网络到 Cloudflare，留足余量。
_TIMEOUT = 30


class R2NotConfigured(RuntimeError):
    """R2 凭据未配置（三个 KB_VECTOR_* 任一为空）。调用点应转成 503 而非 500。"""


class R2Error(RuntimeError):
    """R2 返回了非 2xx。``status`` 保留原始 HTTP 状态便于诊断。"""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


def _require_config() -> tuple[str, str, str]:
    """取桶基址与 S3 凭据；任一缺失即抛 :class:`R2NotConfigured`。

    **刻意不静默降级成匿名请求**：对私有桶匿名必然 403，失败信息会离根因更远。
    """
    base = (settings.kb_vector_url or "").strip()
    ak = (settings.kb_vector_access_key_id or "").strip()
    sk = (settings.kb_vector_secret_access_key or "").strip()
    if not (base and ak and sk):
        raise R2NotConfigured(
            "R2 未配置：需要 KB_VECTOR_URL / KB_VECTOR_ACCESS_KEY_ID / "
            "KB_VECTOR_SECRET_ACCESS_KEY 三者齐备"
        )
    return base, ak, sk


def is_configured() -> bool:
    """是否已配置 R2（供只读端点在依赖注入阶段决定要不要挂载）。"""
    try:
        _require_config()
        return True
    except R2NotConfigured:
        return False


def _call(method: str, key: str, *, body: bytes = b"", content_type: str | None = None) -> tuple[bytes, dict[str, str]]:
    """执行一次带 SigV4 的 R2 请求，返回 (响应体, 响应头)。

    失败一律转成 :class:`R2Error`（带原始状态码）；**不在这里吞异常**——
    路由层决定降级还是上抛。
    """
    base, ak, sk = _require_config()
    url = object_url(base, key)
    try:
        # 签名必须在 try **内**：URL 构造/SHA256 计算也会抛 SigV4Error。
        # 放外面的话这个 except 分支永远不触发（urlopen 不抛它），签名缺陷会裸抛出去，
        # 破坏本函数「失败一律是 R2Error」的约定。
        headers = sign_request(method, url, ak, sk, body=body, content_type=content_type)

        req = urllib.request.Request(url, data=body or None, method=method.upper(), headers=headers)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.read(), dict(resp.headers.items())
    except urllib.error.HTTPError as e:  # R2 返回 4xx/5xx
        detail = b""
        try:
            detail = e.read()[:400]
        except Exception:  # noqa: BLE001 - 读错误体失败不能盖掉原始错误
            pass
        logger.warning("[R2] %s %s -> HTTP %s: %s", method, key, e.code, detail[:200])
        raise R2Error(f"R2 {method} 失败：HTTP {e.code}", status=e.code) from e
    except urllib.error.URLError as e:  # DNS/连接/超时
        logger.warning("[R2] %s %s -> 连接失败: %s", method, key, e)
        raise R2Error(f"R2 {method} 连接失败：{e.reason}", status=0) from e
    except SigV4Error as e:
        # 签名/URL 构造问题属于**代码缺陷**，不是上游故障，单独标出来便于定位
        raise R2Error(f"R2 签名构造失败：{e}", status=0) from e


def put_object(key: str, data: bytes, content_type: str) -> dict[str, str]:
    """PUT 一个对象，返回 R2 回的头（``ETag`` 等）。

    ``x-amz-content-sha256`` 由 :func:`r2_sigv4.sign_request` 按真实 body 计算 ——
    不能用占位符，否则 R2 会拒。
    """
    _body, headers = _call("PUT", key, body=data, content_type=content_type)
    return headers


def get_object(key: str) -> tuple[bytes, str]:
    """GET 一个对象，返回 (内容, Content-Type)。

    R2 找不到对象时抛 :class:`R2Error`（``status=404``），由路由层翻译成 404。
    """
    body, headers = _call("GET", key)
    ctype = headers.get("Content-Type") or headers.get("content-type") or "application/octet-stream"
    return body, ctype


def delete_object(key: str) -> dict[str, str]:
    """DELETE 一个对象（走同一套 SigV4 签名），返回 R2 回的头。

    ## 幂等：删不存在的对象**不算失败**

    S3/R2 的 DELETE 对「对象存在」与「对象不存在」都回 ``204``，所以本函数通常
    什么都不用判断即可成功。契约（openapi v1.11.0）据此把「删成功」与
    「本来就没有」都定为 204。

    但仍然兜住上游的 404：不同 S3 兼容实现对「删不存在的 key」是否回 404
    并不统一（有的回 204，有的回 404）。若不兜，同一个幂等调用会因实现差异
    被路由层翻成 502 —— 那就既违反契约又误导调用方。故显式吞掉 404，
    把它归一为「已删除」。这让本函数在两种上游行为下都给出同一结果。
    """
    try:
        _body, headers = _call("DELETE", key)
    except R2Error as e:
        if e.status == 404:
            # 幂等：已经不在了，等价于删除成功
            logger.info("[R2] DELETE %s -> 上游回 404，按幂等视作已删除", key)
            return {}
        raise
    return headers