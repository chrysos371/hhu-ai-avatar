import { createBrowserRouter } from 'react-router-dom';
import { AppShell, navigation } from './AppShell';
export function createRouter() {
  return createBrowserRouter([{element:<AppShell/>,errorElement:<div role="alert">页面加载失败，请刷新后重试。</div>,children:navigation.map(n=>({path:n.path,element:<section><div className="page-heading"><div><p className="eyebrow">MISSION CONTROL</p><h1>{n.label}</h1></div></div><div className="panel empty">功能模块正在接入。这里将展示真实数据。</div></section>}))}]);
}
