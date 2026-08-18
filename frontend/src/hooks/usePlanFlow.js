/**
 * 学习计划生成流程 Hook —— 把 StudyGuide / StudyPlanEditor 共享的
 * 7 个 state + 3 个 handler 抽出来，调用方只关心 UI 渲染。
 *
 * 流程语义：
 * - mount: 拉取当日计划（如有）回填 minutes / taskValue，置 hasExistingPlan
 * - generate(): 调 createPlan，成功后回填 plan + 抽首条任务给推荐
 * - handleEnter(): 未生成 → 生成；已生成 → 放行跳转
 * - handleTaskUpdated(): PATCH 任务成功后局部更新 plan.tasks
 */

import { useCallback, useEffect, useState } from 'react';
import { createPlan, getPlanByDate, localDateString } from '@/services/plans';
import { isNetworkError } from '@/services/http';
import { subjectLabels } from '@/styles/theme';

/** openapi PlanCreate.availableMinutes 校验：整数 10-600 */
const MINUTES_VALIDATOR = (value) => {
  if (value === '') return false;
  const n = Number(value);
  return Number.isInteger(n) && n >= 10 && n <= 600;
};

export function usePlanFlow() {
  const [taskValue, setTaskValue] = useState('');
  const [minutes, setMinutes] = useState('');
  const [plan, setPlan] = useState(null);
  const [hasGenerated, setHasGenerated] = useState(false);
  const [hasExistingPlan, setHasExistingPlan] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [offlineNote, setOfflineNote] = useState('');

  // mount: 查当日是否已有计划 → 回填 minutes / taskValue
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const existing = await getPlanByDate(localDateString());
      if (!cancelled && existing) {
        setHasExistingPlan(true);
        if (existing.availableMinutes != null) setMinutes(String(existing.availableMinutes));
        if (existing.tasks?.[0]?.topic && !taskValue) {
          setTaskValue(existing.tasks[0].topic);
        }
      }
    })();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * 生成计划（公共方法：minMinutes 不传则默认 60 并把分钟设为 60）。
   * 返回值 { rec, plan }：rec 是"学科 · 主题"字符串，给 UI 用。
   */
  const generate = useCallback(async (opts = {}) => {
    setSubmitError('');
    setOfflineNote('');
    let minutesNum;
    if (MINUTES_VALIDATOR(minutes)) {
      minutesNum = Number(minutes);
    } else {
      minutesNum = opts.minMinutes ?? 60;
      setMinutes(String(minutesNum));
    }
    const { plan: created, fromCache } = await createPlan({
      planDate: localDateString(),
      availableMinutes: minutesNum,
      regenerate: hasExistingPlan || undefined,
    });
    const first = created.tasks?.[0];
    const rec = first
      ? `${subjectLabels[first.subject] ?? first.subject} · ${first.topic}`
      : '';
    if (fromCache) setOfflineNote('离线取用上次成功计划');
    setPlan(created);
    setHasGenerated(true);
    setHasExistingPlan(true);
    return { rec, plan: created };
  }, [minutes, hasExistingPlan]);

  /**
   * 「进入」回调：
   * - 未生成：先生成（失败/缺分钟都拦截，不放行）
   * - 已生成：返回 true，放行 EnterButton 跳转
   */
  const handleEnter = useCallback(async () => {
    if (hasGenerated) return true;
    if (!MINUTES_VALIDATOR(minutes)) {
      setSubmitError('请先填写 10-600 的可用学习分钟数');
      return false;
    }
    try {
      await generate();
      return false; // 生成成功后留在页面，让用户能完成/调整任务
    } catch (err) {
      setSubmitError(
        isNetworkError(err)
          ? '服务暂不可用，请稍后再试'
          : (err?.message ?? '计划生成失败，请稍后再试'),
      );
      return false;
    }
  }, [hasGenerated, minutes, generate]);

  /** PATCH 任务成功后局部更新 plan.tasks */
  const handleTaskUpdated = useCallback((updated) => {
    setPlan((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        tasks: prev.tasks.map((t) => (t.taskId === updated.taskId ? { ...t, ...updated } : t)),
      };
    });
  }, []);

  return {
    state: {
      taskValue,
      setTaskValue,
      minutes,
      setMinutes,
      plan,
      hasGenerated,
      submitError,
      offlineNote,
    },
    validators: { MINUTES_VALIDATOR },
    handlers: { generate, handleEnter, handleTaskUpdated },
  };
}

export default usePlanFlow;
