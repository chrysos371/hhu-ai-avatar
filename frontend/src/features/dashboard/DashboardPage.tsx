import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BookOpen,
  BrainCircuit,
  Database,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";
import { apiRequest, formatTime } from "../../lib/api";
import type { Dashboard } from "../../lib/types";
import { PageHeading, QueryState } from "../../components/QueryState";
const patrolLabels: Record<string,string> = {
  unexpected_goodnight:"告别语境不符", verbatim_repeat:"重复上一轮回复",
  possible_unwanted_advice:"疑似违背只倾听要求", possible_language_drift:"疑似语言漂移",
  possible_physical_invitation:"疑似线下邀请", departure_question:"告别后继续追问",
  invalid_json:"JSON格式错误", title_format:"标题格式错误",
  generation_degraded:"模型降级", empty_reply:"空回复", call_error:"调用异常",
  completed:"批次完成", completed_with_errors:"批次有异常", running:"正在巡检", interrupted:"运行中断",
};
export function DashboardPage() {
  const query = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => apiRequest<Dashboard>("/dashboard"),
    refetchInterval: 15000,
  });
  const patrol = useQuery({
    queryKey: ["improvement"],
    queryFn: () => apiRequest<{available:boolean; runs:{id:string;status:string;turns:number}[]; issues:{id:string;category:string;occurrences:number}[]}>("/improvement"),
    refetchInterval: 60000,
  });
  const d = query.data;
  return (
    <section>
      <PageHeading
        title="数字人大脑总览"
        description="观察当前状态、数据与最近事件。每一项指标都来自实际记录。"
        action={<span className="badge">认知工作区</span>}
      />
      <article className="panel" style={{ marginBottom: 20 }}>
        <h2>自动开发巡检</h2>
        <p className="muted">合成场景的自动检查信号，不代表语义验收；不会自动训练或发布。</p>
        {patrol.isPending && <p>正在读取巡检记录…</p>}
        {patrol.isError && <p role="status">巡检记录暂时不可用。</p>}
        {patrol.data && (!patrol.data.available ? <p>尚无巡检记录。</p> : <>
          <p>最近批次：{patrolLabels[patrol.data.runs[0]?.status] || patrol.data.runs[0]?.status || "尚未执行"} · {patrol.data.runs[0]?.turns ?? 0}轮</p>
          {patrol.data.issues?.length ? <ul>{patrol.data.issues.map(i=><li key={i.id}>{patrolLabels[i.category] || i.category}：{i.occurrences}次待定位信号</li>)}</ul> : <p>当前检查器未发现信号，仍需语义评估。</p>}
        </>)}
      </article>
      <QueryState query={query}>
        {d && (
          <>
            <div className="grid four">
              {[
                {
                  label: "当前记忆",
                  value: d.counts.memories,
                  icon: Database,
                  hint: "已持久化的当前版本",
                },
                {
                  label: "知识来源",
                  value: d.counts.knowledge_sources,
                  icon: BookOpen,
                  hint: "与个人记忆分开存储",
                },
                {
                  label: "人设版本",
                  value: "#" + d.persona_version,
                  icon: BrainCircuit,
                  hint: "仅已确认版本生效",
                },
                {
                  label: "语义验收",
                  value:
                    d.verification_rate == null
                      ? "—"
                      : Math.round(d.verification_rate * 100) + "%",
                  icon: ShieldCheck,
                  hint: d.verification_reason,
                },
              ].map(({ label, value, icon: Icon, hint }) => (
                <article className="panel" key={label}>
                  <div className="section-top">
                    <span className="metric-label">{label}</span>
                    <Icon size={16} color="#82acbf" />
                  </div>
                  <div className="metric-number">{value ?? "—"}</div>
                  <small>{hint}</small>
                </article>
              ))}
            </div>
            <div className="grid two" style={{ marginTop: 20 }}>
              <article className="panel">
                <div className="section-top">
                  <h2>角色自动状态</h2>
                  <Link to="/emotion" className="button secondary small">
                    查看干预 <ArrowUpRight size={12} />
                  </Link>
                </div>
                <div className="metric-number" style={{ fontSize: 22 }}>
                  {d.emotion.label}
                </div>
                <p className="muted">
                  愉悦度 {d.emotion.valence.toFixed(2)} · 唤醒度{" "}
                  {d.emotion.arousal.toFixed(2)}
                </p>
                <div className="section-top">
                  <span className="metric-label">角色活跃度</span>
                  <span>{d.energy.toFixed(2)}</span>
                </div>
                <meter
                  min={0}
                  max={1}
                  value={d.energy}
                  style={{ width: "100%", height: 10 }}
                />
                <small>情绪与活跃度是角色状态，不代表模型准确率。</small>
              </article>
              <article className="panel">
                <div className="section-top">
                  <h2>最近对话事件</h2>
                  <span className="badge">本次服务</span>
                </div>
                {d.recent_events.length === 0 ? (
                  <p className="empty">尚无本次服务的对话事件。</p>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>时间</th>
                          <th>策略</th>
                          <th>路径</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.recent_events.slice(0, 6).map((e, i) => (
                          <tr key={e.timestamp + "-" + i}>
                            <td className="timestamp">
                              {formatTime(e.timestamp)}
                            </td>
                            <td>{e.strategy}</td>
                            <td>{e.route}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </article>
            </div>
            <article className="panel" style={{ marginTop: 20 }}>
              <div className="section-top">
                <h2>最近管理操作</h2>
                <Link to="/audit" className="button secondary small">
                  完整审计 <ArrowUpRight size={12} />
                </Link>
              </div>
              {d.audit.length === 0 ? (
                <p className="empty">
                  还没有管理操作记录。草案不会改变已生效状态。
                </p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>操作</th>
                        <th>结果</th>
                        <th>时间</th>
                        <th>编号</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.audit.slice(0, 5).map((a) => (
                        <tr key={a.id}>
                          <td>{a.operation_type}</td>
                          <td>
                            <span
                              className={
                                "badge " +
                                (a.status === "success" ? "ok" : "error")
                              }
                            >
                              {a.status === "success" ? "已执行" : "失败"}
                            </span>
                          </td>
                          <td className="timestamp">
                            {formatTime(a.created_at)}
                          </td>
                          <td>#{a.id}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </article>
          </>
        )}
      </QueryState>
    </section>
  );
}
