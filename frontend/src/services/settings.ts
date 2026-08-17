/**
 * 用户设置 —— 读取与更新。
 *
 * 接口映射（docs/openapi.yaml）：
 * - GET   /me/settings   读取设置（Settings）
 * - PATCH /me/settings   更新设置（SettingsUpdate，至少传一项）
 *
 * 字段全部 camelCase，对应 Settings / SettingsUpdate schema。
 * 两个开关的合规含义见 pages/Settings 的文案：sendTextToAI 关闭后自由文本不出域（PRD 6.2）。
 */

import { apiGet, apiPatch } from './http';
import type { Settings, SettingsUpdate } from '@/types/api';

export function getSettings(signal?: AbortSignal): Promise<Settings> {
  return apiGet<Settings>('/me/settings', undefined, signal);
}

export function updateSettings(patch: SettingsUpdate, signal?: AbortSignal): Promise<Settings> {
  return apiPatch<Settings>('/me/settings', patch, signal);
}
