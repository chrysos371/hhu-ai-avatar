import { screen, fireEvent } from "@testing-library/react";
import { renderPage, response, draftFixture } from "../../test/render";
import { AuditPage } from "./AuditPage";
afterEach(() => vi.unstubAllGlobals());
it("reverse action creates another preview instead of undoing immediately", async () => {
  const f = vi.fn(async (path: string) =>
    response(
      path.endsWith("/reverse-draft")
        ? draftFixture()
        : [
            {
              id: 1,
              draft_id: 1,
              operation_type: "persona.update",
              actor: "local-admin",
              status: "success",
              before: { id: 1 },
              after: { id: 2 },
              created_at: 1,
              error: null,
            },
          ],
    ),
  );
  vi.stubGlobal("fetch", f);
  renderPage(<AuditPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "生成反向草案 #1" }),
  );
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  expect(f.mock.calls.some(([p]) => p.includes("/confirm"))).toBe(false);
});
