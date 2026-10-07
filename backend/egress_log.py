"""出域留痕（2026-09-30 合规口径第 ④ 条）。

为什么单独一个模块，而不是写进 ``ai_call_log``：

- ``ai_call_log`` 记的是「这次调用好不好」（延迟 / 成败 / 成本），且按 PRD §7 铁律
  **不存任何用户身份字段**——它回答不了「谁把什么发出去了」。
- 放宽 ``user_error_content`` 的前提之一就是「出域留痕，含用户、内容类型、时间」。
  把 user_id 落库会与铁律冲突，所以这里**只写应用日志**（``egress`` logger），
  由运维侧收集；日志里的时间由 logging 的 asctime 统一给，不自己拼。

调用点只有一处：``routes/search.py`` 真正把题面交给模型的那一刻。
"""
from __future__ import annotations

import logging
from typing import Iterable

__all__ = ["log_egress_allowed"]

# 独立 logger，便于运维单独采集 / 单独关闭
logger = logging.getLogger("egress")


def log_egress_allowed(
    *,
    user_id: str,
    data_class: str,
    scene: str,
    keys: Iterable[str],
    note: str = "",
) -> None:
    """记录一次**放行**的出域（用户、内容类型、字段名清单）。

    只记字段名清单，不记字段值——留痕要能回答「发了哪几类内容」，
    不需要把内容再抄一遍进日志（抄了反而制造第二份出域副本）。
    """
    logger.info(
        "[EGRESS][ALLOW] user=%s data_class=%s scene=%s keys=%s%s",
        user_id,
        data_class,
        scene,
        ",".join(sorted(keys)),
        f" note={note}" if note else "",
    )
