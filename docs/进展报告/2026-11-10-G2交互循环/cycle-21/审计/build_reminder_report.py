"""Validate and render the isolated local-action transaction repair stage."""
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
WORK = HERE/'工作目录/007-本地动作事务边界'
TITLE = '本地动作事务边界修复报告'


def build():
    sources = {}
    def bind(name, expected, refs):
        for ref in refs:
            result = subprocess.run(['git', 'show', ref+':'+name], cwd=ROOT, capture_output=True)
            if result.returncode == 0 and sha256(result.stdout).hexdigest() == expected:
                sources.setdefault(name+':'+expected, {'path': name, 'sha256': expected, 'git_ref': ref})
                return
        raise AssertionError('Unbound bytes '+name)
    for name in ('reminder-before.json', 'reminder-after.json', 'reminder-http-after.json'):
        data = json.loads((WORK/name).read_text())
        assert data['completed'] and len(data['cases']) == 9
        for row in data['cases']:
            normal = row['change'] == 'normal'
            assert row['cleanup'] and row['terminal'] == ('result' if normal else 'cancelled')
            assert row['assistant_count'] == int(normal)
            assert row['business_changed'] is (normal or name == 'reminder-before.json')
        for path, expected in data['source_sha256'].items():
            bind(path, expected, ('db23938', '56ca7cb', 'bc5d750', 'a101027'))
    binding = json.loads((WORK/'verification-binding.json').read_text())
    for name, row in binding['sha256'].items():
        if row['git_ref']: bind(name, row['sha256'], (row['git_ref'],))
        else:
            assert name.startswith('frontend/dist/') and sha256((ROOT/name).read_bytes()).hexdigest() == row['sha256']
    for name in ('src/avatar/main.py', 'src/avatar/brain/reminders.py', 'tests/test_reminder_transaction_boundary.py'):
        expected = sha256(subprocess.check_output(['git','show','c9d3db3:'+name], cwd=ROOT)).hexdigest()
        bind(name, expected, ('c9d3db3',))
    for name, expected in [('transaction-red.log','6 failed, 3 passed in 0.99s'),
                           ('transaction-fixed-related.log','90 passed in 1.34s'),
                           ('transaction-lock-related.log','102 passed in 1.54s'),
                           ('python-full-transaction.log','1394 passed, 1 skipped in 87.93s'),
                           ('browser-default-transaction.log','15 passed (36.9s)')]:
        assert expected in (WORK/name).read_text()
    (WORK/'来源核验.json').write_text(json.dumps({'passed': True, 'unique_path_sha_versions': len(sources),
        'versions': list(sources.values()), 'red_source_and_tests_ref':'c9d3db3',
        'full_and_browser_source_ref':'56ca7cb', 'product_fix':'bc5d750'}, ensure_ascii=False, indent=2)+'\n')
    snapshot = WORK/'单项归档快照.md'
    if not snapshot.exists(): snapshot.write_bytes((HERE/'issues/007-P1-本地提醒失效请求仍提交事务.md').read_bytes())
    lines = ['# '+TITLE, '',
        '日期2026-11-12，作者spinner-bot。fix/reminder-transaction-cycle21独立分支阶段，尚未合入主树；主树CPU254冻结开发继续。合并后以新进展为准，本报告不回写历史。', '',
        '## 已证实问题与修复', '',
        'C21-007/P1：本轮检查通过后、实际提醒事务开始前，取消或独立forget仍允许创建/取消/到期认领写SQL；末端Cancelled与assistant0并不等于业务零副作用。真实SQLite受控调度6/6可达，不估计随机发生率。',
        'bc5d750让内置Avatar把原回合revision/token闭包传入ReminderStore，在BEGIN IMMEDIATE取得写锁后、SQL业务变更前复核；Cancelled冒泡并回滚，旧独立Store API保留。该提交建立本地动作提交边界，不能逆转此前已经合法提交的动作。', '',
        '| 本地操作 | 修前失效反例 | 修后相同反例 | 正常正控 |', '| --- | --- | --- | --- |',
        '| 创建 | 取消/forget后均新建 | 2/2零新增 | 成功创建 |',
        '| 取消 | 取消/forget后均active→cancelled | 2/2状态保持 | 成功取消 |',
        '| 到期认领 | 取消/forget后均写notified_at | 2/2标记保持空 | 成功认领 |', '',
        '到期认领只更新本地标记，实验没有实际发送外部通知。三组的失效终端均Cancelled、assistant0；forget实际revision0→1，独立于token取消。', '',
        '| 验证层 | 结果 | 证据范围 |', '| --- | --- | --- |',
        '| 初始红测 | 6失败/3通过，0.99s | 原断言保留，不放宽 |',
        '| SDK独立重放 | 9例，6失效零业务/3正常成功 | 真Avatar/SQLite，模型关闭 |',
        '| 鉴权HTTP/SSE | 9例，6失效零业务/3正常成功 | 实际/turns、/cancel与SSE，forget独立SQL |',
        '| 锁与等待 | 新增12项，相关总102通过/1.54s | 写锁内检查、回滚、另一连接等待BEGIN期间失效 |', '',
        '| 回归 | 结果 | 源码绑定 |', '| --- | --- | --- |',
        '| 完整Python | 1394通过/1跳过，87.93s | 56ca7cb，产品bc5d750 |',
        '| 默认浏览器 | 15通过/11跳过，36.9s | 56ca7cb与独有复制C18 dist |',
        '| 较早相关阶段 | 90通过/1.34s | bc5d750实现首验，不能与102相加 |', '',
        '| 边界 | 本阶段结论 |', '| --- | --- |',
        '| 取消时间 | 取得事务锁后的检查阻止此前已失效请求；合法提交后的取消不撤销动作 |',
        '| API兼容 | Store checkpoint为可选；自定义store内部策略不自动获得本检查 |',
        '| 语义/设备 | 无模型质量、真实Edge、通知送达、物理设备或多日验收 |',
        '| 主树/前端 | 尚未合并；无前端源码变化/构建/单测、百轮或PCM本轮重跑 |', '',
        '## 原始资料与复核', '',
        '[当前单项](issues/007-P1-本地提醒失效请求仍提交事务.md)可随合并更新。阶段单项快照、源/测试逐版本哈希和以下原始日志封存；完整与相关数量不重复累加，HTTP采证器后于全回归新增，不冒称参与1394测试。']
    inputs = [p for p in WORK.iterdir() if p.is_file() and p.name != 'report-browser.json']
    for path in sorted(inputs):
        relative = Path(os.path.relpath(path, HERE)).as_posix(); lines.append(f'- [{path.name}]({relative})')
    (HERE/(TITLE+'.md')).write_text('\n'.join(lines)+'\n')
    def inline(value): return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',escape(value))
    body = []; table = False
    for line in lines:
        if line.startswith('| ---'): continue
        if line.startswith('|'):
            if not table: body.append('<div class="table-wrap"><table>'); tag='th'; table=True
            else: tag='td'
            body.append('<tr>'+''.join(f'<{tag}>'+inline(cell)+f'</{tag}>' for cell in line.strip('| ').split(' | '))+'</tr>'); continue
        if table: body.append('</table></div>');table=False
        if line.startswith('# '): body.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):body.append('<h2>'+inline(line[3:])+'</h2>')
        elif line:body.append('<p>'+inline(line.removeprefix('- '))+'</p>')
    style=re.search(r'<style>.*?</style>',(HERE/'独立SDK与语音修复报告.html').read_text()).group()
    (HERE/(TITLE+'.html')).write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+TITLE+'</title>'+style+'<main>'+'\n'.join(body)+'</main></html>')
    inputs += [Path(__file__),HERE/(TITLE+'.md'),HERE/(TITLE+'.html'), HERE/'独立SDK与语音修复报告.html']
    if (WORK/'report-browser.json').exists(): inputs.append(WORK/'report-browser.json')
    inputs += list(HERE.glob('reminder-report-*.png'))
    if (HERE/'preview_reminder_report.mjs').exists():inputs.append(HERE/'preview_reminder_report.mjs')
    manifest={str(p.relative_to(HERE.parent)):sha256(p.read_bytes()).hexdigest() for p in sorted(set(inputs))}
    (HERE/'本地动作修复证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(len(manifest),'evidence artifacts;',len(sources),'unique path+SHA versions')


if __name__ == '__main__':build()
