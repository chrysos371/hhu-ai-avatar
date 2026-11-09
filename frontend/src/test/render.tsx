import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
export function renderPage(page: ReactNode) {
  sessionStorage.setItem("avatar-token", "unit-session-token-123456");
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter>{page}</MemoryRouter>
    </QueryClientProvider>,
  );
}
export function response(data: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ data, error: null, request_id: "unit-test" }),
  };
}
export const personaFixture = {
  id: 1,
  parent_id: null,
  created_at: 1,
  data: {
    name: "小海",
    core_identity: "伙伴",
    expression_principles: "自然表达",
    relationship_boundaries: "支持现实关系",
    immutable_rules: "不编造事实",
    temperature_bias: 0,
    initiative: 0.5,
  },
};
export function draftFixture(
  operation_type = "persona.update",
  diff: unknown[] = [{ field: "name", before: "小海", after: "星澜" }],
) {
  return {
    draft_id: 1,
    operation_type,
    diff,
    warnings: [],
    expires_at: Date.now() / 1000 + 600,
    confirmation_token: "unit-confirm-token-123456789",
  };
}
