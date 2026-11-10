import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../lib/api';
import { ErrorMessage } from '../../components/QueryState';

type Profile={id:string;model:string;structured_analysis:string;tools:boolean;thinking:boolean|null};
type Fact={id:string;key:string;value:string;characters:string[]};
type Audit={id:number;fact_id:string;action:string};
type Card={id:string;name:string};

export function ModelSettings({id}:{id:string}) {
  const client=useQueryClient();
  const [choice,setChoice]=useState('');
  const models=useQuery({queryKey:['model-profiles'],queryFn:()=>apiRequest<Profile[]>('/characters/models')});
  const current=useQuery({queryKey:['character-model',id],queryFn:()=>apiRequest<Profile>('/characters/'+id+'/model')});
  const save=useMutation({mutationFn:()=>apiRequest('/characters/'+id+'/model',{method:'POST',body:{profile_id:choice}}),onSuccess:async()=>{await client.invalidateQueries({queryKey:['character-model',id]});await client.invalidateQueries({queryKey:['characters']});setChoice('');}});
  return <details><summary>模型配置</summary>
    <p>切换模型保留当前角色的人设和记忆。这里只列出已配置的服务，未验证服务在线状态。</p>
    <label htmlFor="role-model">当前角色使用的模型</label>
    <select id="role-model" value={choice||current.data?.id||'default'} onChange={e=>setChoice(e.target.value)}>{models.data?.map(p=><option key={p.id} value={p.id}>{p.id} · {p.model}</option>)}</select>
    <button className="button secondary" disabled={!choice||save.isPending} onClick={()=>save.mutate()}>应用模型</button>
    <ErrorMessage error={models.error||current.error||save.error}/>
  </details>;
}

export function SharedMemorySettings({cards}:{cards:Card[]}) {
  const client=useQueryClient();
  const [key,setKey]=useState('preference');const [value,setValue]=useState('');
  const [scope,setScope]=useState<string[]>([]);const [editing,setEditing]=useState<string|null>(null);
  const data=useQuery({queryKey:['shared-facts'],queryFn:()=>apiRequest<{facts:Fact[];audit:Audit[]}>('/characters/shared-facts')});
  const change=useMutation({mutationFn:({body,undo=false}:{body:Record<string,unknown>;undo?:boolean})=>apiRequest('/characters/shared-facts'+(undo?'/undo':''),{method:'POST',body}),onSuccess:async()=>{setValue('');setScope([]);setEditing(null);await client.invalidateQueries({queryKey:['shared-facts']});}});
  function edit(f:Fact){setEditing(f.id);setKey(f.key);setValue(f.value);setScope(f.characters);}
  return <details><summary>管理跨角色共享事实</summary>
    <p>仅在本机角色馆内共享你明确填写的称呼、饮食和偏好。默认不共享；角色关系与共同经历独立，QQ身份尚未绑定。</p>
    <label htmlFor="shared-key">事实类型</label><select id="shared-key" value={key} onChange={e=>setKey(e.target.value)}><option value="name">称呼</option><option value="diet">饮食</option><option value="preference">偏好</option></select>
    <label htmlFor="shared-value">共享内容</label><input id="shared-value" value={value} maxLength={300} onChange={e=>setValue(e.target.value)}/>
    <fieldset><legend>允许读取的角色</legend>{cards.map(c=><label key={c.id}><input type="checkbox" checked={scope.includes(c.id)} onChange={e=>setScope(e.target.checked?[...scope,c.id]:scope.filter(v=>v!==c.id))}/>{c.name}</label>)}</fieldset>
    <button className="button secondary" disabled={!value.trim()||change.isPending} onClick={()=>change.mutate({body:{key,value,characters:scope,...(editing?{fact_id:editing}:{})}})}>{editing?'保存事实修改':'保存共享事实'}</button>
    {editing&&<button className="button secondary" onClick={()=>{setEditing(null);setValue('');setScope([]);}}>取消编辑</button>}
    <ErrorMessage error={data.error||change.error}/>
    {data.data?.facts.map(f=><article key={f.id}><p>{f.value} · {f.characters.length?f.characters.map(id=>cards.find(c=>c.id===id)?.name||id).join('、'):'不共享'}</p><button disabled={change.isPending} onClick={()=>edit(f)}>编辑共享范围</button> <button disabled={change.isPending} onClick={()=>change.mutate({body:{fact_id:f.id,revoke:true}})}>撤销共享</button></article>)}
    {data.data?.audit[0]&&data.data.audit[0].action!=='undo'&&<button disabled={change.isPending} onClick={()=>change.mutate({body:{fact_id:data.data!.audit[0].fact_id},undo:true})}>撤回最近一次事实操作</button>}
    <p className="muted">修改范围后，下轮重新构建上下文；已有聊天记录仍保留供你查看，无法收回已经看见的回复。</p>
  </details>;
}
