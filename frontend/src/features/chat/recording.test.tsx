import { startRecording } from "./recording";

let stopped: ReturnType<typeof vi.fn>;
let node: { disconnect: ReturnType<typeof vi.fn>; port: {
  onmessage: ((event: { data: Float32Array | string }) => void) | null;
  postMessage: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn>;
} };
let closed: ReturnType<typeof vi.fn>;
beforeEach(() => {
  stopped = vi.fn(); closed = vi.fn();
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopped }] }) } });
  const gain = { gain: { value: 1 }, connect: vi.fn() };
  vi.stubGlobal("AudioContext", class {
    sampleRate = 48000; state = "running"; destination = {};
    audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };
    createMediaStreamSource() { return { connect: () => ({ connect: () => gain }) }; }
    createGain() { return gain; }
    resume() { return Promise.resolve(); }
    close() { this.state = "closed"; closed(); return Promise.resolve(); }
  });
  vi.stubGlobal("AudioWorkletNode", class {
    disconnect = vi.fn();
    port = { onmessage: null, postMessage: vi.fn(), close: vi.fn() };
    constructor() { node = { port: this.port, disconnect: this.disconnect }; }
  });
});
afterEach(() => vi.unstubAllGlobals());
function send(data: Float32Array | string) { node.port.onmessage?.({ data }); }
function voice(ms: number) {
  return Float32Array.from({ length: 48 * ms }, (_, i) => .04 * Math.sin(2 * Math.PI * 220 * i / 48000));
}
it("ends on a pause, preserves the onset and releases the microphone before callback", async () => {
  const callback = vi.fn(() => expect(stopped).toHaveBeenCalledOnce());
  const handle = await startRecording(new AbortController().signal, callback);
  send(voice(1000)); send(new Float32Array(48 * 1400));
  expect(callback).toHaveBeenCalledOnce();
  expect(callback.mock.calls[0]).toEqual([expect.objectContaining({ size: 44 + 48000 * 2200 / 1000 * 2 }), "pause"]);
  expect(handle.finished).toBe(true);
  expect(closed).toHaveBeenCalledOnce(); expect(node.port.close).toHaveBeenCalledOnce();
  send(voice(1000)); handle.stop();
  expect(callback).toHaveBeenCalledOnce();
});
it("reports no speech after eight seconds so the caller can avoid transcription", async () => {
  const callback = vi.fn();
  await startRecording(new AbortController().signal, callback);
  send(new Float32Array(48000 * 9));
  expect(callback).toHaveBeenCalledWith(expect.any(Blob), "no_speech");
  expect(stopped).toHaveBeenCalledOnce();
});
it("abort releases resources and prevents any late completion", async () => {
  const callback = vi.fn(); const controller = new AbortController();
  await startRecording(controller.signal, callback);
  const late = node.port.onmessage!;
  controller.abort(); late({ data: voice(1000) }); late({ data: "done" });
  expect(callback).not.toHaveBeenCalled(); expect(stopped).toHaveBeenCalledOnce();
  expect(closed).toHaveBeenCalledOnce();
});
it("allows opting out and flushes a manual stop", async () => {
  const callback = vi.fn();
  const handle = await startRecording(new AbortController().signal, callback, false);
  send(new Float32Array(48000 * 9)); expect(callback).not.toHaveBeenCalled();
  handle.stop(); send(voice(100)); send("done");
  expect(callback).toHaveBeenCalledWith(expect.any(Blob), "manual");
});
it("releases a microphone granted after cancellation", async () => {
  let grant!: (value: unknown) => void;
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: () => new Promise(resolve => { grant = resolve; }) } });
  const controller = new AbortController();
  const pending = startRecording(controller.signal, vi.fn());
  controller.abort(); grant({ getTracks: () => [{ stop: stopped }] });
  await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  expect(stopped).toHaveBeenCalledOnce();
});
