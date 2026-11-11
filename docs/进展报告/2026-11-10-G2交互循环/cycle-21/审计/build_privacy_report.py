"""Seal the completed privacy phase, without claiming pending model quality."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CYCLE = HERE.parent
ROOT = HERE.parents[4]
EV = CYCLE/'实验'
sys.path.insert(0, str(ROOT/'scripts'))
from evaluate_capability_pair import verify_freeze


def build():
    before = json.loads((EV/'prompt-privacy-before.json').read_text())
    after = json.loads((EV/'prompt-privacy-after.json').read_text())
    assert before['completed'] and after['completed']
    a, b = before['arms']; c, d = after['arms']
    assert [row['private_sent_after_forget'] for row in (a, b, c, d)] == [True, False, False, False]
    assert [len(row['post_forget_reply_requests']) for row in (a, b, c, d)] == [1, 0, 0, 0]
    assert all(row['cleanup'] and row['positive_mode'] == 'llm' and row['positive_request_count'] == 2
               and not row['positive_private_present'] and not row['stored_assistants_after_cancel']
               and row['first_terminal'] == 'cancelled' for row in (a, b, c, d))
    for name, text in [('prompt-dispatch-before.log', '7 failed in 0.90s'),
        ('prompt-dispatch-fixed.log', '64 passed in 6.00s'),
        ('dispatch-analysis-related.log', '27 passed in 0.99s'),
        ('python-full-privacy-fixed.log', '1304 passed, 1 skipped in 86.03s'),
        ('browser-default-privacy-fixed.log', '15 passed (36.4s)')]:
        assert text in (EV/name).read_text(), name
    bindings = []
    for report in (before, after):
        for name, expected in report['sourceSha256'].items():
            for ref in ('3de52eb', 'e0ba40e', 'd46ea19'):
                result = subprocess.run(['git', 'show', ref+':'+name], cwd=ROOT, capture_output=True)
                if result.returncode == 0 and sha256(result.stdout).hexdigest() == expected:
                    bindings.append({'path': name, 'sha256': expected, 'git_ref': ref}); break
            else: raise AssertionError('Unbound source: '+name)
    for filename in ('full-test-source-binding.json', 'privacy-fixed-full-test-binding.json'):
        data = json.loads((EV/filename).read_text()); ref = data['runtime_and_test_bytes_git_ref']
        log = EV/('python-full.log' if filename.startswith('full-') else 'python-full-privacy-fixed.log')
        assert sha256(log.read_bytes()).hexdigest() == data['log_sha256']
        for name, expected in data['sha256'].items():
            actual = subprocess.check_output(['git', 'show', ref+':'+name], cwd=ROOT)
            assert sha256(actual).hexdigest() == expected
            bindings.append({'path': name, 'sha256': expected, 'git_ref': ref})
    frozen = ROOT/'evals/interaction/cycle-21/candidate-development-freeze-v2-privacy-fixed.json'
    assert len(verify_freeze(frozen, 'development', 'lab_source_capability_v2')['sha256']) == 225
    try: verify_freeze(frozen, 'prospective', 'lab_source_capability_v2')
    except ValueError: pass
    else: raise AssertionError('Prospective incorrectly authorized')
    unique = {json.dumps(item, sort_keys=True): item for item in bindings}
    checked = {'all_passed': True, 'source_bindings': list(unique.values()),
        'development_freeze_inputs': 225, 'prospective_rejected': True,
        'scope': 'Historical Git byte verification; completed privacy phase only, no GPU quality assertion'}
    (EV/'privacy-source-check.json').write_text(json.dumps(checked, ensure_ascii=False, indent=2)+'\n')
    lines = ['# 第二十一轮隐私修复阶段审计报告', '',
        '日期：2026-11-12。作者：spinner-bot。远期Goal继续active；这是已完成的隐私阶段报告，真实模型能力候选质量实验尚未完成，后续另出全轮报告。', '',
        '## 实证结论', '',
        '确认并修复G2C21-001/P1：默认Avatar的system提示已经编译后，独立数据库连接完成遗忘，原_messages仍可能把旧提示发给回复模型。最终取消、无assistant入库没有撤回已发出的请求。实际受控HTTP中，修前默认遗忘提交后1次回复请求含已删合成姓名，修后0次；两个阶段的v2候选均0次。', '',
        '| 阶段/分支 | 遗忘后回复HTTP | 已删姓名外发 | 最终assistant | 新话题正控HTTP |',
        '| --- | --- | --- | --- | --- |',
        '| 修前默认 | 1 | 是 | 0 | 2，llm且无旧名 |',
        '| 修前v2 | 0 | 否 | 0 | 2，llm且无旧名 |',
        '| 修后默认 | 0 | 否 | 0 | 2，llm且无旧名 |',
        '| 修后v2 | 0 | 否 | 0 | 2，llm且无旧名 |', '',
        '每臂此前1次分析请求发生在遗忘之前，不能误称遗忘后泄露。合成姓名只用于隔离临时库，受控提供方实际读取HTTP正文并留原记录；不是伪造LLM返回值的Recorder计数。所有临时库清理成功。钩子安排真实编译/写入交错，不能推断自然发生率。', '',
        '## 修复与验证', '',
        '3de52eb在默认Avatar保存本轮独立隐私revision，消息组装前、完整system与短期消息组装后均检查同一revision和取消；分析发送前也检查。本实例forget/correct更新可变任务/归属版本，不能把旧回合追认为新版本。既有最终提交检查、来源依赖和权限路径继续保留。', '',
        '| 检查 | 实际结果 | 绑定版本/范围 |', '| --- | --- | --- |',
        '| 首次竞争红测 | 7失败，0.90s | e0ba40e默认；测试字节2f6e13e |',
        '| 修后相关 | 64通过，6.00s | 默认修复3de52eb，含来源/角色/纯控制 |',
        '| 分析/冻结关联 | 27通过，0.99s | 10隐私+17冻结/元数据 |',
        '| 完整Python | 1304通过/1跳过，86.03s | 入口及全部源/测试字节5576bab |',
        '| 默认浏览器 | 15通过/11可选跳过，36.4s | 含隐私修复；前端源和dist未改 |', '',
        '前端unit/build、独立百轮和PCM本阶段未重跑，不能借用C18历史结果冒称本轮通过。受控HTTP修前脚本首次执行时尚未提交，其字节随后纳入e0ba40e；修后执行时main改动字节随后纳入3de52eb，不把当时HEAD等同于尚未提交的实现。源码核验按逐文件SHA匹配Git，旧1288全量与新1304全量分别绑定。', '',
        '## 候选与资源状态', '',
        '| 项目 | 状态 |', '| --- | --- |',
        '| C19 v1 | 仍拒绝启用，不追溯放行 |',
        '| C21来源能力v2 | 隔离lab，默认工厂不安装，无后处理/额外模型或工具调用 |',
        '| 原211项冻结 | 默认修复后实际核验拒绝；未执行真实模型 |',
        '| 新225项冻结 | 当前默认隐私修复基线；只授权已知开发12场景20回合/臂 |',
        '| 前瞻12场景21回合 | 未授权，实际校验拒绝 |',
        '| GPU启动前两次 | 均资源门槛拒绝、无ready/无采样；退出1保留，资源已离开不等于样本成功 |', '',
        '资源观察器只读每10秒记录实际显存/利用率/UUID，连续同卡两次达到原门槛才返回；不预留GPU，实际提供方必须再次检查。不能靠一次利用率0的快照认定后续空闲，也不为启动成功而放宽条件。', '',
        '## 限制与下一步', '',
        '该屏障阻止发送时已经观察到的取消或版本变化；最后检查后仍可能有新的外部写入，不能宣称撤回历史或在途提供方请求。正常分析在遗忘前的实际请求不受追溯删除保证。本报告不构成真实模型语义、独立真人、多日或物理设备验收。', '',
        '| 优先级 | 后续工作 | 证据门槛 |', '| --- | --- | --- |',
        '| P1 | 默认短信/邮件/电话能力诚实性C19-001 | 新225冻结下实际4B/14B配对，native/visible/final/stored与副作用分开，逐span审阅 |',
        '| P2 | 草稿/续改与当前来源 | 保留用户主体/原文，已知开发仅回归；通过后另冻前瞻 |',
        '| P2 | 其他入口与重启 | 真实独立进程、来源缺口与权限组合，不以历史显示恢复冒称生成恢复 |',
        '| P3 | 听→思→演→记 | 中文人声/音画/真实设备/多日分别采证 |', '',
        '## 可复核资料', '',
        '[计划](../计划.md)、[过程记录](../进展.md)、[单项issue](issues/001-默认提示组装期间遗忘后仍外发.md)、[源码核验](../实验/privacy-source-check.json)。']
    evidence_names = ['prompt-privacy-before.json', 'prompt-privacy-after.json', 'prompt-privacy-before.log',
        'prompt-privacy-after.log', 'prompt-dispatch-before.log', 'prompt-dispatch-fixed.log',
        'dispatch-analysis-related.log', 'python-full-privacy-fixed.log', 'browser-default-privacy-fixed.log',
        'privacy-fixed-full-test-binding.json', 'full-test-source-binding.json', 'freeze-retirement.json',
        'privacy-source-check.json', 'admission-rejection-cleanup.json']
    lines += [f'- [{name}](../实验/{name})' for name in evidence_names]
    (HERE/'隐私修复阶段报告.md').write_text('\n'.join(lines)+'\n')
    def inline(value):
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', escape(value))
    body = []; table = False
    for line in lines:
        if line.startswith('| ---'): continue
        if line.startswith('|'):
            if not table: body.append('<div class="table-wrap"><table>'); tag = 'th'; table = True
            else: tag = 'td'
            body.append('<tr>'+''.join(f'<{tag}>'+inline(cell)+f'</{tag}>' for cell in line.strip('| ').split(' | '))+'</tr>'); continue
        if table: body.append('</table></div>'); table = False
        if line.startswith('# '): body.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '): body.append('<h2>'+inline(line[3:])+'</h2>')
        elif line: body.append('<p>'+inline(line.removeprefix('- '))+'</p>')
    style = re.search(r'<style>.*?</style>', (CYCLE.parent/'cycle-20/审计/系统审计与推进报告.html').read_text()).group()
    (HERE/'隐私修复阶段报告.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第二十一轮隐私修复阶段报告</title>'+style+'<main>'+'\n'.join(body)+'</main></html>')
    manifest_paths = [EV/name for name in evidence_names] + [Path(__file__).resolve(),
        HERE/'隐私修复阶段报告.md', HERE/'隐私修复阶段报告.html',
        HERE/'issues/001-默认提示组装期间遗忘后仍外发.md']
    manifest_paths += list(HERE.glob('privacy-report-*.png'))
    manifest_paths += [p for p in (HERE/'preview_privacy_report.mjs', EV/'privacy-report-browser.json') if p.exists()]
    manifest = {str(p.relative_to(CYCLE)): sha256(p.read_bytes()).hexdigest() for p in manifest_paths}
    (HERE/'隐私阶段证据清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print('privacy report:', len(manifest), 'artifacts;', len(unique), 'source bindings')


if __name__ == '__main__': build()
