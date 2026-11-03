# X2 降级矩阵实测记录（2026-10-30 / 31）

> 对应派单「X2 发布验收欠账三项」第 2 项与主计划 §7 门 4「降级矩阵实测」。
> 主计划只有一句「降级矩阵每条有实测记录」、没有现成清单——本矩阵的**行**是从代码里
> 枚举的（每个写了降级分支的模块一行），**每行的「实测结果」列都是真实请求/真实日志**，不是计划文档的转述。
> 未实测的行显式标出并给原因，不冒充。

## 0. 测法与三件套

- 受控后端：worktree `D:/Projects/p1-x2acc/backend`（基线 `origin/main 3750240`），隔离库
  `backend/data.db`（head `b8e2d4f1a7c3`），端口 8010；**逐条重启改配置**，不留共享状态。
- 驱动：`python -I .workbuddy/tmp/x2acc/battery.py`（urllib 真发 HTTP，逐行记录到
  `matrix-results.txt`）；配 SMTP/数据库两轮单独重启。
- 计数：E2E 浏览器轮 6 步 + 本矩阵 13 行（12 行有实测，1 行未实测并注明）。

| # | 降级场景（触发方式） | 预期（契约/代码口径） | **实测结果** | 证据 |
|---|---|---|---|---|
| D1 | LLM 无输出（`LLM_PROVIDER=mock`，provider 返回 None） | 建议：模板兜底 `source=template`；绝不悬挂 pending | `POST /recommendations` 202 pending → 轮询 **`status=ready, source=template, items=1`**（~1.5s 内到终态） | A9 |
| D2 | LLM 无输出 → Chat 主链路 | 温和兜底文案，HTTP 200，`crisis=false` | **`"我暂时接不上你的话，能换个说法再跟我说一次吗？"`**，200，93ms | A1 |
| D3 | 复盘在记录不足时（LLM 失败前先挡） | `insufficient_data`，**不做模板兜底**（PRD 5.4） | `POST /summaries` → **`status=insufficient_data`「本周记录较少，暂不生成完整复盘」**。注：`failed` 终态（LLM 失败）由 `run_summary_generation` 的单元测试覆盖，本次实测走到的是记录数挡板 | A10 |
| D4 | 危机信号（第 1 层确定性，不过 LLM） | 200 + `crisis=true` + **硬编码 L3 文案逐字输出** | 200，27ms，回复与 `CRISIS_RESPONSE` **逐字一致**（含 12355 热线），`crisis=true` | A2 |
| D5 | R2 未配置（三个 `KB_VECTOR_*` 全空） | `/f/media` 上传/取回/删除 → **503 `R2_NOT_CONFIGURED`**，不是 500 | POST/GET/DELETE 全部 **503 `R2_NOT_CONFIGURED`**（31/28/36ms）；**UI 实测**：拍题面板红字「上传失败：对象存储未配置，请联系管理员」 | A4/A5/A6 + E2E Step 4 |
| D6 | 带图 Chat 但 R2 不可用 | 不让整轮失败：降级纯文本，200 | **200**（49ms），回复正常给出（mock 下为兜底文案；真实 LLM 下的「看不到图」措辞属模型行为，未单测） | A3 |
| D7 | 实例重启时有遗留 queued/processing 任务 | 启动对账 → `failed` + `CHAT_JOB_INTERRUPTED` + 用户可读文案 | 预插 `cj_e2ereconcile001 (queued)` → 重启 → `GET /chat/jobs/{id}`：**`status=failed, errorCode=CHAT_JOB_INTERRUPTED, errorMessage="服务刚刚重启，这次带图提问没有跑完，请再发一次"`** | A7 |
| D8 | 向量索引文件缺失（worktree 无 `kb_vectors/`） | 启动照常；检索静默降级 `name_fuzzy`；`/health/vector-index` 暴露退化 | 启动无异常；**`/health/vector-index` → `status=degraded, searchMode=name_fuzzy, searchable=false, indexFileExists=false`**；启动日志「[VECTOR] 索引文件不存在…检索将降级 name_fuzzy」 | 启动实测 |
| D9 | embedding API 配置缺失（`KB_EMBED_MODE=api` 但无 key） | `embed_text` 返回 None → `name_fuzzy` 降级，不抛 500 | `GET /knowledge/points/match?text=勾股定理` → **200 `{"items":[],"matchedBy":"keyword_fallback"}`**（库空 + 降级，两种空都如实返回） | A11 |
| D10 | SMTP 凭据缺失（`SMTP_PROVIDER=real` 且 user/pass 空） | 短路不连网；验证码已落库；接口不阻塞 | 接口 200；日志 **`[SMTP] 未配置 SMTP_USER/SMTP_PASS，验证码 564382 未发送`**；`auth_codes` 1 行 | backend2.log |
| D11 | SMTP 主机不可达（真发信失败：`127.0.0.1:1` + 假凭据） | 后台任务失败只记日志；**接口快速 200**、码在库 | 接口 **200（126ms）**；随后日志 `[SMTP] 发送 register 验证码失败` + ConnectionRefused traceback；`auth_codes` 已有行。这正是 2026-10-11 事故修的「发信必须后台化」的回归验证 | backend3.log |
| D12 | 数据库在**启动时**不可用（路径指向目录） | ——（未承诺；实测什么就是什么） | **lifespan 崩溃、服务起不来**：`sqlite3.OperationalError: unable to open database file` → starlette lifespan 抛错，8011 无监听。⚠️ `/health degraded` 分支只覆盖「启动后库变坏」，Windows 文件锁下无法安全实测该场景（运行中改 data.db），**如实标注未测** | baddb3.log |
| D13 | 真实 LLM 慢调用期间的辅助写（ai_call_logs / usage_ledger 真实行） | 留痕必须落库（PRD 6.5）、真实用量必须记账（铁律 5） | **❌ 双双丢失**：INSERT 后 5.5s ROLLBACK（写锁 busy timeout），且失败被 `logger.debug` 吞掉。详见 E2E 文档 §2.2（P1）。**mock 快调用下 5/5 全部落库** → 问题锁定在慢调用窗口的写锁竞争 | backend.log + A13 |
| — | 安全审核拦截（`check()` 命中禁止词后走模板） | 建议走模板、chat 走兜底 | **未实测**：不改代码无法注入「模型输出恰好命中黑名单」；该分支由 `tests/test_ai_suggestion*` 单测覆盖。要在 E2E 层实测需可控 provider（如加测试用毒化 provider），属后续项 | — |

## 1. 结论

- **12/13 行有实测**，全部与代码/契约口径一致——除了 D13，它是本轮 E2E 抓出的**真实缺陷**（SQLite 运行时）。
- pilot 放行前建议处理两件事（见 E2E 文档 §2）：
  1. P0 计时页白屏（E2E 抓出，非降级矩阵项）；
  2. P1 慢调用辅助写丢失（D13），或至少在 Neon 上复核该问题是否存在。
- 建议把本文件挂进主计划 §7 门 4 的销项记录；门 4 的表述「降级矩阵每条有实测记录」至此有了第一份完整载体。
