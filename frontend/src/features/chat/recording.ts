import workletUrl from "./pcm-recorder.worklet.js?url";

export function encodeWav(chunks: Float32Array[], sampleRate: number): Blob {
  const count = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + count * 2);
  const view = new DataView(buffer);
  function text(offset: number, value: string) {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  }
  text(0, "RIFF"); view.setUint32(4, 36 + count * 2, true); text(8, "WAVE");
  text(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, "data"); view.setUint32(40, count * 2, true);
  let offset = 44;
  for (const chunk of chunks) for (const value of chunk) {
    const sample = Math.max(-1, Math.min(1, value));
    view.setInt16(offset, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export async function startRecording(signal: AbortSignal, onComplete: (audio: Blob) => void) {
  let stream: MediaStream | null = null;
  let context: AudioContext | null = null;
  let node: AudioWorkletNode | null = null;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const chunks: Float32Array[] = [];
  let count = 0;
  const cancel = () => {
    stopped = true;
    clearTimeout(timer);
    signal.removeEventListener("abort", cancel);
    stream?.getTracks().forEach(track => track.stop());
    node?.disconnect();
    if (context && context.state !== "closed") void context.close().catch(() => {});
  };
  const checkCancelled = () => {
    if (signal.aborted) throw new DOMException("录音已取消", "AbortError");
  };
  const finish = () => {
    if (stopped || !context) return;
    const rate = context.sampleRate;
    cancel();
    onComplete(encodeWav(chunks, rate));
  };
  try {
    checkCancelled();
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true }, video: false });
    checkCancelled();
    signal.addEventListener("abort", cancel, { once: true });
    context = new AudioContext({ sampleRate: 48000 });
    await context.audioWorklet.addModule(workletUrl);
    checkCancelled();
    const source = context.createMediaStreamSource(stream);
    node = new AudioWorkletNode(context, "avatar-pcm-recorder");
    const mute = context.createGain();
    mute.gain.value = 0;
    source.connect(node).connect(mute).connect(context.destination);
    node.port.onmessage = (event: MessageEvent<Float32Array | string>) => {
      if (stopped) return;
      if (event.data === "done") { finish(); return; }
      if (!(event.data instanceof Float32Array)) return;
      const chunk = event.data.subarray(0, Math.max(0, 60 * context!.sampleRate - count));
      chunks.push(chunk);
      count += chunk.length;
      if (count >= 60 * context!.sampleRate) finish();
    };
    await context.resume();
    checkCancelled();
    timer = setTimeout(finish, 60000);
    return { stop: () => { node?.port.postMessage("stop"); clearTimeout(timer); timer = setTimeout(finish, 500); }, cancel };
  } catch (err) { cancel(); throw err; }
}
