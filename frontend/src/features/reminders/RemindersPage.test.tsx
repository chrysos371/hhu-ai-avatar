import { screen, fireEvent } from "@testing-library/react";
import { renderPage, response, draftFixture } from "../../test/render";
import { RemindersPage } from "./RemindersPage";
afterEach(() => vi.unstubAllGlobals());
it("reminder completion generates a draft instead of mutating immediately", async () => {
  const f = vi.fn(async (path: string) =>
    response(
      path.includes("status-draft")
        ? draftFixture("memory.batch")
        : path.endsWith("/due")
          ? []
          : [
              {
                id: 1,
                title: "答辩",
                due_at: 4000000000,
                created_at: 1,
                status: "active",
                notified_at: null,
              },
            ],
    ),
  );
  vi.stubGlobal("fetch", f);
  renderPage(<RemindersPage />);
  await screen.findByRole("button", { name: "完成 #1" });
  fireEvent.click(screen.getByRole("button", { name: "完成 #1" }));
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  expect(f.mock.calls.some(([p]) => p.includes("/confirm"))).toBe(false);
});
