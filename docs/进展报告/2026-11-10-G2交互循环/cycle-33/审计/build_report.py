"""Measured C33 report with primary, post-hoc and fault-control scopes separated."""
import json
import os
from pathlib import Path
import sys
from shared_affect_common import ROOT,BASE,PROTOCOL,digest
sys.path.insert(0,str(BASE/'审计'))
from render_report import render


def read(path):return json.loads(path.read_text())


def main():
    out=BASE/'审计';work=out/'工作目录';primary=work/'001-共享历史隐含情绪';rows=[];strata=[];models=[];continuity=[]
    for label in ('4b','32b'):
        data=read(BASE/('实验/shared-affect-'+label+'/evaluation.json'));proof=read(primary/(label+'-independent-binding.json'));stats=read(primary/(label+'-阶段描述汇总.json'));post=read(work/('003-角色状态连续性补审/'+label+'-posthoc-continuity.json'))
        assert data['completed'] and proof['verified'] and stats['evaluation_sha256']==proof['evaluation_sha256']
        models.append(data);continuity.append(post);gpu=data['provider_ready']['chosen_gpu']
        rows.append([label,'192 / 144 / 48',str(proof['native_calls']),str(proof['candidate_skips']),f"GPU{gpu['index']} / {gpu['uuid']} / {gpu['free_mib']}MiB / {gpu['utilization_percent']}%",f"{data['seconds']:.6f}s"])
        for scope,title in (('implicit_affect','隐含线索'),('neutral_control','中性对照')):
            values=stats['strata'][scope];pairs=[pair for pair in proof['pairs'] if pair['stratum']==scope]
            strata.append([label,title,str(values['pairs']),str(values['skips']),str(values['user_observation_changed']),str(sum(pair['raw_replies_equal'] for pair in pairs)),str(sum(pair['strict_code_correct'][0] for pair in pairs))+'/'+str(sum(pair['strict_code_correct'][1] for pair in pairs))])
    supplemental=read(work/'补审与版本管理独立核验.json');assert supplemental['verified'] and supplemental['individual_group_commits_verified']==96
    retired=read(ROOT/'evals/interaction/cycle-33/implicit-affect-retirement.json');assert retired['native_calls']==730
    after=read(work/'002-工作约定去重/整理后核验.json');before=read(work/'002-工作约定去重/整理前测量.json')
    link=lambda label,path:(label,os.path.relpath(path,out))
    sections=[{'title':'主实验：共享真实准备，隔离两臂来源','paragraphs':[
        '12个既有C31白盒隐含cue与4个中性对照，各固定3重复。每场景/重复只真实准备两回合一次，关闭该OS后SQLite backup两独立库；两臂各新OS、初始PAD0、恢复相同四条user/assistant消息，仅probe分析路径不同。不编辑助手情绪词强制skip，不按实际路由或答案筛选。',
        '两模型各192应用回合/144OS/48共享对，合384/288/96。原生730调用=384生成+342认知+4预热，两个提供方均退出0、未强杀且GPU PID清理；安装0.3.19/54运行文件前后绑定、GGUF/revision与341当前/历史源已核验。C32 logical_reset在每实际completion前执行，不把reset当正确性或全局决定性保证。',
        '采证用时含指纹、模型加载/清理、备份、OS启动和审计写盘，未登记速度收益门槛，不作纯推理时间或跨轮速度比较。所有问题为已知cue/同一代号查询的开发诊断，不是独立真人质量验收。'],
        'table':(['模型','回合/OS/共享对','原生调用','候选skip','实际GPU/启动余量','完整采证时间'],rows),
        'links':[link('预登记协议',ROOT/PROTOCOL),link('341来源执行冻结',primary/'执行冻结.json'),link('原生研究退役',ROOT/'evals/interaction/cycle-33/implicit-affect-retirement.json')]+[link(label+'完整实验',BASE/('实验/shared-affect-'+label+'/evaluation.json')) for label in ('4b','32b')]+[link(label+'独立原SDK/SQL/SSE/API/模块/状态核验',primary/(label+'-independent-binding.json')) for label in ('4b','32b')]},
        {'title':'候选观察：正确代号不等于情绪行为相同','paragraphs':[
        '4B实际skip24（隐含12/36、中性12/12），其余24因recent_affect委托；32B skip18（隐含6/36、中性12/12），其余30委托。共享实际助手回复会触发词表保护，这是实际覆盖结果，不能用原单条白盒history的eligible率替代。',
        '4B48对用户观测/原文相同；32B两隐含cue各3重复，共6/48对用户delta、PAD及style改变。例05：当前分析用户[-0.4,-0.3]、角色[0.05,-0.2]、风格清晰耐心·沉稳；候选均0、风格清晰耐心；双方均答AB-2738。两模型原文各48/48相同，严格代号两臂各48/48。',
        '这已否定本批32B“保持默认情绪行为不变”的描述，不证明真人情绪真值或体验退化；用户只要代号，不应强求额外安慰文字。4B无差异也不证明一般语义中性。32B默认分析27组用户/角色非0，其中21组两臂同样分析，另6组不同；差异数与绝对非0数须分开。C31候选继续隔离，不新建事后推广门槛。'],
        'table':(['模型','分层','对数','实际skip','用户观测改变','原文相同','严格对照/候选'],strata),
        'links':[link('C31-002延续问题与完整例',out/'问题单/C33-006-只读候选改变部分隐含情绪观测.md')]+[link(label+'分层描述',primary/(label+'-阶段描述汇总.json')) for label in ('4b','32b')]},
        {'title':'系统补审：数值状态、来源失效与过程留痕','paragraphs':[
        '事后补审明确不属于主实验预登记终点、没有新模型调用：4B27/48、32B36/48组旧角色PAD非0，新OS均从0开始，同时四角色/同revision0/未红删完整恢复。当前分析probe用户/角色为0分别48与21组。文本恢复与数值状态连续性分离，这是已披露限制的量化，不证明保存一定改善质量。',
        '补充真实HTTP/假模型方法、各3重复：遗忘已完成情绪来源后源红删/revision0→1，但3/3仍返回旧用户[-0.4,0.3]，随后中性角色PAD仍约[0.04999,-0.19996]。这是开放的进程内自动状态失效问题，应先修，再研究持久化。另3次认知完成后显式取消生成均cancelled/无助手结果，观测仍可保留；按既有取消合同不能直接判为必须回滚，避免撤销合法已提交输入/动作。',
        '资料提交71407a7误收活动32B快照，completed=False；原历史与根快照字节保留，225新增路径移出index后按闭合组重新独立提交，原生输入/运行未改。独立核验96个不同共享组各有单独提交。AGENTS初始整理90023→11578字节、506→124行、58→12二级标题，十节项目参考字节未变；测量绑定c11e2e5，后续只更新当前阶段，不冒称真人阅读提速。'],
        'table':(['核验或补审','规模/数据','结果与解释'],[
            ['共享备份/委托/隔离/删除CPU控制','8项，真实进程内Web+假方法','通过；非HTTP/OS/GPU'],
            ['真实子进程前置拒绝','3项，无模型/DB输出','通过；未计入native请求'],
            ['真实HTTP补审','12提交=9result/3cancelled，6SQL末态','遗忘3复现未修；取消3保留行为披露'],
            ['数值状态连续性（事后）','4B27/48、32B36/48旧非0→新初始0','工程限制量化；无真人质量批准'],
            ['版本与交接资料','96组独立提交；225误入路径原Git/SHA；原文/尾段SHA','独立程序验证，历史不改写']]),
        'links':[link('补审与版本管理独立核验',work/'补审与版本管理独立核验.json'),link('真实HTTP/SSE/SQL补审',work/'004-遗忘与取消情绪状态补审/controlled-http-state.json'),link('CPU8项工程控制',primary/'shared-cpu-controls.json'),link('进程前置3负控',primary/'前置负控/controls.json')]+[link(label+'事后状态连续性',work/('003-角色状态连续性补审/'+label+'-posthoc-continuity.json')) for label in ('4b','32b')]+[link('工作约定整理测量',work/'002-工作约定去重/整理后核验.json'),link('误收快照与纠正记录',work/'005-运行中快照误入暂存/纠正与原快照清单.json')]},
        {'title':'问题状态、默认产品与推进优先级','paragraphs':[
        '本轮产品src/tests/scripts未改；完整1769 passed/1 skipped与552输入、默认浏览器15 passed/16 optional skipped与190输入仍为C29历史执行，不冒称新回归。前端153/CYNSx0Ec仍旧快照。旧C3–C32共30封存的逐文件收尾核验单独保存。',
        '下一阶段先修C33-004：让自动情绪/相关诊断随当前隐私版本失效，覆盖API与新回复，并用同源真实HTTP before/after及完整回归验证。取消并非遗忘，不默认回滚合法已完成输入/观测/事实/提醒。该边界完善后才考虑跨OS数值连续性；候选仍隔离，通用C19-001 P1、真实设备/真人/多日验收继续开放。',
        '解释勘误保留：早期把6个组间差异误写成仅6组绝对非0，实际为27；将取消保留直接定为需回滚也过强，现按合同披露。原始实验JSON/独立证明未重写，报告直接读完整测量，人工解释不替代数据。阶段研究完成不等于代际跃迁或整个远期目标完成。'],
        'table':(['单项','优先级/状态','结论与方向'],[
            ['C33-001 工作约定历史堆积','P3 按文档范围关闭','完整旧文/规范/项目尾段保留，当前入口整理'],
            ['C33-002 角色PAD跨OS连续性','P2 开放（既有工程限制）','27/36组量化；先修失效再扩展'],
            ['C33-003 活动快照误入资料提交','P3 过程纠正关闭','不改历史/输入；最终证据独立绑定'],
            ['C33-004 遗忘未使自动数值失效','P2 开放/下一阶段优先','3/3受控复现；需修版本失效/API/新回复'],
            ['C33-005 取消后观测语义','P3 文档披露关闭','当前合同下不直接判缺陷，不增加回滚承诺'],
            ['C33-006 延续C31-002候选保护','P2 开放，不重复计新缺陷','32B6对观测改变；原文同不代表无变化']]),
        'links':[link(path.stem,path) for path in sorted((out/'问题单').glob('*.md'))]+[link('全过程进展与勘误',BASE/'进展.md')]}]
    metadata=render(out,'第三十三轮系统审计与推进报告','共享真实准备历史、隐含情绪诊断与数值状态补审；单一作者代理核验，非独立人评。','730原生调用/384应用回合/288OS证据完整；只读候选保持隔离，确认遗忘数值失效待修，取消观测按现有合同披露。',sections,BASE.parent/'cycle-32/审计/系统审计与推进报告.html')
    (out/'report-render-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');print(metadata)


if __name__=='__main__':main()
