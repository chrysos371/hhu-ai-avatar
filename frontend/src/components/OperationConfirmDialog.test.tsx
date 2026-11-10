import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { OperationConfirmDialog } from "./OperationConfirmDialog";
import type { Draft } from "../lib/types";
const draft: Draft = {
  draft_id: 1,
  operation_type: "persona.update",
  diff: [{ field: "name", before: "旧名字", after: "新名字" }],
  warnings: [],
  expires_at: Date.now() / 1000 + 600,
  confirmation_token: "unit-confirmation-token-123456",
};
function show(d = draft, onClose = vi.fn()) {
  sessionStorage.setItem("avatar-token", "unit-session-token-123456");
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <OperationConfirmDialog draft={d} onClose={onClose} />
    </QueryClientProvider>,
  );
  return onClose;
}
afterEach(() => vi.unstubAllGlobals());
it("shows real diff and performs no confirmation until explicitly clicked", async () => {
  const fetcher = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      data: { audit_id: 1 },
      error: null,
      request_id: "test",
    }),
  });
  vi.stubGlobal("fetch", fetcher);
  show();
  expect(screen.getByText("旧名字")).toBeInTheDocument();
  expect(screen.getByText("新名字")).toBeInTheDocument();
  expect(fetcher).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认执行" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  expect(fetcher.mock.calls[0][0]).toBe("/api/v1/operations/1/confirm");
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
    confirmation_token: draft.confirmation_token,
  });
});
it("cancel closes without executing a mutation", () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const close = show();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(close).toHaveBeenCalledOnce();
  expect(fetcher).not.toHaveBeenCalled();
});
it("expired drafts and unacknowledged dangerous changes cannot execute", () => {
  show({ ...draft, expires_at: Date.now() / 1000 - 1 });
  expect(screen.getByRole("button", { name: "确认执行" })).toBeDisabled();
});
it("stale response disables confirmation and requests a new preview", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({
        data: null,
        error: { code: "stale_draft", message: "基线已变化，请重新预览" },
        request_id: "test",
      }),
    }),
  );
  show();
  fireEvent.click(screen.getByRole("button", { name: "确认执行" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("基线已变化");
  expect(screen.getByRole("button", { name: "确认执行" })).toBeDisabled();
});
it("requires a separate acknowledgement for irreversible deletion", () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  show({ ...draft, warnings: ["彻底删除不可撤销。"] });
  const confirm = screen.getByRole("button", { name: "确认执行" });
  expect(confirm).toBeDisabled();
  fireEvent.click(confirm);
  expect(fetcher).not.toHaveBeenCalled();
  fireEvent.click(screen.getByLabelText("我理解此操作不可撤销"));
  expect(confirm).toBeEnabled();
});
