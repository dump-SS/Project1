# ADR：板块二本地向量库与 embedding 选型

- 状态：已决策（MVP 倾向，待真实数据回流后复核）
- 日期：2026-08-24
- 依据：PRD 12.11 待办、`docs/module2-3-gap-architecture-api-checklist.md` §3.3
- 决策背景：错题录入 → 本地向量化 → 知识点建议匹配（Top-5），原文不出域

## 决策

| 项 | 选择 | 备选 | 理由 |
|---|---|---|---|
| 向量库 | **FAISS** | Chroma / Qdrant | 零服务依赖、进程内 numpy 内存检索、1000 条切片规模完全够用；与 SQLite 同目录索引文件，满足 PRD 12.2.3「可备份/销毁」要求；避免为 MVP 引入需要独立部署/运维的服务 |
| embedding 模型 | **bge-small-zh-v1.5**（本地） | m3e-small / 云端过渡 | 中文题干嵌入质量好、small 规格（约 102MB）本地可加载；`embed_mode=cloud` 作过渡开关（受 PRD 6.2 告知约束），`off` 时降级名称关键词匹配 |
| 降级路径 | embedding 挂 → `KB_EMBEDDING_FAILED`，录入降级为手动选知识点（不阻断）；LLM 挂 → 本地规则模板复盘 | — | 板块二验收「LLM 全挂时核心流程可用」 |

## 权衡记录

- **Chroma/Qdrant 被否**：单机单用户 MVP 不需要服务端向量 DB 的并发/分布式能力，额外进程与持久化复杂度不符合「演示页转正，不推倒重写」的工程原则。
- **bge-small-zh 打包体积（+~50-100MB）**：本地懒加载（首次匹配延迟可接受），模型随部署文档说明打包方案；v2.1 先以 `name_fuzzy` 降级保底，模型未就绪不阻塞错题录入 P0 流程。
- **云端 embedding 过渡**：仅作 `embed_mode=cloud` 实验开关，出域内容仍是向量（非原文），且默认关闭。

## 影响

- 新增依赖：`faiss-cpu`（pyproject.toml，随 v2.1-B5 一并加）；`sentence-transformers` 仅在 `embed_mode=local` 时被 `embedding_service.py` 延迟 import，避免启动即加载大依赖。
- 新增模块：`backend/embedding_service.py`、`backend/vector_store.py`（FAISS 封装 + `kb_embeddings` 表引用）。
