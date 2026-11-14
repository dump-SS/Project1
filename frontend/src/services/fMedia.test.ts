/**
 * 删除权接线单测（node 环境，只 mock ./http，不引 jsdom —— 项目惯例）。
 *
 * 钉死派单四条：clearAll 触发 deleteMedia(key)；DELETE 失败 UI 仍清除且可见；
 * 重复清除不报错（幂等，404 不算错）；未上传过点清除不调 DELETE。
 * 另钉死 key 编码口径：原样拼接（后端 /{key:path}），不做 encodeURIComponent。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./http', () => ({
  apiDelete: vi.fn(),
  apiGetBlob: vi.fn(),
  apiPost: vi.fn(),
  apiPostBinary: vi.fn(),
}));

import { apiDelete } from './http';
import { clearUploadedMedia, deleteMedia } from './fMedia';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('deleteMedia', () => {
  it('走 apiDelete，key 原样拼接（含斜杠不编码，与 fetchMedia 口径一致）', async () => {
    vi.mocked(apiDelete).mockResolvedValue(undefined as never);
    await deleteMedia('user/u1/a.png');
    expect(apiDelete).toHaveBeenCalledWith('/f/media/user/u1/a.png', undefined);
    const path = vi.mocked(apiDelete).mock.calls[0][0] as string;
    expect(path).not.toContain('%2F');
  });
});

describe('clearUploadedMedia（clearAll 的删除接线）', () => {
  it('有 key：撤引用块 + 调 deleteMedia(key)', () => {
    const del = vi.fn().mockResolvedValue(undefined);
    const onClear = vi.fn();
    const onFail = vi.fn();
    clearUploadedMedia('user/u1/a.png', { deleteMedia: del, onClear, onFail });
    expect(onClear).toHaveBeenCalledWith('user/u1/a.png');
    expect(del).toHaveBeenCalledWith('user/u1/a.png');
    expect(onFail).not.toHaveBeenCalled();
  });

  it('DELETE 失败：onClear 仍已调用（UI 清除不被阻塞），且 onFail 可见', async () => {
    const del = vi.fn().mockRejectedValue(Object.assign(new Error('502'), { status: 502 }));
    const onClear = vi.fn();
    const onFail = vi.fn();
    clearUploadedMedia('user/u1/a.png', { deleteMedia: del, onClear, onFail });
    expect(onClear).toHaveBeenCalledWith('user/u1/a.png');
    await vi.waitFor(() => expect(onFail).toHaveBeenCalled());
    expect(onFail.mock.calls[0][0]).toContain('图片删除失败');
  });

  it('404 视为幂等成功：不报失败（契约重复调用 204、对象已不在等同删掉）', async () => {
    const del = vi.fn().mockRejectedValue(Object.assign(new Error('404'), { status: 404 }));
    const onFail = vi.fn();
    clearUploadedMedia('user/u1/a.png', { deleteMedia: del, onClear: vi.fn(), onFail });
    await Promise.resolve();
    await Promise.resolve();
    expect(onFail).not.toHaveBeenCalled();
  });

  it('重复清除不报错：第二次 clearAll 时 result 已空 → 无 key → 不调 DELETE', () => {
    const del = vi.fn().mockResolvedValue(undefined);
    const onClear = vi.fn();
    const onFail = vi.fn();
    clearUploadedMedia('user/u1/a.png', { deleteMedia: del, onClear, onFail });
    clearUploadedMedia(undefined, { deleteMedia: del, onClear, onFail });
    expect(del).toHaveBeenCalledTimes(1);
    expect(onFail).not.toHaveBeenCalled();
  });

  it('未上传过（无 key）：不调 DELETE，也不撤引用', () => {
    const del = vi.fn();
    const onClear = vi.fn();
    clearUploadedMedia(undefined, { deleteMedia: del, onClear, onFail: vi.fn() });
    expect(del).not.toHaveBeenCalled();
    expect(onClear).not.toHaveBeenCalled();
  });
});
