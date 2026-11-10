import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, formatTime } from "../../lib/api";
import type { AuditEvent, Draft, MemoryRow } from "../../lib/types";
import { OperationConfirmDialog } from "../../components/OperationConfirmDialog";
import { ErrorMessage, PageHeading } from "../../components/QueryState";

type Context = { context_key: string; scope: {kind?: string; user_id?: string; target?: string}; updated_at: number };
type Trace = { receipt_key: string; created_at: number; trace: Record<string, unknown> };
export function QQPage() {
  const client = useQueryClient();
  const [key, setKey] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [id, setId] = useState<number | null>(null);
  const [content, setContent] = useState("");
  const prefix = "/qq/contexts/" + key;
  const contexts = useQuery({queryKey:["qq-contexts"], queryFn:()=>apiRequest<Context[]>("/qq/contexts")});
  const memories = useQuery({queryKey:["qq-memory",key], queryFn:()=>apiRequest<MemoryRow[]>(prefix+"/memory?history=1"), enabled:!!key});
  const audit = useQuery({queryKey:["qq-audit",key], queryFn:()=>apiRequest<AuditEvent[]>(prefix+"/audit"), enabled:!!key});
  const traces = useQuery({queryKey:["qq-traces",key], queryFn:()=>apiRequest<Trace[]>(prefix+"/traces"), enabled:!!key});
  const detail = useQuery({queryKey:["qq-detail",key,id], queryFn:()=>apiRequest<MemoryRow>(prefix+"/memory/"+id), enabled:!!key && id!==null});
  const mutation = useMutation({mutationFn:(action:string)=>apiRequest<Draft>(prefix+"/memory/batch-draft", {method:"POST",body:{actions:[{action,id,...(action==="correct"?{content}:{})}]}}), onSuccess:setDraft});
  function refreshed() {
    setDraft(null);setId(null);setContent("");
    for (const name of ["qq-memory","qq-audit","qq-traces","qq-detail"]) void client.invalidateQueries({queryKey:[name,key]});
  }
  return <section>
    <PageHeading title="QQ 会话管理" description="QQ 使用已确认的全局人设和知识。个人记忆按用户与群隔离；修改需预览、确认并记录到该会话审计。" />
    <article className="panel">
      <label htmlFor="qq-context">选择 QQ 会话</label>
      <select id="qq-context" value={key} disabled={!!draft} onChange={e=>{setKey(e.target.value);setId(null);setContent("");mutation.reset();}}>
        <option value="">请选择</option>
        {contexts.data?.map(c=><option key={c.context_key} value={c.context_key}>{c.scope.kind==="group"?`群 ${c.scope.target} · 用户 ${c.scope.user_id}`:c.scope.user_id?`私聊 ${c.scope.user_id}`:`旧会话 ${c.context_key.slice(0,12)}`}</option>)}
      </select>
      <button onClick={()=>{void contexts.refetch();if(key)refreshed();}}>刷新</button>
      <ErrorMessage error={contexts.error} />
      {contexts.data?.length===0 && <p>尚无 QQ 会话。收到消息后在此选择；旧会话暂以摘要编号显示。</p>}
    </article>
    {key && <>
      <article className="panel"><h2>个人记忆</h2><ErrorMessage error={memories.error}/>
        {memories.data?.map(row=><button key={row.id} className="button secondary" onClick={()=>{setId(row.id);setContent(row.content);mutation.reset();}}>#{row.id} [{row.status}] {row.content}</button>)}
        {id!==null && <div><h3>记忆 #{id}</h3><pre>{JSON.stringify(detail.data,null,2)}</pre><ErrorMessage error={detail.error}/>
          <label htmlFor="qq-correction">纠正后的事实</label><textarea id="qq-correction" value={content} maxLength={4000} onChange={e=>setContent(e.target.value)}/>
          <div className="actions">{[['correct','预览纠错'],['badhit','预览标记误召回'],['forget','预览彻底删除']].map(([action,label])=><button key={action} disabled={mutation.isPending || !!draft || (action==='correct' && !content.trim())} onClick={()=>mutation.mutate(action)}>{label}</button>)}</div>
          <ErrorMessage error={mutation.error}/></div>}
      </article>
      <article className="panel"><h2>最近处理记录</h2><ErrorMessage error={traces.error}/>{traces.data?.map(row=><details key={row.receipt_key}><summary>{formatTime(row.created_at)} · {row.receipt_key.slice(0,12)}</summary><pre>{JSON.stringify(row.trace,null,2)}</pre></details>)}</article>
      <article className="panel"><h2>该会话操作审计</h2><ErrorMessage error={audit.error}/>{audit.data?.map(row=><details key={row.id}><summary>#{row.id} {row.operation_type} · {row.status} · {formatTime(row.created_at)}</summary><pre>{JSON.stringify(row,null,2)}</pre></details>)}</article>
    </>}
    {draft && <OperationConfirmDialog key={key+draft.draft_id} draft={draft} apiPrefix={prefix} onClose={()=>setDraft(null)} onApplied={refreshed}/>}
  </section>;
}
