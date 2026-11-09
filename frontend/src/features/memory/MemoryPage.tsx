import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Database } from "lucide-react";
import { apiRequest, formatTime } from "../../lib/api";
import type { Draft, MemoryRow, Summary } from "../../lib/types";
import {
  ErrorMessage,
  PageHeading,
  QueryState,
} from "../../components/QueryState";
import { useDraftDialog } from "../../components/OperationConfirmDialog";
const sourceLabels: Record<string, string> = {
  manual_correction: "人工纠错",
  source_backed: "原话来源",
  unrecorded: "未记录来源",
};
export function MemoryPage() {
  const [q, setQ] = useState("");
  const [history, setHistory] = useState(false);
  const [type, setType] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [since, setSince] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [correction, setCorrection] = useState("");
  const params = new URLSearchParams({ q, history: history ? "1" : "0" });
  if (type) params.set("type", type);
  if (confirmation) params.set("confirmation", confirmation);
  if (since)
    params.set(
      "since",
      String(new Date(since + "T00:00:00+08:00").getTime() / 1000),
    );
  const query = useQuery({
    queryKey: ["memories", q, history, type, confirmation, since],
    queryFn: () => apiRequest<MemoryRow[]>("/memory?" + params.toString()),
  });
  const detail = useQuery({
    queryKey: ["memory-detail", detailId],
    queryFn: () => apiRequest<MemoryRow>("/memory/" + detailId),
    enabled: detailId !== null,
  });
  const summary = useQuery({
    queryKey: ["summary"],
    queryFn: () => apiRequest<Summary>("/summary"),
  });
  const operation = useDraftDialog(() => {
    setSelected([]);
    setDetailId(null);
    setCorrection("");
  });
  const draft = useMutation({
    mutationFn: (actions: unknown[]) =>
      apiRequest<Draft>("/memory/batch-draft", {
        method: "POST",
        body: { actions },
      }),
    onSuccess: operation.openDraft,
  });
  const forgetSource = useMutation({
    mutationFn: (id: number) =>
      apiRequest<Draft>("/summary/" + id + "/forget-draft", {
        method: "POST",
        body: {},
      }),
    onSuccess: operation.openDraft,
  });
  function selectDetail(row: MemoryRow) {
    setDetailId(row.id);
    setCorrection(row.content);
  }
  return (
    <section>
      <PageHeading
        title="记忆中枢"
        description="查看事实、原话和版本。来源记录不等于语义验收；纠错保留历史，彻底删除需明确确认。"
        action={
          <span className="badge">
            <Database size={13} />
            个人记忆
          </span>
        }
      />
      <article className="panel">
        <div className="toolbar">
          <div className="field" style={{ margin: 0, flex: 1 }}>
            <label htmlFor="memory-search">搜索记忆</label>
            <input
              id="memory-search"
              value={q}
              maxLength={200}
              onChange={(e) => {
                setQ(e.target.value);
                setSelected([]);
              }}
              placeholder="内容关键词"
            />
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="memory-type">类型</label>
            <select
              id="memory-type"
              value={type}
              onChange={(e) => {
                setType(e.target.value);
                setSelected([]);
              }}
            >
              <option value="">全部类型</option>
              {["user_profile", "preference", "fact", "episode", "goal"].map(
                (t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ),
              )}
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="memory-confirmation">确认/来源状态</label>
            <select
              id="memory-confirmation"
              value={confirmation}
              onChange={(e) => {
                setConfirmation(e.target.value);
                setSelected([]);
              }}
            >
              <option value="">全部来源</option>
              {Object.entries(sourceLabels).map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="memory-since">起始日期（北京时间）</label>
            <input
              id="memory-since"
              type="date"
              value={since}
              onChange={(e) => {
                setSince(e.target.value);
                setSelected([]);
              }}
            />
          </div>
        </div>
        <div className="section-top">
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={history}
              onChange={(e) => {
                setHistory(e.target.checked);
                setSelected([]);
              }}
            />
            包含历史版本
          </label>
          <button
            className="button danger small"
            disabled={!selected.length || draft.isPending}
            onClick={() =>
              draft.mutate(selected.map((id) => ({ action: "forget", id })))
            }
          >
            批量删除（{selected.length}）
          </button>
        </div>
        <ErrorMessage error={draft.error || forgetSource.error} />
        {operation.success && (
          <p className="success-text" role="status">
            {operation.success}
          </p>
        )}
        <QueryState query={query}>
          {query.data?.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>选择</th>
                    <th>编号/类型</th>
                    <th>内容</th>
                    <th>版本与来源</th>
                    <th>创建时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <input
                          aria-label={"选择记忆 #" + row.id}
                          type="checkbox"
                          checked={selected.includes(row.id)}
                          onChange={(e) =>
                            setSelected((ids) =>
                              e.target.checked
                                ? [...ids, row.id]
                                : ids.filter((id) => id !== row.id),
                            )
                          }
                        />
                      </td>
                      <td>
                        #{row.id}
                        <br />
                        <small>{row.memory_type}</small>
                      </td>
                      <td className="cell-content">
                        {row.content.length > 160
                          ? row.content.slice(0, 160) + "…"
                          : row.content}
                      </td>
                      <td>
                        <span
                          className={
                            "badge " + (row.status === "active" ? "ok" : "")
                          }
                        >
                          {row.status === "active" ? "当前" : "历史"}
                        </span>
                        <br />
                        <small>
                          {sourceLabels[row.confirmation_status ?? ""] ??
                            "未记录来源"}
                        </small>
                      </td>
                      <td className="timestamp">
                        {formatTime(row.created_at)}
                      </td>
                      <td>
                        <div className="actions">
                          <button
                            className="button secondary small"
                            aria-label={"来源 #" + row.id}
                            onClick={() => selectDetail(row)}
                          >
                            来源 / 纠错
                          </button>
                          <button
                            className="button secondary small"
                            aria-label={"反馈不相关 #" + row.id}
                            disabled={draft.isPending}
                            onClick={() =>
                              draft.mutate([{ id: row.id, action: "badhit" }])
                            }
                          >
                            不相关
                          </button>
                          <button
                            className="button danger small"
                            aria-label={"删除记忆 #" + row.id}
                            disabled={draft.isPending}
                            onClick={() =>
                              draft.mutate([{ id: row.id, action: "forget" }])
                            }
                          >
                            删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty">没有匹配记忆。</p>
          )}
        </QueryState>
        {detailId !== null && (
          <section className="source-detail" aria-label="记忆详情">
            <div className="section-top">
              <h2>记忆 #{detailId} · 来源与版本</h2>
              <button
                className="button secondary small"
                onClick={() => setDetailId(null)}
              >
                收起详情
              </button>
            </div>
            <QueryState query={detail}>
              {detail.data && (
                <>
                  <p className="source-quote">{detail.data.content}</p>
                  <p className="muted">
                    状态：{detail.data.status} · 前一版本：
                    {detail.data.predecessor_id ?? "无"} · 创建于{" "}
                    {formatTime(detail.data.created_at)}
                  </p>
                  {detail.data.sources?.length ? (
                    detail.data.sources.map((s) => (
                      <article key={s.id}>
                        <small>
                          来源 #{s.id} · 会话 {s.session_id ?? "人工操作"} ·{" "}
                          {formatTime(s.created_at)}
                        </small>
                        <blockquote className="source-quote">
                          {s.evidence ?? s.message_content ?? "没有保留原文"}
                        </blockquote>
                      </article>
                    ))
                  ) : (
                    <p className="muted">没有保留来源记录。</p>
                  )}
                  {detail.data.status === "active" && (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        draft.mutate([
                          {
                            id: detailId,
                            action: "correct",
                            content: correction,
                          },
                        ]);
                      }}
                    >
                      <div className="field">
                        <label htmlFor="memory-correction">记忆纠正内容</label>
                        <textarea
                          id="memory-correction"
                          value={correction}
                          onChange={(e) => setCorrection(e.target.value)}
                          maxLength={4000}
                          required
                        />
                      </div>
                      <button
                        className="button"
                        disabled={draft.isPending || !correction.trim()}
                      >
                        生成纠错草案
                      </button>
                    </form>
                  )}
                </>
              )}
            </QueryState>
          </section>
        )}
      </article>
      <article className="panel">
        <h2>会话摘要与来源</h2>
        <p className="muted">
          带编号的历史原话摘录，用作讨论线索，不自动视为当前事实。
        </p>
        <QueryState query={summary}>
          {summary.data?.items.length ? (
            summary.data.items.map((item) => (
              <article className="source-detail" key={item.message_id}>
                <div className="section-top">
                  <small>
                    原话 #{item.message_id} · {formatTime(item.created_at)}
                  </small>
                  <button
                    className="button danger small"
                    disabled={forgetSource.isPending}
                    onClick={() => forgetSource.mutate(item.message_id)}
                  >
                    预览删除此原话
                  </button>
                </div>
                <p className="source-quote">{item.text}</p>
              </article>
            ))
          ) : (
            <p className="empty">暂无早期会话摘录。</p>
          )}
        </QueryState>
      </article>
      {operation.confirmation}
    </section>
  );
}
