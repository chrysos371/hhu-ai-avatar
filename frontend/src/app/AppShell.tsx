import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { Activity, BookOpen, BrainCircuit, Clock3, Gauge, Menu, MessageSquare, Orbit, ScanLine, ShieldCheck, SlidersHorizontal, Wrench } from 'lucide-react';

export const navigation = [
  {path:'/',label:'总览',icon:Gauge}, {path:'/chat',label:'对话观测',icon:MessageSquare},
  {path:'/persona',label:'人设管理',icon:BrainCircuit}, {path:'/emotion',label:'情绪干预',icon:Activity},
  {path:'/memory',label:'记忆中枢',icon:ScanLine}, {path:'/knowledge',label:'知识与学习',icon:BookOpen},
  {path:'/reminders',label:'提醒',icon:Clock3}, {path:'/tools',label:'工具',icon:Wrench},
  {path:'/audit',label:'操作审计',icon:ShieldCheck},
];

export function AppShell() {
  const [expanded,setExpanded]=useState(false);
  return <div className={'app-shell'+(expanded?' expanded':'')}>
    <a className="skip-link" href="#main">跳转至内容</a>
    <aside className="sidebar">
      <div className="brand"><div className="brand-symbol"><Orbit size={25}/></div><div className="nav-label"><strong>小海</strong><small>DIGITAL MIND</small></div></div>
      <div className="nav-caption nav-label">MISSION CONTROL</div>
      <nav aria-label="主导航">{navigation.map(({path,label,icon:Icon})=><NavLink key={path} to={path} end={path==='/'} aria-label={label} title={label} className={({isActive})=>'nav-link'+(isActive?' active':'')}><Icon size={18} aria-hidden="true"/><span className="nav-label">{label}</span></NavLink>)}</nav>
      <div className="sidebar-footer"><SlidersHorizontal size={16}/><span className="nav-label">认知管理 · v0.1</span></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label="展开导航" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}><Menu size={19}/></button><span className="eyebrow">HHU / AVATAR</span><span className="topbar-divider"/><span>认知控制台</span></div><span className="local-warning"><span className="status-dot"/>单用户 · 本机运行</span></header>
      <main id="main"><Outlet/></main>
      <footer className="workspace-footer">所有管理变更均需预览与确认 <span>LOCAL FIRST · AUDITABLE</span></footer>
    </div>
  </div>;
}
