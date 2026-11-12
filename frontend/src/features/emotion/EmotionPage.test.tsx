import { act, screen, fireEvent, waitFor } from "@testing-library/react";
import { renderPage, response, draftFixture } from "../../test/render";
import { EmotionPage } from "./EmotionPage";
import { stateVersion } from "../../test/stateVersion";
import type { EmotionInfo } from "../../lib/types";
afterEach(() => vi.unstubAllGlobals());

function emotion(context = { instance_id: 'unit-state', revision: 0 }): EmotionInfo {
  return { context, automatic: { valence: .1, arousal: .2 }, effective: { valence: .1, arousal: .2 },
    user_observation: { valence: -.4, arousal: .3 }, override: null, recent_observations: [] };
}

function neutral(context = { instance_id: 'unit-state', revision: 1 }): EmotionInfo {
  return { ...emotion(context), automatic: { valence: 0, arousal: 0 }, effective: { valence: 0, arousal: 0 },
    user_observation: { valence: 0, arousal: 0 } };
}

it('invalidates both unedited automatic prefill values on a privacy revision change', async () => {
  const version = stateVersion();
  let value = emotion(version.current);
  vi.stubGlobal('fetch', vi.fn((path: string, options?: RequestInit) => version.handle(path, options)
    ?? Promise.resolve(response(value))));
  renderPage(<EmotionPage />);
  await waitFor(() => expect(screen.getByLabelText(/愉悦度 P/)).toHaveValue('0.1'));
  expect(screen.getByLabelText(/唤醒度 A/)).toHaveValue('0.2');
  value = neutral();
  act(() => version.advance(value.context));
  await waitFor(() => expect(screen.getByLabelText(/愉悦度 P/)).toHaveValue('0'));
  expect(screen.getByLabelText(/唤醒度 A/)).toHaveValue('0');
  expect(screen.queryByText(/P -0.40/)).not.toBeInTheDocument();
});

it('preserves only truly edited expression fields, duration and reason while clearing automatic prefill', async () => {
  const version = stateVersion();
  let value = emotion(version.current);
  vi.stubGlobal('fetch', vi.fn((path: string, options?: RequestInit) => version.handle(path, options)
    ?? Promise.resolve(response(value))));
  renderPage(<EmotionPage />);
  await waitFor(() => expect(screen.getByLabelText(/愉悦度 P/)).toHaveValue('0.1'));
  fireEvent.change(screen.getByLabelText(/愉悦度 P/), { target: { value: '.8' } });
  fireEvent.change(screen.getByLabelText(/持续秒数/), { target: { value: '900' } });
  fireEvent.change(screen.getByLabelText('干预原因'), { target: { value: '明确的手工草稿' } });
  value = neutral();
  act(() => version.advance(value.context));
  await waitFor(() => expect(screen.getByLabelText(/唤醒度 A/)).toHaveValue('0'));
  expect(screen.getByLabelText(/愉悦度 P/)).toHaveValue('0.8');
  expect(screen.getByLabelText(/持续秒数/)).toHaveValue(900);
  expect(screen.getByLabelText('干预原因')).toHaveValue('明确的手工草稿');
});

it('keeps a confirmed manual override while automatic values and observations are cleared', async () => {
  const version = stateVersion();
  const override = { id: 7, data: { valence: .6, arousal: -.1, reason: '人工覆盖' }, starts_at: 1,
    expires_at: Date.now() / 1000 + 300 };
  let value: EmotionInfo = { ...emotion(version.current), override, effective: { valence: .6, arousal: -.1 } };
  vi.stubGlobal('fetch', vi.fn((path: string, options?: RequestInit) => version.handle(path, options)
    ?? Promise.resolve(response(value))));
  renderPage(<EmotionPage />);
  await waitFor(() => expect(screen.getByLabelText(/愉悦度 P/)).toHaveValue('0.6'));
  value = { ...neutral(), override, effective: { valence: .6, arousal: -.1 } };
  act(() => version.advance(value.context));
  await waitFor(() => expect(screen.getAllByText(/P 0.00 \/ A 0.00/)).toHaveLength(2));
  expect(screen.getByText('当前存在已确认覆盖')).toBeInTheDocument();
  expect(screen.getByLabelText(/愉悦度 P/)).toHaveValue('0.6');
  expect(screen.getByLabelText(/唤醒度 A/)).toHaveValue('-0.1');
});

it('treats an explicitly edited zero as manual rather than a missing value', async () => {
  const version = stateVersion();
  let value = emotion(version.current);
  vi.stubGlobal('fetch', vi.fn((path: string, options?: RequestInit) => version.handle(path, options)
    ?? Promise.resolve(response(value))));
  renderPage(<EmotionPage />);
  await waitFor(() => expect(screen.getByLabelText(/愉悦度 P/)).toHaveValue('0.1'));
  fireEvent.change(screen.getByLabelText(/愉悦度 P/), { target: { value: '0' } });
  value = { ...neutral(), effective: { valence: .6, arousal: .4 }, override: {
    id: 8, data: { valence: .6, arousal: .4, reason: '另一已确认人工表达' }, starts_at: 1,
    expires_at: Date.now() / 1000 + 300 } };
  act(() => version.advance(value.context));
  await waitFor(() => expect(screen.getByLabelText(/唤醒度 A/)).toHaveValue('0.4'));
  expect(screen.getByLabelText(/愉悦度 P/)).toHaveValue('0');
});

it('does not refill cleared fields from an old response which ignores abort', async () => {
  const version = stateVersion();
  let release!: (value: ReturnType<typeof response>) => void;
  const old = new Promise<ReturnType<typeof response>>(resolve => { release = resolve; });
  let reads = 0, originalSignal: AbortSignal | null | undefined;
  vi.stubGlobal('fetch', vi.fn((path: string, options?: RequestInit) => {
    const metadata = version.handle(path, options);
    if (metadata) return metadata;
    if (++reads === 1) { originalSignal = options?.signal; return old; }
    return Promise.resolve(response(neutral(version.current)));
  }));
  renderPage(<EmotionPage />);
  await waitFor(() => expect(reads).toBe(1));
  act(() => version.advance({ ...version.current, revision: 1 }));
  await waitFor(() => expect(screen.getByLabelText(/愉悦度 P/)).toHaveValue('0'));
  expect(originalSignal?.aborted).toBe(true);
  await act(async () => release(response(emotion())));
  expect(screen.getByLabelText(/愉悦度 P/)).toHaveValue('0');
  expect(screen.getByLabelText(/唤醒度 A/)).toHaveValue('0');
  expect(screen.queryByText(/P -0.40/)).not.toBeInTheDocument();
});
it("keeps automatic/effective views distinct and requires a preview", async () => {
  const version = stateVersion();
  const f = vi.fn((path: string, options?: RequestInit) => version.handle(path, options)
    ?? Promise.resolve(response(path.endsWith("/draft") ? draftFixture("emotion.override") : emotion(version.current))));
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
