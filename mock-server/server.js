// EpochX API Server —— 本地开发服务，验证码通过 163 SMTP 真实发送
// 启动: node mock-server/server.js  (监听 http://localhost:4000)
// 数据持久化到 SQLite（mock-server/data.db，已加入 .gitignore）
// SMTP 配置见 mock-server/.env（已加入 .gitignore，不提交到仓库）

import http from 'node:http'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { DatabaseSync } from 'node:sqlite'
import dotenv from 'dotenv'
import nodemailer from 'nodemailer'
import { EMAIL_LOGO_DATA_URI } from './email-logo.b64.js'

dotenv.config({ path: fileURLToPath(new URL('./.env', import.meta.url)) })

const PORT = 4000
const DB_PATH = fileURLToPath(new URL('./data.db', import.meta.url))
const SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000  // 会话有效期 7 天
const CODE_TTL_MS = 5 * 60 * 1000                 // 验证码有效期 5 分钟
const MAX_FAILS = 5                                // 连续验证失败上限
const LOCK_MS = 15 * 60 * 1000                     // 锁定 15 分钟

/* ===================== SMTP ===================== */

const transporter = nodemailer.createTransport({
  host: process.env.SMTP_HOST || 'smtp.163.com',
  port: Number(process.env.SMTP_PORT) || 465,
  secure: true,
  auth: {
    user: process.env.SMTP_USER,
    pass: process.env.SMTP_PASS
  }
})

/* ===================== SQLite 数据库 ===================== */

const db = new DatabaseSync(DB_PATH)

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    email        TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at   TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS codes (
    type       TEXT NOT NULL,
    email      TEXT NOT NULL,
    code_hash  TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    PRIMARY KEY (type, email)
  );

  CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS learning_records (
    record_id         TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL,
    subject           TEXT NOT NULL,
    started_at        TEXT NOT NULL,
    duration_minutes  INTEGER NOT NULL,
    completion        TEXT NOT NULL,
    focus             INTEGER NOT NULL,
    fatigue           INTEGER NOT NULL,
    emotion           TEXT NOT NULL,
    difficulty_feel   TEXT NOT NULL,
    created_at        TEXT NOT NULL
  );

CREATE TABLE IF NOT EXISTS feedbacks (
    target_type TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    rating      TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    PRIMARY KEY (target_type, target_id)
  );

  CREATE TABLE IF NOT EXISTS plans (
    email            TEXT NOT NULL,
    plan_date        TEXT NOT NULL,
    available_minutes INTEGER NOT NULL,
    payload_json     TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (email, plan_date)
  );
`)

/* ===================== 密码哈希（scrypt + 随机盐） ===================== */

function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex')
  const hash = crypto.scryptSync(password, salt, 64).toString('hex')
  return `${salt}:${hash}`
}

function verifyPassword(password, stored) {
  if (!stored || !stored.includes(':')) return false
  const [salt, hash] = stored.split(':')
  const expected = Buffer.from(hash, 'hex')
  const actual = crypto.scryptSync(password, salt, 64)
  return expected.length === actual.length && crypto.timingSafeEqual(expected, actual)
}

// 密码复杂度：大写字母 / 小写字母 / 数字 / 符号 四类中至少满足两类
function isStrongPassword(password) {
  const kinds = [/[A-Z]/, /[a-z]/, /\d/, /[^A-Za-z0-9]/].filter((re) => re.test(password)).length
  return kinds >= 2
}

/* ===================== 通用哈希 ===================== */

function sha256(input) {
  return crypto.createHash('sha256').update(String(input)).digest('hex')
}

function safeEqual(aHex, bHex) {
  const a = Buffer.from(aHex, 'hex')
  const b = Buffer.from(bHex, 'hex')
  return a.length === b.length && crypto.timingSafeEqual(a, b)
}

/* ===================== 学习记录 ===================== */

const SUBJECTS = ['chinese', 'math', 'english', 'physics', 'chemistry', 'biology', 'history', 'geography', 'politics', 'other']
const EMOTIONS = ['positive', 'neutral', 'negative']
const DIFFICULTIES = ['easy', 'moderate', 'hard']
const COMPLETIONS = ['completed', 'partial', 'abandoned']

function genId(prefix) {
  return `${prefix}_${crypto.randomBytes(4).toString('hex')}`
}

function buildRecommendationItems(record) {
  const items = []
  if (record.fatigue >= 4) {
    items.push({
      title: '这次有点累了，下次把单次时长压短一点',
      content: `你的疲劳度自评是 ${record.fatigue} 分，建议下次缩短单次专注时长，中间多安排 5 分钟休息，恢复精力再继续。`,
    })
  }
  if (record.focus >= 4) {
    items.push({
      title: '专注状态不错，保持这个节奏',
      content: `这次专注度自评 ${record.focus} 分，说明这个时段和状态挺适合你，可以继续沿用。`,
    })
  }
  if (items.length === 0) {
    items.push({
      title: '平稳完成，继续保持',
      content: '这次的专注时长和自评都比较平稳，按自己的节奏来，积累下去会看到变化的。',
    })
  }
  return items
}

/* ===================== 验证码 ===================== */

function genCode() {
  const code = String(Math.floor(100000 + Math.random() * 900000))
  console.log(`[DEV] 验证码: ${code}`)
  return code
}

// 邮件 HTML（主题色 #4AD1FF，衬线体标题 + 非衬线正文）
function buildEmailHtml(type, code) {
  const copy = {
    register: {
      title: '欢迎加入 EpochX',
      greeting: '感谢你注册 EpochX，请输入下面的验证码完成邮箱验证：'
    },
    login: {
      title: '登录验证码',
      greeting: '你正在登录 EpochX，请输入下面的验证码完成登录：'
    },
    reset: {
      title: '重置密码验证码',
      greeting: '你正在重置登录密码，请输入下面的验证码继续：'
    }
  }[type] || {
    title: '邮箱验证码',
    greeting: '请输入下面的验证码完成验证：'
  }

  return `<!DOCTYPE html>
<html lang="zh-CN">
<body style="margin:0;padding:0;background:#f2fafd;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f2fafd;padding:36px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;">
          <tr>
            <td style="background:#ffffff;border-radius:16px;padding:40px 36px 36px;border:1px solid #e8f6fc;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 14px;">
                <tr>
                  <td align="left" valign="top" style="font-family:Georgia,'Noto Serif SC','Songti SC',serif;font-size:22px;font-weight:bold;color:#2c3e50;letter-spacing:1px;">${copy.title}</td>
                  <td align="right" valign="top" style="width:52px;">
                    <img src="${EMAIL_LOGO_DATA_URI}" alt="EpochX" width="44" height="44" style="display:block;border:0;outline:none;" />
                  </td>
                </tr>
              </table>
              <div style="width:44px;height:4px;background:#4AD1FF;border-radius:2px;margin:0 0 26px;"></div>
              <p style="font-family:'PingFang SC','Microsoft YaHei',sans-serif;font-size:14px;color:#5a6b7a;line-height:1.8;margin:0 0 26px;">${copy.greeting}</p>
              <div style="background:#eaf7ff;border:1px solid #cdeeff;border-radius:12px;padding:22px 16px;text-align:center;margin:0 0 26px;">
                <div style="font-family:'PingFang SC','Microsoft YaHei',sans-serif;font-size:12px;color:#7a8a99;letter-spacing:3px;margin-bottom:10px;">验 证 码</div>
                <div style="font-family:'Courier New',Consolas,monospace;font-size:36px;font-weight:bold;color:#4AD1FF;letter-spacing:6px;padding-left:6px;line-height:1;">${code}</div>
              </div>
              <p style="font-family:'PingFang SC','Microsoft YaHei',sans-serif;font-size:12px;color:#9aa8b5;line-height:1.7;margin:0;">验证码 5 分钟内有效，请勿泄露给他人。<br>如非本人操作，请忽略本邮件。</p>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:18px 0 0;font-family:'PingFang SC','Microsoft YaHei',sans-serif;font-size:12px;color:#b0bcc7;">EpochX</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`
}

async function setCode(type, email) {
  const code = genCode()
  const subjects = {
    register: '【EpochX】注册验证码',
    reset: '【EpochX】重置密码验证码',
    login: '【EpochX】登录验证码'
  }
  const subject = subjects[type] || '【EpochX】邮箱验证码'
  // 开发环境跳过 SMTP 发送，验证码直接输出到控制台
  try {
    const info = await transporter.sendMail({
      from: `"EpochX" <${process.env.SMTP_USER}>`,
      to: email,
      subject,
      text: `您的验证码是 ${code}，5 分钟内有效。如非本人操作，请忽略本邮件。`,
      html: buildEmailHtml(type, code)
    })
    console.log(`[SMTP] 已发送 ${subject} -> ${email} (messageId: ${info.messageId})`)
  } catch (smtpErr) {
    console.log(`[DEV] SMTP 发送失败，开发模式跳过邮件: ${smtpErr.message}`)
  }
  const expiresAt = Date.now() + CODE_TTL_MS
  db.prepare(`
    INSERT INTO codes (type, email, code_hash, expires_at) VALUES (?, ?, ?, ?)
    ON CONFLICT(type, email) DO UPDATE SET
      code_hash = excluded.code_hash,
      expires_at = excluded.expires_at
  `).run(type, email, sha256(code), expiresAt)
}

function verifyCode(type, email, code) {
  const row = db.prepare('SELECT code_hash, expires_at FROM codes WHERE type = ? AND email = ?').get(type, email)
  if (!row) return { ok: false, msg: '请先获取验证码' }
  if (Date.now() > row.expires_at) return { ok: false, msg: '验证码已过期' }
  if (!safeEqual(row.code_hash, sha256(code))) return { ok: false, msg: '验证码不正确' }
  return { ok: true }
}

function consumeCode(type, email) {
  db.prepare('DELETE FROM codes WHERE type = ? AND email = ?').run(type, email)
}

/* ===================== Session ===================== */

function parseCookies(header) {
  const out = {}
  if (!header) return out
  for (const part of header.split(';')) {
    const i = part.indexOf('=')
    if (i === -1) continue
    out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim())
  }
  return out
}

function createSession(email) {
  const token = crypto.randomBytes(32).toString('hex')
  const expiresAt = Date.now() + SESSION_TTL_MS
  db.prepare('INSERT INTO sessions (token_hash, email, expires_at, created_at) VALUES (?, ?, ?, ?)')
    .run(sha256(token), email, expiresAt, new Date().toISOString())
  return {
    cookie: `sid=${token}; HttpOnly; Path=/; SameSite=Lax; Max-Age=${Math.floor(SESSION_TTL_MS / 1000)}`
  }
}

function getSession(req) {
  const sid = parseCookies(req.headers.cookie).sid
  if (!sid) return null
  const hash = sha256(sid)
  const row = db.prepare('SELECT email, expires_at FROM sessions WHERE token_hash = ?').get(hash)
  if (!row) return null
  if (Date.now() > row.expires_at) {
    db.prepare('DELETE FROM sessions WHERE token_hash = ?').run(hash)
    return null
  }
  return { email: row.email }
}

function destroySession(req) {
  const sid = parseCookies(req.headers.cookie).sid
  if (sid) db.prepare('DELETE FROM sessions WHERE token_hash = ?').run(sha256(sid))
  return 'sid=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0'
}

/* ===================== 限流（进程内存级） ===================== */

const rateBuckets = new Map()  // key -> { count, resetAt }

function allow(key, limit, windowMs) {
  const now = Date.now()
  const b = rateBuckets.get(key)
  if (!b || now >= b.resetAt) {
    rateBuckets.set(key, { count: 1, resetAt: now + windowMs })
    return true
  }
  if (b.count >= limit) return false
  b.count++
  return true
}

// 连续验证失败锁定（防暴力破解）
const loginFails = new Map()  // email -> { count, lockedUntil }

function isLocked(email) {
  const rec = loginFails.get(email)
  if (!rec) return false
  if (rec.lockedUntil && Date.now() < rec.lockedUntil) return true
  if (rec.lockedUntil) loginFails.delete(email)
  return false
}

function recordFail(email) {
  const rec = loginFails.get(email) || { count: 0, lockedUntil: 0 }
  rec.count++
  if (rec.count >= MAX_FAILS) {
    rec.lockedUntil = Date.now() + LOCK_MS
    rec.count = 0
  }
  loginFails.set(email, rec)
}

function clearFails(email) {
  loginFails.delete(email)
}

function clientIp(req) {
  const fwd = req.headers['x-forwarded-for']
  if (fwd) return String(fwd).split(',')[0].trim()
  return req.socket.remoteAddress || 'unknown'
}

/* ===================== HTTP 工具 ===================== */

function json(res, status, data, extraHeaders = {}) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    ...extraHeaders
  })
  res.end(JSON.stringify(data))
}

async function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = ''
    req.on('data', (c) => { raw += c })
    req.on('end', () => {
      try { resolve(raw ? JSON.parse(raw) : {}) }
      catch (_) { reject(new Error('JSON 解析失败')) }
    })
    req.on('error', reject)
  })
}

function err(res, status, code, message, field) {
  json(res, status, { error: { code, message, field } })
}

const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/

/* ===================== 路由处理 ===================== */

const server = http.createServer(async (req, res) => {
  // CORS 预检
  if (req.method === 'OPTIONS') { json(res, 204, {}); return }

  const url = new URL(req.url, `http://${req.headers.host}`)
  const path = url.pathname
  let body = {}
  if (req.method === 'POST') {
    try { body = await readBody(req) }
    catch (_) { return err(res, 400, 'VALIDATION_FAILED', '请求体格式错误') }
  }

  try {

    /* --------------- 1. 发送验证码 --------------- */

    // 注册验证码
    if (path === '/api/v1/auth/send-register-code' && req.method === 'POST') {
      const { email } = body
      if (!EMAIL_RE.test(email)) return err(res, 400, 'VALIDATION_FAILED', '邮箱格式不正确', 'email')
      const existing = db.prepare('SELECT email FROM users WHERE email = ?').get(email)
      if (existing) return err(res, 409, 'EMAIL_ALREADY_REGISTERED', '该邮箱已注册，请直接登录', 'email')
      const ip = clientIp(req)
      if (!allow('ip:' + ip, 20, 3600_000)) return err(res, 429, 'RATE_LIMITED', '请求过于频繁，请稍后再试')
      if (!allow('code:' + email, 1, 60_000)) return err(res, 429, 'RATE_LIMITED', '验证码发送过于频繁，请稍后再试')
      await setCode('register', email)
      return json(res, 200, { ok: true, sent: true })
    }

    // 重置密码验证码
    if (path === '/api/v1/auth/send-reset-code' && req.method === 'POST') {
      const { email } = body
      if (!EMAIL_RE.test(email)) return err(res, 400, 'VALIDATION_FAILED', '邮箱格式不正确', 'email')
      const existing = db.prepare('SELECT email FROM users WHERE email = ?').get(email)
      if (!existing) return err(res, 404, 'EMAIL_NOT_REGISTERED', '该邮箱尚未注册，请先注册', 'email')
      const ip = clientIp(req)
      if (!allow('ip:' + ip, 20, 3600_000)) return err(res, 429, 'RATE_LIMITED', '请求过于频繁，请稍后再试')
      if (!allow('code:' + email, 1, 60_000)) return err(res, 429, 'RATE_LIMITED', '验证码发送过于频繁，请稍后再试')
      await setCode('reset', email)
      return json(res, 200, { ok: true, sent: true })
    }

    // 登录验证码
    if (path === '/api/v1/auth/send-login-code' && req.method === 'POST') {
      const { email } = body
      if (!EMAIL_RE.test(email)) return err(res, 400, 'VALIDATION_FAILED', '邮箱格式不正确', 'email')
      const existing = db.prepare('SELECT email FROM users WHERE email = ?').get(email)
      if (!existing) return err(res, 404, 'EMAIL_NOT_REGISTERED', '该邮箱尚未注册，请先注册', 'email')
      const ip = clientIp(req)
      if (!allow('ip:' + ip, 20, 3600_000)) return err(res, 429, 'RATE_LIMITED', '请求过于频繁，请稍后再试')
      if (!allow('code:' + email, 1, 60_000)) return err(res, 429, 'RATE_LIMITED', '验证码发送过于频繁，请稍后再试')
      await setCode('login', email)
      return json(res, 200, { ok: true, sent: true })
    }

    /* --------------- 2. 注册 --------------- */

    if (path === '/api/v1/auth/register' && req.method === 'POST') {
      const { email, code, password, confirmPassword } = body
      if (!EMAIL_RE.test(email)) return err(res, 400, 'VALIDATION_FAILED', '邮箱格式不正确', 'email')
      if (db.prepare('SELECT email FROM users WHERE email = ?').get(email)) return err(res, 409, 'EMAIL_ALREADY_REGISTERED', '该邮箱已注册，请直接登录', 'email')
      if (!/^\d{6}$/.test(String(code))) return err(res, 400, 'VALIDATION_FAILED', '验证码为 6 位数字', 'code')
      if (!password || password.length < 6 || password.length > 32) return err(res, 400, 'VALIDATION_FAILED', '密码长度 6-32 位', 'password')
      if (!isStrongPassword(password)) return err(res, 400, 'VALIDATION_FAILED', '密码需包含大写字母、小写字母、数字、符号中的至少两种', 'password')
      if (password !== confirmPassword) return err(res, 400, 'VALIDATION_FAILED', '两次输入的密码不一致', 'confirmPassword')

      if (isLocked(email)) return err(res, 429, 'RATE_LIMITED', '验证失败次数过多，请 15 分钟后再试')

      const v = verifyCode('register', email, code)
      if (!v.ok) { recordFail(email); return err(res, 400, 'CODE_INVALID', v.msg, 'code') }
      consumeCode('register', email)
      clearFails(email)

      db.prepare('INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)')
        .run(email, hashPassword(password), new Date().toISOString())
      console.log(`[REGISTER] 新用户注册: ${email}`)
      return json(res, 201, { ok: true })
    }

    /* --------------- 3. 登录 --------------- */

    // 邮箱 + 验证码登录
    if (path === '/api/v1/auth/login-email-code' && req.method === 'POST') {
      const { email, code } = body
      if (!EMAIL_RE.test(email)) return err(res, 400, 'VALIDATION_FAILED', '邮箱格式不正确', 'email')

      const existing = db.prepare('SELECT email FROM users WHERE email = ?').get(email)
      if (!existing) return err(res, 404, 'EMAIL_NOT_REGISTERED', '该邮箱尚未注册，请先注册', 'email')

      if (isLocked(email)) return err(res, 429, 'RATE_LIMITED', '验证失败次数过多，请 15 分钟后再试')

      const v = verifyCode('login', email, code)
      if (!v.ok) { recordFail(email); return err(res, 400, 'CODE_INVALID', v.msg, 'code') }
      consumeCode('login', email)
      clearFails(email)

      const session = createSession(email)
      return json(res, 200, { ok: true }, { 'Set-Cookie': session.cookie })
    }

    // 邮箱 + 密码登录
    if (path === '/api/v1/auth/login-password' && req.method === 'POST') {
      const { email, password } = body
      if (!EMAIL_RE.test(email)) return err(res, 400, 'VALIDATION_FAILED', '邮箱格式不正确', 'email')
      if (!password) return err(res, 400, 'VALIDATION_FAILED', '请输入密码', 'password')

      const u = db.prepare('SELECT email, password_hash FROM users WHERE email = ?').get(email)
      if (!u) return err(res, 404, 'EMAIL_NOT_REGISTERED', '该邮箱尚未注册，请先注册', 'email')

      if (isLocked(email)) return err(res, 429, 'RATE_LIMITED', '验证失败次数过多，请 15 分钟后再试')

      if (!verifyPassword(password, u.password_hash)) {
        recordFail(email)
        return err(res, 401, 'PASSWORD_INCORRECT', '密码错误', 'password')
      }
      clearFails(email)

      const session = createSession(email)
      return json(res, 200, { ok: true }, { 'Set-Cookie': session.cookie })
    }

    /* --------------- 4. 会话（登录态校验 / 退出） --------------- */

    if (path === '/api/v1/auth/me' && req.method === 'GET') {
      const session = getSession(req)
      if (!session) return err(res, 401, 'UNAUTHORIZED', '未登录或登录已过期')
      return json(res, 200, { ok: true, user: { email: session.email } })
    }

    if (path === '/api/v1/auth/logout' && req.method === 'POST') {
      const cookie = destroySession(req)
      return json(res, 200, { ok: true }, { 'Set-Cookie': cookie })
    }

    /* --------------- 5. 重置密码 --------------- */

    if (path === '/api/v1/auth/verify-reset-code' && req.method === 'POST') {
      const { email, code } = body
      if (!EMAIL_RE.test(email)) return err(res, 400, 'VALIDATION_FAILED', '邮箱格式不正确', 'email')

      if (isLocked(email)) return err(res, 429, 'RATE_LIMITED', '验证失败次数过多，请 15 分钟后再试')

      const v = verifyCode('reset', email, code)
      if (!v.ok) { recordFail(email); return err(res, 400, 'CODE_INVALID', v.msg, 'code') }
      // 不消费，后面 reset-password 还会再校验一次
      return json(res, 200, { ok: true })
    }

    if (path === '/api/v1/auth/reset-password' && req.method === 'POST') {
      const { email, code, newPassword, confirmPassword } = body
      if (!EMAIL_RE.test(email)) return err(res, 400, 'VALIDATION_FAILED', '邮箱格式不正确', 'email')
      if (!/^\d{6}$/.test(String(code))) return err(res, 400, 'VALIDATION_FAILED', '验证码为 6 位数字', 'code')
      if (!newPassword || newPassword.length < 6 || newPassword.length > 32) return err(res, 400, 'VALIDATION_FAILED', '密码长度 6-32 位', 'newPassword')
      if (!isStrongPassword(newPassword)) return err(res, 400, 'VALIDATION_FAILED', '密码需包含大写字母、小写字母、数字、符号中的至少两种', 'newPassword')
      if (newPassword !== confirmPassword) return err(res, 400, 'VALIDATION_FAILED', '两次输入的密码不一致', 'confirmPassword')

      const u = db.prepare('SELECT email FROM users WHERE email = ?').get(email)
      if (!u) return err(res, 404, 'EMAIL_NOT_REGISTERED', '该邮箱尚未注册，请先注册', 'email')

      if (isLocked(email)) return err(res, 429, 'RATE_LIMITED', '验证失败次数过多，请 15 分钟后再试')

      const v = verifyCode('reset', email, code)
      if (!v.ok) { recordFail(email); return err(res, 400, 'CODE_INVALID', v.msg, 'code') }
      consumeCode('reset', email)
      clearFails(email)

      db.prepare('UPDATE users SET password_hash = ? WHERE email = ?').run(hashPassword(newPassword), email)
      // 密码已改，使该用户所有已有会话失效
      db.prepare('DELETE FROM sessions WHERE email = ?').run(email)
      console.log(`[RESET-PWD] ${email} 密码已重置，已有会话已失效`)
      return json(res, 200, { ok: true })
    }

    /* --------------- 6. 学习记录（提交自评 + 建议轮询） --------------- */

    if (path === '/api/v1/learning-records' && req.method === 'POST') {
      const { subject, startedAt, durationMinutes, behavior, selfReport } = body || {}
      const completion = behavior?.completion
      const focus = selfReport?.focus
      const fatigue = selfReport?.fatigue
      const emotion = selfReport?.emotion
      const difficultyFeel = selfReport?.difficultyFeel

      if (!subject || !SUBJECTS.includes(subject)) return err(res, 400, 'VALIDATION_FAILED', '学科取值不合法', 'subject')
      if (!startedAt) return err(res, 400, 'VALIDATION_FAILED', '缺少学习开始时间', 'startedAt')
      if (!Number.isInteger(durationMinutes) || durationMinutes < 1 || durationMinutes > 600) return err(res, 400, 'VALIDATION_FAILED', '学习时长需为 1-600 的整数', 'durationMinutes')
      if (!completion || !COMPLETIONS.includes(completion)) return err(res, 400, 'VALIDATION_FAILED', '完成度取值不合法', 'behavior.completion')
      if (!Number.isInteger(focus) || focus < 1 || focus > 5) return err(res, 400, 'VALIDATION_FAILED', '专注度需为 1-5 的整数', 'selfReport.focus')
      if (!Number.isInteger(fatigue) || fatigue < 1 || fatigue > 5) return err(res, 400, 'VALIDATION_FAILED', '疲劳度需为 1-5 的整数', 'selfReport.fatigue')
      if (!EMOTIONS.includes(emotion)) return err(res, 400, 'VALIDATION_FAILED', '情绪取值不合法', 'selfReport.emotion')
      if (!DIFFICULTIES.includes(difficultyFeel)) return err(res, 400, 'VALIDATION_FAILED', '难度感受取值不合法', 'selfReport.difficultyFeel')

      const recordId = genId('r')
      const recommendationId = genId('rec')
      const createdAt = new Date().toISOString()

      db.prepare(`
        INSERT INTO learning_records
          (record_id, recommendation_id, subject, started_at, duration_minutes, completion, focus, fatigue, emotion, difficulty_feel, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(recordId, recommendationId, subject, startedAt, durationMinutes, completion, focus, fatigue, emotion, difficultyFeel, createdAt)

      const recordCount = db.prepare('SELECT COUNT(*) AS c FROM learning_records WHERE subject = ?').get(subject).c
      const dataSufficient = recordCount >= 3
      const stateLabel = !dataSufficient ? 'insufficient_data' : (fatigue >= 4 ? 'fatigue_warning' : 'efficient_stable')

      return json(res, 201, {
        recordId,
        subject,
        startedAt,
        durationMinutes,
        planTaskId: null,
        behavior: { completion },
        selfReport: { focus, fatigue, emotion, difficultyFeel },
        assessment: {
          assessmentId: genId('a'),
          subject,
          windowScore: Math.round((focus / 5) * 100) / 100,
          trend: 'flat',
          stateLabel,
          dataSufficient,
          recordCount,
        },
        recommendation: { recommendationId, status: 'pending' },
        createdAt,
      })
    }

    if (path.startsWith('/api/v1/recommendations/') && req.method === 'GET') {
      const recommendationId = path.slice('/api/v1/recommendations/'.length)
      const row = db.prepare('SELECT * FROM learning_records WHERE recommendation_id = ?').get(recommendationId)
      if (!row) return err(res, 404, 'RESOURCE_NOT_FOUND', '建议不存在')

      const fb = db.prepare('SELECT * FROM feedbacks WHERE target_type = ? AND target_id = ?').get('recommendation', recommendationId)

      return json(res, 200, {
        recommendationId,
        scene: 'post_session',
        subject: row.subject,
        generation: {
          status: 'ready',
          source: 'template',
          completedAt: new Date().toISOString(),
        },
        items: buildRecommendationItems(row),
        basedOn: {
          recordId: row.record_id,
          stateLabel: row.fatigue >= 4 ? 'fatigue_warning' : 'efficient_stable',
          explain: '依据本次学习记录的专注度与疲劳度自评生成',
        },
        feedback: fb ? { rating: fb.rating, submittedAt: fb.submitted_at } : null,
      })
    }

    // PUT /recommendations/{id}/feedback
    if (path.startsWith('/api/v1/recommendations/') && path.endsWith('/feedback') && req.method === 'PUT') {
      const recommendationId = path.slice('/api/v1/recommendations/'.length, -'/feedback'.length)
      const row = db.prepare('SELECT * FROM learning_records WHERE recommendation_id = ?').get(recommendationId)
      if (!row) return err(res, 404, 'RESOURCE_NOT_FOUND', '建议不存在')

      const body = await readBody(req)
      const { rating } = body
      if (!['useful', 'neutral', 'not_useful'].includes(rating)) {
        return err(res, 400, 'VALIDATION_FAILED', 'rating 需为 useful/neutral/not_useful')
      }

      const submittedAt = new Date().toISOString()
      db.prepare(`
        INSERT INTO feedbacks (target_type, target_id, rating, submitted_at) VALUES (?, ?, ?, ?)
        ON CONFLICT(target_type, target_id) DO UPDATE SET rating = excluded.rating, submitted_at = excluded.submitted_at
      `).run('recommendation', recommendationId, rating, submittedAt)

      return json(res, 200, {
        recommendationId,
        feedback: { rating, submittedAt },
      })
    }

    // GET /summaries
    if (path === '/api/v1/summaries' && req.method === 'GET') {
      const records = db.prepare('SELECT * FROM learning_records ORDER BY created_at DESC LIMIT 10').all()
      const summaryId = 'sum-latest'
      const fb = db.prepare('SELECT * FROM feedbacks WHERE target_type = ? AND target_id = ?').get('summary', summaryId)

      const items = records.length > 0 ? [{
        summaryId,
        periodStart: records[records.length - 1]?.created_at,
        periodEnd: records[0]?.created_at,
        generation: { status: 'ready', source: 'template', completedAt: new Date().toISOString() },
        content: {
          overview: `过去这段时间你完成了 ${records.length} 次学习记录，学科集中在${[...new Set(records.map(r => r.subject))].join('、')}。`,
          patterns: ['专注度整体稳定，建议保持当前学习节奏', '疲劳度适中，注意劳逸结合'],
          suggestions: ['可以尝试在专注度最高的时段安排重点学科', '每次学习后做简短回顾，强化记忆效果'],
          encouragement: '每一步坚持都算数，继续保持你的学习节奏！',
        },
        dataPoints: {
          recordCount: records.length,
          subjects: [...new Set(records.map(r => r.subject))],
          minRequired: 3,
        },
        feedback: fb ? { rating: fb.rating, submittedAt: fb.submitted_at } : null,
      }] : []

      return json(res, 200, {
        items,
        pagination: { page: 1, pageSize: 5, total: items.length, totalPages: 1 },
      })
    }

    // PUT /summaries/{id}/feedback
    if (path.startsWith('/api/v1/summaries/') && path.endsWith('/feedback') && req.method === 'PUT') {
      const summaryId = path.slice('/api/v1/summaries/'.length, -'/feedback'.length)

      const body = await readBody(req)
      const { rating } = body
      if (!['useful', 'neutral', 'not_useful'].includes(rating)) {
        return err(res, 400, 'VALIDATION_FAILED', 'rating 需为 useful/neutral/not_useful')
      }

      const submittedAt = new Date().toISOString()
      db.prepare(`
        INSERT INTO feedbacks (target_type, target_id, rating, submitted_at) VALUES (?, ?, ?, ?)
        ON CONFLICT(target_type, target_id) DO UPDATE SET rating = excluded.rating, submitted_at = excluded.submitted_at
      `).run('summary', summaryId, rating, submittedAt)

      return json(res, 200, {
        summaryId,
        feedback: { rating, submittedAt },
      })
    }

    /* --------------- 7. 学习计划（流程环节②） ---------------
     * mock 实现：仅满足"创建计划页能跑通"的最小需求。规则引擎同步生成 1-3 条任务，
     * 不走 LLM，与 openapi.yaml 2.1 Plan / PlanTask 字段保持一致（PlanAdaptation 暂无）。
     * 数据库表 plans 已在上面初始化，key = (email, plan_date)，确保同用户同日幂等。
     */

    const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

    // 任务模板：subject / topic，按 availableMinutes 拆分分钟、产出 1-3 条
    function buildPlanPayload(planDate, availableMinutes) {
      const templates = [
        { subject: 'math',    topic: '函数图像与性质 · 巩固已学' },
        { subject: 'english', topic: '单词短时高频复习' },
        { subject: 'physics', topic: '电磁感应 · 公式与例题复盘' }
      ]
      const count = availableMinutes >= 90 ? 3 : availableMinutes >= 45 ? 2 : 1
      const base = Math.floor(availableMinutes / count)
      const remainder = availableMinutes - base * count
      const tasks = []
      let acc = 0
      for (let i = 0; i < count; i++) {
        const minutes = i === count - 1 ? availableMinutes - acc : base + (i < remainder ? 1 : 0)
        acc += minutes
        tasks.push({
          taskId: `t_${Date.now()}_${i + 1}`,
          subject: templates[i].subject,
          topic: templates[i].topic,
          estimatedMinutes: minutes,
          priority: i + 1,
          status: 'pending',
          goalId: null
        })
      }
      return {
        planId: `p_${Date.now()}`,
        planDate,
        availableMinutes,
        adaptedFrom: null,
        tasks,
        createdAt: new Date().toISOString()
      }
    }

    if (path === '/api/v1/plans' && req.method === 'POST') {
      const session = getSession(req)
      if (!session) return err(res, 401, 'UNAUTHENTICATED', '未登录或登录已过期')

      const { planDate, availableMinutes, regenerate } = body
      if (!planDate || typeof planDate !== 'string' || !DATE_RE.test(planDate)) {
        return err(res, 400, 'VALIDATION_FAILED', 'planDate 必须为 YYYY-MM-DD', 'planDate')
      }
      const minutes = Number(availableMinutes)
      if (!Number.isInteger(minutes) || minutes < 10 || minutes > 600) {
        return err(res, 400, 'VALIDATION_FAILED', 'availableMinutes 必须为 10-600 的整数', 'availableMinutes')
      }

      const existing = db.prepare('SELECT payload_json FROM plans WHERE email = ? AND plan_date = ?')
        .get(session.email, planDate)
      if (existing && regenerate !== true) {
        return err(res, 409, 'STATE_CONFLICT', '当日已存在计划，如需覆盖请传 regenerate=true')
      }

      const plan = buildPlanPayload(planDate, minutes)
      db.prepare(`
        INSERT INTO plans (email, plan_date, available_minutes, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(email, plan_date) DO UPDATE SET
          available_minutes = excluded.available_minutes,
          payload_json     = excluded.payload_json,
          created_at       = excluded.created_at
      `).run(session.email, planDate, minutes, JSON.stringify(plan), plan.createdAt)

      console.log(`[PLAN] ${session.email} ${planDate} ${minutes}min 任务数=${plan.tasks.length}`)
      return json(res, 201, plan)
    }

    // 简单支持：GET /api/v1/plans?dateFrom=...&dateTo=...（仅作占位，便于前端走查）
    if (path === '/api/v1/plans' && req.method === 'GET') {
      const session = getSession(req)
      if (!session) return err(res, 401, 'UNAUTHENTICATED', '未登录或登录已过期')
      const rows = db.prepare('SELECT payload_json FROM plans WHERE email = ? ORDER BY plan_date DESC LIMIT 50')
        .all(session.email)
      return json(res, 200, { items: rows.map((r) => JSON.parse(r.payload_json)) })
    }

    /* --------------- 404 --------------- */
    return err(res, 404, 'RESOURCE_NOT_FOUND', `未找到 ${path}`)

  } catch (e) {
    console.error('[API SERVER ERROR]', e)
    return err(res, 500, 'INTERNAL_ERROR', '服务内部错误')
  }
})

server.listen(PORT, () => {
  console.log('')
  console.log('  ─────────────────────────────────────────')
  console.log(`   EpochX API Server  http://localhost:${PORT}`)
  console.log('   持久化: SQLite (mock-server/data.db)')
  console.log('   发件邮箱: ' + (process.env.SMTP_USER || '未配置'))
  console.log('  ─────────────────────────────────────────')
  console.log('')
})