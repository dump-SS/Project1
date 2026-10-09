// 前端纯函数运行时校验（本项目前端没有测试框架，用 esbuild 就地转译后跑真实代码）。
//
// **为什么需要**：`frontend/tsconfig.json` 有意只检查 `.ts/.tsx`，而页面是 `.jsx`；
// `vite build` 只能抓引用/语法错，**抓不到逻辑错**。所以把容易写错的纯逻辑
// （计时恢复数学、目标树组装）单独拎出来跑真实代码做断言——
// 不是"重写一份逻辑自证"，而是转译后直接 import 真模块。
//
// 用法（在 frontend/ 目录）：node ../scripts/verify_frontend_pure_fns.mjs
// 依赖 frontend/node_modules 里的 esbuild（vite 自带），不需要额外安装。
//
// 退出码：0 = 全过；非 0 = 有断言失败。
import assert from 'node:assert'
import { pathToFileURL } from 'node:url'
import path from 'node:path'

const frontendDir = path.resolve(process.cwd())
const esbuildEntry = path.join(frontendDir, 'node_modules', 'esbuild', 'lib', 'main.js')
const { build } = await import(pathToFileURL(esbuildEntry).href)

async function loadModule(relPath) {
  const result = await build({
    entryPoints: [path.join(frontendDir, relPath)],
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
  return import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'))
}

let passed = 0
function check(name, fn) {
  fn()
  passed += 1
  console.log('  ok  ' + name)
}

// ===========================================================================
console.log('== services/timer.ts（D30 恢复数学）==')
const timer = await loadModule('src/services/timer.ts')
const { computeDisplaySeconds, computeElapsedSeconds, isCountdownReached } = timer

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
  assert.strictEqual(computeDisplaySeconds(s, at(7)).remaining, 18 * 60)
  assert.strictEqual(computeDisplaySeconds(s, at(7)).remaining, computeDisplaySeconds(s, at(7)).remaining)
})

check('时间戳异常时不炸（返回 0）', () => {
  assert.strictEqual(computeElapsedSeconds({ startedAt: 'not-a-date' }, Date.now()), 0)
})

// ===========================================================================
console.log('\n== services/goals.ts（D6 目标树组装）==')
const goalsMod = await loadModule('src/services/goals.ts')
const { buildGoalTree } = goalsMod

const card = (goalId, parentGoalId = null) => ({
  goalId,
  title: goalId,
  type: 'short_term',
  subject: 'SX',
  parentGoalId,
  examId: null,
  targetScore: null,
  percent: 0,
})

check('扁平列表 → 父子嵌套（根在前，子挂父下）', () => {
  const tree = buildGoalTree([card('root'), card('kid', 'root')])
  assert.strictEqual(tree.length, 1, '只有一个根')
  assert.strictEqual(tree[0].goalId, 'root')
  assert.deepStrictEqual(tree[0].children.map((c) => c.goalId), ['kid'])
})

check('父不在列表里（已归档/丢页）→ 子按顶层处理，不整条丢掉', () => {
  const tree = buildGoalTree([card('orphan', 'g_gone')])
  assert.strictEqual(tree.length, 1)
  assert.strictEqual(tree[0].goalId, 'orphan')
  assert.deepStrictEqual(tree[0].children, [])
})

check('历史脏数据成环 → 断环并收敛，不死循环', () => {
  // a → b → a，组装时若不 visited 会无限递归
  const tree = buildGoalTree([card('a', 'b'), card('b', 'a')])
  assert.strictEqual(tree.length, 1, '成环时至少仍能渲染出一个根')
  const seen = []
  const walk = (n) => {
    seen.push(n.goalId)
    ;(n.children ?? []).forEach(walk)
  }
  tree.forEach(walk)
  assert.strictEqual(new Set(seen).size, seen.length, '同一节点不应被渲染两次')
})

check('空列表 / 全平级都不炸', () => {
  assert.deepStrictEqual(buildGoalTree([]), [])
  const flat = buildGoalTree([card('x'), card('y')])
  assert.deepStrictEqual(flat.map((g) => g.goalId), ['x', 'y'])
})

console.log(`\n${passed} passed`)
