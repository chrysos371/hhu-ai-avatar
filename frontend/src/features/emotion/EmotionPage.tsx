import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiRequest, formatTime } from "../../lib/api";
import type { Draft, EmotionInfo } from "../../lib/types";
import { usePrivateStateQuery } from "../../lib/usePrivateStateQuery";
import {
  ErrorMessage,
  PageHeading,
  QueryState,
} from "../../components/QueryState";
import { useDraftDialog } from "../../components/OperationConfirmDialog";
export function EmotionPage() {
  const query = usePrivateStateQuery<EmotionInfo>("emotion", 10000);
  const [prefill, setPrefill] = useState<{ epoch: number; valence: number; arousal: number } | null>(null);
  const [editedValence, setEditedValence] = useState<number | null>(null);
  const [editedArousal, setEditedArousal] = useState<number | null>(null);
  const currentPrefill = prefill?.epoch === query.privacyEpoch ? prefill : null;
  const valence = editedValence ?? currentPrefill?.valence ?? 0;
  const arousal = editedArousal ?? currentPrefill?.arousal ?? 0;
  const [duration, setDuration] = useState(600);
  const [reason, setReason] = useState("");
  const op = useDraftDialog();
  useEffect(() => {
    if (query.data && prefill?.epoch !== query.privacyEpoch) {
      setPrefill({ epoch: query.privacyEpoch, ...query.data.effective });
    }
  }, [query.data, query.privacyEpoch, prefill?.epoch]);
  const create = useMutation({
    mutationFn: (params: unknown) =>
      apiRequest<Draft>("/emotion/draft", { method: "POST", body: params }),
    onSuccess: op.openDraft,
  });
  const d = query.data;
  return (
    <section>
      <PageHeading
        title="情绪干预"
        description="有时限地调整角色表达。自动状态和用户观测保持独立，到期后恢复自动表达。"
        action={<span className="badge">PAD · P/A 两维</span>}
      />
      <QueryState query={query}>
        {d && (
          <>
            <div className="grid three">
              {[
                { title: "自动状态", values: d.automatic },
                { title: "实际表达", values: d.effective },
                { title: "用户最近观测", values: d.user_observation },
              ].map((x) => (
                <article className="panel" key={x.title}>
                  <h2>{x.title}</h2>
                  <p className="metric-number" style={{ fontSize: 22 }}>
                    P {x.values.valence.toFixed(2)} / A{" "}
                    {x.values.arousal.toFixed(2)}
                  </p>
                  <small>
                    {x.title === "实际表达"
                      ? d.override
                        ? "当前存在已确认覆盖"
                        : "未启用覆盖，跟随自动状态"
                      : "不因手动干预而改写"}
                  </small>
                </article>
              ))}
            </div>
            <div className="grid two" style={{ marginTop: 20 }}>
              <article className="panel">
                <h2>创建表达覆盖</h2>
                {d.override && (
                  <p className="notice">
                    覆盖 #{d.override.id}：{d.override.data.reason}
                    <br />
                    到期 {formatTime(d.override.expires_at)}
                  </p>
                )}
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    create.mutate({
                      values: { valence, arousal },
                      duration_seconds: duration,
                      reason,
                    });
                  }}
                >
                  <div className="field">
                    <label htmlFor="override-valence">
                      愉悦度 P：{valence.toFixed(2)}
                    </label>
                    <input
                      id="override-valence"
                      type="range"
                      min={-1}
                      max={1}
                      step={0.05}
                      value={valence}
                      onChange={(e) => setEditedValence(Number(e.target.value))}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="override-arousal">
                      唤醒度 A：{arousal.toFixed(2)}
                    </label>
                    <input
                      id="override-arousal"
                      type="range"
                      min={-1}
                      max={1}
                      step={0.05}
                      value={arousal}
                      onChange={(e) => setEditedArousal(Number(e.target.value))}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="override-duration">
                      持续秒数（30～86400）
                    </label>
                    <input
                      id="override-duration"
                      type="number"
                      min={30}
                      max={86400}
                      step={1}
                      value={duration}
                      onChange={(e) => setDuration(Number(e.target.value))}
                      required
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="override-reason">干预原因</label>
                    <textarea
                      id="override-reason"
                      value={reason}
                      maxLength={500}
                      required
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </div>
                  <p className="muted">
                    仅覆盖常规角色表达，安全路由优先；不将情绪数值当作心理诊断。
                  </p>
                  <ErrorMessage error={create.error} />
                  <div className="actions">
                    <button
                      className="button"
                      disabled={create.isPending || !reason.trim()}
                    >
                      生成情绪草案
                    </button>
                    {d.override && (
                      <button
                        type="button"
                        className="button secondary"
                        disabled={create.isPending}
                        onClick={() =>
                          create.mutate({
                            clear: true,
                            reason: "管理员结束当前表达覆盖",
                          })
                        }
                      >
                        预览结束覆盖
                      </button>
                    )}
                  </div>
                  {op.success && (
                    <p role="status" className="success-text">
                      {op.success}
                    </p>
                  )}
                </form>
              </article>
              <article className="panel">
                <h2>近期表达趋势</h2>
                <small>仅使用本次服务实际对话产生的观测。</small>
                {d.recent_observations.length ? (
                  <div className="chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={d.recent_observations}>
                        <CartesianGrid stroke="#2a3b4a" strokeDasharray="3 3" />
                        <XAxis
                          dataKey="timestamp"
                          tickFormatter={(x) =>
                            new Date(Number(x) * 1000).toLocaleTimeString(
                              "zh-CN",
                              { hour: "2-digit", minute: "2-digit" },
                            )
                          }
                          stroke="#93aabd"
                        />
                        <YAxis domain={[-1, 1]} stroke="#93aabd" />
                        <Tooltip
                          contentStyle={{
                            background: "#17232f",
                            border: "1px solid #40566a",
                          }}
                          labelFormatter={(x) => formatTime(Number(x))}
                        />
                        <Legend />
                        <Line
                          name="愉悦度"
                          dataKey="valence"
                          stroke="#7ed4e5"
                          dot={false}
                        />
                        <Line
                          name="唤醒度"
                          dataKey="arousal"
                          stroke="#a3c6b2"
                          dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <p className="empty">尚无本次服务的对话观测。</p>
                )}
              </article>
            </div>
          </>
        )}
      </QueryState>
      {op.confirmation}
    </section>
  );
}
