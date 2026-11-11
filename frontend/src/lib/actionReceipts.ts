import { apiRequest } from './api';

export const localActionLabels = {
  'reminder.created': '创建提醒',
  'reminder.cancelled': '取消提醒',
  'reminder.completed': '标记提醒完成',
  'reminder.claimed_due': '记录到期提醒（送达未核验）',
} as const;
export type LocalAction = keyof typeof localActionLabels;
export interface ActionReceipt {
  id: number; source_message_id: number; session_id: string; context_revision: number;
  action: LocalAction; reminder_id: number; recorded_at: number;
}
export interface ActionReceiptPage {
  instance_id: string; revision: number; items: ActionReceipt[];
  has_more: boolean; next_after_id: number | null;
  scope: 'current_visible_local_sql_receipts'; notification_delivery_verified: false;
}
export type ActionReceiptVersion = { instance_id: string; revision: number };
const integer = (value: unknown, minimum = 0): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= minimum;
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

export async function readActionReceipts(version: ActionReceiptVersion, afterId: number, signal: AbortSignal) {
  const value: unknown = await apiRequest('/conversation/actions?revision=' + version.revision + '&after_id=' + afterId + '&limit=100', { signal });
  if (!record(value) || value.instance_id !== version.instance_id || value.revision !== version.revision)
    throw new Error('操作记录的服务或记忆版本已变化，请刷新对话记录后重试。');
  if (value.scope !== 'current_visible_local_sql_receipts' || value.notification_delivery_verified !== false
    || !Array.isArray(value.items) || value.items.length > 100 || typeof value.has_more !== 'boolean')
    throw new Error('操作记录格式无法核验。');
  let previous = afterId;
  for (const item of value.items) {
    if (!record(item) || !integer(item.id, previous + 1) || !integer(item.source_message_id, 1)
      || !integer(item.reminder_id, 1) || item.context_revision !== version.revision
      || typeof item.session_id !== 'string' || !item.session_id || typeof item.action !== 'string'
      || !Object.hasOwn(localActionLabels, item.action) || typeof item.recorded_at !== 'number'
      || !Number.isFinite(item.recorded_at) || item.recorded_at < 0)
      throw new Error('操作记录格式无法核验。');
    previous = item.id;
  }
  if (value.has_more ? !value.items.length || value.next_after_id !== previous : value.next_after_id !== null)
    throw new Error('操作记录分页无法核验。');
  return value as unknown as ActionReceiptPage;
}
