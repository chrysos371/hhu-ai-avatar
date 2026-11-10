import { screen } from "@testing-library/react";
import { renderPage, response } from "../../test/render";
import { ToolsPage } from "./ToolsPage";
afterEach(() => vi.unstubAllGlobals());
it("an unavailable optional model does not hide working services", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      response([
        { name: "SQLite", configured: true, available: true, last_error: null },
        {
          name: "本地管理模型",
          configured: true,
          available: false,
          last_error: "本地服务暂不可用",
        },
      ]),
    ),
  );
  renderPage(<ToolsPage />);
  expect(await screen.findByText("SQLite")).toBeInTheDocument();
  expect(screen.getByText("本地服务暂不可用")).toBeInTheDocument();
});
