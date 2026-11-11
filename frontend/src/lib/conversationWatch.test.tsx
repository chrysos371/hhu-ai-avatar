import { ApiError } from './api';
import { watchConversationChanges } from './conversationWatch';

const initial = { instance_id: 'one', revision: 2 };
const response = (data: unknown, status = 200) => ({ ok: status === 200, status, json: async () => ({ data,
  error: status === 200 ? null : { code: 'unauthorized', message: 'token rejected' } }) });
const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
let controller: AbortController;
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  sessionStorage.setItem('avatar-token', 'disposable-watch-test-token'); controller = new AbortController();
});
afterEach(() => { controller.abort(); vi.useRealTimers(); vi.unstubAllGlobals(); });

it('holds exactly one authenticated metadata request and advances its cursor without transcript reads', async () => {
  const scheduled = vi.spyOn(globalThis, 'setTimeout'), cleared = vi.spyOn(globalThis, 'clearTimeout');
  let release!: (value: unknown) => void;
  const fetch = vi.fn().mockResolvedValueOnce(response(initial))
    .mockResolvedValueOnce(response({ instance_id: 'one', revision: 3 }))
    .mockImplementation(() => new Promise(resolve => { release = resolve; }));
  vi.stubGlobal('fetch', fetch); const onVersion = vi.fn(), onUnavailable = vi.fn();
  const running = watchConversationChanges(initial, controller.signal, { onVersion, onUnavailable }); await settle();
  expect(fetch).toHaveBeenCalledTimes(3); expect(onVersion.mock.calls.map(row => row[0].revision)).toEqual([2, 3]);
  expect(fetch.mock.calls.map(row => row[0])).toEqual([
    '/api/v1/conversation/changes?instance_id=one&revision=2', '/api/v1/conversation/changes?instance_id=one&revision=2',
    '/api/v1/conversation/changes?instance_id=one&revision=3']);
  expect(fetch.mock.calls[0][1].headers['X-Avatar-Token']).toBe('disposable-watch-test-token');
  const signal = fetch.mock.calls[2][1].signal;
  controller.abort(); release(response(initial)); await running;
  expect(signal.aborted).toBe(true); expect(onVersion).toHaveBeenCalledTimes(2); expect(onUnavailable).not.toHaveBeenCalled();
  // JSDOM has one startup timer in the first test (retained diagnostic log).
  // Assert ownership directly: every timer created by this watch was cleared.
  expect(scheduled).toHaveBeenCalledTimes(3); expect(cleared).toHaveBeenCalledTimes(3);
  for (const timer of scheduled.mock.results) expect(cleared).toHaveBeenCalledWith(timer.value);
  scheduled.mockRestore(); cleared.mockRestore();
});

it('backs off with the frozen cap, reports one outage, and resets after a successful heartbeat', async () => {
  const fetch = vi.fn().mockRejectedValue(new Error('offline')); vi.stubGlobal('fetch', fetch);
  const onVersion = vi.fn(), onUnavailable = vi.fn();
  const running = watchConversationChanges(initial, controller.signal, { onVersion, onUnavailable }); await settle();
  for (const [index, delay] of [250, 500, 1000, 2000, 5000, 5000].entries()) {
    await vi.advanceTimersByTimeAsync(delay - 1); expect(fetch).toHaveBeenCalledTimes(index + 1);
    await vi.advanceTimersByTimeAsync(1); expect(fetch).toHaveBeenCalledTimes(index + 2);
  }
  expect(onUnavailable).toHaveBeenCalledTimes(1);
  fetch.mockResolvedValueOnce(response(initial)); await vi.advanceTimersByTimeAsync(5000);
  expect(onVersion).toHaveBeenCalledWith(initial); expect(onUnavailable).toHaveBeenCalledTimes(2);
  const count = fetch.mock.calls.length; await vi.advanceTimersByTimeAsync(250); expect(fetch).toHaveBeenCalledTimes(count + 1);
  controller.abort(); await running; expect(vi.getTimerCount()).toBe(0);
});

it('times out a stalled request at 15 seconds and aborts its retry timer on unmount', async () => {
  const fetch = vi.fn((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
  }));
  vi.stubGlobal('fetch', fetch); const onUnavailable = vi.fn();
  const running = watchConversationChanges(initial, controller.signal, { onVersion: vi.fn(), onUnavailable });
  await vi.advanceTimersByTimeAsync(14999); expect(onUnavailable).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1); expect(onUnavailable).toHaveBeenCalledTimes(1);
  controller.abort(); await running; expect(vi.getTimerCount()).toBe(0); expect(fetch).toHaveBeenCalledTimes(1);
});

it.each([401, 403])('stops retries for terminal authorization status %s', async status => {
  const fetch = vi.fn().mockResolvedValue(response(null, status)); vi.stubGlobal('fetch', fetch);
  const onUnavailable = vi.fn(); await watchConversationChanges(initial, controller.signal, { onVersion: vi.fn(), onUnavailable });
  expect(onUnavailable.mock.calls[0][0]).toBeInstanceOf(ApiError); expect(fetch).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

it.each([null, { ...initial, text: 'private transcript' }, { instance_id: '', revision: 2 },
  { instance_id: 'one', revision: -1 }, { instance_id: 'one', revision: Number.MAX_SAFE_INTEGER + 1 },
  { instance_id: 'one', revision: 1 }])('fails closed for invalid or regressing metadata %#', async data => {
  const fetch = vi.fn().mockResolvedValue(response(data)); vi.stubGlobal('fetch', fetch);
  const onUnavailable = vi.fn(), onVersion = vi.fn();
  const running = watchConversationChanges(initial, controller.signal, { onVersion, onUnavailable }); await settle();
  expect(onUnavailable).toHaveBeenCalledTimes(1); expect(onVersion).not.toHaveBeenCalled();
  controller.abort(); await running;
});

it('accepts revision zero in a different server namespace', async () => {
  const onVersion = vi.fn(() => controller.abort());
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ instance_id: 'two', revision: 0 })));
  await watchConversationChanges(initial, controller.signal, { onVersion, onUnavailable: vi.fn() });
  expect(onVersion).toHaveBeenCalledWith({ instance_id: 'two', revision: 0 });
});

it('opts into one source-cursor wait and advances ordinary context without a privacy revision change', async () => {
  const value = { ...initial, context_cursor: 0 };
  let release!: (value: unknown) => void;
  const fetch = vi.fn().mockResolvedValueOnce(response(value))
    .mockResolvedValueOnce(response({ ...value, context_cursor: 3 }))
    .mockImplementation(() => new Promise(resolve => { release = resolve; }));
  vi.stubGlobal('fetch', fetch); const onVersion = vi.fn(), onUnavailable = vi.fn();
  const running = watchConversationChanges(value, controller.signal, { onVersion, onUnavailable }); await settle();
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(fetch.mock.calls.map(row => row[0])).toEqual([
    '/api/v1/conversation/changes?instance_id=one&revision=2&context_cursor=0',
    '/api/v1/conversation/changes?instance_id=one&revision=2&context_cursor=0',
    '/api/v1/conversation/changes?instance_id=one&revision=2&context_cursor=3']);
  expect(onVersion.mock.calls.map(row => row[0])).toEqual([value, { ...value, context_cursor: 3 }]);
  controller.abort(); release(response(value)); await running;
  expect(onUnavailable).not.toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
});

it.each([{ ...initial }, { ...initial, context_cursor: -1 }, { ...initial, context_cursor: 1 },
  { ...initial, context_cursor: 4, text: 'private-text' }, { ...initial, context_cursor: Number.MAX_SAFE_INTEGER + 1 },
])('fails closed for invalid or regressing opted-in cursor %#', async data => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(data)));
  const onUnavailable = vi.fn(), onVersion = vi.fn();
  const running = watchConversationChanges({ ...initial, context_cursor: 3 }, controller.signal, { onVersion, onUnavailable }); await settle();
  expect(onUnavailable).toHaveBeenCalledTimes(1); expect(onVersion).not.toHaveBeenCalled();
  controller.abort(); await running; expect(vi.getTimerCount()).toBe(0);
});

it('accepts a fresh source cursor only when the server namespace changes', async () => {
  const value = { instance_id: 'two', revision: 0, context_cursor: 0 };
  const onVersion = vi.fn(() => controller.abort());
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(value)));
  await watchConversationChanges({ ...initial, context_cursor: 5 }, controller.signal, { onVersion, onUnavailable: vi.fn() });
  expect(onVersion).toHaveBeenCalledWith(value);
});
