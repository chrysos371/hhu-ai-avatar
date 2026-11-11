// Snapshot/turn ordering is isolated here; transport has dedicated and Chromium tests.
vi.mock('../../lib/conversationWatch', () => ({ watchConversationChanges: vi.fn(async () => {}) }));
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useCallback, useRef } from 'react';
import { notifyConversationPrivacyChanged, type ConversationItem, type ConversationSnapshot } from '../../lib/conversation';
import { useChatHistory } from './useChatHistory';

let current: ReturnType<typeof useChatHistory>;
let invalidated: ReturnType<typeof vi.fn>;
function Harness({ busy = false }: { busy?: boolean }) {
  const busyRef = useRef(busy); busyRef.current = busy;
  const isBusy = useCallback(() => busyRef.current, []);
  current = useChatHistory({ isBusy, onInvalidate: invalidated });
  return <><button onClick={() => void current.refresh()}>刷新</button>
    <button onClick={() => void current.refresh(true)}>更早</button>
    <output data-testid="ready">{String(current.ready && !current.loading)}</output>
    <output data-testid="error">{current.error?.message}</output>
    {current.rows.map((row, index) => <p key={row.id ?? 'local-' + index}>{row.id}:{row.text}</p>)}
  </>;
}
const item = (id: number, text = 'row-' + id): ConversationItem => ({ id, role: 'user', text, session_id: 'one', created_at: id, redacted: false });
const snapshot = (items: ConversationItem[], revision = 0, has_more = false, instance_id = 'one'): ConversationSnapshot => ({
  items, revision, has_more, instance_id, next_before_id: has_more ? items[0].id : null,
});
const response = (data: ConversationSnapshot) => ({ ok: true, json: async () => ({ data }) });
beforeEach(() => {
  sessionStorage.setItem('avatar-token', 'history-test-disposable-session-token'); invalidated = vi.fn();
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
async function ready() { await waitFor(() => expect(screen.getByTestId('ready')).toHaveTextContent('true')); }

it('merges older pages and fresh overlapping snapshots without dropping loaded history', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(response(snapshot([item(3), item(4)], 0, true)))
    .mockResolvedValueOnce(response(snapshot([item(1), item(2)])))
    .mockResolvedValueOnce(response(snapshot([item(3), item(4), item(5), item(6)], 0, true)));
  vi.stubGlobal('fetch', fetch); render(<Harness />); await ready();
  fireEvent.click(screen.getByText('更早')); await screen.findByText('1:row-1'); await ready();
  expect(fetch.mock.calls[1][0]).toContain('before_id=3'); expect(fetch.mock.calls[1][0]).toContain('revision=0');
  fireEvent.click(screen.getByText('刷新')); await screen.findByText('6:row-6'); await ready();
  expect(current.rows.map(row => row.id)).toEqual([1, 2, 3, 4, 5, 6]); expect(current.hasMore).toBe(false);
});

it('discards a held old snapshot even when the fetch mock ignores abort', async () => {
  let release!: (value: unknown) => void;
  const fetch = vi.fn().mockResolvedValueOnce(response(snapshot([item(1, 'private-old')])))
    .mockImplementationOnce(() => new Promise(resolve => { release = resolve; }))
    .mockResolvedValueOnce(response(snapshot([{ ...item(1, '此条内容已删除。'), redacted: true }], 1)));
  vi.stubGlobal('fetch', fetch); render(<Harness />); await ready(); const epoch = current.epoch.current;
  fireEvent.click(screen.getByText('刷新'));
  await act(async () => { notifyConversationPrivacyChanged(); });
  await screen.findByText('1:此条内容已删除。'); await ready();
  expect(current.isCurrent(epoch)).toBe(false);
  await act(async () => release(response(snapshot([item(1, 'private-old')]))));
  expect(screen.queryByText('1:private-old')).not.toBeInTheDocument(); expect(current.rows[0].redacted).toBe(true);
  expect(fetch.mock.calls[1][1].signal.aborted).toBe(true);
});

it('does not duplicate a persisted pending user or replace a local draft on unchanged reads', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(response(snapshot([])))
    .mockResolvedValueOnce(response(snapshot([item(1, 'pending-user')])));
  vi.stubGlobal('fetch', fetch); const view = render(<Harness />); await ready();
  act(() => current.setRows([{ role: 'user', text: 'pending-user' }, { role: 'assistant', text: 'draft', pending: true }]));
  view.rerender(<Harness busy />); fireEvent.click(screen.getByText('刷新')); await ready();
  expect(current.rows).toHaveLength(2); expect(current.rows[1].pending).toBe(true);
  expect(current.rows.filter(row => row.text === 'pending-user')).toHaveLength(1);
});

it('replaces old pages after a stale pagination revision instead of mixing versions', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(snapshot([item(3, 'old')], 0, true)))
    .mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({ data: null, error: { code: 'conversation_changed', message: 'changed' } }) })
    .mockResolvedValueOnce(response(snapshot([item(3, 'new')], 1))));
  render(<Harness />); await ready(); fireEvent.click(screen.getByText('更早'));
  await screen.findByText('3:new'); await ready(); expect(screen.queryByText('3:old')).not.toBeInTheDocument();
  expect(current.version?.revision).toBe(1); expect(invalidated).toHaveBeenCalled();
});

it('revalidates on focus and treats a new server instance as a new version space', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(snapshot([item(1, 'old-instance')], 4)))
    .mockResolvedValueOnce(response(snapshot([item(1, 'new-instance')], 0, false, 'two'))));
  render(<Harness />); await ready(); act(() => window.dispatchEvent(new Event('focus')));
  await screen.findByText('1:new-instance'); await ready(); expect(current.version?.instance_id).toBe('two');
  expect(screen.queryByText('1:old-instance')).not.toBeInTheDocument();
});

it('aborts an unmounted read and rejects late callbacks for its submission epoch', async () => {
  let release!: (value: unknown) => void;
  const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<unknown>>(() => new Promise(resolve => { release = resolve; }));
  vi.stubGlobal('fetch', fetch); const view = render(<Harness />); const epoch = current.epoch.current;
  view.unmount(); expect((fetch.mock.calls[0][1] as RequestInit).signal?.aborted).toBe(true);
  await act(async () => release(response(snapshot([item(1, 'late')]))));
  expect(current.isCurrent(epoch)).toBe(false); expect(invalidated).not.toHaveBeenCalled();
});
