// Snapshot/turn ordering is isolated here; transport has dedicated and Chromium tests.
vi.mock('../../lib/conversationWatch', () => ({ watchConversationChanges: vi.fn(async () => {}) }));
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { ChatPage } from './ChatPage';
import type { ChatResult } from '../../lib/types';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('does not retain 40 completed chat mutation results after the page unmounts', async () => {
  sessionStorage.setItem('avatar-token', 'cache-audit-disposable-session-token');
  let count = 0;
  const messages: unknown[] = [];
  const reply = (i: number) => `cache-sensitive-reply-${i}`;
  const results = new Map<string, ChatResult>();
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.endsWith('/persona')) return Promise.resolve({ ok: true, json: async () => ({ data: { data: { name: '缓存测试' } } }) });
    if (url.endsWith('/capabilities')) return Promise.resolve({ ok: true, json: async () => ({ data: { asr_enabled: false } }) });
    if (url.includes('/conversation')) return Promise.resolve({ ok: true, json: async () => ({ data: {
      instance_id: 'cache-audit-instance', revision: 0, items: [...messages], has_more: false, next_before_id: null,
    } }) });
    if (url.endsWith('/turns')) {
      const i = ++count, id = 'cache_audit_job_' + String(i).padStart(12, '0');
      const result = { reply: reply(i), emotion: '中性', strategy: 'answer',
        conversation: { session_id: 'cache-session', user_message_id: 2 * i - 1, assistant_message_id: 2 * i, revision: 0 },
        trace: { recalled_memories: [], decision: { strategy: 'answer' }, guard: { route: 'normal', guarded: false },
          verifier: { available: false, reason: 'fixture' }, tool_calls: [] } } as ChatResult;
      results.set(id, result);
      messages.push({ id: 2 * i - 1, role: 'user', text: `cache-input-${i}`, session_id: 'cache-session', created_at: i, redacted: false },
        { id: 2 * i, role: 'assistant', text: result.reply, session_id: 'cache-session', created_at: i, redacted: false, result });
      return Promise.resolve({ ok: true, json: async () => ({ data: { job_id: id } }) });
    }
    const id = url.split('/').at(-2)!;
    const bytes = new TextEncoder().encode('event: result\ndata: ' + JSON.stringify(results.get(id)) + '\n\n');
    return Promise.resolve({ ok: true, body: new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } }) });
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><ChatPage /></QueryClientProvider>);
  await screen.findByRole('heading', { name: '缓存测试在这里' });
  for (let i = 1; i <= 40; i++) {
    fireEvent.change(screen.getByLabelText('消息'), { target: { value: `cache-input-${i}` } });
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
    await screen.findByText(reply(i), { exact: true });
    await screen.findByRole('button', { name: '发送消息' });
  }
  const mounted = client.getMutationCache().getAll().length;
  view.unmount(); await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
  const retained = client.getMutationCache().getAll();
  const observed = { mountedMutations: mounted, afterUnmountMutations: retained.length,
    retainedSensitiveReplies: retained.filter(m => (m.state.data as ChatResult | undefined)?.reply?.startsWith('cache-sensitive-reply-')).length,
    gcTimes: [...new Set(retained.map(m => m.gcTime))] };
  const folder = process.env.AVATAR_CACHE_EVIDENCE_DIR;
  if (folder) {
    mkdirSync(folder, { recursive: true });
    const paths = ['src/features/chat/ChatPage.tsx', 'src/features/chat/ChatCache.test.tsx', '../evals/interaction/cycle-11/history-contract.json'];
    for (const p of ['src/features/chat/useChatHistory.ts', 'src/lib/conversation.ts']) if (existsSync(p)) paths.push(p);
    writeFileSync(join(folder, 'cache.json'), JSON.stringify({ scope: 'Actual ChatPage and QueryClient, fixed40 controlled fetch/SSE turns, next task after unmount; not a complete heap diagnosis',
      head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
      sourceSha256: Object.fromEntries(paths.map(p => [p, createHash('sha256').update(readFileSync(p)).digest('hex')])),
      turns: count, ...observed }, null, 2) + '\n', { flag: 'wx' });
  }
  client.clear();
  expect(count).toBe(40); expect(observed.afterUnmountMutations).toBe(0); expect(observed.retainedSensitiveReplies).toBe(0);
}, 0);
