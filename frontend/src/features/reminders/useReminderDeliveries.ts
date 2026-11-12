import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../../lib/api';
import { watchConversationChanges, type ConversationVersion } from '../../lib/conversationWatch';
import type { Reminder } from '../../lib/types';

export interface ReminderDelivery extends Reminder { delivery_id: number; delivery_created_at: number }
interface Snapshot extends ConversationVersion { items: ReminderDelivery[] }
const same = (a: ConversationVersion, b: ConversationVersion) => a.instance_id === b.instance_id && a.revision === b.revision;
function snapshot(value: Snapshot): Snapshot {
  if (!value || typeof value.instance_id !== 'string' || !value.instance_id || value.instance_id.length > 100
    || !Number.isSafeInteger(value.revision) || value.revision < 0 || !Array.isArray(value.items)
    || value.items.some(row => !row || !Number.isSafeInteger(row.delivery_id) || row.delivery_id <= 0
      || !Number.isSafeInteger(row.id) || row.id <= 0 || typeof row.title !== 'string'
      || !Number.isFinite(row.due_at) || !Number.isFinite(row.delivery_created_at) || row.status !== 'active')
    || new Set(value.items.map(row => row.delivery_id)).size !== value.items.length)
    throw new Error('提醒同步响应无效，请稍后重试。');
  return value;
}

// One metadata watch plus one bounded poll/ACK. No acknowledgement is inferred
// from mounting, rendering, navigation or request completion.
export function useReminderDeliveries(onAcknowledged: () => void) {
  const [items, setItems] = useState<ReminderDelivery[]>([]);
  const [error, setError] = useState<Error | null>(null);
  const [ackId, setAckId] = useState<number | null>(null);
  const action = useRef<((id: number) => Promise<void>) | null>(null);
  const onAck = useRef(onAcknowledged);
  useEffect(() => { onAck.current = onAcknowledged; }, [onAcknowledged]);
  useEffect(() => {
    const lifetime = new AbortController();
    let known: ConversationVersion | null = null, epoch = 0;
    let pollRequest: AbortController | null = null, ackRequest: AbortController | null = null;
    let currentItems: ReminderDelivery[] = [];
    const clear = () => {
      epoch += 1; pollRequest?.abort(); ackRequest?.abort();
      pollRequest = ackRequest = null; currentItems = [];
      if (!lifetime.signal.aborted) { setItems([]); setAckId(null); }
    };
    const poll = async () => {
      if (!known || lifetime.signal.aborted || pollRequest || ackRequest) return;
      const expected = known, ticket = epoch, controller = new AbortController();
      pollRequest = controller;
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const value = snapshot(await apiRequest<Snapshot>('/reminders/deliveries/pending',
          { method: 'POST', body: {}, signal: controller.signal }));
        if (lifetime.signal.aborted || ticket !== epoch) return;
        if (!same(value, expected)) {
          clear(); known = null; setError(new Error('提醒版本已变化，正在重新同步。')); return;
        }
        currentItems = value.items; setItems(value.items); setError(null);
      } catch {
        if (!lifetime.signal.aborted && ticket === epoch) {
          clear(); setError(new Error('提醒同步暂不可用，恢复后会自动重试。'));
        }
      } finally {
        clearTimeout(timeout);
        if (pollRequest === controller) pollRequest = null;
      }
    };
    action.current = async id => {
      if (!known || lifetime.signal.aborted || ackRequest || !currentItems.some(row => row.delivery_id === id)) return;
      // Discard a poll that could otherwise reinstall its pre-ACK snapshot.
      epoch += 1; pollRequest?.abort(); pollRequest = null;
      const ticket = epoch, expected = known, controller = new AbortController();
      ackRequest = controller; setAckId(id); setError(null);
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        await apiRequest('/reminders/deliveries/' + id + '/ack',
          { method: 'POST', body: { instance_id: expected.instance_id, revision: expected.revision }, signal: controller.signal });
        if (lifetime.signal.aborted || ticket !== epoch) return;
        currentItems = currentItems.filter(row => row.delivery_id !== id); setItems(currentItems); onAck.current();
      } catch {
        if (!lifetime.signal.aborted && ticket === epoch)
          setError(new Error('确认结果尚未核实，请重试或等待同步。'));
      } finally {
        clearTimeout(timeout);
        if (ackRequest === controller) {
          ackRequest = null;
          if (!lifetime.signal.aborted) { setAckId(null); void poll(); }
        }
      }
    };
    // The server immediately supplies the actual namespace before any titles
    // are fetched; later heartbeats invalidate old in-flight responses.
    void watchConversationChanges({ instance_id: 'pending-reminders-bootstrap', revision: 0 }, lifetime.signal, {
      onVersion(value) {
        if (lifetime.signal.aborted) return;
        if (!known || !same(known, value)) { clear(); known = value; void poll(); }
      },
      onUnavailable() {
        if (lifetime.signal.aborted) return;
        clear(); known = null; setError(new Error('提醒版本同步暂不可用，恢复后会自动重试。'));
      },
    });
    const timer = setInterval(() => { void poll(); }, 10000);
    return () => { lifetime.abort(); clear(); clearInterval(timer); action.current = null; };
  }, []);
  return { items, error, ackId, acknowledge: (id: number) => { void action.current?.(id); } };
}
