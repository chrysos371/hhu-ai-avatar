import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "./AppShell";
it("renders accessible navigation, local warning and no invented metrics", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({ data: { backend: { available: true } } }),
        ),
    ),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  for (const name of [
    "总览",
    "对话观测",
    "人设管理",
    "情绪干预",
    "记忆中枢",
    "知识与学习",
    "提醒",
    "工具",
    "操作审计",
  ])
    expect(screen.getByRole("link", { name })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "总览" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByText(/单用户.*本机/)).toBeInTheDocument();
  expect(screen.queryByText("99.9%")).not.toBeInTheDocument();
});

afterEach(() => vi.unstubAllGlobals());
