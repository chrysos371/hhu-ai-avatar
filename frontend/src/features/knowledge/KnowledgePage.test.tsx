import { screen, fireEvent } from "@testing-library/react";
import { renderPage, response, draftFixture } from "../../test/render";
import { KnowledgePage } from "./KnowledgePage";
afterEach(() => vi.unstubAllGlobals());
it("parses a knowledge preview without importing before confirmation", async () => {
  const f = vi.fn(async (path: string) =>
    response(
      path.endsWith("/sources")
        ? []
        : {
            preview: {
              title: "手册",
              characters: 10,
              accepted: [{ content: "手册正文", sha256: "hash" }],
              rejected: [],
              semantic_status: "unconfigured",
              semantic_chunk_limit: 32,
            },
            draft: draftFixture("knowledge.import"),
          },
    ),
  );
  vi.stubGlobal("fetch", f);
  renderPage(<KnowledgePage />);
  fireEvent.change(screen.getByLabelText("知识标题"), {
    target: { value: "手册" },
  });
  fireEvent.change(screen.getByLabelText("知识正文"), {
    target: { value: "手册正文" },
  });
  fireEvent.click(screen.getByRole("button", { name: "解析并生成预览" }));
  expect(await screen.findByText("手册正文")).toBeInTheDocument();
  expect(f.mock.calls.some(([p]) => p.includes("/confirm"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "检查导入差异" }));
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
});
