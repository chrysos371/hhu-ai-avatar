import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Send, Volume2, Square } from "lucide-react";
import { streamTurn, cancelTurn, type TurnInput } from "../../lib/turns";
import { apiRequest } from "../../lib/api";
import type { PersonaVersion } from "../../lib/types";
import type { ChatResult } from "../../lib/types";
import { ErrorMessage, PageHeading } from "../../components/QueryState";
import { useSpeechPlayer } from "./useSpeechPlayer";
import { SpeechAvatarStage } from "./SpeechAvatarStage";
import { VoiceInput } from "./VoiceInput";
export function ChatPage() {
  const speech = useSpeechPlayer();
  const persona = useQuery({ queryKey: ["persona"], queryFn: () => apiRequest<PersonaVersion>("/persona"), retry: false });
  const name = persona.data?.data.name ?? "角色";
  const [text, setText] = useState("");
  const [useWeb, setUseWeb] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(false);
  const activeTurn = useRef<{ id: string; controller: AbortController } | null>(null);
  useEffect(() => () => {
    const active = activeTurn.current;
    active?.controller.abort();
    if (active) void cancelTurn(active.id).catch(() => {});
  }, []);
  const [messages, setMessages] = useState<
    { role: "user" | "assistant"; text: string; result?: ChatResult; pending?: boolean; cancelled?: boolean }[]
  >([]);
  const client = useQueryClient();
  const send = useMutation({
    mutationFn: (input: TurnInput & { index: number }) => {
      const controller = new AbortController();
      activeTurn.current = { id: input.request_id, controller };
      return streamTurn({ request_id: input.request_id, text: input.text, use_web: input.use_web }, controller.signal,
        piece => setMessages(rows => rows.map((row, i) => i === input.index ? { ...row, text: row.text + piece } : row)));
    },
    onSuccess: (result, input) => {
      setMessages(rows => rows.map((row, i) => i === input.index ? { role: "assistant", text: result.reply, result } : row));
      if (autoSpeak) void speech.play(input.index, result, true);
    },
    onError: (error, input) => {
      const cancelled = error.name === "AbortError";
      setMessages(rows => rows.map((row, i) => i === input.index ? { ...row, pending: false, cancelled,
        text: row.text || (cancelled ? "本轮已停止。" : "本轮未完成。") } : row));
    },
    onSettled: () => {
      activeTurn.current = null;
      setUseWeb(false);
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      void client.invalidateQueries({ queryKey: ["memories"] });
      void client.invalidateQueries({ queryKey: ["emotion"] });
    },
  });
  function submit() {
    if (!text.trim() || send.isPending || voiceBusy) return;
    speech.stop();
    const value = text.trim();
    const index = messages.length + 1;
    setMessages((m) => [...m, { role: "user", text: value }, { role: "assistant", text: "", pending: true }]);
    setText("");
    send.mutate({ request_id: crypto.randomUUID(), text: value, use_web: useWeb, index });
  }
  function interrupt() {
    speech.stop();
    const active = activeTurn.current;
    active?.controller.abort();
    if (active) void cancelTurn(active.id).catch(() => {});
  }
  return (
    <section>
      <PageHeading
        title="对话观测"
        description={`与${name}聊天，点击回复旁的朗读即可听见语音。可以随时停止，也可以只用文字交流。`}
      />
      <div className="speech-panel panel">
        <SpeechAvatarStage name={name} frameSource={speech.mouthFrames} busy={send.isPending}
          speaking={speech.status === "playing"}
          valence={messages.find((_, i) => i === speech.active)?.result?.valence ?? messages.at(-1)?.result?.valence}
          arousal={messages.find((_, i) => i === speech.active)?.result?.arousal ?? messages.at(-1)?.result?.arousal} />
        <div className="speech-controls">
          <h2>{name}在这里</h2>
          <p className="muted">朗读会把这段文字交给在线语音服务。默认不自动播放。</p>
          <label className="checkbox-row"><input type="checkbox" checked={autoSpeak}
            onChange={e => { setAutoSpeak(e.target.checked); if (!e.target.checked) speech.stop(); }} />自动分段朗读新回复</label>
          {send.isPending && <button type="button" className="button secondary" onClick={interrupt}><Square size={14} />停止生成</button>}
          {speech.status === "loading" && <p role="status">正在准备语音…</p>}
          {speech.segment.total > 1 && <p className="muted" role="status">语音片段 {speech.segment.index} / {speech.segment.total}</p>}
          <audio ref={speech.audioRef} controls preload="none" aria-label={`${name}语音播放器`}
            hidden={speech.active === null || speech.status === "loading" || speech.status === "error"}
            onPlay={speech.onPlay} onPause={speech.onPause} onEnded={speech.onEnded} onError={speech.onError} />
          {speech.active !== null && <button type="button" className="button secondary" onClick={speech.stop}>
            <Square size={14} />{speech.status === "loading" ? "取消朗读" : "停止播放"}</button>}
          {speech.warning && <p className="notice">{speech.warning}</p>}
          {speech.error && <p role="alert" className="notice">{speech.error}</p>}
        </div>
      </div>
      <div className="panel">
        <div className="chat-history" aria-live="polite">
          {messages.length === 0 && (
            <div className="empty">
              <MessageSquare size={28} style={{ margin: "0 auto 12px" }} />
              <h2>开始一段对话</h2>
              <p>
                回复会使用已生效的人设、记忆与知识。未配置对话模型时使用规则回退。
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <article key={i} className={"chat-message " + m.role}>
              <small>{m.role === "user" ? "你" : name}</small>
              <div>{m.text}</div>
              {m.pending && <small>正在生成；最终回复会完成检查后替换此草稿。</small>}
              {m.cancelled && <small>已停止，未完成的助手内容不存入记忆。</small>}
              {m.result && <button type="button" className="button secondary speech-read"
                disabled={voiceBusy || speech.active === i && speech.status === "loading" || m.text.length > 2000}
                title={m.text.length > 2000 ? "这段回复超过 2000 字，请选择较短内容朗读" : undefined}
                onClick={() => void speech.play(i, m.result!)}>
                <Volume2 size={14} />{speech.active === i && speech.status === "loading" ? "准备语音…" : "朗读回复"}
              </button>}
              {m.result?.trace && (
                <details className="trace">
                  <summary>本轮决策与来源</summary>
                  {m.result.trace.guard?.guarded && (
                    <p className="notice">本轮由安全或现实边界规则直接回应。</p>
                  )}
                  <h3>策略与状态</h3>
                  <pre>{JSON.stringify(m.result.trace.decision, null, 2)}</pre>
                  <h3>召回记忆</h3>
                  <pre>
                    {JSON.stringify(m.result.trace.recalled_memories, null, 2)}
                  </pre>
                  <h3>知识来源</h3>
                  <pre>
                    {JSON.stringify(
                      m.result.trace.knowledge_sources ?? [],
                      null,
                      2,
                    )}
                  </pre>
                  <h3>检查</h3>
                  <pre>
                    {JSON.stringify(
                      {
                        guard: m.result.trace.guard,
                        verifier: m.result.trace.verifier,
                      },
                      null,
                      2,
                    )}
                  </pre>
                  <h3>工具调用</h3>
                  <pre>
                    {JSON.stringify(m.result.trace.tool_calls, null, 2)}
                  </pre>
                </details>
              )}
            </article>
          ))}
          {send.isPending && (
            <div role="status" className="muted">
              正在生成回复…
            </div>
          )}
        </div>
        <ErrorMessage error={send.error?.name === "AbortError" ? null : send.error} />
        <VoiceInput disabled={false} beforeCapture={interrupt} onBusyChange={setVoiceBusy}
          onTranscript={value => setText(old => old ? old + "\n" + value : value)} />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div className="field">
            <label htmlFor="chat-message">消息</label>
            <textarea
              id="chat-message"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={`说说现在的想法，或交给${name}一个具体任务…`}
              maxLength={4000}
              disabled={send.isPending}
            />
          </div>
          <div className="section-top" style={{ marginBottom: 0 }}>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={useWeb}
                onChange={(e) => setUseWeb(e.target.checked)}
                disabled={send.isPending || voiceBusy}
              />
              本轮允许联网工具
            </label>
            <button
              className="button"
              disabled={send.isPending || voiceBusy || !text.trim()}
            >
              <Send size={14} />
              {send.isPending ? "等待回复…" : "发送消息"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
