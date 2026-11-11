/**
 * 引用块 wire 序列化单测：D22 payload 注入不拼字符串。
 * 旧 chip（无 payload）行为必须与从前逐字一致，避免改坏 D51 既有链路。
 */
import { describe, expect, it } from 'vitest';
import { refChipWireText, type RefChip } from './types';

describe('refChipWireText', () => {
  it('无 payload 的旧 chip：[label] text，与从前一致', () => {
    const chip: RefChip = { id: 'r1', label: '引用', text: '被划选的原文' };
    expect(refChipWireText(chip)).toBe('[引用] 被划选的原文');
  });

  it('有 payload：JSON 引用块（结构化），不摊成散文', () => {
    const payload = { refs: { planId: 'p1' }, instruction: '基于计划现状继续' };
    const chip: RefChip = { id: 'r2', label: '继续计划', text: '继续 11-11 计划', payload };
    const wire = refChipWireText(chip);
    expect(wire).toBe(`[继续计划] ${JSON.stringify(payload)}`);
    expect(wire).not.toContain('继续 11-11 计划');
    expect(JSON.parse(wire.slice('[继续计划] '.length))).toEqual(payload);
  });

  it('payload 为 null 时退回旧行为', () => {
    const chip: RefChip = { id: 'r3', label: '引用', text: 'x', payload: null };
    expect(refChipWireText(chip)).toBe('[引用] x');
  });
});
