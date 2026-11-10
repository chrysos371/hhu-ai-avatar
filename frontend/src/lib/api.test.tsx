import { apiRequest, readToken } from "./api";
afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});
it("moves token out of the URL into this session and refuses requests without it", async () => {
  window.history.replaceState(null, "", "/#unit-session-token-1234567");
  expect(readToken()).toBe("unit-session-token-1234567");
  expect(window.location.hash).toBe("");
  sessionStorage.clear();
  const f = vi.fn();
  vi.stubGlobal("fetch", f);
  await expect(apiRequest("/system")).rejects.toMatchObject({
    code: "missing_token",
  });
  expect(f).not.toHaveBeenCalled();
});
