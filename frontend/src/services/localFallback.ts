/**
 * localStorage 安全读写封装。
 * 用于「后端接口不可达时的降级缓存」：登录页回填上次邮箱、创建计划页缓存最近计划。
 * 所有读写都用 try/catch 包裹，失败静默返回 null，绝不让缓存的异常冒泡到业务层。
 * key 统一加 `epochx:` 前缀，避免与第三方/未来模块冲突。
 */

const PREFIX = 'epochx:'

export function cacheSet(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value))
  } catch (_) {
    /* 隐私模式/容量满等场景：静默失败，不影响页面 */
  }
}

export function cacheGet(key: string): unknown {
  try {
    const raw = window.localStorage.getItem(PREFIX + key)
    if (raw == null) return null
    return JSON.parse(raw)
  } catch (_) {
    return null
  }
}