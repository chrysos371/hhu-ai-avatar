import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { apiRequest, formatTime } from "../../lib/api";
import type { Draft, Reminder } from "../../lib/types";
import {
  ErrorMessage,
  PageHeading,
  QueryState,
} from "../../components/QueryState";
import { useDraftDialog } from "../../components/OperationConfirmDialog";
import { useReminderDeliveries } from "./useReminderDeliveries";
export function RemindersPage() {
  const client = useQueryClient();
  const deliveries = useReminderDeliveries(() => { void client.invalidateQueries({ queryKey: ["reminders"] }); });
  const query = useQuery({
    queryKey: ["reminders"],
    queryFn: () => apiRequest<Reminder[]>("/reminders"),
    refetchInterval: 10000,
  });
  const [text, setText] = useState("");
  const operation = useDraftDialog(() => setText(""));
  const create = useMutation({
    mutationFn: () =>
      apiRequest<Draft>("/reminders", { method: "POST", body: { text } }),
    onSuccess: operation.openDraft,
  });
  const update = useMutation({
    mutationFn: ({
      id,
      action,
    }: {
      id: number;
      action: "complete" | "cancel" | "delete";
    }) =>
      apiRequest<Draft>(
        "/reminders/" +
          id +
          "/" +
          (action === "delete" ? "delete-draft" : "status-draft"),
        {
          method: "POST",
          body:
            action === "delete"
              ? {}
              : { status: action === "complete" ? "completed" : "cancelled" },
        },
      ),
    onSuccess: operation.openDraft,
  });
  return (
    <section>
      <PageHeading
        title="提醒"
        description="创建明确日期、钟点和事项的本机提醒。创建和手动状态修改都先预览，再确认。"
      />
      <ErrorMessage error={deliveries.error} />
      {deliveries.items.length > 0 && (
        <div className="notice" role="status">
          <Bell size={15} style={{ display: "inline", marginRight: 8 }} />
          到期提醒：
          {deliveries.items.map((r) => (
            <div key={r.delivery_id}>
              <span>{r.title}</span>
              <button className="button secondary small" style={{ marginLeft: 10 }}
                disabled={deliveries.ackId !== null}
                aria-label={"确认已看到提醒 #" + r.id}
                onClick={() => deliveries.acknowledge(r.delivery_id)}>
                {deliveries.ackId === r.delivery_id ? "正在确认…" : "已看到"}
              </button>
            </div>
          ))}
          <small>未确认的近期提醒可在返回或刷新后恢复；确认仅记录客户端提交。</small>
        </div>
      )}
      <article className="panel">
        <h2>创建提醒</h2>
        <form
          className="toolbar"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="field" style={{ flex: 1, margin: 0 }}>
            <label htmlFor="reminder-text">提醒内容</label>
            <input
              id="reminder-text"
              value={text}
              required
              maxLength={4000}
              placeholder="提醒我明天下午3点答辩"
              onChange={(e) => setText(e.target.value)}
            />
          </div>
          <button
            className="button"
            disabled={create.isPending || !text.trim()}
          >
            生成提醒草案
          </button>
        </form>
        <p className="muted">
          服务运行且打开提醒页时在本机提示，不会向手机或其他人发送通知。仅恢复24小时内仍有效的待确认事项；旧版已认领记录不自动补发。时间以北京时间解析。
        </p>
        <ErrorMessage error={create.error || update.error} />
        {operation.success && (
          <p className="success-text" role="status">
            {operation.success}
          </p>
        )}
      </article>
      <article className="panel">
        <h2>提醒记录</h2>
        <QueryState query={query}>
          {query.data?.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>事项</th>
                    <th>到期时间</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.map((r) => (
                    <tr key={r.id}>
                      <td>
                        #{r.id} {r.title}
                      </td>
                      <td className="timestamp">{formatTime(r.due_at)}</td>
                      <td>
                        <span className="badge">
                          {r.status === "active"
                            ? "进行中"
                            : r.status === "completed"
                              ? "已完成"
                              : "已取消"}
                        </span>
                        {r.delivery_acknowledged_at != null
                          ? <small> · 网页已确认（客户端）</small>
                          : r.notified_at != null && <small> · 已标记到期，显示未确认</small>}
                      </td>
                      <td>
                        <div className="actions">
                          {r.status === "active" && (
                            <>
                              <button
                                className="button secondary small"
                                aria-label={"完成 #" + r.id}
                                disabled={update.isPending}
                                onClick={() =>
                                  update.mutate({
                                    id: r.id,
                                    action: "complete",
                                  })
                                }
                              >
                                完成
                              </button>
                              <button
                                className="button secondary small"
                                aria-label={"取消 #" + r.id}
                                disabled={update.isPending}
                                onClick={() =>
                                  update.mutate({ id: r.id, action: "cancel" })
                                }
                              >
                                取消
                              </button>
                            </>
                          )}
                          <button
                            className="button danger small"
                            aria-label={"删除提醒 #" + r.id}
                            disabled={update.isPending}
                            onClick={() =>
                              update.mutate({ id: r.id, action: "delete" })
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
            <p className="empty">还没有提醒记录。</p>
          )}
        </QueryState>
      </article>
      {operation.confirmation}
    </section>
  );
}
