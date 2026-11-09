import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { BrainCircuit } from "lucide-react";
import { apiRequest, formatTime } from "../../lib/api";
import type { Draft, PersonaData, PersonaVersion } from "../../lib/types";
import {
  ErrorMessage,
  PageHeading,
  QueryState,
} from "../../components/QueryState";
import { useDraftDialog } from "../../components/OperationConfirmDialog";
import { AdminCommandForm } from "../../components/AdminCommand";
const labels: { key: keyof PersonaData; label: string; multiline?: boolean }[] =
  [
    { key: "name", label: "角色名称" },
    { key: "core_identity", label: "核心定位", multiline: true },
    { key: "expression_principles", label: "表达原则", multiline: true },
    { key: "relationship_boundaries", label: "关系边界", multiline: true },
    { key: "immutable_rules", label: "不可覆盖规则", multiline: true },
  ];
export function PersonaPage() {
  const current = useQuery({
    queryKey: ["persona"],
    queryFn: () => apiRequest<PersonaVersion>("/persona"),
  });
  const history = useQuery({
    queryKey: ["persona-history"],
    queryFn: () => apiRequest<PersonaVersion[]>("/persona/history"),
  });
  const [form, setForm] = useState<PersonaData | null>(null);
  const operation = useDraftDialog();
  useEffect(() => {
    if (current.data) setForm({ ...current.data.data });
  }, [current.data?.id]);
  const create = useMutation({
    mutationFn: (changes: Partial<PersonaData>) =>
      apiRequest<Draft>("/persona/draft", {
        method: "POST",
        body: { changes },
      }),
    onSuccess: operation.openDraft,
  });
  const [previewText, setPreviewText] = useState("");
  const preview = useMutation({
    mutationFn: () =>
      apiRequest<{ reply: string }>("/persona/preview-chat", {
        method: "POST",
        body: { changes, text: previewText },
      }),
  });
  const changes =
    form && current.data
      ? Object.fromEntries(
          Object.entries(form).filter(
            ([key, value]) =>
              value !== current.data.data[key as keyof PersonaData],
          ),
        )
      : {};
  return (
    <section>
      <PageHeading
        title="人设管理"
        description="编辑表达与定位，保留不可变版本。修改先生成草案，确认后才会进入实际对话。"
        action={
          current.data ? (
            <span className="badge">
              <BrainCircuit size={13} />
              版本 #{current.data.id}
            </span>
          ) : null
        }
      />
      <QueryState query={current}>
        {form && (
          <div className="grid two">
            <article className="panel">
              <h2>当前人设</h2>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (Object.keys(changes).length) create.mutate(changes);
                }}
              >
                {labels.map(({ key, label, multiline }) => (
                  <div className="field" key={key}>
                    <label htmlFor={"persona-" + key}>{label}</label>
                    {multiline ? (
                      <textarea
                        id={"persona-" + key}
                        value={String(form[key])}
                        maxLength={2000}
                        required
                        onChange={(e) =>
                          setForm({ ...form, [key]: e.target.value })
                        }
                      />
                    ) : (
                      <input
                        id={"persona-" + key}
                        value={String(form[key])}
                        maxLength={80}
                        required
                        onChange={(e) =>
                          setForm({ ...form, [key]: e.target.value })
                        }
                      />
                    )}
                  </div>
                ))}
                <div className="grid two">
                  <div className="field">
                    <label htmlFor="temperature-bias">
                      温度偏置（-0.5～0.5）
                    </label>
                    <input
                      id="temperature-bias"
                      type="number"
                      min={-0.5}
                      max={0.5}
                      step={0.05}
                      value={form.temperature_bias}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          temperature_bias: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="initiative">主动程度（0～1）</label>
                    <input
                      id="initiative"
                      type="number"
                      min={0}
                      max={1}
                      step={0.05}
                      value={form.initiative}
                      onChange={(e) =>
                        setForm({ ...form, initiative: Number(e.target.value) })
                      }
                    />
                  </div>
                </div>
                <p className="notice">
                  人设配置只调整表达，不能关闭事实校验与现实安全边界。
                </p>
                <ErrorMessage error={create.error} />
                <button
                  className="button"
                  disabled={
                    create.isPending || Object.keys(changes).length === 0
                  }
                >
                  {create.isPending ? "正在生成…" : "生成人设草案"}
                </button>
                {operation.success && (
                  <p className="success-text" role="status">
                    {operation.success}
                  </p>
                )}
              </form>
            </article>
            <div>
              <article className="panel">
                <h2>试聊预览</h2>
                <p className="muted">
                  仅用本地管理模型测试当前编辑的表达，不激活人设，不写入记忆；不是正式安全评测。
                </p>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    preview.mutate();
                  }}
                >
                  <div className="field">
                    <label htmlFor="preview-text">测试消息</label>
                    <textarea
                      id="preview-text"
                      maxLength={1000}
                      required
                      value={previewText}
                      onChange={(e) => setPreviewText(e.target.value)}
                    />
                  </div>
                  <button
                    className="button secondary"
                    disabled={preview.isPending || !previewText.trim()}
                  >
                    本地试聊
                  </button>
                  <ErrorMessage error={preview.error} />
                  {preview.data && (
                    <blockquote>{preview.data.reply}</blockquote>
                  )}
                </form>
              </article>
              <article className="panel">
                <h2>用自然语言提出修改</h2>
                <AdminCommandForm onDraft={operation.openDraft} />
              </article>
              <article className="panel">
                <h2>版本历史</h2>
                <QueryState query={history}>
                  {history.data?.length ? (
                    <div>
                      {history.data.map((v) => (
                        <div className="section-top" key={v.id}>
                          <div>
                            <strong>
                              #{v.id} · {v.data.name}
                            </strong>
                            <br />
                            <span className="timestamp">
                              {formatTime(v.created_at)}
                            </span>
                          </div>
                          <button
                            className="button secondary small"
                            disabled={
                              v.id === current.data?.id || create.isPending
                            }
                            onClick={() => create.mutate(v.data)}
                          >
                            预览恢复 #{v.id}
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="muted">还没有历史版本。</p>
                  )}
                </QueryState>
              </article>
            </div>
          </div>
        )}
      </QueryState>
      {operation.confirmation}
    </section>
  );
}
