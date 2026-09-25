/**
 * 考试（D49 独立实体）—— Exam CRUD 与成绩回填。
 *
 * 接口映射（docs/openapi.yaml v1.7.1）：
 * - GET    /exams              列表（按学科 / 日期范围过滤）
 * - POST   /exams              新建（考前记日程 or 考后一次录入）
 * - GET    /exams/{examId}     详情
 * - PATCH  /exams/{examId}     更新 / **回填成绩**
 * - DELETE /exams/{examId}     删除（被 Goal 引用时 409）
 *
 * 为什么考试独立成实体：目标表达意愿（"这次想考到 120"），考试表达事实（"11/05 期中，考了 118"）。
 * 混在一张表里就会出现"同一个目标既想表达意愿又想表达结果"的平行体系。
 * 所以 `exams` 存事实，`goals.examId + targetScore` 存意愿。
 *
 * **回填成绩会连带生成一条 `source=exam` 的学习记录**（D49 喂状态评估），前提是
 * `durationMinutes` 已填——记录的学习时长必填，而考试时长是客观事实，
 * 没填就不生成记录，不编时长。
 *
 * ⚠️ 类型定义随 openapi v1.7.1 新增，暂放本文件而不动 `types/api.ts`（归 X1 管）。
 */

import { apiDelete, apiGet, apiGetAllPages, apiPatch, apiPost } from './http';
import type { Subject } from '@/types/api';

export interface Exam {
  examId: string;
  subject: Subject;
  /** 考试名称，如「期中考试」 */
  name: string;
  /** YYYY-MM-DD */
  examDate: string;
  /** 得分；null = 尚未回填（0 分与未回填是两回事） */
  score?: number | null;
  fullScore: number;
  /**
   * 考试时长（分钟，可空）。
   * 存在的理由很具体：成绩回填要生成一条学习记录，而记录的学习时长必填——
   * **填了才生成记录，不填就不生成**，绝不为了凑一条记录去编一个时长。
   */
  durationMinutes?: number | null;
  createdAt: string;
  updatedAt?: string | null;
}

export interface ExamCreateInput {
  subject: Subject;
  name: string;
  examDate: string;
  fullScore: number;
  score?: number | null;
  durationMinutes?: number | null;
}

export interface ExamUpdateInput {
  name?: string;
  examDate?: string;
  fullScore?: number;
  /** 显式传 null = 撤回回填（连带删掉那条 source=exam 的记录） */
  score?: number | null;
  durationMinutes?: number | null;
}

export function listExams(
  query: { subject?: Subject; dateFrom?: string; dateTo?: string } = {},
  signal?: AbortSignal,
): Promise<Exam[]> {
  return apiGetAllPages<Exam>('/exams', query, signal);
}

export function createExam(body: ExamCreateInput): Promise<Exam> {
  return apiPost<Exam>('/exams', body);
}

export function getExam(examId: string, signal?: AbortSignal): Promise<Exam> {
  return apiGet<Exam>(`/exams/${examId}`, undefined, signal);
}

/**
 * 更新考试 / **回填成绩**。
 *
 * 被 Goal 引用时删除会 409；成绩超满分是 400（后端不静默截断——静默截断会让用户以为系统算错了）。
 */
export function updateExam(examId: string, body: ExamUpdateInput): Promise<Exam> {
  return apiPatch<Exam>(`/exams/${examId}`, body);
}

export function deleteExam(examId: string): Promise<{ deleted: boolean; examId: string }> {
  return apiDelete<{ deleted: boolean; examId: string }>(`/exams/${examId}`);
}

/** 展示辅助：得分率（0-1）。未回填或满分为 0 时返回 null。 */
export function examScoreRate(exam: Pick<Exam, 'score' | 'fullScore'>): number | null {
  if (exam.score === null || exam.score === undefined) return null;
  if (!exam.fullScore) return null;
  return exam.score / exam.fullScore;
}
