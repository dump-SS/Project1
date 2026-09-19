# 落地执行细节（v0.28 配套）

> 版本：v1.0 · 2026-09-17
> 定位：[product-redesign-target.md](./product-redesign-target.md) 是**目标态**（做成什么样），本文件是**执行项**（怎么落地 + 需要新建什么）。
> 状态：均为已拍板待实施，不是待讨论项。
> 契约铁律：涉及新字段 / 新实体的一律先改 `docs/openapi.yaml`。

---

## 1. 成本计量（对应 #9）

pilot 不收费，但需**按用户统计模型花费**为后续定价做准备。

⚠️ **冲突点**：现有 `ai_call_log.py` 写 `AICallLog` 表是**刻意不带身份字段**的（合规去身份化）。按用户计费必须带身份。

**解法：分两套，不合并**

| 表 | 身份 | 内容 | 用途 | 留存 |
|---|---|---|---|---|
| `AICallLog`（现有，保持不动）| ❌ 无 | 调用留痕 | 合规审计 | 长期 |
| `usage_ledger`（**新增**）| ✅ `user_id` | **只存数值**（tokens / 成本 / 功能档位 / 时间）| 成本计量与定价依据 | 长期 |

- `usage_ledger` **不存任何提示词或输出内容**——只存数字。
- 绝不给 `AICallLog` 补身份字段（会破坏去身份化设计）。

## 2. 推理等级（#33）

- Chat 等页提供三档：**快速 / 标准 / 深度**。
- 映射到底层模型参数或不同模型；**与 credits 扣费档位绑定**（D38 已定"按功能定档"）。
- 随手问浮窗（§3.9）**跟随主对话档位**，浮窗内不单独给选择。

## 3. 多计划 / 多任务计时（#14）

- **底线：不允许并行计时**（专注态的意义）。
- 采用**一个计时会话内分段**：会话下挂多个时间段，每段标注属于哪个任务，**结束只走一次收尾**。
- 侧面板展示当日任务清单，可勾选、可点「开始计时」。
- 服务端时间戳按 mode 分支恢复（D30 已有）。

## 4. 防破甲 / 防反推型号（#17）

三层，**不要把安全建立在 prompt 保密上**：

1. **System prompt**：固定角色；被问型号 / 厂商 / system prompt 时给统一话术。
2. **输入侧检测 + 输出侧兜底**：角色扮演诱导、"忽略之前指令"检测；输出走现有 `safety_filter.py`。
3. **最重要：不把权限交给模型**——加题本、改画像、改订阅这类动作**一律走结构化 UI 确认**（复用 §3.7c 锚定确认卡），不通过对话指令直接触发。

## 5. 上传文件（#21 / #47 / #26）

- **范围**：Chat 可随意上传（不只是搜题）。照片可入闲聊提供信息；guide 场景**发作业单直接生成计划**。
- **约束**：限页数与大小；**仅会话内有效**；**文件不落库**。
- **留案**：生成的「文档要点」可进收藏（走 `privacy_filter` 脱敏），用户可删。
- ⚠️ 目前**全仓无 `UploadFile` 路由**（原 OCR 501 占位已于 M0 删除），需新建上传通道；R2 等此时再启用。
- **题面 / 解答提取必须可编辑**（§3.5）——多模态提取同样会错，这条不因放弃 OCR 而失效。

## 6. 端与适配（#6 / #10 / #12 / #11）

- **原生 App 等 beta**；pilot 只做响应式适配，重点三页：首页 Chat、计时、拍题。
- **跨端互通不需要额外功能**——同账号同后端，响应式 Web 天然互通；非实时足够，**不要上 WebSocket**。
- 移动端拍题用 `<input type="file" accept="image/*" capture>` 直接调相机。
- **官网 `域/` + 应用 `域/app`，同域**——规避 CORS 凭据与 Cookie `SameSite` 整类问题。
- 文件内**图片/图表圈选追问**为二期（多模态坐标定位精度一般）。

## 7. 账号与治理

| 项 | 要求 |
|---|---|
| **协议与条款**（#29a）| 登录前需可读；**当前未写**，登记为上线前补项（与未成年付费同级）|
| **「将个人数据用于提升体验」开关**（#29b）| 加在设置 → 授权与隐私（D41/D42 已定该页）；**默认关闭（opt-in）** |
| **内容违规处置**（#43）| 分级：1 次警告 → 3 次临时封禁 → 永久；**必须留痕**（审计需要）。现状已有敏感词阻断，缺的是累计处置与处置日志 |
| **邀请码注册**（#50）| pilot 用；**一码一用**（可追踪）；需建 `invite_codes` 表 |
| **用户报错入口**（#46）| **两处**：① 设置/帮助里常驻入口 ② **每条模型输出旁的报错按钮**（消息级才能定位问题）。报错需带上上下文（哪条消息、什么意图）——与 §8「AI 质量反馈」埋点是同一件事 |
| **虚拟奖章**（#49）| pilot 只做**最小版**：3–5 个里程碑（如"连续 7 天记录""第一次完成复盘"）。**不做积分商城 / 排行榜**（排行榜与 §4.5「社区不做社交」冲突）|

## 8. 已排除 / 已放弃

| 项 | 结论 |
|---|---|
| **OCR 路线**（#32）| **彻底放弃**，只保留多模态。✅ **M0 已落地**：`backend/routes/ocr.py` 与 `main.py` 挂载已删；目标态 §3.5 文案已同步（契约本无 /ocr 路径，删后代码与契约一致）|
| **chenglou/pretext**（#27）| 不引入。是文本测量排版库，我们用不到其核心价值 |
| **feitangyuan/motion-web**（#27）| **不能用**。License 为 **CC BY-NC 4.0，禁止商业集成**——我们收费，直接侵权。只能参考其方法论（反 AI 塑料感、弹簧阻尼、自动验收判据）|
| **FastAPI-Users**（#5）| 不引入，会重写认证层且不覆盖 14 岁以下 / 监护人授权分支。详见 [deployment-stack-evaluation.md](./deployment-stack-evaluation.md) |
| **支付相关**（#30 / #7 / #5b）| **推迟到 pilot 测试结束后**。pilot 只做用量统计与只读用量视图 |

## 9. 上线前补项汇总

- 协议与条款（缺）
- 未成年付费（监护人 / 支付资质）—— 与支付渠道选型一并推迟到 pilot 后
- ✅ **危机响应 prompt 基线（§4.6 P2）**—— 已由 X0 交付：`backend/prompts/crisis_response.txt`（三档基调 + L3 固定转介文案 + 触发范围），并**内联**进 `backend/prompts/chat_system.txt` 第 6 条硬约束（防实现侧漏注入导致合规事故）
- ✅ **#24 中学解法约束 prompt 基线**—— 已由 X0 交付：`backend/prompts/chat_system.txt` 第 1 条硬约束（禁洛必达 / 微积分等超纲方法）；B 板块据此实现，并补「超纲触发」的用例
- CORS 白名单 + Cookie `Secure`（[deployment-stack-evaluation.md](./deployment-stack-evaluation.md) §4）
- **`current_user` 越权修复（P0）** —— 任务单见 [deployment-stack-evaluation.md](./deployment-stack-evaluation.md) 附 A

## 11. 稳定用户 ID 改造（D59，pilot 期间做）

### 为什么现在做

beta 起不删档，若届时再改主键，要 UPDATE 全部业务表外键。pilot 是删档期，数据可丢、schema 可直接重建——**成本最低的窗口就是现在**。

### 已核实的现状

| 事实 | 位置 |
|---|---|
| `users.id` 已是 `String(64)` **主键**，列存在 | `models/user.py:26` |
| 但**实际填入的值就是邮箱** | `routes/deps.py:80` 拿 `get_session()` 返回值当 user_id → `routes/user.py:76` 用它建 `UserORM` |
| `auth_sessions` **存 email、返回 email** | `auth/session.py:44` / `:82` |
| **`users` 表没有 email 字段** | `models/user.py` 的 `User` 只有 id/stage/grade/subjects/onboarding_completed |
| `AuthUser` 以 **email 为主键** | `routes/auth.py:165` `db.get(AuthUser, body.email)` |
| **业务表外键都指向 `users.id`**（不是直接存 email）| `models/` 下 11 个文件 |

**结论：不需要改表结构**，只需要改"往 `users.id` 里填什么" + 给 `users` 补一个 email 列。

### 目标：三层身份

| 层 | 字段 | 变化 | 用途 |
|---|---|---|---|
| 内部主键 | `users.id` | ❌ 永不变 | 业务表外键 |
| 登录凭证 | `AuthUser.email` / 密码 / 验证码 | ✅ 可改可换绑 | 仅认证，不作身份 |
| 对外标识 | `users.handle`（可选）| ✅ 可改 | 展示，不暴露邮箱 |

### 改造步骤

1. **`users` 表加列**：`email`（唯一索引）、可选 `handle`（唯一索引，可空）。
2. **`AuthUser` 加 `user_id` 列**：指向 `users.id`；email 降为登录凭证（保留唯一约束）。
3. **注册流程改序**：先生成稳定 `user_id`（建议 `u_` + UUID4/base62 短码）→ 建 `users` 行（含 email）→ 建 `AuthUser` 行（email + user_id + password_hash）。
4. **`create_session` 存 `user_id`**（不再存 email），`get_session` **返回 `user_id`**。
5. `deps.current_user` **基本不用改**（它只拿 id 查 `User`）。
6. **改邮箱流程**：改 `AuthUser.email` + `users.email`，**`users.id` 不动** → 所有业务数据自动保留。
7. **数据迁移**（若有存量）：一次性脚本——为每个 `users.id`(=email) 生成新 id，UPDATE 所有业务表外键；**pilot 删档期可直接跳过，按新 schema 重建**。

### ⚠️ 联动项

- `deps.py` 第 4 层匿名兜底 `u_10237` 与越权问题**一并处理**（[deployment-stack-evaluation.md](./deployment-stack-evaluation.md) 附 A）。
- 测试中 8 个文件用 `X-User-ID: u_xxx` 头，新 ID 格式需保持 `u_` 前缀兼容。
- `docs/openapi.yaml` 里 `User.userId` 的语义要更新：**它是稳定 ID，不是邮箱**。
- **隐私**：`handle` 若默认生成，**不要用真名或邮箱前缀**（未成年保护）；建议随机短码，用户可改。

### 验收

- [ ] 改邮箱后，历史学习记录 / 目标 / 错题 / 收藏**全部还在**
- [ ] `users.id` 在任何业务流程（改邮箱、重新登录、换设备）中**均不变**
- [ ] 注册 / 登录 / 改邮箱 / 注销 全链路通过
- [ ] `cd backend && pytest` 全绿

## 10. 一个待查项

`kb_subjects` 表当前 **0 行**，但 `models/knowledge.py:55` 注释写"学科（kb_subjects）。**enabled=true 才可查**"。若前端学科列表依赖该表，会是空列表——**需确认学科是读表还是硬编码**。

（知识点库本身有内容：`kb_points` 3391 行、`kb_point_relations` 3127 行，已于 9/7 导入。）
