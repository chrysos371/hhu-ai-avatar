import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ShieldCheck } from "lucide-react";
import { ApiError, apiRequest, formatTime } from "../lib/api";
import type { Draft } from "../lib/types";
import { PersonaDiff } from "../features/persona/PersonaDiff";
export function OperationConfirmDialog({
  draft,
  onClose,
  onApplied,
}: {
  draft: Draft;
  onClose: () => void;
  onApplied?: (result: { audit_id: number }) => void;
}) {
  const client = useQueryClient();
  const [now, setNow] = useState(Date.now() / 1000);
  const [blocked, setBlocked] = useState(false);
  const [ack, setAck] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    cancel.current?.focus();
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => {
      clearInterval(timer);
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  const expired = now >= draft.expires_at;
  const dangerous = draft.warnings.some((w) => w.includes("不可撤销"));
  const keys = [
    "dashboard",
    "system",
    "audit",
    ...(draft.operation_type === "persona.update"
      ? ["persona", "persona-history"]
      : draft.operation_type === "emotion.override"
        ? ["emotion"]
        : draft.operation_type === "knowledge.import"
          ? ["knowledge", "knowledge-sources"]
          : ["memories", "memory-detail", "summary", "reminders"]),
  ];
  const confirm = useMutation({
    mutationFn: () =>
      apiRequest<{ audit_id: number }>(
        "/operations/" + draft.draft_id + "/confirm",
        {
          method: "POST",
          body: { confirmation_token: draft.confirmation_token },
        },
      ),
    onSuccess: async (result) => {
      await Promise.all(
        keys.map((k) => client.invalidateQueries({ queryKey: [k] })),
      );
      onApplied?.(result);
      onClose();
    },
    onError: (error) => {
      if (
        error instanceof ApiError &&
        (error.status === 409 || error.status === 410)
      ) {
        setBlocked(true);
        keys.forEach((k) => {
          void client.invalidateQueries({ queryKey: [k] });
        });
      }
    },
  });
  return (
    <div className="modal-backdrop">
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirmation-title"
        ref={root}
        onKeyDown={(e) => {
          if (e.key === "Escape" && !confirm.isPending) onClose();
          if (e.key === "Tab") {
            const controls = root.current?.querySelectorAll<HTMLElement>(
              "button:not([disabled]), input:not([disabled]), [href]",
            );
            if (controls?.length) {
              const first = controls[0],
                last = controls[controls.length - 1];
              if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
              } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
              }
            }
          }
        }}
      >
        <header>
          <div>
            <p className="eyebrow">REVIEW CHANGE / #{draft.draft_id}</p>
            <h2 id="confirmation-title">确认管理操作</h2>
            <span className="badge">{draft.operation_type}</span>
          </div>
          <ShieldCheck size={24} color="#86d2e1" />
        </header>
        <p className="muted">
          请核对字段差异。只有点击确认后，后台才会原子执行并写入审计。
        </p>
        {draft.proposal_provider && (
          <p className="notice">
            本次建议来源：
            {draft.proposal_provider === "cloud"
              ? "本次明确选择的云端模型"
              : "本地模型"}
            。最终差异由后台计算。
          </p>
        )}
        <PersonaDiff diff={draft.diff} />
        {draft.warnings.map((w, i) => (
          <p className="notice" key={i}>
            <AlertTriangle
              size={13}
              style={{ display: "inline", marginRight: 6 }}
            />
            {w}
          </p>
        ))}
        {dangerous && (
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
            />
            我理解此操作不可撤销
          </label>
        )}
        <p className="timestamp">
          有效至 {formatTime(draft.expires_at)}（北京时间）
        </p>
        {expired && <p className="notice">预览已过期，请关闭后重新生成。</p>}
        {confirm.error && (
          <div role="alert" className="error-box">
            {confirm.error.message}
            {blocked && <p>请关闭此预览，基于最新状态重新生成。</p>}
          </div>
        )}
        <div
          className="actions"
          style={{ justifyContent: "flex-end", marginTop: 20 }}
        >
          <button
            ref={cancel}
            className="button secondary"
            disabled={confirm.isPending}
            onClick={onClose}
          >
            取消
          </button>
          <button
            className={"button" + (dangerous ? " danger" : "")}
            disabled={
              expired || blocked || confirm.isPending || (dangerous && !ack)
            }
            onClick={() => {
              if (!expired && !blocked && (!dangerous || ack)) confirm.mutate();
            }}
          >
            {confirm.isPending ? "正在确认…" : "确认执行"}
          </button>
        </div>
      </div>
    </div>
  );
}
export function useDraftDialog(onApplied?: () => void) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [success, setSuccess] = useState("");
  return {
    draft,
    openDraft: (d: Draft) => {
      setSuccess("");
      setDraft(d);
    },
    confirmation: draft ? (
      <OperationConfirmDialog
        key={draft.draft_id}
        draft={draft}
        onClose={() => setDraft(null)}
        onApplied={(r) => {
          setSuccess("已执行并写入审计 #" + r.audit_id);
          onApplied?.();
        }}
      />
    ) : null,
    success,
  };
}
