import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ChatPage } from './ChatPage';
import { notifyConversationPrivacyChanged, type ConversationSnapshot } from '../../lib/conversation';

const result = { reply: 'late-private-reply', emotion: '中性', strategy: 'answer',
  conversation: { session_id: 'privacy-unit', revision: 0, user_message_id: 1, assistant_message_id: 2 },
  trace: { recalled_memories: [], decision: { strategy: 'answer' }, guard: { route: 'normal', guarded: false },
    verifier: { available: false, reason: 'fixture' }, tool_calls: [] } };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function setup(hold: boolean) {
  sessionStorage.setItem('avatar-token', 'privacy-unit-disposable-session-token');
  let snapshot: ConversationSnapshot = { instance_id: 'privacy-server', revision: 0, items: [], has_more: false, next_before_id: null };
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const complete = () => {
    const bytes = new TextEncoder().encode('event: result\ndata: ' + JSON.stringify(result) + '\n\n');
    controller.enqueue(bytes); controller.close();
    if (snapshot.revision === 0) snapshot = { ...snapshot, items: [
      { id: 1, role: 'user', text: 'late-private-user', created_at: 1, session_id: 'privacy-unit', redacted: false },
      { id: 2, role: 'assistant', text: result.reply, created_at: 2, session_id: 'privacy-unit', redacted: false, result },
    ] };
  };
  const fetch = vi.fn((url: string) => {
    if (url.endsWith('/persona')) return Promise.resolve({ ok: true, json: async () => ({ data: { data: { name: '屏障测试' } } }) });
    if (url.endsWith('/capabilities')) return Promise.resolve({ ok: true, json: async () => ({ data: { asr_enabled: false } }) });
    if (url.includes('/conversation?')) { const data = snapshot; return Promise.resolve({ ok: true, json: async () => ({ data }) }); }
    if (url.endsWith('/cancel')) return Promise.resolve({ ok: true, json: async () => ({ data: { cancelled: true } }) });
    if (url.endsWith('/turns')) return Promise.resolve({ ok: true, json: async () => ({ data: { job_id: 'privacy_unit_job_identifier' } }) });
    return Promise.resolve({ ok: true, body: new ReadableStream<Uint8Array>({ start(value) { controller = value; if (!hold) complete(); } }) });
  });
  vi.stubGlobal('fetch', fetch);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ChatPage /></QueryClientProvider>);
  await waitFor(() => expect(document.querySelector('.chat-history')).toHaveAttribute('data-history-ready', 'true'));
  fireEvent.change(screen.getByLabelText('消息'), { target: { value: 'late-private-user' } });
  fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
  await waitFor(() => expect(controller).toBeDefined());
  return { client, fetch, complete, erase: () => {
    snapshot = { ...snapshot, revision: 1, items: [] };
    notifyConversationPrivacyChanged();
  } };
}

it('does not let a final result released after privacy clear repopulate chat or mutation cache', async () => {
  const control = await setup(true);
  expect(screen.getByText('late-private-user')).toBeInTheDocument();
  await act(async () => control.erase());
  await waitFor(() => expect(screen.queryByText('late-private-user')).not.toBeInTheDocument());
  await act(async () => control.complete());
  await waitFor(() => expect(document.querySelector('.chat-history')).toHaveAttribute('data-history-ready', 'true'));
  expect(screen.queryByText('late-private-reply')).not.toBeInTheDocument();
  await waitFor(() => expect(control.client.getMutationCache().getAll()).toHaveLength(0));
  expect(control.fetch.mock.calls.some(([url]) => url.endsWith('/cancel'))).toBe(true);
  control.client.clear();
});

it('clears an already completed visible result and its observed mutation on privacy invalidation', async () => {
  const control = await setup(false);
  await screen.findByText('late-private-reply');
  expect(control.client.getMutationCache().getAll()).toHaveLength(1);
  await act(async () => control.erase());
  await waitFor(() => expect(document.querySelector('.chat-history')).toHaveAttribute('data-history-ready', 'true'));
  expect(document.body.textContent).not.toContain('late-private-');
  await waitFor(() => expect(control.client.getMutationCache().getAll()).toHaveLength(0));
  control.client.clear();
});
