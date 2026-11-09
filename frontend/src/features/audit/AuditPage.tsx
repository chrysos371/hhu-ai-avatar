import { useState } from "react";
import { useInfiniteQuery, useMutation } from "@tanstack/react-query";
import { apiRequest, formatTime } from "../../lib/api";
import type { AuditEvent, Draft } from "../../lib/types";
import {
  ErrorMessage,
  PageHeading,
  QueryState,
} from "../../components/QueryState";
import { useDraftDialog } from "../../components/OperationConfirmDialog";
import { PersonaDiff } from "../persona/PersonaDiff";
function reversible(e: AuditEvent) {
  if (e.status !== "success") return false;
  if (
    e.operation_type === "persona.update" ||
    e.operation_type === "emotion.override"
  )
    return true;
  if (e.operation_type === "knowledge.import")
    return !!(e.after as { source_id?: number })?.source_id;
  const actions = (e.after as { actions?: { action: string }[] })?.actions;
  return !!actions?.length && actions.every((a) => a.action === "correct");
}
export function AuditPage() {
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [detail, setDetail] = useState<AuditEvent | null>(null);
  const operation = useDraftDialog();
  const query = useInfiniteQuery({
    queryKey: ["audit", type, status],
    initialPageParam: undefined as number | undefined,
    queryFn: ({ pageParam }) => {
      const p = new URLSearchParams({ limit: "30" });
      if (type) p.set("operation_type", type);
      if (status) p.set("status", status);
      if (pageParam) p.set("before_id", String(pageParam));
      return apiRequest<AuditEvent[]>("/audit?" + p);
    },
    getNextPageParam: (last) =>
      last.length === 30 ? last.at(-1)?.id : undefined,
  });
  const reverse = useMutation({
    mutationFn: (id: number) =>
      apiRequest<Draft>("/audit/" + id + "/reverse-draft", {
        method: "POST",
        body: {},
      }),
    onSuccess: operation.openDraft,
  });
  const rows = query.data?.pages.flat() ?? [];
  return (
    <section>
      <PageHeading
        title="操作审计"
        description="追踪确认执行的结果、版本引用与失败。反向操作也必须生成新草案并再次确认。"
      />
      <article className="panel">
        <div className="toolbar">
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="audit-type">操作类型</label>
            <select
              id="audit-type"
              value={type}
              onChange={(e) => setType(e.target.value)}
            >
              <option value="">全部操作</option>
              {[
                "persona.update",
                "emotion.override",
                "knowledge.import",
                "memory.batch",
              ].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="audit-status">结果</label>
            <select
              id="audit-status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">全部结果</option>
              <option value="success">已执行</option>
              <option value="failed">失败</option>
            </select>
          </div>
        </div>
        <ErrorMessage error={reverse.error} />
        {operation.success && (
          <p className="success-text" role="status">
            {operation.success}
          </p>
        )}
        <QueryState query={query}>
          {rows.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>编号</th>
                    <th>操作</th>
                    <th>操作者</th>
                    <th>结果</th>
                    <th>时间</th>
                    <th>追踪</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td>#{row.id}</td>
                      <td>
                        {row.operation_type}
                        <br />
                        <small>草案 #{row.draft_id}</small>
                      </td>
                      <td>{row.actor}</td>
                      <td>
                        <span
                          className={
                            "badge " +
                            (row.status === "success" ? "ok" : "error")
                          }
                        >
                          {row.status === "success" ? "已执行" : "失败"}
                        </span>
                        {row.error && <small> {row.error}</small>}
                      </td>
                      <td className="timestamp">
                        {formatTime(row.created_at)}
                      </td>
                      <td>
                        <div className="actions">
                          <button
                            className="button secondary small"
                            onClick={() => setDetail(row)}
                          >
                            详情
                          </button>
                          <button
                            className="button secondary small"
                            aria-label={"生成反向草案 #" + row.id}
                            disabled={!reversible(row) || reverse.isPending}
                            onClick={() => reverse.mutate(row.id)}
                          >
                            生成反向草案
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty">没有匹配的审计记录。</p>
          )}
        </QueryState>
        {query.hasNextPage && (
          <button
            className="button secondary"
            disabled={query.isFetchingNextPage}
            onClick={() => query.fetchNextPage()}
            style={{ marginTop: 18 }}
          >
            加载更早记录
          </button>
        )}
        {detail && (
          <section className="source-detail">
            <div className="section-top">
              <h2>审计详情 #{detail.id}</h2>
              <button
                className="button secondary small"
                onClick={() => setDetail(null)}
              >
                收起
              </button>
            </div>
            <PersonaDiff
              diff={[
                {
                  field: detail.operation_type,
                  before: detail.before,
                  after: detail.after,
                },
              ]}
            />
            <small>记忆审计保留版本与内容哈希；不复制已删除的私人原文。</small>
          </section>
        )}
      </article>
      {operation.confirmation}
    </section>
  );
}
