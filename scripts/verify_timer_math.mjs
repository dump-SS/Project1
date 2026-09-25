// 前端纯函数运行时校验（本项目前端没有测试框架，用 esbuild 就地转译后跑真实代码）。
//
// **为什么需要**：`frontend/tsconfig.json` 有意只检查 `.ts/.tsx`，而页面是 `.jsx`；
// `vite build` 只能抓引用/语法错，**抓不到逻辑错**。计时恢复的数学（按 mode 算剩余/累计、
// 暂停扣减、到点判定）是「刷新不丢上下文」的核心，值得单独钉住。
//
// 用法（在 frontend/ 目录）：node ../scripts/verify_timer_math.mjs
// 依赖 frontend/node_modules 里的 esbuild（vite 自带），不需要额外安装。
//
// 退出码：0 = 全过；非 0 = 有断言失败。
import assert from 'node:assert'
import { pathToFileURL } from 'node:url'
import path from 'node:path'

const frontendDir = path.resolve(process.cwd())
const esbuildEntry = path.join(frontendDir, 'node_modules', 'esbuild', 'lib', 'main.js')
const { build } = await import(pathToFileURL(esbuildEntry).href)

const result = await build({
  entryPoints: [path.join(frontendDir, 'src', 'services', 'timer.ts')],
  bundle: true,
  write: false,
  format: 'esm',
  platform: 'neutral',
  alias: { '@': path.join(frontendDir, 'src') },
  // http.ts 读了 import.meta.env.VITE_API_BASE_URL；纯 node 里没有这个对象，补一个空的
  define: { 'import.meta.env': '{}' },
  logLevel: 'silent',
})

const code = result.outputFiles[0].text
const mod = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'))
const { computeDisplaySeconds, computeElapsedSeconds, isCountdownReached } = mod

let passed = 0
function check(name, fn) {
  fn()
  passed += 1
  console.log('  ok  ' + name)
}

const T0 = Date.parse('2026-09-25T19:00:00.000Z')
const at = (min) => T0 + min * 60_000
const iso = new Date(T0).toISOString()

check('倒计时：剩余 = target − 已过', () => {
  const s = { mode: 'countdown', startedAt: iso, targetMinutes: 30 }
  assert.strictEqual(computeDisplaySeconds(s, at(10)).remaining, 20 * 60)
  assert.strictEqual(computeDisplaySeconds(s, at(10)).elapsed, 600)
})

check('倒计时到点后 remaining 夹到 0（不显示负数）', () => {
  const s = { mode: 'countdown', startedAt: iso, targetMinutes: 30 }
  assert.strictEqual(computeDisplaySeconds(s, at(45)).remaining, 0)
  // 但 elapsed 继续涨——"到点只是提醒，不自动结束"（D32）
  assert.strictEqual(computeDisplaySeconds(s, at(45)).elapsed, 45 * 60)
  assert.strictEqual(isCountdownReached(s, 45 * 60), true)
})

check('正计时：无 remaining，累计 = now − startedAt', () => {
  const s = { mode: 'countup', startedAt: iso, targetMinutes: null }
  const d = computeDisplaySeconds(s, at(50))
  assert.strictEqual(d.remaining, null)
  assert.strictEqual(d.elapsed, 50 * 60)
  assert.strictEqual(isCountdownReached(s, 50 * 60), false)
})

check('暂停时长被扣除（所以前端有暂停时要显式传 durationMinutes）', () => {
  const s = { mode: 'countup', startedAt: iso, targetMinutes: null }
  assert.strictEqual(computeElapsedSeconds(s, at(50), 15 * 60), 35 * 60)
})

check('刷新安全：同一 startedAt 在任意时刻重算结果一致（不是本地递减计数器）', () => {
  const s = { mode: 'countdown', startedAt: iso, targetMinutes: 25 }
  const a = computeDisplaySeconds(s, at(7)).remaining
  const b = computeDisplaySeconds(s, at(7)).remaining
  assert.strictEqual(a, b)
  assert.strictEqual(a, 18 * 60)
})

check('时间戳异常时不炸（返回 0）', () => {
  assert.strictEqual(computeElapsedSeconds({ startedAt: 'not-a-date' }, Date.now()), 0)
})

console.log(`\n${passed} passed`)
