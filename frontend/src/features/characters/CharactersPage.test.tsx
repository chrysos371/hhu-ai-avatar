import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderPage, response, personaFixture } from "../../test/render";
import { CharactersPage } from "./CharactersPage";
afterEach(()=>{vi.unstubAllGlobals();sessionStorage.removeItem('avatar-character');});
it('switches explicit role endpoints and does not reuse another role transcript',async()=>{
 const f=vi.fn(async(path:string)=>response(
  path.endsWith('/characters')?[
   {id:'deepseek',name:'DeepSeek · 鲸鱼娘',description:'沉静',accent:'#69b9e8',has_portrait:false,art:{},backend_model:'local-4b'},
   {id:'gpt',name:'GPT · 白龙娘',description:'耐心',accent:'#d6e5d8',has_portrait:false,art:{},backend_model:'local-4b'}]:
  path.endsWith('/shared-facts')?{facts:[],audit:[]}:
  path.endsWith('/models')?[{id:'default',model:'local-4b'}]:
  path.endsWith('/model')?{id:'default',model:'local-4b'}:
  path.includes('/config/persona')?personaFixture:
  path.endsWith('/deepseek/history')?[{id:1,role:'user',content:'只告诉鲸鱼娘的消息'}]:[]
 ));
 vi.stubGlobal('fetch',f);renderPage(<CharactersPage/>);
 expect(await screen.findByText('只告诉鲸鱼娘的消息')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/GPT · 白龙娘/}));
 await waitFor(()=>expect(screen.queryByText('只告诉鲸鱼娘的消息')).not.toBeInTheDocument());
 expect(f.mock.calls.some(([p])=>p.endsWith('/characters/gpt/history'))).toBe(true);
 expect(screen.getByText(/实际模型：local-4b/)).toBeInTheDocument();
});
