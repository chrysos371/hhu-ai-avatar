import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Send, Volume2, Square } from "lucide-react";
import { streamTurn, cancelTurn, type TurnInput } from "../../lib/turns";
import { ApiError, apiRequest, formatTime } from "../../lib/api";
import type { PersonaVersion } from "../../lib/types";
import { ErrorMessage, PageHeading } from "../../components/QueryState";
import { useSpeechPlayer } from "./useSpeechPlayer";
import { SpeechAvatarStage } from "./SpeechAvatarStage";
import { VoiceInput } from "./VoiceInput";
import { ChatTrace } from "./ChatTrace";
import { LocalActionReceipts } from './LocalActionReceipts';
import { useChatHistory } from "./useChatHistory";
import { SpeakerContextControls } from './SpeakerContextControls';
import { speakerControls, type SpeakerChoice } from '../../lib/speakerContext';
type ChatTurnInput = TurnInput & { index: number; epoch: number; controlChoice?: SpeakerChoice; cancelled?: boolean };
export function ChatPage() {
  const speech = useSpeechPlayer();
  const persona = useQuery({ queryKey: ["persona"], queryFn: () => apiRequest<PersonaVersion>("/persona"), retry: false });
  const name = persona.data?.data.name ?? "角色";
  const [text, setText] = useState("");
  const [useWeb, setUseWeb] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(false);
  const activeTurn = useRef<{ id: string; controller: AbortController } | null>(null);
  const submittedTurn = useRef<string | null>(null);
  const queuedInput = useRef<ChatTurnInput | null>(null), cancelQueued = useRef<() => void>(() => {});
  const resetMutation = useRef<() => void>(() => {});
  const interrupt = useCallback(() => {
    speech.stop();
    const active = activeTurn.current;
    active?.controller.abort();
    if (active) void cancelTurn(active.id).catch(() => {});
    else cancelQueued.current();
  }, [speech.stop]);
  const isBusy = useCallback(() => submittedTurn.current !== null || activeTurn.current !== null, []);
  const onPrivacyChange = useCallback(() => {
    const pending = activeTurn.current !== null;
    interrupt(); setText("");
    if (!pending) { submittedTurn.current = null; resetMutation.current(); }
  }, [interrupt]);
  const history = useChatHistory({ isBusy, onInvalidate: onPrivacyChange, includeContext: true });
  const messages = history.rows, setMessages = history.setRows;
  useEffect(() => () => {
    const active = activeTurn.current;
    active?.controller.abort();
    if (active) void cancelTurn(active.id).catch(() => {});
  }, []);
  const client = useQueryClient();
  const send = useMutation({
    gcTime: 0,
    mutationFn: (input: ChatTurnInput) => {
      if (input.cancelled || submittedTurn.current !== input.request_id || !history.isCurrent(input.epoch))
        throw new DOMException('本轮提交语境已失效或已停止。', 'AbortError');
      const controller = new AbortController();
      activeTurn.current = { id: input.request_id, controller };
      return streamTurn({ request_id: input.request_id, text: input.text, use_web: input.use_web,
        ...(input.expected_context ? { expected_context: input.expected_context } : {}) }, controller.signal,
        piece => { if (history.isCurrent(input.epoch)) setMessages(rows => rows.map((row, i) => i === input.index ? { ...row, text: row.text + piece } : row)); });
    },
    onSuccess: (result, input) => {
      if (input.cancelled || !history.isCurrent(input.epoch, result)) return;
      const source = result.conversation;
      setMessages(rows => rows.map((row, i) => i === input.index
        ? { role: "assistant", text: result.reply, result, id: source?.assistant_message_id, session_id: source?.session_id }
        : i === input.index - 1 ? { ...row, id: source?.user_message_id, session_id: source?.session_id } : row));
      if (autoSpeak && !input.controlChoice) void speech.play(source?.assistant_message_id ?? -(input.index + 1), result, true);
    },
    onError: async (error, input) => {
      if (input.cancelled || !history.isCurrent(input.epoch)) return;
      if (error instanceof ApiError && error.code === 'speaker_context_changed') {
        const context = await history.refreshContext();
        if (input.cancelled || !history.isCurrent(input.epoch)) return;
        // Restore only after an authoritative read confirms that privacy and
        // server identity are unchanged. Never auto-replay this rejected turn.
        if (context && input.expected_context?.instance_id === context.instance_id
          && input.expected_context.revision === context.revision) setText(old => old || input.text);
      }
      const cancelled = error.name === "AbortError";
      setMessages(rows => rows.map((row, i) => i === input.index ? { ...row, pending: false, cancelled,
        text: row.text || (cancelled ? "本轮已停止。" : "本轮未完成。") } : row));
    },
    onSettled: (_, error, input) => {
      const owns = submittedTurn.current === input.request_id;
      if (owns) { submittedTurn.current = null; queuedInput.current = null; }
      if (activeTurn.current?.id === input.request_id) activeTurn.current = null;
      if (owns) setUseWeb(false);
      const invalidated = !history.isCurrent(input.epoch);
      if (invalidated && owns) resetMutation.current();
      if (error?.name !== 'AbortError' || invalidated) void history.refresh();
      else void history.refreshContext();
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      void client.invalidateQueries({ queryKey: ["memories"] });
      void client.invalidateQueries({ queryKey: ["emotion"] });
    },
  });
  resetMutation.current = send.reset;
  cancelQueued.current = () => {
    const input = queuedInput.current;
    if (!input || activeTurn.current) return;
    input.cancelled = true; queuedInput.current = null; submittedTurn.current = null;
    if (history.isCurrent(input.epoch)) {
      setMessages(rows => rows.map((row, i) => i === input.index && row.pending
        ? { ...row, pending: false, cancelled: true, text: row.text || '本轮已停止。' } : row));
      void history.refreshContext();
    }
    send.reset();
  };
  function enqueue(value: string, allowWeb: boolean, controlChoice?: SpeakerChoice) {
    if (!value.trim() || send.isPending || submittedTurn.current !== null || voiceBusy || !history.ready) return false;
    const context = history.context;
    if (!controlChoice && !context) return false;
    const expected = !controlChoice && context ? {
      instance_id: context.instance_id, revision: context.revision, context_cursor: context.context_cursor,
    } : undefined;
    speech.stop();
    const index = messages.length + 1;
    const id = crypto.randomUUID(); submittedTurn.current = id;
    history.markContextPending();
    setMessages((m) => [...m, { role: "user", text: value }, { role: "assistant", text: "", pending: true }]);
    const input = { request_id: id, text: value, use_web: allowWeb, index, epoch: history.epoch.current, controlChoice,
      ...(expected ? { expected_context: expected } : {}) };
    queuedInput.current = input; send.mutate(input);
    return true;
  }
  function submit() {
    if (enqueue(text.trim(), useWeb)) setText('');
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
          valence={messages.find((m, i) => (m.id ?? -(i + 1)) === speech.active)?.result?.valence ?? messages.at(-1)?.result?.valence}
          arousal={messages.find((m, i) => (m.id ?? -(i + 1)) === speech.active)?.result?.arousal ?? messages.at(-1)?.result?.arousal} />
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
      <SpeakerContextControls context={history.context} loading={history.contextLoading} error={history.contextError}
        disabled={send.isPending || voiceBusy || !history.ready || history.loading}
        switching={send.isPending ? send.variables?.controlChoice ?? null : null}
        onChoice={choice => { enqueue(speakerControls[choice], false, choice); }} />
      {history.ready && !history.loading && history.version && <LocalActionReceipts
        key={history.version.instance_id + ':' + history.version.revision} version={history.version} busy={send.isPending} />}
      <div className="panel">
        <div className="section-top">
          <button type="button" className="button secondary" disabled={history.loading || send.isPending}
            onClick={() => void history.refresh()}>刷新对话记录</button>
          {history.hasMore && <button type="button" className="button secondary" disabled={history.loading || send.isPending}
            onClick={() => { speech.stop(); void history.refresh(true); }}>加载更早的对话</button>}
        </div>
        <ErrorMessage error={history.error} />
        {history.loading && <p role="status">正在读取对话记录…</p>}
        <div className="chat-history" aria-live="polite" data-history-ready={String(history.ready && !history.loading)}>
          {messages.length === 0 && history.ready && (
            <div className="empty">
              <MessageSquare size={28} style={{ margin: "0 auto 12px" }} />
              <h2>开始一段对话</h2>
              <p>
                回复会使用已生效的人设、记忆与知识。未配置对话模型时使用规则回退。
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <article key={m.id ?? 'local-' + i} className={"chat-message " + m.role} data-message-id={m.id}>
              <small>{m.role === "user" ? "你" : name}</small>
              {m.created_at !== undefined && <small className="timestamp"> · {formatTime(m.created_at)}</small>}
              <div>{m.text}</div>
              {m.pending && <small>正在生成；最终回复会完成检查后替换此草稿。</small>}
              {m.cancelled && <small>已停止，未完成的助手内容不存入记忆。</small>}
              {m.role === 'assistant' && !m.pending && !m.cancelled && !m.redacted && (m.result || m.id !== undefined) && <button type="button" className="button secondary speech-read"
                disabled={voiceBusy || speech.active === (m.id ?? -(i + 1)) && speech.status === "loading" || m.text.length > 2000}
                title={m.text.length > 2000 ? "这段回复超过 2000 字，请选择较短内容朗读" : undefined}
                onClick={() => void speech.play(m.id ?? -(i + 1), m.result ?? { reply: m.text })}>
                <Volume2 size={14} />{speech.active === (m.id ?? -(i + 1)) && speech.status === "loading" ? "准备语音…" : "朗读回复"}
              </button>}
              {m.result?.trace && <ChatTrace trace={m.result.trace} />}
              {m.id !== undefined && m.role === 'assistant' && !m.result && !m.redacted && <p className="muted">这条历史回复未保留可用的决策记录。</p>}
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
                disabled={send.isPending || voiceBusy || !history.context?.real_actions_for_new_turn}
              />
              本轮允许联网工具
            </label>
            <button
              className="button"
              disabled={send.isPending || voiceBusy || !text.trim() || !history.ready || !history.context}
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
