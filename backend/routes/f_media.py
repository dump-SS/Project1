"""F 板块：用户上传的题目图片（多模态拍题的最小入口）。

## 范围（lead-1 定的「先做最小可用」）

只打通 **上传 -> 存储 -> 取回** 这条链路，不做图像识别（那是二期）。
存储用 Cloudflare R2 私有桶 ``epoch-x``，后端做 S3 SigV4 代理。

## 架构：服务端代理（架构 A，lead-1 裁定）

    前端 --POST raw bytes--> 后端 --PUT SigV4--> R2
    前端 <--GET 二进制----  后端 --GET SigV4--> R2

不用「浏览器直传 + 预签名 URL」的理由（lead-1 采纳并补充）：
1. 不需要给 R2 配 CORS（实测该桶 CORS 未配置）；
2. **合规更安全**：题目图片是用户数据，走后端可控；直传等于把签名 URL 交给前端。

## 为什么收 raw body 而不是 multipart

``backend/pyproject.toml`` 里**没有 python-multipart**，写 ``File(...)`` / ``UploadFile``
会让 FastAPI 在**启动时直接报错**（不是运行时报）。所以这里收 ``application/octet-stream``
的原始字节，零新依赖。前端相应地用 ``fetch`` + ArrayBuffer 直发。

## 为什么这个文件里是 async def（偏离项目「一律同步 def」惯例）

Starlette 的 ``request.body()`` 是协程，读原始 body **只能**在 async 函数里 await。
阻塞部分（urllib 调 R2）用 ``asyncio.to_thread`` 丢进线程，不阻塞事件循环。
这是必要且唯一的例外，故在此说明。

## ⚠️ 安全性：key 绝不能让调用方控制

R2 桶里同时有生产向量索引（``embeddings.index`` / ``refs.json``）与用户图片。
若 key 由请求方指定，传 ``key=embeddings.index`` 就能**覆盖生产检索索引**。
所以：

- 上传时 key **由服务端生成**：``user/{userId}/{uuid}{扩展名}``；
- 取回时**校验归属**：key 必须以 ``user/{当前 userId}/`` 开头，否则 403。
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

import r2_storage
from r2_sigv4 import SigV4Error
from schemas.user import User
from .deps import current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/f/media", tags=["F 板块·媒体"])

# --- 上传约束（pilot 期够用，二期按需放开）---
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB
USER_PREFIX = "user/"

# 只收图片。content type 由**魔数**二次校验，不只信请求头（请求头可伪造）。
# 魔数取各格式的固定文件头；够用且零依赖。
#
# 结构是「候选签名列表」，每个候选签名是若干 (偏移, 字节) 且**必须全部命中**。
# 两层语义不能混：
# - WebP 必须验两处 —— `RIFF` 是**容器**魔数，WAV/AVI 也以 RIFF 开头，
#   真实 WebP 的判定字样 `WEBP` 在第 8 字节。写成单前缀等于放行任意 RIFF 文件。
# - GIF 是两个**候选**（87a / 89a），命中任一即可，写成"全部命中"会把 GIF 全拒掉。
_ALLOWED_IMAGE_TYPES: dict[str, tuple[tuple[tuple[int, bytes], ...], ...]] = {
    "image/jpeg": (((0, b"\xff\xd8\xff"),),),
    "image/png": (((0, b"\x89PNG\r\n\x1a\n"),),),
    "image/webp": (((0, b"RIFF"), (8, b"WEBP")),),
    "image/gif": (((0, b"GIF87a"),), ((0, b"GIF89a"),)),
}
_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class MediaUploadResponse(BaseModel):
    """上传成功后的回执。前端凭 mediaId/getUrl 取回。"""

    model_config = ConfigDict(populate_by_name=True)

    media_id: str = Field(..., alias="mediaId", description="服务端生成的媒体 ID")
    key: str = Field(..., description="R2 对象 key（user/{userId}/ 前缀）")
    content_type: str = Field(..., alias="contentType", description="图片 MIME")
    size: int = Field(..., description="字节数")
    get_url: str = Field(..., alias="getUrl", description="取回路径（相对 API 基址）")


def _sniff_image_type(body: bytes, declared: str) -> str:
    """用魔数判定图片类型；声明与实际不符即拒。

    为什么必须验：桶里是**用户数据**，不能让调用方把任意文件（可执行包、HTML——HTML
    存进去若被同源回显就成了存储型 XSS）当作图片塞进来。
    """
    normalized = (declared or "").split(";")[0].strip().lower()
    for ctype, signatures in _ALLOWED_IMAGE_TYPES.items():
        hit = any(
            all(body[off : off + len(mag)] == mag for off, mag in signature)
            for signature in signatures
        )
        if hit:
            if normalized and normalized != ctype:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "VALIDATION_FAILED",
                        "message": f"内容是 {ctype}，与声明的 {normalized} 不一致",
                        "field": "contentType",
                    },
                )
            return ctype
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "VALIDATION_FAILED",
            "message": "只接受图片（jpeg/png/webp/gif）",
            "field": "contentType",
        },
    )


def _build_key(user_id: str, content_type: str) -> str:
    """生成**服务端**的 key。调用方无法影响除 userId 以外的任何部分。"""
    ext = _EXT_BY_TYPE[content_type]
    return f"{USER_PREFIX}{user_id}/{uuid.uuid4().hex}{ext}"


def _assert_owner(key: str, user_id: str) -> None:
    """取回前的归属校验：非本人的 key 一律 403。

    注意这里用 403 而不是 404：不泄露「该 key 是否存在」，同时语义正确
    （不是资源不存在，而是你无权访问）。
    """
    if not key.startswith(f"{USER_PREFIX}{user_id}/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "无权访问该媒体"},
        )
    # 二次防线：即使前缀对了，也不允许出现路径穿越片段
    if ".." in key or key.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "非法的媒体 key"},
        )


@router.post(
    "",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上传题目图片（raw body，非 multipart）",
)
async def upload_media(
    request: Request,
    user: User = Depends(current_user),
) -> MediaUploadResponse:
    """收原始字节 -> R2 私有桶。请求体直接是图片字节。

    ⚠️ 内容类型走 **`Content-Type` 请求头**（`request.headers.get("content-type")`），
    **不是 query 参数**。旧注释误写为「类型放 query」，与实现不符，会误导调用方。
    另注意该头**可伪造**，故类型还要经 `_sniff_image_type` 的**文件魔数二次校验**。
    """
    body = await request.body()

    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_FAILED", "message": "请求体为空", "field": "body"},
        )
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "VALIDATION_FAILED",
                "message": f"图片超过上限 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
                "field": "body",
            },
        )

    declared = request.headers.get("content-type", "")
    content_type = _sniff_image_type(body, declared)
    key = _build_key(user.user_id, content_type)

    try:
        await asyncio.to_thread(r2_storage.put_object, key, body, content_type)
    except r2_storage.R2NotConfigured as e:
        # 明确区分「没配」与「上游坏了」：前者是部署问题(503)，后者才是 502
        logger.error("[F-MEDIA] R2 未配置: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "R2_NOT_CONFIGURED", "message": "对象存储未配置，请联系管理员"},
        ) from e
    except (r2_storage.R2Error, SigV4Error) as e:
        logger.warning("[F-MEDIA] 上传失败 user=%s key=%s: %s", user.user_id, key, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "STORAGE_FAILED", "message": "图片存储失败，请稍后再试"},
        ) from e

    logger.info("[F-MEDIA] 上传成功 user=%s key=%s size=%d", user.user_id, key, len(body))
    return MediaUploadResponse(
        mediaId=key.rsplit("/", 1)[-1].rsplit(".", 1)[0],
        key=key,
        contentType=content_type,
        size=len(body),
        getUrl=f"/f/media/{key}",
    )


@router.get(
    "/{key:path}",
    summary="取回题目图片（后端代理，二进制）",
)
async def get_media(key: str, user: User = Depends(current_user)) -> Response:
    """取回自己的图片。**只能取自己的**（归属校验见 _assert_owner）。"""
    _assert_owner(key, user.user_id)

    try:
        data, ctype = await asyncio.to_thread(r2_storage.get_object, key)
    except r2_storage.R2NotConfigured as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "R2_NOT_CONFIGURED", "message": "对象存储未配置，请联系管理员"},
        ) from e
    except r2_storage.R2Error as e:
        if e.status == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "图片不存在"},
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "STORAGE_FAILED", "message": "图片读取失败，请稍后再试"},
        ) from e

    return Response(
        content=data,
        media_type=ctype,
        # 私有用户数据：禁止任何中间层/浏览器缓存复用
        headers={"Cache-Control": "private, no-store"},
    )