/**
 * 面板数据获取 hook：统一「先占位、再请求、失败保留占位并如实标注」的行为。
 *
 * 需求要求「不要静默 mock」，所以这里刻意不把占位数据伪装成接口数据：
 * source 字段会一路传到卡片头部，UI 上明确显示当前是占位还是真实数据。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { PanelState } from '@/types/view';
import { ApiError } from '@/services/http';

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

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    setState((prev) => ({ ...prev, loading: true }));

    fetcherRef
      .current(controller.signal)
      .then((data) => {
        if (cancelled) return;
        setState({ data, loading: false, source: 'api', error: null });
      })
      .catch((error: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        setState({
          data: placeholderRef.current,
          loading: false,
          source: 'placeholder',
          error: describeError(error),
        });
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
