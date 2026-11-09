import { screen, fireEvent } from "@testing-library/react";
import {
  renderPage,
  response,
  personaFixture,
  draftFixture,
} from "../../test/render";
import { PersonaPage } from "./PersonaPage";
afterEach(() => vi.unstubAllGlobals());
it("manual edits produce a field-level draft and never auto-confirm", async () => {
  const f = vi.fn(async (path: string) =>
    response(
      path.endsWith("/history")
        ? [personaFixture]
        : path.endsWith("/draft")
          ? draftFixture()
          : personaFixture,
    ),
  );
  vi.stubGlobal("fetch", f);
  renderPage(<PersonaPage />);
  await screen.findByDisplayValue("小海");
  fireEvent.change(screen.getByLabelText("角色名称"), {
    target: { value: "星澜" },
  });
  fireEvent.click(screen.getByRole("button", { name: "生成人设草案" }));
  expect(await screen.findByRole("dialog")).toHaveTextContent("星澜");
  expect(f.mock.calls.some(([p]) => p.includes("/confirm"))).toBe(false);
});
