import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiRequest, fetchSpeechAudio } from "../../lib/api";
import type { ChatResult, LipFrame, SpeechResult } from "../../lib/types";
import { splitSpeechText } from "./segmentation";

export function frameAt(frames: LipFrame[], time: number): LipFrame | null {
  let lo = 0, hi = frames.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    if (frames[mid].time <= time) { found = mid; lo = mid + 1; }
    else hi = mid - 1;
  }
  return found < 0 || time - frames[found].time > 0.05 ? null : frames[found];
}

function delay(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException("已停止", "AbortError")); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, 100);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
  });
}

export function useSpeechPlayer() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const request = useRef<AbortController | null>(null);
  const activeRequests = useRef(new Set<string>());
  const objectUrl = useRef<string | null>(null);
  const generation = useRef(0);
  const frames = useRef<LipFrame[]>([]);
  const nextPart = useRef<(() => void) | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [mouth, setMouth] = useState<LipFrame | null>(null);
  const [segment, setSegment] = useState({ index: 0, total: 0 });

  const release = useCallback(() => {
    generation.current++;
    request.current?.abort();
    request.current = null;
    for (const id of activeRequests.current) {
      void apiRequest("/speech/cancel", { method: "POST", body: { request_id: id }, keepalive: true }).catch(() => {});
    }
    activeRequests.current.clear();
    nextPart.current = null;
    if (audioRef.current?.hasAttribute("src")) {
      audioRef.current.pause();
      audioRef.current.removeAttribute("src");
      audioRef.current.load();
    }
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = null;
    frames.current = [];
  }, []);
  const stop = useCallback(() => {
    release();
    setStatus("idle"); setActive(null); setMouth(null);
    setWarning(null); setError(null); setSegment({ index: 0, total: 0 });
  }, [release]);
  useEffect(() => {
    const audio = audioRef.current;
    return () => {
      release();
      if (audio?.hasAttribute("src")) { audio.pause(); audio.removeAttribute("src"); audio.load(); }
    };
  }, [release]);
  useEffect(() => {
    if (status !== "playing") return;
    let raf = 0;
    const tick = () => {
      const audio = audioRef.current;
      setMouth(audio && !audio.paused && !audio.ended ? frameAt(frames.current, audio.currentTime) : null);
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [status]);

  async function play(index: number, result: ChatResult, segmented = false) {
    stop();
    const current = generation.current;
    const controller = new AbortController();
    request.current = controller;
    setActive(index); setStatus("loading");
    const parts = segmented ? splitSpeechText(result.reply) : [result.reply];
    type Prepared = { speech: SpeechResult; blob: Blob };
    type Outcome = { value: Prepared; error?: never } | { error: unknown; value?: never };
    async function prepare(text: string): Promise<Prepared> {
      const id = crypto.randomUUID();
      activeRequests.current.add(id);
      try {
        let speech: SpeechResult | undefined;
        for (let attempt = 0; attempt < 6; attempt++) {
          if (controller.signal.aborted) throw new DOMException("已停止", "AbortError");
          try {
            speech = await apiRequest<SpeechResult>("/speech", { method: "POST", signal: controller.signal,
              body: { request_id: id, text, rate: result.speech_rate ?? "+0%", pitch: result.speech_pitch ?? "+0Hz", mouth_intensity: result.mouth_intensity ?? 0.75 } });
            break;
          } catch (err) {
            if (!(err instanceof ApiError) || err.status !== 429 || attempt === 5) throw err;
            await delay(controller.signal);
          }
        }
        if (!speech) throw new Error("语音未生成。");
        if (controller.signal.aborted) throw new DOMException("已停止", "AbortError");
        const blob = await fetchSpeechAudio(speech.audio_id, controller.signal);
        return { speech, blob };
      } finally { activeRequests.current.delete(id); }
    }
    function failed(err: unknown) {
      if (current !== generation.current) return;
      release(); setMouth(null); setStatus("error");
      setError(err instanceof Error ? err.message : "语音暂不可用，请重试。");
    }
    async function startPart(position: number, prepared?: Promise<Outcome>) {
      try {
        const outcome = prepared ? await prepared : { value: await prepare(parts[position]) };
        if (outcome.error !== undefined) throw outcome.error;
        if (!outcome.value || current !== generation.current || !audioRef.current) return;
        const { speech, blob } = outcome.value;
        if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
        frames.current = speech.frames;
        setWarning(speech.warning); setSegment({ index: position + 1, total: parts.length });
        objectUrl.current = URL.createObjectURL(blob);
        audioRef.current.src = objectUrl.current;
        // Only one upcoming segment is prepared while the current one plays.
        if (position + 1 < parts.length) {
          const upcoming = prepare(parts[position + 1]).then(value => ({ value }), error => ({ error }));
          nextPart.current = () => { setStatus("loading"); void startPart(position + 1, upcoming); };
        } else nextPart.current = null;
        setStatus("ready");
        try { await audioRef.current.play(); }
        catch {
          if (current === generation.current) { setStatus("paused"); setWarning("语音已准备好，请点击播放器的播放按钮。"); }
        }
      } catch (err) { failed(err); }
    }
    await startPart(0);
  }
  return { audioRef, active, status, error, warning, mouth, segment, play, stop,
    onPlay: () => setStatus("playing"),
    onPause: () => { if (audioRef.current?.hasAttribute("src")) { setMouth(null); setStatus("paused"); } },
    onEnded: () => { setMouth(null); const next = nextPart.current; nextPart.current = null; if (next) next(); else setStatus("ended"); },
    onError: () => { if (audioRef.current?.hasAttribute("src")) failedPlayback(); },
  };
  function failedPlayback() {
    release(); setMouth(null); setStatus("error"); setError("音频无法播放，请重新生成。");
  }
}
