// Snapshot/turn ordering is isolated here; transport has dedicated and Chromium tests.
vi.mock('../../lib/conversationWatch', () => ({ watchConversationChanges: vi.fn(async () => {}) }));
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatPage } from "./ChatPage";
afterEach(() => vi.unstubAllGlobals());
it("streams a reviewed draft then replaces it with the final traced reply", async () => {
  sessionStorage.setItem("avatar-token", "unit-session-token-123456");
  let finish!: (x: unknown) => void;
  let completed = false;
  const result = { reply: "你好，我在。", emotion: "中性", strategy: "answer",
    conversation: { session_id: 'unit', revision: 0, user_message_id: 1, assistant_message_id: 2 }, trace: {
    recalled_memories: [], decision: { strategy: "answer" }, guard: { route: "normal", guarded: false },
    verifier: { available: false, reason: "未配置" }, tool_calls: [],
  } };
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (url.endsWith("/persona")) return Promise.resolve({ ok: true, json: async () => ({ data: { data: { name: "星澜" } } }) });
    if (url.endsWith("/capabilities")) return Promise.resolve({ ok: true, json: async () => ({ data: { asr_enabled: false } }) });
    if (url.endsWith('/conversation/speaker')) return Promise.resolve({ ok: true, json: async () => ({ data: {
      instance_id: 'unit-server', revision: 0, context_cursor: completed ? 1 : 0, scope: 'current_user',
      profile_writes_for_new_turn: true, real_actions_for_new_turn: true, general_coreference_verified: false, version: 1,
    } }) });
    if (url.includes('/conversation?')) return Promise.resolve({ ok: true, json: async () => ({ data: {
      instance_id: 'unit-server', revision: 0, has_more: false, next_before_id: null,
      items: completed ? [{ id: 1, role: 'user', text: '你好', session_id: 'unit', created_at: 1, redacted: false },
        { id: 2, role: 'assistant', text: result.reply, session_id: 'unit', created_at: 2, redacted: false, result }] : [],
    } }) });
    if (url.endsWith("/turns")) return new Promise(resolve => { finish = resolve; });
    completed = true;
    const bytes = new TextEncoder().encode('event: text\ndata: {"text":"已检查的草稿。"}\n\nevent: result\ndata: ' + JSON.stringify(result) + '\n\n');
    return Promise.resolve({ ok: true, body: new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } }) });
  }));
  render(<QueryClientProvider client={new QueryClient()}><ChatPage /></QueryClientProvider>);
  expect(await screen.findByRole("heading", { name: "星澜在这里" })).toBeInTheDocument();
  expect(screen.getByLabelText("星澜语音播放器")).toBeInTheDocument();
  await waitFor(() => expect(document.querySelector('.chat-history')).toHaveAttribute('data-history-ready', 'true'));
  fireEvent.change(screen.getByLabelText("消息"), { target: { value: "你好" } });
  fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
  expect(await screen.findByRole("button", { name: "等待回复…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "停止生成" })).toBeEnabled();
  finish({ ok: true, json: async () => ({ data: { job_id: "unit_job_identifier_123456" }, error: null }) });
  expect(await screen.findByText("你好，我在。")).toBeInTheDocument();
  expect(screen.queryByText("已检查的草稿。")).not.toBeInTheDocument();
  expect(screen.getByText("本轮决策与来源").closest("details")).not.toHaveAttribute("open");
  const trace = screen.getByText("本轮决策与来源").closest("details")!;
  expect(trace.querySelectorAll('pre')).toHaveLength(0);
  fireEvent.click(screen.getByText("本轮决策与来源"));
  await waitFor(() => expect(trace.querySelectorAll('pre')).toHaveLength(5));
  expect(JSON.parse(trace.querySelector('pre')!.textContent!)).toEqual(result.trace.decision);
  fireEvent.click(screen.getByText("本轮决策与来源"));
  await waitFor(() => expect(trace.querySelectorAll('pre')).toHaveLength(0));
});

it('reads a legacy reply without inventing a trace and preserves it when speech is unavailable', async () => {
  sessionStorage.setItem('avatar-token', 'legacy-reply-disposable-session-token');
  const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<unknown>>((url: string) => {
    if (url.endsWith('/persona')) return Promise.resolve({ ok: true, json: async () => ({ data: { data: { name: '历史测试' } } }) });
    if (url.endsWith('/capabilities')) return Promise.resolve({ ok: true, json: async () => ({ data: { asr_enabled: false } }) });
    if (url.endsWith('/conversation/speaker')) return Promise.resolve({ ok: true, json: async () => ({ data: {
      instance_id: 'legacy-instance', revision: 0, context_cursor: 0, scope: 'current_user',
      profile_writes_for_new_turn: true, real_actions_for_new_turn: true, general_coreference_verified: false, version: 1,
    } }) });
    if (url.includes('/conversation?')) return Promise.resolve({ ok: true, json: async () => ({ data: {
      instance_id: 'legacy-instance', revision: 0, has_more: false, next_before_id: null,
      items: [{ id: 2, role: 'assistant', text: 'legacy-original-reply', session_id: 'legacy', created_at: 1, redacted: false }],
    } }) });
    return Promise.resolve({ ok: false, status: 503, json: async () => ({ data: null, error: { code: 'speech_unavailable', message: '暂不可朗读' } }) });
  });
  vi.stubGlobal('fetch', fetch);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ChatPage /></QueryClientProvider>);
  await screen.findByText('legacy-original-reply');
  expect(screen.queryByText('本轮决策与来源')).not.toBeInTheDocument();
  expect(screen.getByText('这条历史回复未保留可用的决策记录。')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '朗读回复' }));
  await screen.findByText('暂不可朗读');
  const call = fetch.mock.calls.find(([url]) => url.endsWith('/speech'))!;
  expect(JSON.parse((call[1] as RequestInit).body as string)).toMatchObject({ text: 'legacy-original-reply', rate: '+0%', pitch: '+0Hz', mouth_intensity: .75 });
  expect(screen.getByText('legacy-original-reply')).toBeInTheDocument(); client.clear();
});
