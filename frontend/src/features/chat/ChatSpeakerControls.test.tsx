vi.mock('../../lib/conversationWatch', () => ({ watchConversationChanges: vi.fn(async () => {}) }));
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ChatPage } from './ChatPage';

const response = (data: unknown) => ({ ok: true, json: async () => ({ data }) });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function setup(initial: 'current_user' | 'fictional_character' | 'unverified' = 'current_user') {
  sessionStorage.setItem('avatar-token', 'speaker-controls-disposable-token');
  let scope = initial, cursor = 0, finish!: () => void;
  const items: unknown[] = [];
  const fetcher = vi.fn((url: string, options?: RequestInit) => {
    if (url.endsWith('/persona')) return Promise.resolve(response({ data: { name: '语境测试' } }));
    if (url.endsWith('/capabilities')) return Promise.resolve(response({ asr_enabled: false }));
    if (url.endsWith('/conversation/speaker')) return Promise.resolve(response({ instance_id: 'speaker-ui', revision: 0,
      context_cursor: cursor, scope, profile_writes_for_new_turn: scope === 'current_user',
      real_actions_for_new_turn: scope === 'current_user', general_coreference_verified: false, version: 1 }));
    if (url.includes('/conversation?')) return Promise.resolve(response({ instance_id: 'speaker-ui', revision: 0,
      items, has_more: false, next_before_id: null }));
    if (url.endsWith('/turns')) {
      const body = JSON.parse(options!.body as string);
      cursor += 2;
      scope = body.text === '回到现实。' ? 'current_user' : 'fictional_character';
      items.push({ id: cursor - 1, role: 'user', text: body.text, session_id: 'speaker-ui', created_at: 1, redacted: false });
      return Promise.resolve(response({ job_id: body.request_id }));
    }
    if (url.includes('/events')) return Promise.resolve({ ok: true, body: new ReadableStream<Uint8Array>({ start(controller) {
      finish = () => {
        const result = { reply: '已记录这次选择。', emotion: '中性', strategy: 'answer',
          conversation: { session_id: 'speaker-ui', revision: 0, user_message_id: cursor - 1, assistant_message_id: cursor } };
        items.push({ id: cursor, role: 'assistant', text: result.reply, session_id: 'speaker-ui', created_at: 2, redacted: false, result });
        controller.enqueue(new TextEncoder().encode('event: result\ndata: '+JSON.stringify(result)+'\n\n')); controller.close();
      };
    } }) });
    if (url.endsWith('/cancel')) return Promise.resolve(response({ cancelled: true }));
    throw Error('Unexpected route '+url);
  });
  vi.stubGlobal('fetch', fetcher);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ChatPage /></QueryClientProvider>);
  await waitFor(() => expect(document.querySelector('[data-speaker-context]')).toHaveAttribute('data-speaker-context', initial));
  return { client, fetcher, ready: () => finish !== undefined, finish: () => finish() };
}

it.each([
  ['current_user', '进入角色', '我来扮演一个虚构角色。', 'fictional_character'],
  ['fictional_character', '以本人说话', '回到现实。', 'current_user'],
] as const)('sends an independent control from %s and preserves the unsent draft', async (initial, button, text, expected) => {
  const control = await setup(initial);
  try {
    fireEvent.change(screen.getByLabelText('消息'), { target: { value: '提醒我明天下午3点去码头' } });
    fireEvent.click(screen.getByLabelText('自动分段朗读新回复'));
    if (initial === 'current_user') fireEvent.click(screen.getByLabelText('本轮允许联网工具'));
    fireEvent.click(screen.getByRole('button', { name: button }));
    await waitFor(() => expect(control.ready()).toBe(true));
    expect(screen.getByLabelText('消息')).toHaveValue('提醒我明天下午3点去码头');
    expect(document.querySelector('[data-speaker-context]')).toHaveAttribute('data-speaker-context', 'pending');
    const posts = control.fetcher.mock.calls.filter(([url]) => url.endsWith('/turns'));
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1]!.body as string)).toEqual({ request_id: expect.any(String), text, use_web: false });
    await act(async () => control.finish());
    await waitFor(() => expect(document.querySelector('[data-speaker-context]')).toHaveAttribute('data-speaker-context', expected));
    expect(screen.getByLabelText('消息')).toHaveValue('提醒我明天下午3点去码头');
    expect(control.fetcher.mock.calls.filter(([url]) => url.endsWith('/speech'))).toHaveLength(0);
  } finally { control.client.clear(); }
});

it('allows explicit confirmation from unverified context and admits only one immediate click', async () => {
  const control = await setup('unverified');
  try {
    const button = screen.getByRole('button', { name: '以本人说话' });
    expect(button).toBeEnabled();
    await act(async () => { button.click(); button.click(); });
    await waitFor(() => expect(control.ready()).toBe(true));
    expect(control.fetcher.mock.calls.filter(([url]) => url.endsWith('/turns'))).toHaveLength(1);
    await act(async () => control.finish());
    await waitFor(() => expect(document.querySelector('[data-speaker-context]')).toHaveAttribute('data-speaker-context', 'current_user'));
  } finally { control.client.clear(); }
});

it('captures reminder-only mode on submission, disables web and resets the next turn', async () => {
  const control = await setup();
  try {
    fireEvent.click(screen.getByLabelText('本轮允许联网工具'));
    fireEvent.click(screen.getByLabelText('本轮仅查询提醒'));
    expect(screen.getByLabelText('本轮允许联网工具')).toBeDisabled();
    expect(screen.getByLabelText('本轮允许联网工具')).not.toBeChecked();
    fireEvent.change(screen.getByLabelText('消息'), { target: { value: '提醒编号1状态？' } });
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    await waitFor(() => expect(control.ready()).toBe(true));
    const posts = control.fetcher.mock.calls.filter(([url]) => url.endsWith('/turns'));
    expect(JSON.parse(posts[0][1]!.body as string)).toMatchObject({ mode: 'reminder_query', use_web: false, text: '提醒编号1状态？' });
    expect(screen.getByLabelText('本轮仅查询提醒')).toBeDisabled();
    await act(async () => control.finish());
    await waitFor(() => expect(screen.getByLabelText('本轮仅查询提醒')).not.toBeChecked());
  } finally { control.client.clear(); }
});

it('keeps independent speaker controls in chat mode even with reminder mode selected', async () => {
  const control = await setup('unverified');
  try {
    fireEvent.click(screen.getByLabelText('本轮仅查询提醒'));
    fireEvent.click(screen.getByRole('button', { name: '以本人说话' }));
    await waitFor(() => expect(control.ready()).toBe(true));
    const body = JSON.parse(control.fetcher.mock.calls.find(([url]) => url.endsWith('/turns'))![1]!.body as string);
    expect(body.text).toBe('回到现实。'); expect(body.mode).toBeUndefined();
    await act(async () => control.finish());
  } finally { control.client.clear(); }
});

it('preserves a long chat draft but refuses query submission until shortened', async () => {
  const control = await setup();
  try {
    fireEvent.change(screen.getByLabelText('消息'), { target: { value: '字'.repeat(2001) } });
    fireEvent.click(screen.getByLabelText('本轮仅查询提醒'));
    expect(screen.getByLabelText('消息')).toHaveValue('字'.repeat(2001));
    expect(screen.getByRole('alert')).toHaveTextContent('超过2000字');
    expect(screen.getByRole('button', { name: '发送消息' })).toBeDisabled();
    expect(control.fetcher.mock.calls.filter(([url]) => url.endsWith('/turns'))).toHaveLength(0);
  } finally { control.client.clear(); }
});
