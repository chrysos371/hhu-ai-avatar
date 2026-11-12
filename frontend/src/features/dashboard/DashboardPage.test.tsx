import { act, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DashboardPage } from "./DashboardPage";
import { MemoryRouter } from "react-router-dom";
import { renderPage, response } from "../../test/render";
import { stateVersion } from "../../test/stateVersion";
afterEach(() => vi.unstubAllGlobals());

function dashboard(context = { instance_id: 'unit-state', revision: 0 }) {
  return { context, counts: { memories: 7, knowledge_sources: 2 }, persona_version: 1,
    emotion: { valence: .05, arousal: -.2, label: '旧角色状态' }, energy: .55,
    verification_rate: null, verification_reason: '没有独立评分',
    recent_events: [{ timestamp: 1, strategy: 'old-private-event', route: 'normal', valence: .05, arousal: -.2 }], audit: [] };
}

it('removes old counts, affect and events before a newer-version response is available', async () => {
  const version = stateVersion();
  let hold = false, release!: (value: ReturnType<typeof response>) => void;
  const held = new Promise<ReturnType<typeof response>>(resolve => { release = resolve; });
  vi.stubGlobal('fetch', vi.fn((path: string, options?: RequestInit) => version.handle(path, options)
    ?? (hold ? held : Promise.resolve(response(dashboard(version.current))))));
  renderPage(<DashboardPage />);
  await screen.findByText('old-private-event');
  await waitFor(() => expect(version.pending).toBe(1));
  hold = true;
  act(() => version.advance({ ...version.current, revision: 1 }));
  await waitFor(() => expect(screen.queryByText('old-private-event')).not.toBeInTheDocument());
  expect(screen.queryByText('旧角色状态')).not.toBeInTheDocument();
  expect(screen.queryByText('7')).not.toBeInTheDocument();
  await act(async () => release(response({ ...dashboard(version.current), counts: { memories: 0 },
    emotion: { valence: 0, arousal: 0, label: '新角色状态' }, recent_events: [] })));
  expect(await screen.findByText('新角色状态')).toBeInTheDocument();
  expect(screen.queryByText('old-private-event')).not.toBeInTheDocument();
});

it('hides existing data on a real metadata transport failure', async () => {
  const version = stateVersion();
  vi.stubGlobal('fetch', vi.fn((path: string, options?: RequestInit) => version.handle(path, options)
    ?? Promise.resolve(response(dashboard(version.current)))));
  renderPage(<DashboardPage />);
  await screen.findByText('old-private-event');
  await waitFor(() => expect(version.pending).toBe(1));
  act(() => version.fail(new Error('controlled metadata offline')));
  expect(await screen.findByRole('alert')).toHaveTextContent('已暂停旧状态');
  expect(screen.queryByText('old-private-event')).not.toBeInTheDocument();
  expect(screen.queryByText('7')).not.toBeInTheDocument();
});
it("uses actual counts and leaves missing verification metrics unavailable", async () => {
  sessionStorage.setItem("avatar-token", "unit-session-token-123456");
  const version = stateVersion();
  vi.stubGlobal("fetch", vi.fn((path: string, options?: RequestInit) => version.handle(path, options)
    ?? Promise.resolve(response({ context: version.current,
      counts: { memories: 7, knowledge_sources: 2, audit_events: 3 },
      persona_version: 4, emotion: { valence: 0, arousal: 0, label: "中性" },
      energy: 0.5, verification_rate: null, verification_reason: "没有独立评分",
      recent_events: [], audit: [],
    }))));
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
