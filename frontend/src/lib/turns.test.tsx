import { streamTurn } from "./turns";

const input = { request_id: "turn_request_unique_12345678", text: "你好", use_web: false };
beforeEach(() => sessionStorage.setItem("avatar-token", "unit-session-token-123456"));
afterEach(() => vi.unstubAllGlobals());
it("decodes split UTF-8 SSE events, retaining the token in headers", async () => {
  const wire = new TextEncoder().encode('event: text\r\ndata: {"text":"你好。"}\r\n\r\nevent: result\r\ndata: {"reply":"最终回复。"}\r\n\r\n');
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ data: { job_id: input.request_id } }) })
    .mockResolvedValueOnce({ ok: true, body: new ReadableStream({ start(controller) {
      for (let i = 0; i < wire.length; i += 2) controller.enqueue(wire.slice(i, i + 2));
      controller.close();
    } }) });
  vi.stubGlobal('fetch', fetch);
  const text = vi.fn();
  const result = await streamTurn(input, new AbortController().signal, text);
  expect(text).toHaveBeenCalledWith('你好。');
  expect(result.reply).toBe('最终回复。');
  expect(fetch.mock.calls[1][0]).not.toContain('token');
  expect(fetch.mock.calls[1][1].headers['X-Avatar-Token']).toBe('unit-session-token-123456');
});
it("does not silently accept a stream without a terminal result or replay the request", async () => {
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ data: { job_id: input.request_id } }) })
    .mockResolvedValueOnce({ ok: true, body: new ReadableStream({ start(controller) { controller.close(); } }) })
    .mockResolvedValue({ ok: true, json: async () => ({ data: {} }) });
  vi.stubGlobal('fetch', fetch);
  await expect(streamTurn(input, new AbortController().signal, vi.fn())).rejects.toThrow('不会自动重复发送');
  expect(fetch.mock.calls.filter(call => call[0] === '/api/v1/turns')).toHaveLength(1);
  expect(fetch.mock.calls[2][0]).toBe('/api/v1/turns/' + input.request_id + '/cancel');
});
