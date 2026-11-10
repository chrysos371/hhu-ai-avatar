import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, fetchSpeechAudio } from "../../lib/api";
import type { ChatResult, LipFrame, SpeechResult } from "../../lib/types";

export function frameAt(frames: LipFrame[], time: number): LipFrame | null {
  let lo = 0, hi = frames.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    if (frames[mid].time <= time) { found = mid; lo = mid + 1; }
    else hi = mid - 1;
  }
  // No extrapolated mouth opening after the analyzed audio ends.
  return found < 0 || time - frames[found].time > 0.05 ? null : frames[found];
}

export function useSpeechPlayer() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const request = useRef<AbortController | null>(null);
  const objectUrl = useRef<string | null>(null);
  const generation = useRef(0);
  const frames = useRef<LipFrame[]>([]);
  const [active, setActive] = useState<number | null>(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [mouth, setMouth] = useState<LipFrame | null>(null);

  const release = useCallback(() => {
    generation.current++;
    request.current?.abort();
    request.current = null;
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
    setStatus("idle");
    setActive(null);
    setMouth(null);
    setWarning(null);
    setError(null);
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

  async function play(index: number, result: ChatResult) {
    stop();
    const current = generation.current;
    const controller = new AbortController();
    request.current = controller;
    setActive(index);
    setStatus("loading");
    try {
      const speech = await apiRequest<SpeechResult>("/speech", {
        method: "POST", signal: controller.signal,
        body: { text: result.reply, rate: result.speech_rate ?? "+0%",
          pitch: result.speech_pitch ?? "+0Hz", mouth_intensity: result.mouth_intensity ?? 0.75 },
      });
      if (current !== generation.current) return;
      const blob = await fetchSpeechAudio(speech.audio_id, controller.signal);
      if (current !== generation.current || !audioRef.current) return;
      frames.current = speech.frames;
      setWarning(speech.warning);
      objectUrl.current = URL.createObjectURL(blob);
      audioRef.current.src = objectUrl.current;
      setStatus("ready");
      try { await audioRef.current.play(); }
      catch {
        if (current === generation.current) {
          setStatus("paused");
          setWarning("语音已准备好，请点击播放器的播放按钮。");
        }
      }
    } catch (err) {
      if (current !== generation.current) return;
      release();
      setMouth(null);
      setStatus("error");
      setError(err instanceof Error ? err.message : "语音暂不可用，请重试。");
    }
  }
  return { audioRef, active, status, error, warning, mouth, play, stop,
    onPlay: () => setStatus("playing"),
    onPause: () => { if (audioRef.current?.hasAttribute("src")) { setMouth(null); setStatus("paused"); } },
    onEnded: () => { setMouth(null); setStatus("ended"); },
    onError: () => { if (audioRef.current?.hasAttribute("src")) { setMouth(null); setStatus("error"); setError("音频无法播放，请重新生成。"); } },
  };
}
