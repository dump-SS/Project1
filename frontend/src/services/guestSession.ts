/**
 * 游客态（D1 / D43）—— **纯前端本地状态**。
 *
 * 契约口径（`docs/openapi.yaml` v1.6.0 起，A 板块只叠加不重写）：
 * 生产环境无有效会话一律 401，**游客的「试用」不走任何后端接口**——不落库、不串号；
 * 登录/注册成功后试用数据直接清空。所以这里分两层：
 *
 * 1. **游客标记**（sessionStorage：`epochx:guest-mode`）：只存一个布尔，用来跨刷新
 *    记住「我要以游客身份试用」。关闭标签页即消失，不含任何个人信息；
 *    登录/注册成功时由 AuthContext 负责清掉。
 * 2. **试用数据**（模块内存）：计划等数据只活在内存里，**刷新即清空**——
 *    "不保存任何用户数据"是产品对游客的明示口径，页面文案与这里保持一致。
 */

import type { Plan, PlanTask } from '@/types/api';

const GUEST_FLAG_KEY = 'epochx:guest-mode';

/* ---------- 标记 ---------- */

export function isGuestMode(): boolean {
  try {
    return window.sessionStorage.getItem(GUEST_FLAG_KEY) === '1';
  } catch {
    return false;
  }
}

export function enterGuestMode(): void {
  try {
    window.sessionStorage.setItem(GUEST_FLAG_KEY, '1');
  } catch {
    /* 隐私模式等场景：静默失败，游客态退化为「仅本次页面有效」 */
  }
}

export function exitGuestMode(): void {
  try {
    window.sessionStorage.removeItem(GUEST_FLAG_KEY);
  } catch {
    /* 同上，静默 */
  }
}

/* ---------- 试用数据（内存，刷新即失） ---------- */

/** 内存计划池：planDate → Plan（游客不落库，同一日期只保留最近一次生成的） */
const guestPlans = new Map<string, Plan>();

export const guestPlanStore = {
  put(plan: Plan): void {
    guestPlans.set(plan.planDate, plan);
  },
  byDate(planDate: string): Plan | null {
    return guestPlans.get(planDate) ?? null;
  },
  byId(planId: string): Plan | null {
    for (const plan of guestPlans.values()) {
      if (plan.planId === planId) return plan;
    }
    return null;
  },
  patchTask(planId: string, taskId: string, patch: Partial<PlanTask>): PlanTask | null {
    const plan = guestPlanStore.byId(planId);
    if (!plan) return null;
    let updated: PlanTask | null = null;
    plan.tasks = plan.tasks.map((t) => {
      if (t.taskId !== taskId) return t;
      updated = { ...t, ...patch };
      return updated;
    });
    return updated;
  },
  clear(): void {
    guestPlans.clear();
  },
};

/** 生成游客态计划：不调规则引擎，按用户填写的科目/任务/时长就地成型。 */
export function buildGuestPlan(input: {
  planDate: string;
  availableMinutes: number;
  subject?: string;
  topic?: string;
}): Plan {
  const subject = (input.subject || 'other') as PlanTask['subject'];
  const topic = input.topic?.trim() || '未命名学习任务';
  const now = new Date().toISOString();

  return {
    planId: `guest_plan_${Date.now().toString(36)}`,
    planDate: input.planDate,
    availableMinutes: input.availableMinutes,
    adaptedFrom: null,
    tasks: [
      {
        taskId: `guest_task_${Date.now().toString(36)}`,
        subject,
        topic,
        estimatedMinutes: input.availableMinutes,
        priority: 1,
        status: 'pending',
        goalId: null,
      },
    ],
    weaknessHints: [],
    createdAt: now,
  };
}

/**
 * 清空游客试用数据 + 退出游客态。
 * 调用点：登录/注册成功（AuthContext）、游客主动去登录、退出登录。
 */
export function clearGuestSession(): void {
  guestPlans.clear();
  exitGuestMode();
}
