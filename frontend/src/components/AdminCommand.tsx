import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Terminal } from "lucide-react";
import { apiRequest } from "../lib/api";
import type { Draft } from "../lib/types";
import { ErrorMessage } from "./QueryState";
import { useDraftDialog } from "./OperationConfirmDialog";
export function AdminCommandForm({
  onDraft,
}: {
  onDraft: (draft: Draft) => void;
}) {
  const [text, setText] = useState("");
  const [cloud, setCloud] = useState(false);
  const propose = useMutation({
    mutationFn: () =>
      apiRequest<Draft>("/admin-agent/draft", {
        method: "POST",
        body: { text, allow_cloud: cloud },
      }),
    onSuccess: onDraft,
    onSettled: () => setCloud(false),
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim() && !propose.isPending) propose.mutate();
      }}
    >
      <div className="field">
        <label htmlFor="management-command">管理要求</label>
        <textarea
          id="management-command"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={4000}
          placeholder="例如：让小海的表达更克制一些，保留现实关系边界。"
          required
        />
      </div>
      <p className="muted">
        模型只建议草案，不能直接执行。默认使用本地管理模型；不可用时仍可手动编辑。
      </p>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={cloud}
          onChange={(e) => setCloud(e.target.checked)}
          disabled={propose.isPending}
        />
        仅本次请求明确使用已配置的云端模型
      </label>
      <ErrorMessage error={propose.error} />
      <button
        className="button"
        style={{ marginTop: 16 }}
        disabled={propose.isPending || !text.trim()}
      >
        {propose.isPending ? "正在生成草案…" : "生成管理草案"}
      </button>
    </form>
  );
}
export function AdminCommand() {
  const [open, setOpen] = useState(false);
  const operation = useDraftDialog();
  return (
    <>
      <button className="button secondary small" onClick={() => setOpen(true)}>
        <Terminal size={14} />
        管理指令
      </button>
      {open && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="自然语言管理"
          >
            <header>
              <h2>自然语言管理</h2>
              <button
                className="button secondary small"
                onClick={() => setOpen(false)}
              >
                关闭
              </button>
            </header>
            <AdminCommandForm
              onDraft={(d) => {
                setOpen(false);
                operation.openDraft(d);
              }}
            />
          </section>
        </div>
      )}
      {operation.confirmation}
    </>
  );
}
