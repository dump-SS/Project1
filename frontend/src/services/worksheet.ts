/**
 * D55 · 作业单照片抽取 —— 对应 openapi.yaml v1.15.0「POST /f/worksheet/extract」。
 *
 * 语义：传入已上传（POST /f/media）的作业单照片 key，后端取回字节送视觉 LLM，
 * 抽取结构化作业项。**抽取结果会话内不落库**（契约口径），用户在确认卡里
 * 确认/修改后的最终任务列表经 plans.createPlan 的 tasks 字段落库。
 *
 * 失败语义：403（别人的图）/ 404（图已删）/ 502 EXTRACT_FAILED（LLM 不可用或
 * 解析不出，可重试）——ApiError.message 已是面向用户的中文，调用方直接展示。
 */
import { apiPost } from './http';

/** 与契约 WorksheetItem 同形；subject 取值同 PlanTask（拼音码 + other 兜底） */
export interface WorksheetItemInput {
  subject: string;
  topic: string;
  estimatedMinutes: number;
}

export interface WorksheetExtraction {
  items: WorksheetItemInput[];
}

export async function extractWorksheet(
  mediaKey: string,
  signal?: AbortSignal,
): Promise<WorksheetExtraction> {
  return apiPost<WorksheetExtraction>('/f/worksheet/extract', { mediaKey }, signal);
}
