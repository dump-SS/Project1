// @vitest-environment jsdom
/**
 * ErrorReportButton 提交口径验收：postErrorReport 收到正确 messageId / intent / context；
 * 空描述不提交；失败可见。组件已就绪（G 板块），本单只验挂载后的行为，不改组件。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ErrorReportButton from '@/components/ErrorReportButton';

vi.mock('@/services/feedback', () => ({ postErrorReport: vi.fn() }));

import { postErrorReport } from '@/services/feedback';

// vitest 未开 globals，testing-library 的自动 cleanup 不生效，必须显式清
afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ErrorReportButton 提交口径', () => {
  it('提交带 messageId / context，intent 缺省时不硬编', async () => {
    vi.mocked(postErrorReport).mockResolvedValue({} as never);
    render(<ErrorReportButton messageId="msg_ai_1" context={{ role: 'assistant' }} />);
    fireEvent.click(screen.getByRole('button', { name: '报错' }));
    fireEvent.change(screen.getByPlaceholderText(/哪里不对/), { target: { value: '答非所问' } });
    fireEvent.click(screen.getByRole('button', { name: '提交' }));
    await waitFor(() => expect(postErrorReport).toHaveBeenCalledTimes(1));
    expect(postErrorReport).toHaveBeenCalledWith({
      messageId: 'msg_ai_1',
      intent: undefined,
      description: '答非所问',
      context: { role: 'assistant' },
    });
  });

  it('空描述不提交（提交按钮禁用）', () => {
    render(<ErrorReportButton messageId="m1" context={{ role: 'assistant' }} />);
    fireEvent.click(screen.getByRole('button', { name: '报错' }));
    expect((screen.getByRole('button', { name: '提交' }) as HTMLButtonElement).disabled).toBe(true);
    expect(postErrorReport).not.toHaveBeenCalled();
  });

  it('提交失败可见错误文案', async () => {
    // 带 status 的错误走业务失败分支（无 status 会被 isNetworkError 判成网络不可用）
    vi.mocked(postErrorReport).mockRejectedValue(Object.assign(new Error('服务端错误'), { status: 500 }));
    render(<ErrorReportButton messageId="m1" context={{ role: 'assistant' }} />);
    fireEvent.click(screen.getByRole('button', { name: '报错' }));
    fireEvent.change(screen.getByPlaceholderText(/哪里不对/), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: '提交' }));
    expect(await screen.findByText('服务端错误')).toBeTruthy();
  });
});
