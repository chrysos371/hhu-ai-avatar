import { ModelSettings, SharedMemorySettings } from "./BrainSettings";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, Sparkles } from "lucide-react";
import { apiRequest } from "../../lib/api";
import type { Draft, PersonaVersion } from "../../lib/types";
import { PageHeading, ErrorMessage } from "../../components/QueryState";
import { OperationConfirmDialog } from "../../components/OperationConfirmDialog";

type Card = {id:string; name:string; description:string; accent:string; has_portrait:boolean; backend_model:string; persona_origin:string; art:{creators?:string[]; source_url?:string; license?:{identifier?:string; note?:string}}};
type Message = {id:number;role:string;content:string};
function PersonaEditor({id,persona}:{id:string;persona:PersonaVersion}) {
  const client=useQueryClient();
  const [name,setName]=useState(persona.data.name);
  const [identity,setIdentity]=useState(persona.data.core_identity);
  const [expression,setExpression]=useState(persona.data.expression_principles);
  const [draft,setDraft]=useState<Draft|null>(null);
  const prefix='/characters/'+id+'/config';
  const save=useMutation({mutationFn:()=>apiRequest<Draft>(prefix+'/persona/draft',{method:'POST',body:{changes:{name,core_identity:identity,expression_principles:expression}}}),onSuccess:setDraft});
  return <details className="character-editor"><summary>编辑这个角色的人设 · 当前版本 #{persona.id}</summary>
    <p className="muted">只修改当前角色。初始人设由本项目编写，可按你的喜好调整。</p>
    <label htmlFor="role-name">角色称呼</label><input id="role-name" value={name} maxLength={40} onChange={e=>setName(e.target.value)}/>
    <label htmlFor="role-identity">性格与身份</label><textarea id="role-identity" value={identity} maxLength={2000} onChange={e=>setIdentity(e.target.value)}/>
    <label htmlFor="role-expression">表达习惯</label><textarea id="role-expression" value={expression} maxLength={2000} onChange={e=>setExpression(e.target.value)}/>
    <button className="button secondary" disabled={save.isPending || !name.trim() || !identity.trim()} onClick={()=>save.mutate()}>预览人设修改</button>
    <ErrorMessage error={save.error}/>
    {draft && <OperationConfirmDialog draft={draft} apiPrefix={prefix} onClose={()=>setDraft(null)} onApplied={()=>{setDraft(null);void client.invalidateQueries({queryKey:['character-persona',id]});}}/>}
  </details>;
}

export function CharactersPage() {
  const client=useQueryClient();
  const [selected,setSelected]=useState(()=>sessionStorage.getItem('avatar-character') || 'deepseek');
  const [text,setText]=useState('');
  const cards=useQuery({queryKey:['characters'],queryFn:()=>apiRequest<Card[]>('/characters')});
  const card=cards.data?.find(c=>c.id===selected);
  const base='/characters/'+encodeURIComponent(selected);
  const portrait=useQuery({queryKey:['character-portrait',selected],queryFn:()=>apiRequest<{data_url:string|null}>(base+'/portrait'),enabled:!!card?.has_portrait,staleTime:Infinity});
  const history=useQuery({queryKey:['character-history',selected],queryFn:()=>apiRequest<Message[]>(base+'/history'),enabled:!!card});
  const traces=useQuery({queryKey:['character-traces',selected],queryFn:()=>apiRequest<Record<string,unknown>[]>(base+'/traces'),enabled:!!card});
  const persona=useQuery({queryKey:['character-persona',selected],queryFn:()=>apiRequest<PersonaVersion>(base+'/config/persona'),enabled:!!card});
  const send=useMutation({mutationFn:({id,text}:{id:string;text:string})=>apiRequest<{reply:string;character_id:string;trace:Record<string,unknown>}>('/characters/'+id+'/chat',{method:'POST',body:{text}}),
    onSuccess:async(_result,input)=>{setText('');await client.invalidateQueries({queryKey:['character-history',input.id]});await client.invalidateQueries({queryKey:['character-traces',input.id]});}});
  function choose(id:string){if(send.isPending)return;setSelected(id);sessionStorage.setItem('avatar-character',id);setText('');send.reset();}
  return <section>
    <PageHeading title="角色馆" description="选一个喜欢的形象，开始你们自己的对话。每个角色都有独立的人设、记忆和情绪。"/>
    <ErrorMessage error={cards.error}/>
    {cards.isPending && <p role="status">正在打开角色馆…</p>}
    <div className="character-layout">
      <aside className="character-list panel" aria-label="角色选择">
        <small className="eyebrow">CHOOSE YOUR COMPANION</small>
        {cards.data?.map(c=><button key={c.id} className={'character-choice'+(c.id===selected?' selected':'')} style={{borderColor:c.id===selected?c.accent:undefined}} aria-pressed={c.id===selected} disabled={send.isPending} onClick={()=>choose(c.id)}>
          <span className="character-orb" style={{background:c.accent}}/>
          <span><strong>{c.name}</strong><small>{c.has_portrait?'立绘已导入':'文字角色 · 立绘待补'}</small></span>
        </button>)}
      </aside>
      {card && <div>
        <div className="character-engine"><Sparkles size={14}/><span>实际模型：{card.backend_model} · 社区拟人角色，切换外观不会切换厂商模型</span></div>
        <div className="character-stage panel">
          <div className="character-visual">
            <div className="character-portrait" style={{borderColor:card.accent}}>
              {portrait.data?.data_url ? <img src={portrait.data.data_url} alt={card.name+'立绘'}/> : <div className="character-placeholder" style={{color:card.accent}}><Sparkles size={64}/><p>{card.has_portrait?'正在读取立绘…':'立绘待补，仍可体验人设'}</p></div>}
            </div>
            <h2>{persona.data?.data.name || card.name}</h2>
            <p className="muted">{card.description}</p>
            <ErrorMessage error={portrait.error}/>
            <details className="character-credits"><summary>形象来源与署名</summary><p>{card.art.creators?.join(' / ') || '图片尚未导入'}</p>{card.art.source_url && <a href={card.art.source_url} target="_blank" rel="noreferrer">查看原作 ↗</a>}<p>{card.art.license?.identifier || card.art.license?.note || '逐项使用说明见本地素材档案。'}</p><p>图片不属于本项目原创，人设为项目自定义。</p></details>
          </div>
          <div className="character-conversation">
            <div className="section-top"><h2>和 {persona.data?.data.name || card.name} 聊聊</h2><span className="badge">独立记忆</span></div>
            <div className="character-messages" aria-live="polite">
              {!history.data?.length && <div className="empty"><p>你们的故事，从这一句开始。</p><small>不会读取其他角色或 QQ 会话的私人记忆。</small></div>}
              {history.data?.map(m=><article key={m.id} className={'chat-message '+m.role}><small>{m.role==='user'?'你':persona.data?.data.name || card.name}</small><div>{m.content}</div></article>)}
              {send.isPending && <p role="status">正在想怎么回应你…</p>}
            </div>
            <ErrorMessage error={history.error}/><ErrorMessage error={send.error}/>
            <form onSubmit={e=>{e.preventDefault();if(text.trim()&&!send.isPending)send.mutate({id:selected,text:text.trim()});}}>
              <label htmlFor="character-message">发给当前角色</label>
              <textarea id="character-message" value={text} maxLength={4000} rows={3} disabled={send.isPending} onChange={e=>setText(e.target.value)} placeholder="分享今天的心情，或交给她一个小任务…"/>
              <div className="actions"><button className="button" disabled={send.isPending||!text.trim()}><Send size={14}/>{send.isPending?'等待回复…':'发送'}</button></div>
            </form>
            <ModelSettings key={'model:'+selected} id={selected}/>
            <SharedMemorySettings cards={cards.data||[]}/>
            <details><summary>最近一轮处理记录</summary><ErrorMessage error={traces.error}/><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{traces.data?.[0]?JSON.stringify(traces.data[0],null,2):'暂无处理记录'}</pre></details>
            <ErrorMessage error={persona.error}/>
            {persona.data && <PersonaEditor key={selected+':'+persona.data.id} id={selected} persona={persona.data}/>}
          </div>
        </div>
      </div>}
    </div>
  </section>;
}
