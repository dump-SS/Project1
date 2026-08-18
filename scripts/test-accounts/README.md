# EpochX 团队测试账号（test-accounts）

> 团队开发/联调用的固定测试账号 + 场景化数据。
> **不用于生产环境**。若误用生产 DB，请立即回滚并重置密码。

## 为什么需要这个

接手时发现：

- mock-server 已退役，但 163 邮箱 SMTP 在团队本地**经常被限流或 535 鉴权失败**
- 每个团队成员手动注册测试账号既慢又乱（每人一个临时邮箱，数据各异）
- 复现 bug 时，需要稳定可复现的"冷启动/活跃/疲劳"三种状态

这个目录提供 **3 个固定场景账号**，跑一次脚本就建好，团队共用来做：
- 自动化截图测试
- 端到端页面验证
- 调权/复盘/建议的回归验证
- 状态机边界值测试

## 三个测试账号

| 邮箱 | 密码 | 场景 | 数据 |
|---|---|---|---|
| `team-coldstart@epochx.dev` | `TestColdStart2026!` | **冷启动**（0 学习记录） | 仅完成建档 |
| `team-active@epochx.dev` | `TestActive2026!` | **活跃用户**（高效稳定） | 14 条记录，3 天连击，windowScore 高 |
| `team-fatigue@epochx.dev` | `TestFatigue2026!` | **疲劳预警** | 5 条记录，连续 fatigue=5，stateLabel=fatigue_warning |

> 密码、邮箱都在 [accounts.json](./accounts.json) 里，请勿上传到任何外网（仓库本身不 push 任何凭据到 .env）。
> 但 epochx.dev 是占位子域——**没有真实 DNS 解析**，仅作为唯一标识符使用。

## 快速开始

### 0. 前置条件

- 后端在 `localhost:8000` 运行
- 前端在 `localhost:5173` 运行
- `backend/.env` 已配 `SMTP_PROVIDER=mock`（**重要**）

```bash
# 在 backend/.env 末尾加一行
echo "SMTP_PROVIDER=mock" >> backend/.env

# 重启后端让配置生效
cd backend
.venv/Scripts/python.exe -m uvicorn main:app --port 8000
```

### 1. 跑种子脚本

```bash
cd scripts/test-accounts
python seed.py
```

脚本会：

1. 检测后端连通性 + SMTP_PROVIDER 配置
2. 对每个账号：
   - 调用 `/auth/send-register-code` 触发验证码
   - **暂停等你输入验证码**（从后端终端 grep `MOCK-EMAIL` 取码）
   - 调 `/auth/register` 完成注册
   - 调 `/learning-records` 注入场景数据（活跃 14 条 / 疲劳 5 条）

### 2. 取验证码的方法

后端终端会输出类似（mock 模式）：

```
WARNING  auth.email.mock: [MOCK-EMAIL] type=register to=team-active@epochx.dev code=482917
(SMTP_PROVIDER=mock, 团队测试模式, 直接从日志取码即可)
```

把 `code=482917` 复制到脚本提示里即可。

### 3. 用测试账号登录

打开 `http://localhost:5173/login`，切到「密码登录」tab，输上面任一组邮箱密码即可。

## 高级用法

### 只跑某个场景

```bash
python seed.py --scenario active     # 只灌活跃用户
python seed.py --scenario fatigue    # 只灌疲劳用户
python seed.py --scenario coldstart  # 只灌冷启动
```

### 跳过 SMTP 检查（用真实邮箱时）

```bash
python seed.py --skip-check-smtp
```

**注意**：跳过检查后，验证码会发到真实邮箱（需要登录邮箱看），不走 mock 日志。

## 常见问题

### Q1: 跑了几次后说 "限流中"

**原因**：163 邮箱或 mock 表里 1 分钟内发了多条 send-code，触发限流。

**解决**：
- mock 模式：清 `auth_codes` 表
  ```python
  python -c "import sqlite3; c=sqlite3.connect('backend/data.db'); c.execute('DELETE FROM auth_codes'); c.commit()"
  ```
- real 模式：等 60 秒或换邮箱

### Q2: 提示 "已存在 (409)"

脚本幂等：账号已注册时会跳过注册步骤，直接灌数据。如果要重建：

```python
# 清空所有测试账号
python -c "import sqlite3; c=sqlite3.connect('backend/data.db'); \
[c.execute('DELETE FROM auth_users WHERE email LIKE \"%@epochx.dev\"'), \
 c.execute('DELETE FROM learning_records WHERE user_id LIKE \"%@epochx.dev\"'), \
 c.execute('DELETE FROM users WHERE id LIKE \"%@epochx.dev\"'), \
 c.commit()]"
```

### Q3: 想新增一个场景（比如"情绪受阻"）

1. 在 `accounts.json` 加一个账号条目
2. 在 `seed.py` 加一个 `seed_*_user` 函数 + 在 main 循环里挂载
3. 重新跑脚本

### Q4: 后端改了启动端口

编辑 `seed.py` 顶部的 `BASE_URL`：
```python
BASE_URL = "http://localhost:8000/api/v1"  # 改这里
```

## 注意事项

1. **不要提交到生产 DB**：`accounts.json` 的邮箱后缀是 `epochx.dev` 占位子域。
2. **密码只是开发用**：8 位以上含大小写 + 数字 + 符号，但写在 `accounts.json` 公开文件里——**任何能看 git 的人都能登录**。
3. **不要往这些账号灌真实数据**：会影响团队测试结果的可复现性。
4. **mock 模式不影响路由测试**：`tests/test_auth.py` 仍走自己的清表逻辑，不与本脚本冲突。

## 文件清单

```
scripts/test-accounts/
├── README.md      # 本文件
├── accounts.json  # 3 个测试账号的元数据（邮箱/密码/场景/数据模板）
└── seed.py        # 主入口：注册 + 灌数据
```