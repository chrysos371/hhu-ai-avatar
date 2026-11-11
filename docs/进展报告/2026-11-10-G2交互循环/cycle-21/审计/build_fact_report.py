"""Validate immutable cognition transaction evidence and render its stage."""
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
WORK=HERE/'工作目录/010-认知事实事务来源'
TITLE='认知事实事务来源修复报告'


def build():
    versions={}
    def bind(name,expected,refs):
        for ref in refs:
            result=subprocess.run(['git','show',ref+':'+name],cwd=ROOT,capture_output=True)
            if result.returncode==0 and sha256(result.stdout).hexdigest()==expected:
                versions.setdefault(name+':'+expected,{'path':name,'sha256':expected,'git_ref':ref});return
        raise AssertionError('Unbound source '+name)
    before=json.loads((WORK/'facts-before.json').read_text());after=json.loads((WORK/'facts-after.json').read_text())
    for data in (before,after):
        assert data['completed'] and len(data['cases'])==6
        for row in data['cases']:
            assert row['cleanup'] and row['verified_facts']
            assert row['terminal']==('result' if row['change']=='normal' else 'cancelled')
            assert len(row['requests'])==(2 if row['change']=='normal' else 1)
            assert row['assistant_count']==int(row['change']=='normal')
        for name,expected in data['source_sha256'].items():bind(name,expected,('4e28690','bcdd967'))
    old={r['change']:r for r in before['cases']};new={r['change']:r for r in after['cases']}
    assert old['same_forget']['final_profile']==old['same_correct']['final_profile']=={'名字':'小岚'}
    assert new['same_forget']['final_profile']==new['external_forget']['final_profile']=={}
    assert new['same_correct']['final_profile']==new['external_correct']['final_profile']=={'名字':'阿澄'}
    assert len(old['cancel']['sources'])==1 and new['cancel']['sources']==[]
    assert all(source['source_message_id'] is None for source in old['same_forget']['sources'])
    full=json.loads((WORK/'full-facts-binding.json').read_text())
    assert sha256((WORK/'python-full-facts-final.log').read_bytes()).hexdigest()==full['log_sha256']
    for name,expected in full['sha256'].items():bind(name,expected,(full['git_ref'],))
    for ref in ('3f98608','440e922','054249b'):
        for name in ('src/avatar/main.py','tests/test_fact_transaction_boundary.py'):
            value=subprocess.check_output(['git','show',ref+':'+name],cwd=ROOT);bind(name,sha256(value).hexdigest(),(ref,))
    path='tests/test_fact_transaction_lock_wait.py';bind(path,sha256((ROOT/path).read_bytes()).hexdigest(),('4e28690',))
    runtime=json.loads((WORK/'browser-runtime.json').read_text());origin=Path(runtime['project_root'])
    assert origin.name=='hhu-ai-avatar-fact-privacy'
    for module,path in runtime['module_paths'].items():
        assert Path(path).is_relative_to(origin/'src')
        bind(str(Path(path).relative_to(origin)),runtime['module_sha256'][module],('054249b',))
    checks=[('facts-red.log','6 failed, 3 passed in 1.00s'),
        ('facts-fixed-first.log','no tests ran in 0.00s'),
        ('facts-fixed-related.log','1 failed, 106 passed in 3.06s'),
        ('facts-batch-final-related.log','108 passed in 2.70s'),
        ('python-full-facts-final.log','1436 passed, 1 skipped in 98.36s'),
        ('facts-lock-wait.log','14 passed in 1.04s'),('browser-facts-bound.log','15 passed (37.2s)')]
    for name,expected in checks:assert expected in (WORK/name).read_text(),name
    (WORK/'来源核验.json').write_text(json.dumps({'passed':True,'unique_path_sha_versions':len(versions),
        'source_versions':list(versions.values()),'full_ref':'054249b','full_count':1436,
        'later_lock_wait_tests':4,'not_claimed_full_1440':True,'browser_actual_runtime':runtime},ensure_ascii=False,indent=2)+'\n')
    snapshot=WORK/'单项归档快照.md'
    if not snapshot.exists():snapshot.write_bytes((HERE/'issues/010-P1-旧认知事实越过公共遗忘纠正写回.md').read_bytes())
    lines=['# '+TITLE,'',
        '日期2026-11-12，作者spinner-bot。独立fix/fact-context-cycle21，基于回执阶段b090960；尚未合主树，主树254冻结CPU研究继续。本报告限定C21-010，不覆盖旧回执阶段，也不宣告全轮或代际跃迁完成。','',
        '## 已证实问题与改动','',
        '默认认知分析完成、事实已验证之后，公共forget/correct会推进可变speaker_scope版本并清空当前source ID。只核对可变scope会重新授权旧facts：已遗忘姓名重新入库，刚纠正的姓名被旧值覆盖，新增来源甚至没有消息ID。末端Cancelled/assistant0没有撤销这些写入。取消也可在事实或来源已经写入后才被末端检测。',
        '054249b在规则/LLM事实事务开始、各条事实写入前以及完整批次提交前检查原_turn_context_revision与token。可变scope更新不授权旧结果；批次末尾取消使尚未提交的事实整体回滚。空事实批次同样先检查，避免继续应用迟到情绪。保留已有scope/原文证据验证，不修改模型输出。','',
        '| 实际分析HTTP受控时序 | 修前真实SQL | 修后相同输入 |','| --- | --- | --- |',
        '| 正常 | 2 HTTP/result，姓名与源ID有效 | 相同正常功能 |',
        '| token取消 | 1 HTTP后Cancelled，仍新增源关联 | 无新增源；新旧姓名不同的单测也不覆盖原资料 |',
        '| 同实例forget | 空资料被旧小岚恢复，source ID=None | 保持空，Cancelled |',
        '| 同实例correct | 阿澄被旧小岚覆盖，旧fact新源ID=None | 保持阿澄，Cancelled |',
        '| 独立连接forget/correct | 已有scope版本检查，保持空/阿澄 | 保持，Cancelled |','',
        '修前/修后各6例，均真实OpenAI兼容分析HTTP与SQLite；提供方返回受控JSON，姓名由实际用户原文规则支持。各5失效反例只有1次分析HTTP、assistant0；正常2次HTTP。取消原始HTTP例初始同名，证实新增来源，不能称该例姓名值变化；不同旧名的关联单测另外验证资料不应变。所有临时库均清理。不把夹具当原生模型语义或自然发生率。','',
        '| 验证阶段 | 结果 | 含义 |','| --- | --- | --- |',
        '| 初始红测 | 6失败/3通过，1.00s | 公共修订、取消、批次与规则路径均可达 |',
        '| 首关联命令 | 0测试，exit4 | 错误测试文件名，原日志保留，不计通过 |',
        '| 首修关联 | 106通过/1失败，3.06s | 最后一条事实内取消仍越过提交 |',
        '| 完整批次补检后关联 | 108通过，2.70s | 新单/双事实提交前取消覆盖 |',
        '| 完整Python | 1436通过/1跳过，98.36s | 054249b逐源/测试/日志绑定 |',
        '| 后加锁等待 | 4新增，含10已有共14通过1.04s | 不称1440完整，不与108相加 |','',
        '| 边界实证 | 结果 |','| --- | --- |',
        '| 等待其他连接BEGIN写锁 | LLM/规则准备后取消或forget，取得锁后4/4在事务内拒绝 |',
        '| 多事实批次 | 取消使该批尚未提交变更/来源整体回滚 |',
        '| 空分析 | 已取消时不继续应用该迟到分析的情绪 |',
        '| 真浏览器来源 | 本事实树四模块路径及独有复制DHh6-woO包SHA核验，15通过/12跳过37.2s |','',
        '| 范围限制 | 本阶段结论 |','| --- | --- |',
        '| 已经合法提交的既往事实 | 不承诺取消会回滚此前独立合法提交事务 |',
        '| 并发与重入 | 本项验证事务前修订、token/批次末尾、独立写锁等待；不外推所有嵌套扩展/回调行为 |',
        '| 设备/语义 | 无真实模型质量、物理音频、多日或独立人评 |',
        '| 前端 | 源码未改，复制已验DHh6-woO；未重建或重跑143前端单测 |',
        '| 后续 | CPU队列完成后统一合并与全轮审计；旧阶段封存文件不回写 |','',
        '## 原始资料','',
        '[010当前单项](issues/010-P1-旧认知事实越过公共遗忘纠正写回.md)可随合并更新，本阶段快照与以下原始证据封存。']
    inputs=[p for p in WORK.iterdir() if p.is_file() and p.name!='report-browser.json']
    for path in sorted(inputs):
        relative=Path(os.path.relpath(path,HERE)).as_posix();lines.append(f'- [{path.name}]({relative})')
    (HERE/(TITLE+'.md')).write_text('\n'.join(lines)+'\n')
    def inline(value):return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',escape(value))
    body=[];table=False
    for line in lines:
        if line.startswith('| ---'):continue
        if line.startswith('|'):
            if not table:body.append('<div class="table-wrap"><table>');tag='th';table=True
            else:tag='td'
            body.append('<tr>'+''.join(f'<{tag}>'+inline(cell)+f'</{tag}>' for cell in line.strip('| ').split(' | '))+'</tr>');continue
        if table:body.append('</table></div>');table=False
        if line.startswith('# '):body.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):body.append('<h2>'+inline(line[3:])+'</h2>')
        elif line:body.append('<p>'+inline(line.removeprefix('- '))+'</p>')
    style=re.search(r'<style>.*?</style>',(HERE/'独立SDK与语音修复报告.html').read_text()).group()
    (HERE/(TITLE+'.html')).write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+TITLE+'</title>'+style+'<main>'+'\n'.join(body)+'</main></html>')
    inputs += [Path(__file__),HERE/(TITLE+'.md'),HERE/(TITLE+'.html'),HERE/'独立SDK与语音修复报告.html']
    inputs += list(HERE.glob('fact-report-*.png'))
    for path in (HERE/'preview_fact_report.mjs',WORK/'report-browser.json'):
        if path.exists():inputs.append(path)
    manifest={str(p.relative_to(HERE.parent)):sha256(p.read_bytes()).hexdigest() for p in sorted(set(inputs))}
    (HERE/'认知事实阶段证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(len(manifest),'artifacts;',len(versions),'unique path+SHA versions')


if __name__=='__main__':build()
