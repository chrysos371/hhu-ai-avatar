import { fireEvent, screen } from "@testing-library/react";
import { renderPage, response, draftFixture } from "../../test/render";
import { QQPage } from "./QQPage";
afterEach(()=>vi.unstubAllGlobals());
it("QQ correction previews and confirms through the selected context only",async()=>{
  const key="a".repeat(64);
  const f=vi.fn(async(path:string)=>response(
    path.endsWith('/qq/contexts')?[{context_key:key,scope:{kind:'private',user_id:'23456'},updated_at:1}]:
    path.endsWith('/memory/batch-draft')?draftFixture('memory.batch'):
    path.endsWith('/confirm')?{audit_id:7}:
    path.endsWith('/memory/1')?{id:1,content:'名字: 小林',status:'active'}:
    path.includes('/memory?')?[{id:1,content:'名字: 小林',status:'active'}]:[]
  ));
  vi.stubGlobal('fetch',f);renderPage(<QQPage/>);
  await screen.findByRole('option',{name:'私聊 23456'});
  fireEvent.change(screen.getByLabelText('选择 QQ 会话'),{target:{value:key}});
  fireEvent.click(await screen.findByRole('button',{name:'#1 [active] 名字: 小林'}));
  fireEvent.change(screen.getByLabelText('纠正后的事实'),{target:{value:'小周'}});
  fireEvent.click(screen.getByRole('button',{name:'预览纠错'}));
  expect(await screen.findByRole('dialog')).toBeInTheDocument();
  expect(f.mock.calls.some(([p])=>p.endsWith('/confirm'))).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'确认执行'}));
  await screen.findByRole('button',{name:'刷新'});
  expect(f.mock.calls.some(([p])=>p.includes('/qq/contexts/'+key+'/operations/')&&p.endsWith('/confirm'))).toBe(true);
});
