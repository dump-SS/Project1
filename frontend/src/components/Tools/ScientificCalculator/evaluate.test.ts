/**
 * D57 求值器测试。覆盖验收门相关的两类关键行为：
 * 1. 常规科学计算正确性（优先级 / 右结合 / 隐式乘法 / DEG-RAD / 常量 / ans）
 * 2. 错误处理（除零 / 括号不匹配 / 定义域越界 / 空表达式）——
 *    「未按 = 的表达式归拢」依赖 safeEvaluate 不抛异常
 */
import { describe, expect, it } from 'vitest'
import { CalcError, evaluateExpression, safeEvaluate } from './evaluate'

const ev = (raw: string, opts?: Parameters<typeof evaluateExpression>[1]) =>
  evaluateExpression(raw, opts)

describe('四则与优先级', () => {
  it('先乘除后加减', () => {
    expect(ev('2+3*4')).toBe(14)
    expect(ev('20/4-2')).toBe(3)
  })

  it('括号覆盖优先级', () => {
    expect(ev('(2+3)*4')).toBe(20)
  })

  it('除零报错且信息可展示', () => {
    expect(() => ev('1/0')).toThrow(CalcError)
    expect(() => ev('1/0')).toThrow('除数不能为 0')
  })

  it('浮点噪声清理：0.1+0.2=0.3', () => {
    expect(ev('0.1+0.2')).toBe(0.3)
  })
})

describe('幂与一元符号', () => {
  it('^ 右结合：2^3^2=512', () => {
    expect(ev('2^3^2')).toBe(512)
  })

  it('指数可带符号：2^-3=0.125', () => {
    expect(ev('2^-3')).toBe(0.125)
  })

  it('负号低于 ^：-2^2=-4', () => {
    expect(ev('-2^2')).toBe(-4)
  })

  it('幂不是完全平方时给无理数近似', () => {
    expect(ev('2^0.5')).toBeCloseTo(Math.SQRT2, 10)
  })
})

describe('隐式乘法', () => {
  it('数字紧邻括号：3(4+5)=27', () => {
    expect(ev('3(4+5)')).toBe(27)
  })

  it('括号相乘：(1+2)(3+4)=21', () => {
    expect(ev('(1+2)(3+4)')).toBe(21)
  })

  it('数字紧邻函数：2sin(30)=1（DEG）', () => {
    expect(ev('2sin(30)')).toBe(1)
  })

  it('数字紧邻常量：2π', () => {
    expect(ev('2π')).toBeCloseTo(2 * Math.PI, 10)
  })
})

describe('函数与角度模式', () => {
  it('DEG 默认：sin(30)=0.5、cos(60)=0.5、tan(45)=1', () => {
    expect(ev('sin(30)')).toBe(0.5)
    expect(ev('cos(60)')).toBe(0.5)
    expect(ev('tan(45)')).toBe(1)
  })

  it('DEG 下反三角回角度：asin(0.5)=30', () => {
    expect(ev('asin(0.5)')).toBe(30)
  })

  it('RAD 模式：sin(π/2)=1', () => {
    expect(ev('sin(pi/2)', { angleMode: 'rad' })).toBe(1)
  })

  it('log 是常用底 10，ln 是自然对数', () => {
    expect(ev('log(100)')).toBe(2)
    expect(ev('ln(e)')).toBe(1)
  })

  it('sqrt 负数报定义域错误', () => {
    expect(() => ev('sqrt(-1)')).toThrow('平方根')
  })

  it('asin 越界报定义域错误', () => {
    expect(() => ev('asin(2)')).toThrow('定义域')
  })
})

describe('常量与 ans', () => {
  it('π 与 e 可用', () => {
    expect(ev('pi*2')).toBeCloseTo(2 * Math.PI, 10)
    expect(ev('e')).toBeCloseTo(Math.E, 10)
  })

  it('ans 引用上一条结果', () => {
    const first = ev('2+3')
    expect(ev('ans*2', { ans: first })).toBe(10)
  })

  it('ans 不存在时报错而不是 NaN', () => {
    expect(() => ev('ans+1')).toThrow('ans')
  })
})

describe('阶乘', () => {
  it('5!=120、0!=1', () => {
    expect(ev('5!')).toBe(120)
    expect(ev('0!')).toBe(1)
  })

  it('非整数阶乘报错', () => {
    expect(() => ev('2.5!')).toThrow('非负整数')
  })
})

describe('错误处理（safeEvaluate 不抛异常）', () => {
  it('括号不匹配：缺右括号', () => {
    expect(() => ev('(2+3')).toThrow('括号不匹配')
  })

  it('多余右括号被抓住', () => {
    expect(() => ev('2+3)')).toThrow(CalcError)
  })

  it('空表达式报错', () => {
    expect(() => ev('   ')).toThrow('表达式为空')
  })

  it('无法识别的符号', () => {
    expect(() => ev('2@3')).toThrow('无法识别的符号')
  })

  it('未知标识符', () => {
    expect(() => ev('foo(2)')).toThrow(CalcError)
  })

  it('safeEvaluate 失败返回 ok:false 与可展示信息', () => {
    const outcome = safeEvaluate('1/0')
    expect(outcome.ok).toBe(false)
    expect(outcome.error).toBe('除数不能为 0')
  })

  it('safeEvaluate 成功返回 ok:true 与数值', () => {
    const outcome = safeEvaluate('2^10')
    expect(outcome.ok).toBe(true)
    expect(outcome.value).toBe(1024)
  })
})
