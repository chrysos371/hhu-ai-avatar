import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Mic, Square, Upload, X } from "lucide-react";
import { apiRequest, transcribeAudio } from "../../lib/api";
import { startRecording } from "./recording";

export function VoiceInput({ disabled, beforeCapture, onTranscript, onBusyChange }: {
  disabled: boolean; beforeCapture: () => void;
  onTranscript: (text: string) => void; onBusyChange: (busy: boolean) => void;
}) {
  const capabilities = useQuery({ queryKey: ["speech-capabilities"],
    queryFn: () => apiRequest<{ asr_enabled: boolean; reason: string | null }>("/speech/capabilities"), retry: false });
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const recording = useRef<Awaited<ReturnType<typeof startRecording>> | null>(null);
  const serial = useRef(0);
  const busy = status !== "idle";
  const enabled = capabilities.data?.asr_enabled === true;
  useEffect(() => { onBusyChange(busy); }, [busy, onBusyChange]);
  useEffect(() => () => { serial.current++; controller.current?.abort(); recording.current?.cancel(); }, []);
  function cancel() {
    serial.current++;
    controller.current?.abort();
    recording.current?.cancel();
    recording.current = null;
    setStatus("idle");
  }
  async function upload(audio: Blob, current: number, signal: AbortSignal) {
    if (current !== serial.current) return;
    setStatus("transcribing");
    try {
      const result = await transcribeAudio(audio, signal);
      if (current === serial.current) onTranscript(result.transcript);
    } catch (err) {
      if (current === serial.current) setError(err instanceof Error ? err.message : "识别失败，请重试。");
    } finally { if (current === serial.current) setStatus("idle"); }
  }
  async function record() {
    beforeCapture();
    setError(null);
    setStatus("requesting");
    const current = ++serial.current;
    const request = new AbortController();
    controller.current = request;
    try {
      const handle = await startRecording(request.signal, audio => {
        recording.current = null;
        void upload(audio, current, request.signal);
      });
      if (current !== serial.current) { handle.cancel(); return; }
      recording.current = handle;
      setStatus("recording");
    } catch {
      if (current === serial.current) { setStatus("idle"); setError("无法开始录音，请检查麦克风权限，或上传 WAV 文件。"); }
    }
  }
  function file(file: File | undefined) {
    if (!file) return;
    if (!/\.wav$/i.test(file.name)) { setError("请选择 PCM WAV 文件。"); return; }
    beforeCapture();
    setError(null);
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    void upload(file, ++serial.current, request.signal);
  }
  return <div className="voice-input">
    <div className="voice-buttons">
      {status === "recording" ? <button type="button" className="button secondary" onClick={() => { setStatus("finishing"); recording.current?.stop(); }}><Square size={14} />结束并识别</button>
        : <button type="button" className="button secondary" onClick={() => void record()} disabled={!enabled || disabled || busy}><Mic size={14} />麦克风输入</button>}
      <label className={"button secondary" + (!enabled || disabled || busy ? " disabled" : "")}>
        <Upload size={14} />上传语音
        <input type="file" accept=".wav,audio/wav" aria-label="上传 WAV 语音" disabled={!enabled || disabled || busy}
          onChange={e => { file(e.target.files?.[0]); e.target.value = ""; }} hidden />
      </label>
      {busy && <button type="button" className="button secondary" onClick={cancel}><X size={14} />取消语音输入</button>}
    </div>
    <p className="muted" role="status">{status === "requesting" ? "正在等待麦克风权限…" : status === "recording" ? "正在录音，最长 60 秒…" : status === "transcribing" || status === "finishing" ? "正在识别录音…" : enabled ? "语音在本机识别；结果填入消息框，检查后发送。支持 60 秒内的 PCM WAV。" : capabilities.isError ? "无法查询语音识别状态，文字输入仍可使用。" : capabilities.data?.reason ?? "正在查询语音识别状态…"}</p>
    {error && <p className="notice" role="alert">{error}</p>}
  </div>;
}
