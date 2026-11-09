import { screen, fireEvent } from "@testing-library/react";
import { renderPage, response, draftFixture } from "../../test/render";
import { MemoryPage } from "./MemoryPage";
afterEach(() => vi.unstubAllGlobals());
it("shows source text safely and previews memory correction", async () => {
  const row = {
    id: 1,
    content: "喜欢游泳",
    memory_type: "preference",
    status: "active",
    created_at: 1,
    confirmation_status: "source_backed",
    sources: [
      {
        id: 1,
        evidence: "<img src=x onerror=alert(1)>",
        message_content: "原话",
        created_at: 1,
      },
    ],
  };
  const f = vi.fn(async (path: string) =>
    response(
      path.endsWith("/batch-draft")
        ? draftFixture("memory.batch", [
            { field: "memory.1", before: "喜欢游泳", after: "喜欢看书" },
          ])
        : path.endsWith("/summary")
          ? { items: [], characters: 2, max_characters: 1600 }
          : path.endsWith("/memory/1")
            ? row
            : [row],
    ),
  );
  vi.stubGlobal("fetch", f);
  renderPage(<MemoryPage />);
  await screen.findByText("喜欢游泳");
  fireEvent.click(screen.getByRole("button", { name: "来源 #1" }));
  expect(
    await screen.findByText("<img src=x onerror=alert(1)>"),
  ).toBeInTheDocument();
  expect(document.querySelector("img")).toBeNull();
  fireEvent.change(screen.getByLabelText("记忆纠正内容"), {
    target: { value: "喜欢看书" },
  });
  fireEvent.click(screen.getByRole("button", { name: "生成纠错草案" }));
  expect(await screen.findByRole("dialog")).toHaveTextContent("喜欢看书");
  expect(f.mock.calls.some(([p]) => p.includes("/confirm"))).toBe(false);
});
