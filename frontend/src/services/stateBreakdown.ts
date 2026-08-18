/**
 * 模块⑧ 调权后算法计算结果 —— 数据获取。
 *
 * 对应 /me/state-breakdown：按用户当前权重（UserWeightConfig）计算最近 7 条
 * 学习记录的窗口分 + 各子分贡献 + 占比 + 状态标签/趋势。
 *
 * 与 /assessments/current 的区别：后者给"标签 + displayText"，
 * 本接口给"调权改了 α/β 后，状态分究竟由行为/自评各贡献了多少"。
 */

import { apiGet } from './http';

export interface StateBreakdownWeights {
  alpha: number;
  beta: number;
  w1: number;
  w2: number;
  w3: number;
  w4: number;
  w5: number;
  w6: number;
}

export interface StateBreakdown {
  subject: string;
  windowScore: number | null;
  behaviorSubAvg: number;
  selfReportSubAvg: number;
  behaviorContribution: number;
  selfReportContribution: number;
  behaviorShare: number;
  selfReportShare: number;
  recordCount: number;
  stateLabel: string | null;
  trend: string | null;
  signals: string[];
  weights: StateBreakdownWeights;
  windowSize: number;
}

export async function fetchStateBreakdown(subject?: string): Promise<StateBreakdown> {
  return apiGet<StateBreakdown>('/me/state-breakdown', subject ? { subject } : undefined);
}
