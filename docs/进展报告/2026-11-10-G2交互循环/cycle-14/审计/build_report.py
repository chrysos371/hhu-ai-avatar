from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
CYCLE=HERE.parent
EV=CYCLE/'实验'
def read(p):return json.loads((EV/p).read_text())

def build():
    before=read('before/mixed-writer.json')
    runs=[read(f'fixed-{i}/mixed-writer.json') for i in [1,2,3]]
    assert before['completed'] and len(before['cases'])==9 and sum(c['passed'] for c in before['cases'])==5
    for run in runs:
        assert run['completed'] and run['allPassed'] and len(run['cases'])==9
        for case in run['cases']:
            assert case['passed'] and all(case['checks'].values()) and case['failure'] is None
    external,notify=read('external-notification/external-erase.json'),read('external-notification/notification.json')
    restore=read('restore/restore.json')
    assert external['completed'] and len(external['rows'])==12 and all(not r['oldTraceVisible'] for r in external['rows'])
    assert notify['completed'] and len(notify['steps'])==8 and not notify['errors']
    assert restore['completed'] and len(restore['turns'])==54 and not restore['errors']
    assert len(restore['steps'][2]['ids'])==len(set(restore['steps'][2]['ids']))==108
    assert restore['steps'][3]['draft'] and len(restore['steps'][3]['snapshot']['items'])==109 and restore['steps'][-1]['submitted']==55
    full=re.search(r'(\d+) passed, (\d+) skipped in ([\d.]+)s',(EV/'python-full.log').read_text())
    assert full and int(full[1])==1067 and int(full[2])==1
    checked=read('snapshot-check.json');assert checked['allPassed']
    issue=next((HERE/'issues').glob('*.md'))
    lines=['# 第十四轮系统审计与推进报告','',
      '日期：2026-11-11（上海时间）。作者：spinner-bot。行为基线725a5da，修前采样692b693、修后冻结28b8542。远期Goal继续active。','',
      '## 当前结论','',
      '修复一项P1组合缺口：其他调用路径写入用户消息后执行遗忘，原隐私fence会跨过未跟踪用户来源而保留真人权限。冻结9项矩阵修前5通过/4失败，修后三轮各9通过，原姓名/提醒越权消失，已跟踪真人与纯助手对照保持可用。','本轮仅实际执行同一OS进程中的Avatar、Web run_chat和不同SQLite连接，CLI是等价编排调用，不是交互CLI子进程；不据此批准所有多写入方、真实模型、完整语义或多日稳定。第十三轮OS重启数据另存，不混范围。','',
      '## 原始失败与修复','',
      '原Web控制cursor=1、scope=current_user；另一个Avatar或直接写入新增用户来源3，但未更新Web控制。遗忘推进revision0→1、cursor→3/4，清空basis却保留current_user。后续Web缺口检查只看新fence之后，于是跳过用户来源3，误将新姓名写入真人资料或创建真实提醒。原状态链和每条实际结果见before/mixed-writer.json。','修复在同一隐私事务推进fence之前检查旧cursor之后的user来源；有缺口只能unverified，再清basis和推进fence。旧受限状态仍受限，无缺口的已跟踪真人保持可用；assistant消息不授予用户权限，也不单独触发用户来源缺口。只查来源ID/角色，不解析或重放旧原文。','',
      '| 冻结场景 | 修前 | 固定三轮修后 |','| --- | --- | --- |']
    labels={'tracked_real_erase':'已跟踪真人+遗忘','cli_role_no_erase':'CLI等价角色，无遗忘','cli_role_erase_name':'CLI等价角色→遗忘→姓名','cli_role_erase_reminder':'CLI等价角色→遗忘→提醒','direct_user_erase_name':'直接用户写入→遗忘→姓名','cli_role_after_erase':'先遗忘→CLI等价角色→提醒','assistant_only_erase':'仅助手写入→遗忘','cli_real_erase':'未跟踪普通用户→遗忘','tracked_role_erase':'另一个已跟踪Web角色→遗忘'}
    for case in before['cases']:
        lines.append(f"| {labels[case['id']]} | {'通过' if case['passed'] else '失败：不应有的真人权限'} | 3/3通过 |")
    lines += ['',
      '不带遗忘时原未跟踪用户检查已经保守生效，问题来自两个单独检查的组合。普通CLI用户消息也不能仅因看似无害就被隐私fence跳过；无法核验的来源按同一契约要求明确确认。修后每个预期unverified的场景另执行单独现实确认和新真人请求，姓名可恢复写入且没有重放被阻断的提醒。','',
      '## 固定实验与回归','',
      '| 轮次 | 原矩阵通过 | 采样器观察秒数 | 来源冻结 |','| --- | --- | --- | --- |']
    for i,run in enumerate(runs,1):lines.append(f"| {i} | 9/9 | {run['elapsedSeconds']:.6f} | 每场景前后SHA相同 |")
    lines += ['',
      f"修前观察{before['elapsedSeconds']:.6f}秒。三轮是同机、同一原矩阵重放，每场景独立临时库，不是独立语义新样本。修后更多场景进入确认恢复分支，执行步数不同；观察时间不作加速比、吞吐或退化结论。未放宽原期望值或把失败加入允许集合。",'',
      '| 检查 | 实际结果 |','| --- | --- |',
      '| 混合写入原矩阵回归 | 修前4失败/5通过；修后关联70项通过1.93秒，非独立新样本 |',
      f'| 完整Python | {full[1]}通过/{full[2]}跳过，{full[3]}秒 |',
      '| 外部删除/通知浏览器 | 2通过11.4秒，原12RAF均无旧trace；通知8步骤含真实PCM停止、部分草稿清理 |',
      f"| 历史恢复浏览器 | {restore['elapsedSeconds']:.3f}秒，54完成+1实际草稿取消、108来源ID无重复、取消后109条、跨tab/迟到旧快照屏障，总提交55 |",'',
      '前端生产源码未改。本轮未重跑默认全浏览器、前端单元/lint/类型/build、独立百轮和原PCM三项；前端76单元及百轮/PCM全记录为第十二轮，默认15通过/11可选跳过为第十三轮快照，均不冒称本轮结果。四项真实模型/ASR可选服务未跑，没有使用GPU。','',
      '## 单项结论与边界','',
      '| 方面 | 当前结论 |','| --- | --- |',
      f'| [{issue.stem}](issues/{issue.name}) | 当前冻结9场景内修复，原始4失败与所有状态保留 |',
      '| 来源/权限 | 旧fence后的未跟踪用户不能因隐私失效被跳过；不是所有外部写入协议完整性证明 |',
      '| 会话与模型 | Web有界控制/指代接续已有证据，一般生成短期/PAD/任务与CLI自身跨进程仍开放 |',
      '| 远期质量 | 原生模型归属/身体边界、模板充分性、真人音素/ü/声调、物理设备/正式渲染及多日未验收 |','',
      '后续转向既有G2C2-009/016的真实模型原生回复审计，先冻结输入、原生输出与创作/引用/否定等保留对照；按实际GPU余量启动自有模型，默认候选不因局部字面检查而放行。继续保留来源/隐私/动作全量回归和新组合审计；不以本轮有限通过宣称整体代际跃迁。','',
      '## 过程与证据','',
      f"{checked['checked']}项源/服务包绑定通过；修前内存实现按692b693提交树核验，修后完整冻结源留在实验/frozen-source，浏览器服务包与第十二轮同SHA归档比对。原失败JSON/日志和矩阵回归重放分开，未以测试总数充当模型质量。",'[计划](../计划.md)、[进展](../进展.md)、[冻结协议](../../../../../evals/interaction/cycle-14/mixed-writer-protocol.json)、[源核对](../实验/snapshot-check.json)、[证据清单](证据清单.json)、[远期路线](../../远期目标与验收路线.md)。','']
    for p in sorted(EV.iterdir()):
        if p.is_file() and p.suffix in ('.json','.log'):lines.append(f'- [{p.name}](../实验/{p.name})')
        elif p.is_dir() and (p/'mixed-writer.json').exists():lines.append(f'- [{p.name}/mixed-writer.json](../实验/{p.name}/mixed-writer.json)')
    (HERE/'系统审计与推进报告.md').write_text('\n'.join(lines)+'\n')
    def inline(s):return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',escape(s))
    body=[];table=False
    for line in lines:
        if line.startswith('| ---'):continue
        if line.startswith('|'):
            if not table:body.append('<div class="table-wrap"><table>');tag='th';table=True
            else:tag='td'
            body.append('<tr>'+''.join(f'<{tag}>'+inline(c)+f'</{tag}>' for c in line.strip('| ').split(' | '))+'</tr>');continue
        if table:body.append('</table></div>');table=False
        if line.startswith('# '):body.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):body.append('<h2>'+inline(line[3:])+'</h2>')
        elif line:body.append('<p>'+inline(line.removeprefix('- '))+'</p>')
    style=re.search(r'<style>(.*?)</style>',(HERE.parent.parent/'cycle-13/审计/系统审计与推进报告.html').read_text()).group(0)
    html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第十四轮系统审计与推进报告</title>'+style+'<main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    inputs=list(EV.rglob('*'))+list((HERE/'issues').glob('*.md'))+list(HERE.glob('*.py'))+list(HERE.glob('*.mjs'))+list(HERE.glob('*.png'))+[CYCLE/'计划.md',CYCLE/'进展.md',HERE/'系统审计与推进报告.md',HERE/'系统审计与推进报告.html']
    manifest={p.relative_to(CYCLE).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(inputs) if p.is_file()}
    (HERE/'证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    for href in re.findall(r'href="([^"]+)"',html):assert (HERE/href).exists(),href
    print(len(manifest),'evidence hashes; fixed gates and local links valid')

if __name__=='__main__':build()
