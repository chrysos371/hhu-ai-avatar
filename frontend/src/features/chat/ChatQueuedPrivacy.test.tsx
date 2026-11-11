vi.mock('../../lib/conversationWatch', () => ({ watchConversationChanges: vi.fn(async () => {}) }));
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ChatPage } from './ChatPage';
import { notifyConversationPrivacyChanged } from '../../lib/conversation';

const response = (data: unknown) => ({ ok: true, json: async () => ({ data }) });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function queued() {
  sessionStorage.setItem('avatar-token', 'queued-privacy-disposable-token');
  let revision = 0, release!: () => void, entered = false;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } },
    mutationCache: new MutationCache({ onMutate: async variables => {
      if ((variables as { text: string }).text === 'old-queued-private') { entered = true; await gate; }
    } }) });
  let finishNew!: () => void;
  const fetcher = vi.fn((url: string, options?: RequestInit) => {
    if (url.endsWith('/persona')) return Promise.resolve(response({ data: { name: '排队测试' } }));
    if (url.endsWith('/capabilities')) return Promise.resolve(response({ asr_enabled: false }));
    if (url.endsWith('/conversation/speaker')) return Promise.resolve(response({ instance_id: 'queue-server', revision,
      context_cursor: 0, scope: 'current_user', profile_writes_for_new_turn: true, real_actions_for_new_turn: true,
      general_coreference_verified: false, version: 1 }));
    if (url.includes('/conversation?')) return Promise.resolve(response({ instance_id: 'queue-server', revision,
      items: [], has_more: false, next_before_id: null }));
    if (url.endsWith('/cancel')) return Promise.resolve(response({ cancelled: true }));
    if (url.endsWith('/turns')) {
      const body = JSON.parse(options!.body as string);
      return Promise.resolve(response({ job_id: body.text === 'new-running' ? 'new_running_job_123456789' : 'old_queued_job_123456789' }));
    }
    if (url.includes('/events')) return Promise.resolve({ ok: true, body: new ReadableStream<Uint8Array>({ start(controller) {
      const finish = () => {
        const value = { reply: 'done', emotion: '中性', strategy: 'answer',
          conversation: { session_id: 'queue-server', revision, user_message_id: 1, assistant_message_id: 2 } };
        controller.enqueue(new TextEncoder().encode('event: result\ndata: '+JSON.stringify(value)+'\n\n')); controller.close();
      };
      if (url.includes('new_running')) finishNew = finish; else finish();
    } }) });
    throw Error('Unexpected route '+url);
  });
  vi.stubGlobal('fetch', fetcher);
  render(<QueryClientProvider client={client}><ChatPage /></QueryClientProvider>);
  await waitFor(() => expect(document.querySelector('.chat-history')).toHaveAttribute('data-history-ready', 'true'));
  fireEvent.change(screen.getByLabelText('消息'), { target: { value: 'old-queued-private' } });
  fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
  await waitFor(() => expect(entered).toBe(true));
  await act(async () => { revision = 1; notifyConversationPrivacyChanged(); });
  await waitFor(() => expect(document.querySelector('.chat-history')).toHaveAttribute('data-history-ready', 'true'));
  return { client, fetcher, release, finishNew: () => finishNew(), newReady: () => finishNew !== undefined };
}

it('does not post a queued request whose epoch expired before mutationFn starts', async () => {
  const control = await queued();
  try {
    await act(async () => control.release());
    await waitFor(() => expect(control.client.getMutationCache().getAll().every(m => m.state.status !== 'pending')).toBe(true));
    expect(control.fetcher.mock.calls.filter(([url]) => url.endsWith('/turns'))).toHaveLength(0);
  } finally { control.release(); control.client.clear(); }
});

it('an old queued settlement cannot reset a newer running mutation', async () => {
  const control = await queued();
  try {
    fireEvent.change(screen.getByLabelText('消息'), { target: { value: 'new-running' } });
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    await waitFor(() => expect(control.newReady()).toBe(true));
    await act(async () => control.release());
    await waitFor(() => expect(control.client.getMutationCache().getAll().filter(m => m.state.status === 'pending')).toHaveLength(1));
    expect(screen.getByRole('button', { name: '等待回复…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '停止生成' })).toBeEnabled();
  } finally {
    control.release(); if (control.newReady()) await act(async () => control.finishNew());
    control.client.clear();
  }
});
