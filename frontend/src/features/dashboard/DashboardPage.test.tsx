import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DashboardPage } from "./DashboardPage";
import { MemoryRouter } from "react-router-dom";
afterEach(() => vi.unstubAllGlobals());
it("uses actual counts and leaves missing verification metrics unavailable", async () => {
  sessionStorage.setItem("avatar-token", "unit-session-token-123456");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        data: {
          counts: { memories: 7, knowledge_sources: 2, audit_events: 3 },
          persona_version: 4,
          emotion: { valence: 0, arousal: 0, label: "中性" },
          energy: 0.5,
          verification_rate: null,
          verification_reason: "没有独立评分",
          recent_events: [],
          audit: [],
        },
        error: null,
      }),
    }),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("7")).toBeInTheDocument();
  expect(screen.getByText("没有独立评分")).toBeInTheDocument();
  expect(screen.queryByText("100%")).not.toBeInTheDocument();
});
it("shows a read error instead of inventing zero metrics", async () => {
  sessionStorage.setItem("avatar-token", "unit-session-token-123456");
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("服务不可用")));
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("服务不可用");
  expect(screen.queryByText("0")).not.toBeInTheDocument();
});

it("shows patrol signals without claiming semantic approval", async () => {
  sessionStorage.setItem("avatar-token", "unit-session-token-123456");
  vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => ({
    ok: true, status: 200, json: async () => ({data: url.endsWith("/improvement") ? {
      available:true, automatic_release:false,
      runs:[{id:"test-run", status:"completed", turns:6}],
      issues:[{id:"signal-1",category:"possible_physical_invitation",occurrences:2}],
    } : {
      counts:{memories:0,knowledge_sources:0,audit_events:0},persona_version:1,
      emotion:{valence:0,arousal:0,label:"中性"},energy:0.5,
      verification_rate:null,verification_reason:"没有独立评分",recent_events:[],audit:[],
    },error:null}),
  })));
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>
    <MemoryRouter><DashboardPage/></MemoryRouter>
  </QueryClientProvider>);
  expect(await screen.findByText("疑似线下邀请：2次待定位信号")).toBeInTheDocument();
  expect(screen.getByText(/不会自动训练或发布/)).toBeInTheDocument();
  expect(screen.queryByText("100%")).not.toBeInTheDocument();
});
