vi.mock('../../lib/conversationWatch', () => ({ watchConversationChanges: vi.fn(async () => {}) }));
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ChatPage } from './ChatPage';

const response = (data: unknown) => ({ ok: true, json: async () => ({ data }) });
const failure = (status: number, code: string) => ({ ok: false, status,
  json: async () => ({ data: null, error: { code, message: '语境已变化，请确认当前模式后重新发送。' } }) });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it.each(['cursor-post', 'cursor-sse', 'privacy', 'restart', 'unavailable'] as const)(
  'reconciles %s before considering a rejected draft and never retries it', async mode => {
    sessionStorage.setItem('avatar-token', 'admission-ui-disposable-token');
    let rejected = false, refreshStarted = false, release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    const version = () => ({ instance_id: rejected && mode === 'restart' ? 'new-instance' : 'original-instance',
      revision: rejected && mode === 'privacy' ? 1 : 0 });
    const metadata = () => ({ ...version(), context_cursor: rejected ? 3 : 1,
      scope: rejected ? 'current_user' : 'fictional_character', profile_writes_for_new_turn: rejected,
      real_actions_for_new_turn: rejected, general_coreference_verified: false, version: 1 });
    const fetcher = vi.fn((url: string, options?: RequestInit): Promise<unknown> => {
      if (url.endsWith('/persona')) return Promise.resolve(response({ data: { name: '入场测试' } }));
      if (url.endsWith('/capabilities')) return Promise.resolve(response({ asr_enabled: false }));
      if (url.endsWith('/conversation/speaker')) {
        if (!rejected) return Promise.resolve(response(metadata()));
        refreshStarted = true;
        return gate.then(() => mode === 'unavailable' ? failure(503, 'context_unavailable') : response(metadata()));
      }
      if (url.includes('/conversation?')) return Promise.resolve(response({ ...version(), items: [], has_more: false, next_before_id: null }));
      if (url.endsWith('/turns')) {
        const body = JSON.parse(options!.body as string);
        expect(body.expected_context).toEqual({ instance_id: 'original-instance', revision: 0, context_cursor: 1 });
        rejected = true;
        return Promise.resolve(mode === 'cursor-post' ? failure(409, 'speaker_context_changed') : response({ job_id: body.request_id }));
      }
      if (url.includes('/events')) return Promise.resolve({ ok: true, body: new ReadableStream<Uint8Array>({ start(controller) {
        controller.enqueue(new TextEncoder().encode('event: error\ndata: {"code":"speaker_context_changed","message":"语境已变化，请确认当前模式后重新发送。"}\n\n'));
        controller.close();
      } }) });
      if (url.endsWith('/cancel')) return Promise.resolve(response({ cancelled: false }));
      throw Error('Unexpected route '+url);
    });
    vi.stubGlobal('fetch', fetcher);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    try {
      render(<QueryClientProvider client={client}><ChatPage /></QueryClientProvider>);
      await waitFor(() => expect(document.querySelector('[data-speaker-context]')).toHaveAttribute('data-speaker-context', 'fictional_character'));
      fireEvent.change(screen.getByLabelText('消息'), { target: { value: '我叫角色许照。' } });
      fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
      await waitFor(() => expect(refreshStarted).toBe(true));
      // Rejected text is not restored while privacy/version verification is pending.
      expect(screen.getByLabelText('消息')).toHaveValue('');
      await act(async () => release());
      await waitFor(() => expect(screen.queryByRole('button', { name: '等待回复…' })).not.toBeInTheDocument());
      if (mode.startsWith('cursor')) {
        await waitFor(() => expect(screen.getByLabelText('消息')).toHaveValue('我叫角色许照。'));
        expect(await screen.findByText('语境已变化，请确认当前模式后重新发送。')).toBeInTheDocument();
      } else {
        expect(screen.getByLabelText('消息')).toHaveValue('');
        expect(screen.queryByText('我叫角色许照。')).not.toBeInTheDocument();
      }
      expect(fetcher.mock.calls.filter(([url]) => url.endsWith('/turns'))).toHaveLength(1);
    } finally { release(); client.clear(); }
  });
