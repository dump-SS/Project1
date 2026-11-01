/**
 * D57 · 科学计算器求值器（零依赖，F 板块）。
 *
 * 设计约束：
 * - 不进 package.json（独占文件），所以手写 tokenizer + 递归下降，不引 mathjs
 * - 纯函数、无 DOM，vitest 直接覆盖（.jsx 是类型检查与测试的双重盲区，
 *   所以计算核心刻意写成 .ts —— 见任务书「三、zcode 的优势」）
 *
 * 文法（^ 右结合、一元负号低于 ^、隐式乘法）：
 *   expr   := term (('+'|'-') term)*
 *   term   := unary (('*'|'/') unary)*        // 隐式乘法在此层识别
 *   unary  := ('-'|'+') unary | power
 *   power  := postfix ('^' unary)?            // 右结合，指数可带符号：2^-3
 *   postfix:= primary ('!')*
 *   primary:= number | constant | func '(' expr ')' | '(' expr ')' | ans
 *
 * 角度模式（DEG 默认）：只影响 sin/cos/tan/asin/acos/atan，
 * 高中场景 sin(30) 应回 0.5 而不是 -0.988。
 */

export type AngleMode = 'deg' | 'rad'

/** 求值失败的业务错误（message 直接可展示给学生） */
export class CalcError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'CalcError'
  }
}

/** 安全求值：不抛异常的薄封装，UI 层用这个 */
export interface EvalOutcome {
  ok: boolean
  /** ok=true 时的数值结果（已去浮点噪声） */
  value?: number
  /** ok=false 时的可展示错误信息 */
  error?: string
}

type TokenType = 'num' | 'ident' | 'op' | 'lparen' | 'rparen'

interface Token {
  type: TokenType
  /** num: 数值；ident 与 op: 原文（乘除与减号已统一成 ASCII） */
  value: string
  pos: number
}

const FUNCTIONS = new Set([
  'sin', 'cos', 'tan', 'asin', 'acos', 'atan',
  'sqrt', 'cbrt', 'log', 'ln', 'abs', 'exp',
])

const CONSTANTS: Record<string, number> = {
  pi: Math.PI,
  e: Math.E,
}

/** 展示层常量：π 与 √ 允许直接出现在表达式里 */
function normalizeInput(raw: string): string {
  return raw
    .replace(/π/g, 'pi')
    .replace(/√/g, 'sqrt')
    .replace(/×/g, '*')
    .replace(/÷/g, '/')
    .replace(/−/g, '-')
}

function tokenize(raw: string): Token[] {
  const src = normalizeInput(raw)
  const tokens: Token[] = []
  let i = 0
  while (i < src.length) {
    const ch = src[i]
    if (ch === ' ' || ch === '\t' || ch === '\n') {
      i += 1
      continue
    }
    if (/[0-9.]/.test(ch)) {
      let j = i
      while (j < src.length && /[0-9.]/.test(src[j])) j += 1
      const text = src.slice(i, j)
      if ((text.match(/\./g) || []).length > 1) {
        throw new CalcError(`「${text}」不是合法数字`)
      }
      tokens.push({ type: 'num', value: text, pos: i })
      i = j
      continue
    }
    if (/[a-zA-Z]/.test(ch)) {
      let j = i
      while (j < src.length && /[a-zA-Z]/.test(src[j])) j += 1
      tokens.push({ type: 'ident', value: src.slice(i, j).toLowerCase(), pos: i })
      i = j
      continue
    }
    if ('+-*/^!'.includes(ch)) {
      tokens.push({ type: 'op', value: ch, pos: i })
      i += 1
      continue
    }
    if (ch === '(') {
      tokens.push({ type: 'lparen', value: ch, pos: i })
      i += 1
      continue
    }
    if (ch === ')') {
      tokens.push({ type: 'rparen', value: ch, pos: i })
      i += 1
      continue
    }
    throw new CalcError(`无法识别的符号「${ch}」`)
  }
  return tokens
}

/** 去浮点噪声：0.1+0.2 → 0.3，而不是 0.30000000000000004 */
function cleanFloat(value: number): number {
  if (!Number.isFinite(value)) return value
  return Number(value.toPrecision(12))
}

function factorial(n: number): number {
  if (n < 0 || !Number.isInteger(n)) throw new CalcError('阶乘只对非负整数有定义')
  if (n > 170) throw new CalcError('阶乘结果超出可表示范围')
  let acc = 1
  for (let k = 2; k <= n; k += 1) acc *= k
  return acc
}

class Parser {
  private pos = 0

  constructor(
    private readonly tokens: Token[],
    private readonly angleMode: AngleMode,
    private readonly ans: number | undefined,
  ) {}

  /** 入口；返回前确保全部 token 被消费（多余的 `)` 在这里被抓住） */
  parseExpression(): number {
    if (this.tokens.length === 0) throw new CalcError('表达式为空')
    const value = this.expr()
    const rest = this.tokens[this.pos]
    if (rest) {
      throw new CalcError(`「${rest.value}」出现在不该出现的位置`)
    }
    return value
  }

  private peek(): Token | undefined {
    return this.tokens[this.pos]
  }

  private next(): Token {
    const token = this.peek()
    if (!token) throw new CalcError('表达式不完整')
    this.pos += 1
    return token
  }

  private expr(): number {
    let value = this.term()
    for (;;) {
      const token = this.peek()
      if (token?.type === 'op' && (token.value === '+' || token.value === '-')) {
        this.pos += 1
        const rhs = this.term()
        value = token.value === '+' ? value + rhs : value - rhs
      } else {
        return value
      }
    }
  }

  private term(): number {
    let value = this.unary()
    for (;;) {
      const token = this.peek()
      if (token?.type === 'op' && (token.value === '*' || token.value === '/')) {
        this.pos += 1
        const rhs = this.unary()
        if (token.value === '/') {
          if (rhs === 0) throw new CalcError('除数不能为 0')
          value /= rhs
        } else {
          value *= rhs
        }
        continue
      }
      // 隐式乘法：2π、3(4+5)、2sin(30)、(1+2)(3+4)
      if (token && (token.type === 'num' || token.type === 'ident' || token.type === 'lparen')) {
        const rhs = this.unary()
        value *= rhs
        continue
      }
      return value
    }
  }

  private unary(): number {
    const token = this.peek()
    if (token?.type === 'op' && (token.value === '-' || token.value === '+')) {
      this.pos += 1
      const value = this.unary()
      return token.value === '-' ? -value : value
    }
    return this.power()
  }

  private power(): number {
    const base = this.postfix()
    const token = this.peek()
    if (token?.type === 'op' && token.value === '^') {
      this.pos += 1
      // 右结合，且指数允许带符号：2^-3、2^3^2 = 2^(3^2)
      const exponent = this.unary()
      const result = base ** exponent
      if (Number.isNaN(result)) throw new CalcError('该幂运算没有实数结果')
      return result
    }
    return base
  }

  private postfix(): number {
    let value = this.primary()
    for (;;) {
      const token = this.peek()
      if (token?.type === 'op' && token.value === '!') {
        this.pos += 1
        value = factorial(value)
        continue
      }
      return value
    }
  }

  private primary(): number {
    const token = this.next()
    if (token.type === 'num') {
      const value = Number(token.value)
      if (Number.isNaN(value)) throw new CalcError(`「${token.value}」不是合法数字`)
      return value
    }
    if (token.type === 'lparen') {
      const value = this.expr()
      const closing = this.peek()
      if (!closing || closing.type !== 'rparen') throw new CalcError('括号不匹配')
      this.pos += 1
      return value
    }
    if (token.type === 'ident') {
      const name = token.value
      if (name === 'ans') {
        if (this.ans === undefined) throw new CalcError('还没有上一次计算结果（ans）')
        return this.ans
      }
      if (name in CONSTANTS) return CONSTANTS[name]
      if (FUNCTIONS.has(name)) {
        const opening = this.next()
        if (opening.type !== 'lparen') throw new CalcError(`${name} 后面要有括号`)
        const arg = this.expr()
        const closing = this.peek()
        if (!closing || closing.type !== 'rparen') throw new CalcError('括号不匹配')
        this.pos += 1
        return this.applyFunction(name, arg)
      }
      throw new CalcError(`不认识「${token.value}」`)
    }
    throw new CalcError(`「${token.value}」出现在不该出现的位置`)
  }

  private applyFunction(name: string, arg: number): number {
    const toRad = (x: number) => (this.angleMode === 'deg' ? (x * Math.PI) / 180 : x)
    const fromRad = (x: number) => (this.angleMode === 'deg' ? (x * 180) / Math.PI : x)
    switch (name) {
      case 'sin': return cleanFloat(Math.sin(toRad(arg)))
      case 'cos': return cleanFloat(Math.cos(toRad(arg)))
      case 'tan': return cleanFloat(Math.tan(toRad(arg)))
      case 'asin': {
        if (arg < -1 || arg > 1) throw new CalcError('asin 的定义域是 [-1, 1]')
        return cleanFloat(fromRad(Math.asin(arg)))
      }
      case 'acos': {
        if (arg < -1 || arg > 1) throw new CalcError('acos 的定义域是 [-1, 1]')
        return cleanFloat(fromRad(Math.acos(arg)))
      }
      case 'atan': return cleanFloat(fromRad(Math.atan(arg)))
      case 'sqrt': {
        if (arg < 0) throw new CalcError('负数没有实数平方根')
        return Math.sqrt(arg)
      }
      case 'cbrt': return Math.cbrt(arg)
      case 'log': {
        if (arg <= 0) throw new CalcError('log 的定义域是正数')
        return cleanFloat(Math.log10(arg))
      }
      case 'ln': {
        if (arg <= 0) throw new CalcError('ln 的定义域是正数')
        return cleanFloat(Math.log(arg))
      }
      case 'abs': return Math.abs(arg)
      case 'exp': return Math.exp(arg)
      default:
        throw new CalcError(`不认识「${name}」`)
    }
  }
}

/**
 * 求值一条表达式。失败抛 CalcError（message 可直接展示）。
 * @param raw    表达式原文（允许 π √ × ÷ − 与中英文混杂输入）
 * @param opts   angleMode 缺省 'deg'；ans 为上一条结果（用 ans 参与运算时必传）
 */
export function evaluateExpression(
  raw: string,
  opts: { angleMode?: AngleMode; ans?: number } = {},
): number {
  const trimmed = raw.trim()
  if (!trimmed) throw new CalcError('表达式为空')
  const tokens = tokenize(trimmed)
  const parser = new Parser(tokens, opts.angleMode ?? 'deg', opts.ans)
  const value = parser.parseExpression()
  if (Number.isNaN(value)) throw new CalcError('结果不是有效数值')
  if (!Number.isFinite(value)) throw new CalcError('结果超出可表示范围')
  return cleanFloat(value)
}

/** 不抛异常版本：给 UI 与「未按 = 的归拢」用 */
export function safeEvaluate(
  raw: string,
  opts: { angleMode?: AngleMode; ans?: number } = {},
): EvalOutcome {
  try {
    return { ok: true, value: evaluateExpression(raw, opts) }
  } catch (err) {
    if (err instanceof CalcError) return { ok: false, error: err.message }
    return { ok: false, error: '无法计算该表达式' }
  }
}
