import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatPage } from "./ChatPage";
afterEach(() => vi.unstubAllGlobals());
it("streams a reviewed draft then replaces it with the final traced reply", async () => {
  sessionStorage.setItem("avatar-token", "unit-session-token-123456");
  let finish!: (x: unknown) => void;
  const result = { reply: "你好，我在。", emotion: "中性", strategy: "answer", trace: {
    recalled_memories: [], decision: { strategy: "answer" }, guard: { route: "normal", guarded: false },
    verifier: { available: false, reason: "未配置" }, tool_calls: [],
  } };
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (url.endsWith("/capabilities")) return Promise.resolve({ ok: true, json: async () => ({ data: { asr_enabled: false } }) });
    if (url.endsWith("/turns")) return new Promise(resolve => { finish = resolve; });
    const bytes = new TextEncoder().encode('event: text\ndata: {"text":"已检查的草稿。"}\n\nevent: result\ndata: ' + JSON.stringify(result) + '\n\n');
    return Promise.resolve({ ok: true, body: new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } }) });
  }));
  render(<QueryClientProvider client={new QueryClient()}><ChatPage /></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText("消息"), { target: { value: "你好" } });
  fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
  expect(await screen.findByRole("button", { name: "等待回复…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "停止生成" })).toBeEnabled();
  finish({ ok: true, json: async () => ({ data: { job_id: "unit_job_identifier_123456" }, error: null }) });
  expect(await screen.findByText("你好，我在。")).toBeInTheDocument();
  expect(screen.queryByText("已检查的草稿。")).not.toBeInTheDocument();
  expect(screen.getByText("本轮决策与来源").closest("details")).not.toHaveAttribute("open");
});
