import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useCallback } from 'react';
import { useChatHistory } from './useChatHistory';

let current: ReturnType<typeof useChatHistory>;
let invalidated: ReturnType<typeof vi.fn>;
function Harness() {
  const busy = useCallback(() => false, []);
  current = useChatHistory({ isBusy: busy, onInvalidate: invalidated });
  return <><button onClick={() => void current.refresh()}>刷新</button><output>{current.error?.message}</output>
    {current.rows.map(row => <p key={row.id}>{row.text}</p>)}</>;
}
const snap = (text: string, revision = 0) => ({ instance_id: 'one', revision, has_more: false, next_before_id: null,
  items: [{ id: 1, role: 'user', text, session_id: 'one', created_at: 1, redacted: false }] });
const response = (data: unknown, status = 200) => ({ ok: status === 200, status, json: async () => ({ data,
  error: status === 200 ? null : { code: 'unauthorized', message: 'token rejected' } }) });
let held: { resolve: (value: unknown) => void; reject: (error: Error) => void; signal: AbortSignal }[];
let snapshotText: string;
beforeEach(() => {
  invalidated = vi.fn(); held = []; snapshotText = 'private-old'; sessionStorage.setItem('avatar-token', 'disposable-watch-test-token');
  vi.stubGlobal('fetch', vi.fn((url: string, options: RequestInit) => url.includes('/changes?')
    ? new Promise((resolve, reject) => held.push({ resolve, reject, signal: options.signal! }))
    : Promise.resolve(response(snap(snapshotText)))));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const ready = async () => { await waitFor(() => expect(current.ready).toBe(true)); await waitFor(() => expect(held).toHaveLength(1)); };

it('clears on an external version and rejects callbacks from the previous submission epoch', async () => {
  render(<Harness />); await ready(); const epoch = current.epoch.current; snapshotText = 'redacted-current';
  await act(async () => held[0].resolve(response({ instance_id: 'one', revision: 1 })));
  // A stale snapshot at revision zero cannot re-enter after version one was observed.
  expect(screen.queryByText('private-old')).not.toBeInTheDocument(); expect(current.isCurrent(epoch)).toBe(false);
  expect(current.rows).toHaveLength(0); expect(invalidated).toHaveBeenCalledTimes(1);
});

it('keeps stale content paused on focus and manual refresh until metadata reconnects', async () => {
  render(<Harness />); await ready(); const epoch = current.epoch.current;
  await act(async () => held[0].reject(new Error('offline')));
  expect(screen.queryByText('private-old')).not.toBeInTheDocument(); expect(current.ready).toBe(false);
  act(() => window.dispatchEvent(new Event('focus'))); fireEvent.click(screen.getByText('刷新'));
  await act(async () => {});
  expect(screen.queryByText('private-old')).not.toBeInTheDocument(); expect(current.ready).toBe(false);
  expect(current.isCurrent(epoch)).toBe(false);
  await waitFor(() => expect(held).toHaveLength(2)); snapshotText = 'verified-again';
  await act(async () => held[1].resolve(response({ instance_id: 'one', revision: 0 })));
  await screen.findByText('verified-again'); expect(current.ready).toBe(true); expect(invalidated).toHaveBeenCalledTimes(1);
});

it('reports terminal authorization honestly', async () => {
  const view = render(<Harness />); await ready();
  await act(async () => held[0].resolve(response(null, 403)));
  expect(screen.getByText(/token rejected/)).not.toHaveTextContent('正在重新连接');
  expect(current.ready).toBe(false); view.unmount();
});

it('aborts a pending watch on unmount and ignores a late response even if fetch ignores abort', async () => {
  const view = render(<Harness />); await ready(); const epoch = current.epoch.current; view.unmount();
  expect(held[0].signal.aborted).toBe(true);
  await act(async () => held[0].resolve(response({ instance_id: 'one', revision: 1 })));
  expect(invalidated).not.toHaveBeenCalled(); expect(current.isCurrent(epoch)).toBe(false);
});
