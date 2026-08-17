/**
 * 面板数据获取 hook：统一「先占位、再请求、成功写缓存、失败先读缓存、再无缓存则保留占位并如实标注」的行为。
 *
 * 降级顺序（保证页面永不白屏）：
 *   1. 真实接口成功        → source = 'api'
 *   2. 接口失败但有本地缓存 → source = 'cache'（上次成功请求的数据）
 *   3. 接口失败且无缓存      → source = 'placeholder'（静态占位数据）
 *
 * 需求要求「不要静默 mock」，所以这里刻意不把占位数据伪装成接口数据：
 * source 字段会一路传到卡片头部，UI 上明确显示当前是实时、缓存还是占位。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { PanelState } from '@/types/view';
import { ApiError } from '@/services/http';

const CACHE_PREFIX = 'epochx:panel:';

function buildCacheKey(cacheKey: string, deps: ReadonlyArray<unknown>): string {
  const suffix = deps.map((dep) => String(dep)).join(':');
  return suffix ? `${CACHE_PREFIX}${cacheKey}:${suffix}` : `${CACHE_PREFIX}${cacheKey}`;
}

function readCache<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeCache<T>(key: string, data: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch {
    // 隐私模式或配额满时写失败属预期，不影响主流程
  }
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return `${error.message}（${error.code}）`;
  }
  if (error instanceof TypeError) {
    return '接口未接通，请检查后端服务与 VITE_API_PROXY_TARGET 配置';
  }
  return error instanceof Error ? error.message : '未知错误';
}

export function usePanelData<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  placeholder: T,
  cacheKey: string,
  deps: ReadonlyArray<unknown> = [],
): PanelState<T> & { reload: () => void } {
  const [state, setState] = useState<PanelState<T>>({
    data: placeholder,
    loading: true,
    source: 'placeholder',
    error: null,
  });

  const [reloadToken, setReloadToken] = useState(0);
  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  // placeholder 每次渲染都是新对象，用 ref 固定住，避免进入 effect 依赖导致死循环
  const placeholderRef = useRef(placeholder);
  placeholderRef.current = placeholder;

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const cacheKeyRef = useRef(cacheKey);
  cacheKeyRef.current = cacheKey;

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    const key = buildCacheKey(cacheKeyRef.current, deps);

    setState((prev) => ({ ...prev, loading: true }));

    fetcherRef
      .current(controller.signal)
      .then((data) => {
        if (cancelled) return;
        writeCache(key, data);
        setState({ data, loading: false, source: 'api', error: null });
      })
      .catch((error: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        const cached = readCache<T>(key);
        if (cached !== null) {
          setState({
            data: cached,
            loading: false,
            source: 'cache',
            error: describeError(error),
          });
        } else {
          setState({
            data: placeholderRef.current,
            loading: false,
            source: 'placeholder',
            error: describeError(error),
          });
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadToken]);

  return { ...state, reload };
}

export default usePanelData;
