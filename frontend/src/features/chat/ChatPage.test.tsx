import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatPage } from "./ChatPage";
afterEach(() => vi.unstubAllGlobals());
it("keeps trace collapsed and disables duplicate sends while pending", async () => {
  sessionStorage.setItem("avatar-token", "unit-session-token-123456");
  let finish!: (x: unknown) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    ),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ChatPage />
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText("消息"), {
    target: { value: "你好" },
  });
  fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
  expect(
    await screen.findByRole("button", { name: "等待回复…" }),
  ).toBeDisabled();
  finish({
    ok: true,
    status: 200,
    json: async () => ({
      data: {
        reply: "你好，我在。",
        emotion: "中性",
        strategy: "answer",
        trace: {
          recalled_memories: [],
          decision: { strategy: "answer" },
          guard: { route: "normal", guarded: false },
          verifier: { available: false, reason: "未配置" },
          tool_calls: [],
        },
      },
      error: null,
    }),
  });
  expect(await screen.findByText("你好，我在。")).toBeInTheDocument();
  expect(
    screen.getByText("本轮决策与来源").closest("details"),
  ).not.toHaveAttribute("open");
});
