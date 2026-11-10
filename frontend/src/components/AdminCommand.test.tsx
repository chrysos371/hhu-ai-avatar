import { screen, fireEvent, waitFor } from "@testing-library/react";
import { AdminCommandForm } from "./AdminCommand";
import { renderPage, response, draftFixture } from "../test/render";
afterEach(() => vi.unstubAllGlobals());
it("defaults to local and resets cloud permission after a single proposal", async () => {
  const fetcher = vi.fn(async (path: string, options: { body: string }) => {
    void path;
    void options;
    return response(draftFixture());
  });
  vi.stubGlobal("fetch", fetcher);
  const onDraft = vi.fn();
  renderPage(<AdminCommandForm onDraft={onDraft} />);
  fireEvent.change(screen.getByLabelText("管理要求"), {
    target: { value: "表达温和一点" },
  });
  const cloud = screen.getByLabelText("仅本次请求明确使用已配置的云端模型");
  expect(cloud).not.toBeChecked();
  fireEvent.click(cloud);
  fireEvent.click(screen.getByRole("button", { name: "生成管理草案" }));
  await waitFor(() => expect(onDraft).toHaveBeenCalledOnce());
  expect(JSON.parse(fetcher.mock.calls[0][1].body).allow_cloud).toBe(true);
  expect(cloud).not.toBeChecked();
  expect(fetcher.mock.calls[0][0]).toBe("/api/v1/admin-agent/draft");
});
