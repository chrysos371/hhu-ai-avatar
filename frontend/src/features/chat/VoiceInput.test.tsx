import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VoiceInput } from "./VoiceInput";
import { encodeWav } from "./recording";

function setup() {
  const onTranscript = vi.fn();
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <VoiceInput disabled={false} beforeCapture={vi.fn()} onTranscript={onTranscript} onBusyChange={vi.fn()} />
  </QueryClientProvider>);
  return onTranscript;
}
beforeEach(() => sessionStorage.setItem("avatar-token", "unit-session-token-123456"));
afterEach(() => vi.unstubAllGlobals());
it("encodes mono 16-bit PCM including clipped samples and correct sample rate", async () => {
  const blob = encodeWav([new Float32Array([-2, -0.5, 0, 0.5, 2])], 48000);
  const buffer = await new Promise<ArrayBuffer>(resolve => {
    const reader = new FileReader(); reader.onload = () => resolve(reader.result as ArrayBuffer); reader.readAsArrayBuffer(blob);
  });
  const view = new DataView(buffer);
  expect(blob.type).toBe("audio/wav");
  expect(view.getUint32(24, true)).toBe(48000);
  expect(view.getUint16(22, true)).toBe(1);
  expect(view.getUint16(34, true)).toBe(16);
  expect(view.getUint32(40, true)).toBe(10);
  expect(view.getInt16(44, true)).toBe(-32768);
  expect(view.getInt16(52, true)).toBe(32767);
});
it("leaves microphone disabled when the local recognizer is not configured", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ data: { asr_enabled: false, reason: "未配置本机模型" } }) }));
  setup();
  await screen.findByText("未配置本机模型");
  expect(screen.getByRole("button", { name: "麦克风输入" })).toBeDisabled();
});
it("fills the draft through a callback without sending a chat request", async () => {
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ data: { asr_enabled: true } }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ data: { transcript: "识别结果" } }) });
  vi.stubGlobal("fetch", fetch);
  const transcript = setup();
  const input = screen.getByLabelText("上传 WAV 语音");
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { files: [new File(["wave"], "recording.wav")] } });
  await waitFor(() => expect(transcript).toHaveBeenCalledWith("识别结果"));
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch.mock.calls[1][0]).toBe("/api/v1/speech/transcribe");
});
it("ignores a late transcript after cancellation", async () => {
  let finish!: (value: unknown) => void;
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ data: { asr_enabled: true } }) })
    .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  vi.stubGlobal("fetch", fetch);
  const transcript = setup();
  const input = screen.getByLabelText("上传 WAV 语音");
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { files: [new File(["wave"], "recording.wav")] } });
  fireEvent.click(await screen.findByRole("button", { name: "取消语音输入" }));
  await act(async () => finish({ ok: true, json: async () => ({ data: { transcript: "迟到结果" } }) }));
  expect(transcript).not.toHaveBeenCalled();
});
