import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { useCallback, useRef } from 'react';
import { useChatHistory } from './useChatHistory';
import type { SpeakerSnapshot } from '../../lib/speakerContext';
import type { ConversationSnapshot } from '../../lib/conversation';

let current: ReturnType<typeof useChatHistory>, invalidated: ReturnType<typeof vi.fn>;
function Harness({ busy = false }: { busy?: boolean }) {
  const busyRef = useRef(busy); busyRef.current = busy;
  const isBusy = useCallback(() => busyRef.current, []);
  current = useChatHistory({ isBusy, onInvalidate: invalidated, includeContext: true });
  return <><output data-testid="context">{current.context?.scope ?? 'unknown'}</output>
    <output>{current.error?.message}</output>{current.rows.map((r, i) => <p key={r.id ?? i}>{r.text}</p>)}</>;
}
const context = (scope: SpeakerSnapshot['scope'] = 'current_user', cursor = 1, instance_id = 'one'): SpeakerSnapshot => ({
  instance_id, revision: 0, context_cursor: cursor, scope, profile_writes_for_new_turn: scope === 'current_user',
  real_actions_for_new_turn: scope === 'current_user', general_coreference_verified: false, version: 1,
});
const response = (data: unknown, status = 200) => ({ ok: status === 200, status, json: async () => ({ data,
  error: status === 200 ? null : { code: 'unauthorized', message: 'token rejected' } }) });
let snapshot: ConversationSnapshot, speaker: SpeakerSnapshot;
let held: { resolve: (value: unknown) => void; reject: (error: Error) => void; signal: AbortSignal; settled: boolean }[];
let speakerRead: (options: RequestInit) => Promise<unknown>;
let fetcher: ReturnType<typeof vi.fn>;
beforeEach(() => {
  invalidated = vi.fn(); held = []; speaker = context();
  snapshot = { instance_id: 'one', revision: 0, has_more: false, next_before_id: null,
    items: [{ id: 1, role: 'user', text: 'stored-private', session_id: 'one', created_at: 1, redacted: false }] };
  sessionStorage.setItem('avatar-token', 'context-view-disposable-token');
  speakerRead = async () => response(speaker);
  fetcher = vi.fn((url: string, options: RequestInit) => {
    if (url.includes('/changes?')) return new Promise((resolve, reject) => {
      const entry = { resolve: (value: unknown) => { entry.settled = true; resolve(value); },
        reject: (error: Error) => { entry.settled = true; reject(error); }, signal: options.signal!, settled: false };
      held.push(entry);
      const abort = () => entry.reject(new DOMException('Aborted', 'AbortError'));
      if (entry.signal.aborted) abort(); else entry.signal.addEventListener('abort', abort, { once: true });
    });
    if (url.endsWith('/conversation/speaker')) return speakerRead(options);
    if (url.includes('/conversation?')) return Promise.resolve(response(snapshot));
    throw Error('Unexpected test route '+url);
  });
  vi.stubGlobal('fetch', fetcher);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
async function ready(scope = 'current_user') {
  await screen.findByText(scope, { selector: '[data-testid=context]' });
  await waitFor(() => expect(current.ready).toBe(true));
  await waitFor(() => expect(held.length).toBeGreaterThanOrEqual(1));
}

it('ordinary context changes preserve pending rows and submission epoch without cancelling', async () => {
  const view = render(<Harness />); await ready(); const epoch = current.epoch.current;
  view.rerender(<Harness busy />);
  act(() => current.setRows([{ role: 'user', text: 'pending-user' }, { role: 'assistant', text: 'pending-draft', pending: true }]));
  speaker = context('fictional_character', 3);
  await act(async () => held[0].resolve(response({ instance_id: 'one', revision: 0, context_cursor: 3 })));
  await screen.findByText('fictional_character');
  expect(current.epoch.current).toBe(epoch); expect(current.isCurrent(epoch)).toBe(true);
  expect(current.rows.map(r => r.text)).toEqual(['pending-user', 'pending-draft']);
  expect(current.rows[1].pending).toBe(true); expect(invalidated).not.toHaveBeenCalled();
  expect(fetcher.mock.calls.filter(([url]) => String(url).includes('/conversation?'))).toHaveLength(1);
  expect(held.filter(h => !h.signal.aborted && !h.settled)).toHaveLength(1);
});

it('ignores a late metadata response even when its fetch ignores abort', async () => {
  render(<Harness />); await ready();
  let release!: (value: unknown) => void; let first = true; let oldSignal!: AbortSignal;
  speakerRead = options => {
    if (first) { first = false; oldSignal = options.signal!; return new Promise(resolve => { release = resolve; }); }
    return Promise.resolve(response(speaker));
  };
  act(() => { void current.refreshContext(); });
  await waitFor(() => expect(release).toBeDefined());
  speaker = context('fictional_character', 4);
  await act(async () => held[0].resolve(response({ instance_id: 'one', revision: 0, context_cursor: 4 })));
  await screen.findByText('fictional_character'); expect(oldSignal.aborted).toBe(true);
  await act(async () => release(response(context())));
  expect(current.context?.scope).toBe('fictional_character'); expect(current.context?.context_cursor).toBe(4);
  expect(invalidated).not.toHaveBeenCalled();
});

it('keeps context paused during watch loss and rechecks on same-version recovery', async () => {
  render(<Harness />); await ready(); const epoch = current.epoch.current;
  await act(async () => held[0].reject(new Error('offline')));
  expect(current.context).toBeNull(); expect(current.ready).toBe(false); expect(current.isCurrent(epoch)).toBe(false);
  const calls = fetcher.mock.calls.length;
  await act(async () => { await current.refreshContext(); window.dispatchEvent(new Event('focus')); });
  expect(fetcher.mock.calls.length).toBe(calls);
  await waitFor(() => expect(held.length).toBeGreaterThanOrEqual(2));
  speaker = context('fictional_character'); snapshot = { ...snapshot, items: [] };
  await act(async () => held[1].resolve(response({ instance_id: 'one', revision: 0, context_cursor: 1 })));
  await screen.findByText('fictional_character'); expect(current.ready).toBe(true); expect(invalidated).toHaveBeenCalledTimes(1);
});

it('rejects a previous-namespace context after server restart', async () => {
  render(<Harness />); await ready();
  let release!: (value: unknown) => void; let first = true;
  speakerRead = () => first ? (first = false, new Promise(resolve => { release = resolve; })) : Promise.resolve(response(speaker));
  act(() => { void current.refreshContext(); }); await waitFor(() => expect(release).toBeDefined());
  speaker = context('unverified', 0, 'two'); snapshot = { ...snapshot, instance_id: 'two', items: [] };
  await act(async () => held[0].resolve(response({ instance_id: 'two', revision: 0, context_cursor: 0 })));
  await screen.findByText('unverified'); expect(current.version?.instance_id).toBe('two');
  await act(async () => release(response(context())));
  expect(current.context?.instance_id).toBe('two'); expect(screen.queryByText('stored-private')).not.toBeInTheDocument();
});

it('can recheck after a cancelled uncommitted control without waiting for a new cursor', async () => {
  render(<Harness />); await ready(); const epoch = current.epoch.current;
  act(() => current.markContextPending()); expect(current.context).toBeNull();
  await act(async () => current.refreshContext());
  expect(current.context?.scope).toBe('current_user'); expect(current.epoch.current).toBe(epoch);
  expect(current.rows[0].text).toBe('stored-private'); expect(invalidated).not.toHaveBeenCalled();
});

it('never publishes incoherent permission metadata or its private payload', async () => {
  render(<Harness />); await ready();
  speakerRead = async () => response({ ...context(), scope: 'fictional_character', text: 'private-snapshot-marker' });
  await act(async () => current.refreshContext());
  expect(current.context).toBeNull(); expect(current.contextError?.message).not.toContain('private-snapshot-marker');
  expect(current.ready).toBe(true); expect(invalidated).not.toHaveBeenCalled();
});

it.each([401, 403])('pauses old context and history on context authorization failure %s', async status => {
  render(<Harness />); await ready(); const epoch = current.epoch.current;
  speakerRead = async () => response(null, status);
  await act(async () => current.refreshContext());
  expect(current.context).toBeNull(); expect(current.ready).toBe(false);
  expect(current.isCurrent(epoch)).toBe(false); expect(current.rows).toHaveLength(0);
  expect(invalidated).toHaveBeenCalledTimes(1);
  const calls = fetcher.mock.calls.length;
  await act(async () => { await current.refreshContext(); window.dispatchEvent(new Event('focus')); });
  expect(fetcher.mock.calls.length).toBe(calls);
});
