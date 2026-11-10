import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Send, Volume2, Square } from "lucide-react";
import { apiRequest } from "../../lib/api";
import type { ChatResult } from "../../lib/types";
import { ErrorMessage, PageHeading } from "../../components/QueryState";
import { useSpeechPlayer } from "./useSpeechPlayer";
import { AvatarStage } from "./AvatarStage";
import { VoiceInput } from "./VoiceInput";
export function ChatPage() {
  const speech = useSpeechPlayer();
  const [text, setText] = useState("");
  const [useWeb, setUseWeb] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [messages, setMessages] = useState<
    { role: "user" | "assistant"; text: string; result?: ChatResult }[]
  >([]);
  const client = useQueryClient();
  const send = useMutation({
    mutationFn: (input: { text: string; use_web: boolean }) =>
      apiRequest<ChatResult>("/chat", { method: "POST", body: input }),
    onSuccess: (result) => {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: result.reply, result },
      ]);
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      void client.invalidateQueries({ queryKey: ["memories"] });
      void client.invalidateQueries({ queryKey: ["emotion"] });
    },
    onSettled: () => setUseWeb(false),
  });
  function submit() {
    if (!text.trim() || send.isPending || voiceBusy) return;
    speech.stop();
    const value = text.trim();
    setMessages((m) => [...m, { role: "user", text: value }]);
    setText("");
    send.mutate({ text: value, use_web: useWeb });
  }
  return (
    <section>
      <PageHeading
        title="对话观测"
        description="与小海聊天，点击回复旁的朗读即可听见语音。可以随时停止，也可以只用文字交流。"
      />
      <div className="speech-panel panel">
        <AvatarStage mouth={speech.mouth} busy={send.isPending}
          speaking={speech.status === "playing"}
          valence={messages.find((_, i) => i === speech.active)?.result?.valence ?? messages.at(-1)?.result?.valence}
          arousal={messages.find((_, i) => i === speech.active)?.result?.arousal ?? messages.at(-1)?.result?.arousal} />
        <div className="speech-controls">
          <h2>小海在这里</h2>
          <p className="muted">朗读会把这段文字交给在线语音服务。默认不自动播放。</p>
          {speech.status === "loading" && <p role="status">正在准备语音…</p>}
          <audio ref={speech.audioRef} controls preload="none" aria-label="小海语音播放器"
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
              <small>{m.role === "user" ? "你" : "小海"}</small>
              <div>{m.text}</div>
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
        <ErrorMessage error={send.error} />
        <VoiceInput disabled={send.isPending} beforeCapture={speech.stop} onBusyChange={setVoiceBusy}
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
              placeholder="说说现在的想法，或交给小海一个具体任务…"
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
