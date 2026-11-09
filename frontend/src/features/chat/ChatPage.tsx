import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Send } from "lucide-react";
import { apiRequest } from "../../lib/api";
import type { ChatResult } from "../../lib/types";
import { ErrorMessage, PageHeading } from "../../components/QueryState";
export function ChatPage() {
  const [text, setText] = useState("");
  const [useWeb, setUseWeb] = useState(false);
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
    if (!text.trim() || send.isPending) return;
    const value = text.trim();
    setMessages((m) => [...m, { role: "user", text: value }]);
    setText("");
    send.mutate({ text: value, use_web: useWeb });
  }
  return (
    <section>
      <PageHeading
        title="对话观测"
        description="正常对话与决策记录分开展示。调试信息默认折叠，来源文本按不可信内容处理。"
      />
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
                disabled={send.isPending}
              />
              本轮允许联网工具
            </label>
            <button
              className="button"
              disabled={send.isPending || !text.trim()}
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
