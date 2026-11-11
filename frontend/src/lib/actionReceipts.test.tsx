import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readActionReceipts } from './actionReceipts';
const request = vi.hoisted(() => vi.fn());
vi.mock('./api', () => ({ apiRequest: request }));
const version = { instance_id: 'server', revision: 1 };
const item = { id: 2, source_message_id: 3, session_id: 'session', context_revision: 1,
  action: 'reminder.created', reminder_id: 4, recorded_at: 1700000000 };
const page = { ...version, items: [item], has_more: false, next_after_id: null,
  scope: 'current_visible_local_sql_receipts', notification_delivery_verified: false };
describe('action evidence transport', () => {
  beforeEach(() => request.mockReset());
  it('accepts only current server/revision with real local action schema', async () => {
    request.mockResolvedValue(page); const signal = new AbortController().signal;
    expect(await readActionReceipts(version, 0, signal)).toEqual(page);
    expect(request).toHaveBeenCalledWith('/conversation/actions?revision=1&after_id=0&limit=100', { signal });
  });
  it.each([
    { ...page, instance_id: 'other' }, { ...page, revision: 2 }, { ...page, notification_delivery_verified: true },
    { ...page, scope: 'model_claim' }, { ...page, items: [{ ...item, action: 'sms.sent' }] },
    { ...page, items: [{ ...item, action: '__proto__' }] }, { ...page, items: [{ ...item, id: 0 }] },
    { ...page, items: [{ ...item, source_message_id: Number.MAX_SAFE_INTEGER + 1 }] },
    { ...page, items: [{ ...item, context_revision: 0 }] }, { ...page, items: [{ ...item, recorded_at: NaN }] },
    { ...page, items: [item, item] }, { ...page, has_more: true, next_after_id: 99 },
    { ...page, has_more: true, items: [], next_after_id: 2 },
  ])('rejects malformed or stale evidence %#', async invalid => {
    request.mockResolvedValue(invalid);
    await expect(readActionReceipts(version, 0, new AbortController().signal)).rejects.toThrow();
  });
});
