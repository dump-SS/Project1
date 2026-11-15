// @vitest-environment jsdom
/**
 * L175（只做一半）挂载验收：AI 气泡有「报错」、用户气泡没有；
 * 报错失败不阻断对话主流程（治理辅助能力不阻断业务）。
 * 不接任何违规检测/自动封禁——本文件也不 mock 任何 sanction 相关模块（根本没有）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import MessageBubble from './MessageBubble';
import type { ChatMessage } from './types';

vi.mock('@/services/feedback', () => ({ postErrorReport: vi.fn() }));

import { postErrorReport } from '@/services/feedback';

// vitest 未开 globals，testing-library 的自动 cleanup 不生效，必须显式清
afterEach(cleanup);

const aiMsg: ChatMessage = {
  id: 'msg_ai_1',
  role: 'ai',
  content: '这是一条模型回复',
  createdAt: 1763100000000,
};
const userMsg: ChatMessage = {
  id: 'msg_user_1',
  role: 'user',
  content: '这是我问的话',
  createdAt: 1763100000000,
};

describe('MessageBubble 报错按钮挂载', () => {
  it('AI 气泡渲染报错按钮', () => {
    render(<MessageBubble message={aiMsg} />);
    expect(screen.getByRole('button', { name: '报错' })).toBeTruthy();
  });

  it('用户气泡不渲染报错按钮', () => {
    render(<MessageBubble message={userMsg} />);
    expect(screen.queryByRole('button', { name: '报错' })).toBeNull();
  });

  it('报错提交失败时对话内容仍在（不阻断主流程）', async () => {
    vi.mocked(postErrorReport).mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    render(<MessageBubble message={aiMsg} />);
    fireEvent.click(screen.getByRole('button', { name: '报错' }));
    fireEvent.change(screen.getByPlaceholderText(/哪里不对/), { target: { value: '答非所问' } });
    fireEvent.click(screen.getByRole('button', { name: '提交' }));
    await waitFor(() => expect(postErrorReport).toHaveBeenCalled());
    // 失败提示可见，且气泡正文没有被卸掉
    expect(await screen.findByText('boom')).toBeTruthy();
    expect(screen.getByText('这是一条模型回复')).toBeTruthy();
  });
});
