import { screen, fireEvent } from "@testing-library/react";
import { renderPage, response, draftFixture } from "../../test/render";
import { EmotionPage } from "./EmotionPage";
afterEach(() => vi.unstubAllGlobals());
it("keeps automatic/effective views distinct and requires a preview", async () => {
  const f = vi.fn(async (path: string) =>
    response(
      path.endsWith("/draft")
        ? draftFixture("emotion.override")
        : {
            automatic: { valence: 0.1, arousal: 0.2 },
            effective: { valence: 0.1, arousal: 0.2 },
            user_observation: { valence: 0, arousal: 0 },
            override: null,
            recent_observations: [],
          },
    ),
  );
  vi.stubGlobal("fetch", f);
  renderPage(<EmotionPage />);
  await screen.findByText("自动状态");
  expect(screen.getByText("实际表达")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("干预原因"), {
    target: { value: "演示" },
  });
  fireEvent.click(screen.getByRole("button", { name: "生成情绪草案" }));
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  expect(f.mock.calls.some(([p]) => p.includes("/confirm"))).toBe(false);
});
