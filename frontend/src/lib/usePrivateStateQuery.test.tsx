import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiRequest } from './api';
import { watchConversationChanges } from './conversationWatch';
import { notifyConversationPrivacyChanged } from './conversation';
import { usePrivateStateQuery } from './usePrivateStateQuery';
import type { StateContext } from './statePrivacy';

vi.mock('./api', () => ({ apiRequest: vi.fn() }));
vi.mock('./conversationWatch', () => ({ watchConversationChanges: vi.fn() }));

type Callbacks = Parameters<typeof watchConversationChanges>[2];
interface Value { context: StateContext; value: string }
let context: StateContext, value: string, client: QueryClient;
let callbacks: Callbacks;
let nextState: Promise<Value> | null;
let observed: string[];

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(finish => { resolve = finish; });
  return { promise, resolve };
}

function Harness({ name = 'emotion' }: { name?: 'emotion' | 'dashboard' }) {
  const query = usePrivateStateQuery<Value>(name, 60000);
  const shown = query.data?.value ?? 'empty';
  observed.push(shown);
  return <><output data-testid="value">{shown}</output><span data-testid="error">{query.error?.message}</span>
    <button onClick={() => query.refetch()}>retry</button></>;
}

function mount(name: 'emotion' | 'dashboard' = 'emotion') {
  return render(<QueryClientProvider client={client}><Harness name={name} /></QueryClientProvider>);
}

beforeEach(() => {
  context = { instance_id: 'original', revision: 0 };
  value = 'old'; nextState = null; observed = [];
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  vi.mocked(apiRequest).mockImplementation(async path => {
    if (path.includes('instance_id=state-bootstrap')) return { ...context } as never;
    if (nextState) { const held = nextState; nextState = null; return await held as never; }
    return { context: { ...context }, value } as never;
  });
  vi.mocked(watchConversationChanges).mockImplementation(async (_initial, signal, handlers) => {
    callbacks = handlers;
    if (!signal.aborted) await new Promise<void>(resolve => signal.addEventListener('abort', () => resolve(), { once: true }));
  });
});
afterEach(() => { client.clear(); vi.clearAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

it.each(['emotion', 'dashboard'] as const)('only reads %s after metadata and supplies the fetch abort signal', async name => {
  const metadata = deferred<StateContext>();
  vi.mocked(apiRequest).mockImplementationOnce(() => metadata.promise as never);
  mount(name);
  expect(screen.getByTestId('value')).toHaveTextContent('empty');
  expect(apiRequest).toHaveBeenCalledTimes(1);
  await act(async () => metadata.resolve(context));
  expect(await screen.findByText('old')).toBeInTheDocument();
  const call = vi.mocked(apiRequest).mock.calls.find(([path]) => path === '/' + name)!;
  expect(call[1]?.signal).toBeInstanceOf(AbortSignal);
  expect(vi.mocked(watchConversationChanges)).toHaveBeenCalledTimes(1);
});

it('hides old state at a higher revision and clears inactive derived cache too', async () => {
  mount(); await screen.findByText('old');
  client.setQueryData(['dashboard', 'original', 0, 1], { context, value: 'inactive private state' });
  expect(client.getQueriesData({ queryKey: ['dashboard'] })).toHaveLength(1);
  context = { ...context, revision: 1 }; value = 'new';
  const held = deferred<Value>(); nextState = held.promise;
  act(() => callbacks.onVersion(context));
  expect(screen.getByTestId('value')).toHaveTextContent('empty');
  expect(client.getQueriesData({ queryKey: ['dashboard'] })).toHaveLength(0);
  await act(async () => held.resolve({ context, value }));
  expect(await screen.findByText('new')).toBeInTheDocument();
});

it('rejects a late old payload even when its transport ignores cancellation', async () => {
  mount(); await screen.findByText('old');
  const held = deferred<Value>(); nextState = held.promise;
  act(() => { void client.invalidateQueries({ queryKey: ['emotion'] }); });
  await waitFor(() => expect(nextState).toBeNull());
  const oldCall = vi.mocked(apiRequest).mock.calls.filter(([path]) => path === '/emotion').at(-1)!;
  context = { ...context, revision: 1 }; value = 'new';
  act(() => callbacks.onVersion(context));
  const checkpoint = observed.length;
  expect(await screen.findByText('new')).toBeInTheDocument();
  expect(oldCall[1]?.signal?.aborted).toBe(true);
  await act(async () => held.resolve({ context: { instance_id: 'original', revision: 0 }, value: 'late secret' }));
  expect(screen.getByTestId('value')).toHaveTextContent('new');
  expect(observed.slice(checkpoint)).not.toContain('late secret');
  expect(client.getQueryCache().getAll().some(query => (query.state.data as Value)?.value === 'late secret')).toBe(false);
});

it('hides state on notification failure and waits for a successful same-revision recovery', async () => {
  mount(); await screen.findByText('old');
  act(() => callbacks.onUnavailable(new Error('watch offline')));
  expect(screen.getByTestId('value')).toHaveTextContent('empty');
  expect(screen.getByTestId('error')).toHaveTextContent('已暂停旧状态');
  value = 'recovered';
  act(() => callbacks.onVersion(context));
  expect(await screen.findByText('recovered')).toBeInTheDocument();
});

it('keeps old state hidden on authentication failure until an explicit metadata retry succeeds', async () => {
  mount(); await screen.findByText('old');
  act(() => callbacks.onUnavailable(new Error('鉴权失败')));
  expect(screen.getByTestId('value')).toHaveTextContent('empty');
  value = 'reauthorized';
  fireEvent.click(screen.getByRole('button', { name: 'retry' }));
  expect(await screen.findByText('reauthorized')).toBeInTheDocument();
});

it('accepts a new instance with a lower revision and rejects same-instance rollback', async () => {
  context.revision = 5;
  mount(); await screen.findByText('old');
  act(() => callbacks.onVersion({ ...context, revision: 4 }));
  expect(screen.getByTestId('value')).toHaveTextContent('empty');
  expect(screen.getByTestId('error')).toHaveTextContent('版本倒退');
  context = { instance_id: 'restarted', revision: 0 }; value = 'restarted';
  act(() => callbacks.onVersion(context));
  expect(await screen.findByText('restarted')).toBeInTheDocument();
});

it('leaves a normal same-revision heartbeat and legitimate state untouched', async () => {
  mount(); await screen.findByText('old');
  const count = vi.mocked(apiRequest).mock.calls.length;
  act(() => callbacks.onVersion({ ...context }));
  expect(screen.getByTestId('value')).toHaveTextContent('old');
  expect(apiRequest).toHaveBeenCalledTimes(count);
});

it.each([undefined, { instance_id: 'original', revision: true }, { instance_id: 'other', revision: 0 }])(
  'never displays a state payload with missing, malformed or mismatched context %j', async invalid => {
    vi.mocked(apiRequest).mockImplementation(async path => path.includes('state-bootstrap')
      ? { ...context } as never : { context: invalid, value: 'unverified secret' } as never);
    mount();
    await waitFor(() => expect(screen.getByTestId('error')).toHaveTextContent('已暂停旧状态'));
    expect(observed).not.toContain('unverified secret');
    expect(screen.getByTestId('value')).toHaveTextContent('empty');
  });

it('does not request state after an unavailable initial metadata check', async () => {
  vi.mocked(apiRequest).mockRejectedValueOnce(new Error('metadata unavailable'));
  mount();
  await waitFor(() => expect(screen.getByTestId('error')).toHaveTextContent('metadata unavailable'));
  expect(apiRequest).toHaveBeenCalledTimes(1);
  expect(watchConversationChanges).not.toHaveBeenCalled();
});

it('times out an unresponsive bootstrap, retries, and rejects its late uncancellable response', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  const held = deferred<StateContext>();
  vi.mocked(apiRequest).mockImplementationOnce(() => held.promise as never);
  mount();
  const signal = vi.mocked(apiRequest).mock.calls[0][1]?.signal;
  await act(async () => { await vi.advanceTimersByTimeAsync(14999); });
  expect(screen.getByTestId('error')).toBeEmptyDOMElement();
  expect(screen.getByTestId('value')).toHaveTextContent('empty');
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(signal?.aborted).toBe(true);
  expect(screen.getByTestId('error')).toHaveTextContent('版本同步超时');
  expect(watchConversationChanges).not.toHaveBeenCalled();
  context = { instance_id: 'newer', revision: 1 }; value = 'fresh';
  fireEvent.click(screen.getByRole('button', { name: 'retry' }));
  await act(async () => { await vi.advanceTimersByTimeAsync(10); });
  // React commits the new query after the first async act; flush its queued observer notification.
  await act(async () => { await vi.advanceTimersByTimeAsync(10); });
  expect(screen.getByTestId('value')).toHaveTextContent('fresh');
  await act(async () => {
    held.resolve({ instance_id: 'original', revision: 0 });
    await vi.advanceTimersByTimeAsync(15000);
  });
  expect(screen.getByTestId('value')).toHaveTextContent('fresh');
  expect(screen.getByTestId('error')).toBeEmptyDOMElement();
  expect(watchConversationChanges).toHaveBeenCalledTimes(1);
});

it('clears its bootstrap deadline and aborts the request when unmounted before metadata', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  const held = deferred<StateContext>();
  vi.mocked(apiRequest).mockImplementationOnce(() => held.promise as never);
  const mounted = mount();
  const signal = vi.mocked(apiRequest).mock.calls[0][1]?.signal;
  mounted.unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () => {
    held.resolve(context);
    await vi.advanceTimersByTimeAsync(20000);
  });
  expect(apiRequest).toHaveBeenCalledTimes(1);
  expect(watchConversationChanges).not.toHaveBeenCalled();
});

it('rechecks same-window privacy notices and never adopts a stale bootstrap response', async () => {
  const held = deferred<StateContext>();
  vi.mocked(apiRequest).mockImplementationOnce(() => held.promise as never);
  mount();
  context = { instance_id: 'new-instance', revision: 3 }; value = 'new';
  act(() => notifyConversationPrivacyChanged());
  expect(await screen.findByText('new')).toBeInTheDocument();
  await act(async () => held.resolve({ instance_id: 'original', revision: 0 }));
  expect(screen.getByTestId('value')).toHaveTextContent('new');
  expect(watchConversationChanges).toHaveBeenCalledTimes(1);
});

it('rechecks a cross-window privacy message with a separate sender', async () => {
  const channels: Array<{ onmessage: ((event: { data: unknown }) => void) | null }> = [];
  class Channel {
    onmessage = null;
    constructor() { channels.push(this); }
    postMessage() {}
    close() {}
  }
  vi.stubGlobal('BroadcastChannel', Channel);
  mount(); await screen.findByText('old');
  context = { ...context, revision: 1 }; value = 'cross-window';
  act(() => channels[0].onmessage?.({ data: { type: 'invalidate', sender: 'another-window' } }));
  expect(await screen.findByText('cross-window')).toBeInTheDocument();
});

it('aborts version and state requests on route unmount and rechecks before reusing a cache', async () => {
  const mounted = mount(); await screen.findByText('old');
  const signal = vi.mocked(watchConversationChanges).mock.calls[0][1];
  mounted.unmount();
  expect(signal.aborted).toBe(true);
  context = { ...context, revision: 1 }; value = 'after navigation';
  const held = deferred<StateContext>();
  vi.mocked(apiRequest).mockImplementationOnce(() => held.promise as never);
  mount();
  expect(screen.getByTestId('value')).toHaveTextContent('empty');
  await act(async () => held.resolve(context));
  expect(await screen.findByText('after navigation')).toBeInTheDocument();
});
