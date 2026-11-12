vi.mock('../../lib/conversationWatch', () => ({ watchConversationChanges: vi.fn(async () => {}) }));
import { act, renderHook } from '@testing-library/react';
import { watchConversationChanges } from '../../lib/conversationWatch';
import { response } from '../../test/render';
import { useReminderDeliveries } from './useReminderDeliveries';

type Callbacks = Parameters<typeof watchConversationChanges>[2];
let callbacks: Callbacks;
let watchSignal: AbortSignal;
const version = { instance_id: 'instance-one', revision: 2 };
const row = { id: 1, title: '待确认提醒', status: 'active', due_at: 123, created_at: 100, notified_at: 124,
  delivery_id: 7, delivery_created_at: 124 };
const pending = (items = [row], current = version) => ({ ...current, items });
const settle = async () => { await act(async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); }); };
const announce = async (current = version) => { act(() => callbacks.onVersion(current)); await settle(); };
function deferred() { let resolve!: (value: ReturnType<typeof response>) => void;
  const promise = new Promise<ReturnType<typeof response>>(r => { resolve = r; }); return { promise, resolve }; }
beforeEach(() => {
  sessionStorage.setItem('avatar-token', 'disposable-reminder-unit-token');
  vi.mocked(watchConversationChanges).mockImplementation(async (_initial, signal, value) => { callbacks = value; watchSignal = signal; });
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it('never infers ACK from rendering; waits for explicit committed client confirmation', async () => {
  const ack = deferred(); let acknowledged = false;
  const fetch = vi.fn((path: string, _options?: { body: string }) => { void _options; return path.endsWith('/ack') ? ack.promise : Promise.resolve(response(pending(acknowledged ? [] : [row]))); });
  vi.stubGlobal('fetch', fetch); const onAck = vi.fn();
  const { result, unmount } = renderHook(() => useReminderDeliveries(onAck)); await announce();
  expect(result.current.items).toEqual([row]); expect(fetch).toHaveBeenCalledTimes(1);
  act(() => result.current.acknowledge(7)); await settle();
  expect(result.current.ackId).toBe(7); expect(result.current.items).toEqual([row]);
  expect(JSON.parse(fetch.mock.calls[1][1]!.body)).toEqual(version);
  acknowledged = true; ack.resolve(response({ acknowledged_at: 125 })); await settle();
  expect(result.current.items).toEqual([]); expect(onAck).toHaveBeenCalledTimes(1);
  unmount(); expect(watchSignal.aborted).toBe(true);
});

it('drops an old revision response even if its transport ignores abort', async () => {
  const old = deferred(); const newer = { ...version, revision: 3 };
  const fresh = { ...row, title: '重新核验的事项' };
  const fetch = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValue(response(pending([fresh], newer)));
  vi.stubGlobal('fetch', fetch);
  const { result } = renderHook(() => useReminderDeliveries(vi.fn())); await announce();
  const signal = fetch.mock.calls[0][1].signal;
  await announce(newer); expect(signal.aborted).toBe(true);
  old.resolve(response(pending())); await settle();
  expect(result.current.items).toEqual([fresh]);
});

it('clears on metadata outage and rejects late ACK success until a new validated read', async () => {
  const ack = deferred(); const onAck = vi.fn();
  const fetch = vi.fn((path: string, _options?: { body: string }) => { void _options; return path.endsWith('/ack') ? ack.promise : Promise.resolve(response(pending())); });
  vi.stubGlobal('fetch', fetch);
  const { result } = renderHook(() => useReminderDeliveries(onAck)); await announce();
  act(() => result.current.acknowledge(7)); await settle();
  act(() => callbacks.onUnavailable(new Error('offline'))); await settle();
  expect(result.current.items).toEqual([]); expect(result.current.error).not.toBeNull();
  ack.resolve(response({ acknowledged_at: 125 })); await settle(); expect(onAck).not.toHaveBeenCalled();
  await announce(); expect(result.current.items).toEqual([row]);
});

it('retains/reloads pending after a failed ACK and permits idempotent retry of the same event', async () => {
  let attempts = 0;
  const fetch = vi.fn((path: string, _options?: { body: string }) => {
    void _options;
    if (path.endsWith('/ack')) { attempts += 1; return attempts === 1 ? Promise.reject(new Error('response lost')) : Promise.resolve(response({ acknowledged_at: 125 })); }
    return Promise.resolve(response(pending(attempts === 2 ? [] : [row])));
  });
  vi.stubGlobal('fetch', fetch); const onAck = vi.fn();
  const { result } = renderHook(() => useReminderDeliveries(onAck)); await announce();
  act(() => result.current.acknowledge(7)); await settle(); expect(result.current.items).toEqual([row]);
  act(() => result.current.acknowledge(7)); await settle(); expect(result.current.items).toEqual([]);
  const calls = fetch.mock.calls.filter(([path]) => path.endsWith('/ack'));
  expect(calls).toHaveLength(2); expect(calls.map(([, options]) => JSON.parse(options!.body))).toEqual([version,version]);
  expect(onAck).toHaveBeenCalledTimes(1);
});

it('bounds polls to one in flight and aborts its request and metadata watch on unmount', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout','clearTimeout','setInterval','clearInterval'] });
  const held = deferred(); const fetch = vi.fn().mockReturnValue(held.promise); vi.stubGlobal('fetch', fetch);
  const { unmount } = renderHook(() => useReminderDeliveries(vi.fn())); await announce();
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); }); expect(fetch).toHaveBeenCalledTimes(1);
  const signal = fetch.mock.calls[0][1].signal; unmount();
  expect(signal.aborted).toBe(true); expect(watchSignal.aborted).toBe(true);
  held.resolve(response(pending())); await settle(); expect(vi.getTimerCount()).toBe(0);
});

it('accepts revision zero only with the newly validated server namespace', async () => {
  const newer = { instance_id: 'instance-two', revision: 0 };
  const fetch = vi.fn().mockResolvedValueOnce(response(pending())).mockResolvedValueOnce(response(pending([row],newer)))
    .mockResolvedValue(response(pending([],newer)));
  vi.stubGlobal('fetch', fetch); const { result } = renderHook(() => useReminderDeliveries(vi.fn()));
  await announce(); await announce(newer); act(() => result.current.acknowledge(7)); await settle();
  const call = fetch.mock.calls.find(([path]) => path.endsWith('/ack'))!;
  expect(JSON.parse(call[1].body)).toEqual(newer);
});

it('does not show a response from an unvalidated version and retries after metadata recovery', async () => {
  const newer = { ...version, revision: 3 };
  const fetch = vi.fn().mockResolvedValue(response(pending([row],newer))); vi.stubGlobal('fetch', fetch);
  const { result } = renderHook(() => useReminderDeliveries(vi.fn())); await announce();
  expect(result.current.items).toEqual([]); expect(result.current.error).not.toBeNull();
  await announce(newer); expect(result.current.items).toEqual([row]);
});

it('rejects duplicate event identities instead of rendering ambiguous confirmations', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(pending([row,row]))));
  const { result } = renderHook(() => useReminderDeliveries(vi.fn())); await announce();
  expect(result.current.items).toEqual([]); expect(result.current.error).not.toBeNull();
});
