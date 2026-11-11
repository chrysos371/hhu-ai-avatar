"""Evidence for synchronous route audio ownership; no relaxed old assertion."""
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
WORK=HERE/'工作目录/012-导航音频释放时序'
INTEGRATION=HERE/'工作目录/011-集成与系统复核'
TITLE='导航音频同步释放修复报告'


def read(path):return json.loads(path.read_text())


def build():
    versions={}
    def bind(name,expected,refs=('001c5d0','96c73ca','b5a70c1','81b8dda')):
        for ref in refs:
            value=subprocess.run(['git','show',ref+':'+name],cwd=ROOT,capture_output=True)
            if value.returncode==0 and sha256(value.stdout).hexdigest()==expected:
                versions.setdefault(name+':'+expected,{'path':name,'sha256':expected,'git_ref':ref});return
        raise AssertionError('Unbound '+name)
    bad=lambda row:not row['paused'] or row['src']
    before=read(WORK/'before/navigation-audio.json');after=read(WORK/'after/navigation-audio.json')
    for data,runtime_path in [(before,WORK/'runtime-before.json'),(after,WORK/'runtime-after.json')]:
        assert data['completed'] and len(data['rounds'])==20 and not data['errors']
        runtime=read(runtime_path);assert Path(runtime['project_root']).name=='hhu-ai-avatar-cycle21-integration'
        for name,expected in data['sourceSha256'].items():
            path=(ROOT/'frontend'/name).resolve();assert path.is_relative_to(ROOT)
            relative=str(path.relative_to(ROOT))
            if relative.startswith('frontend/dist/'):
                assert runtime['frontend_sha256'][relative]==expected
            else:bind(relative,expected)
    old_active=[row for row in before['rounds'] if bad(row['immediate'])]
    assert len(old_active)==2
    assert all(not r['immediate']['chatPresent'] and not r['immediate']['connected']
               and r['immediate']['heading']=='数字人大脑总览' for r in old_active)
    assert all(not bad(r['immediate']) and not bad(r['committed']) for r in after['rounds'])
    old_frames=[row for data in before['rounds'] for row in data['samples'] if not row['chatPresent']]
    new_frames=[row for data in after['rounds'] for row in data['samples'] if not row['chatPresent']]
    assert not any(bad(row) for row in old_frames+new_frames)
    binding=read(WORK/'frontend-fixed-binding.json')
    for name,expected in binding['source_sha256'].items():bind(name,expected,(binding['source_ref'],))
    legacy='frontend/e2e/speech.spec.ts'
    assert (ROOT/legacy).read_bytes()==subprocess.check_output(['git','show','81b8dda:'+legacy],cwd=ROOT)
    for phase in ('b5a70c1','96c73ca'):
        for name in ('frontend/src/features/chat/useSpeechPlayer.ts','frontend/src/features/chat/SpeechRouteCleanup.test.tsx'):
            bind(name,sha256(subprocess.check_output(['git','show',phase+':'+name],cwd=ROOT)).hexdigest(),(phase,))
    runtime=read(WORK/'补充PCM/pcm-runtime.json')
    for path in (WORK/'补充PCM').glob('*.json'):
        if path.name=='pcm-runtime.json':continue
        data=read(path);assert data['completed'] and data['failure'] is None
        for name,expected in data['sourceSha256'].items():
            local=(ROOT/'frontend'/name).resolve();bind(str(local.relative_to(ROOT)),expected)
        for name,expected in data['servedBundleSha256'].items():
            assert runtime['frontend_sha256']['frontend/'+name]==expected
    for name,expected in [('route-cleanup-red.log','1 failed | 1 passed'),
        ('route-cleanup-fixed-related.log','Tests  14 passed'),('frontend-full-fixed.log','Tests  145 passed'),
        ('navigation-before.log','1 passed (28.0s)'),('navigation-after.log','1 passed (28.5s)'),
        ('browser-default-fixed.log','15 passed (36.9s)'),('补充PCM/pcm.log','3 passed (24.1s)')]:
        assert expected in (WORK/name).read_text(),name
    assert '1 failed' in (INTEGRATION/'browser-default-integration.log').read_text()
    (WORK/'来源核验.json').write_text(json.dumps({'passed':True,'unique_path_sha_versions':len(versions),
        'versions':list(versions.values()),'legacy_speech_assertion_unchanged':True,
        'old_immediate_detached_active':2,'new_immediate_detached_active':0,'fixed_rounds_per_phase':20,
        'old_post_detach_rAF_samples':len(old_frames),'new_post_detach_rAF_samples':len(new_frames)},ensure_ascii=False,indent=2)+'\n')
    snapshot=WORK/'单项归档快照.md'
    if not snapshot.exists():snapshot.write_bytes((HERE/'issues/012-P2-导航提交后旧音频短时仍活动.md').read_bytes())
    lines=['# '+TITLE,'',
        '日期2026-11-12，作者spinner-bot。integration/cycle21-source-actions独立集成阶段；修复96c73ca，尚未合主树。主树固定14B研究继续，本报告不作模型质量/代际跃迁或全轮完成声明。','',
        '## 结论与可观测边界','',
        'C21-012/P2：旧聊天DOM已卸载、目标页heading已出现时，被动useEffect清理尚未运行，detached旧audio短时仍未暂停并保留src。资源清理改为同步layout effect，仍捕获原audio并释放请求、队列、对象URL和嘴型帧；原speech.spec.ts暂停且无src断言完全不变，没有新增宽限或重试筛选。','',
        '| 固定20轮真实Chromium/PCM | 修前DHh6-woO | 修后BSMr8F_e |','| --- | --- | --- |',
        '| 点击返回即时观察已离页旧audio仍活动 | 2/20 | 0/20 |',
        '| 稍后目标heading等待观察仍活动 | 0/20 | 0/20 |',
        f'| 离页rAF采样 | {len(old_frames)}，均已停止 | {len(new_frames)}，均已停止 |','',
        '较晚rAF的零异常不能否定修前两次更早的有效观察：两次即时数据同时记录目标heading、chatPresent=false、connected=false、paused=false、src=true。记录中名为committed的字段是后续heading等待后的采样，不能解释成只有此时才提交DOM。这里证实短暂窗口，不是持续泄漏、物理扬声器出声测量或现场发生率估计。','',
        '| 验证阶段 | 结果 | 证据含义 |','| --- | --- | --- |',
        '| 首组合默认浏览器 | 14通过/1失败/12跳过，37.0s | 原失败trace.zip/页面快照保留 |',
        '| 目的页布局红测 | 1失败/1正控通过，1.34s | 在目标layout执行时旧audio仍活动；同页rerender不释放 |',
        '| 播放关联修后 | 14通过，1.44s | 目的页同步清理及既有排队事件/分段正反控 |',
        '| 当前前端全量 | 145通过/34文件，7.54s | 96c73ca源、类型/build/lint通过 |',
        '| 同20轮实际导航 | 修前28.0s、修后28.5s各1采证项 | 每轮保留即时/后续/rAF，不删失败观察 |',
        '| 新包默认浏览器 | 15通过/13跳过，36.9s | 新增显式诊断默认跳过，不称与旧12跳过相同集合 |','',
        '| 新包补充PCM | 结果 |','| --- | --- |',
        '| 媒体时钟 | 倍速、seek、暂停、结束和停止均核验 |',
        '| 全部分段 | 顺序及新时钟核验 |',
        '| 预取中停止 | 排队play和迟到完成没有复活旧播放 |',
        '| 总体 | 3项通过24.1s，实际本树runtime/BSMr8F_e SHA |','',
        '| 适用范围 | 限制 |','| --- | --- |',
        '| 运行环境 | 实际浏览器媒体时钟、PCM和本地鉴权HTTP，受控模型/TTS夹具 |',
        '| 数据解释 | 20轮固定诊断不是现场概率；复制PCM证据不另计样本 |',
        '| 产品范围 | 页面卸载资源释放；不外推所有设备/浏览器、多日或真实声音自然度 |',
        '| 其他检查 | Python代码未因该前端修复改变，组合1449是81b8dda快照，未无故重跑 |',
        '| 后续 | 更宽通知、跨标签恢复、百轮在011另留痕；主树研究结束后统一合并审计 |','',
        '## 原始资料','',
        '[012当前单项](issues/012-P2-导航提交后旧音频短时仍活动.md)可随合并更新；阶段快照、原失败轨迹和下列资料封存。']
    inputs=[p for p in WORK.rglob('*') if p.is_file() and p.name!='report-browser.json']
    inputs += [INTEGRATION/'browser-default-integration.log',INTEGRATION/'browser-default-runtime.json']
    for path in sorted(inputs):
        relative=Path(os.path.relpath(path,HERE)).as_posix();lines.append(f'- [{relative}]({relative})')
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
    inputs += list(HERE.glob('route-audio-report-*.png'))
    for path in (HERE/'preview_route_audio_report.mjs',WORK/'report-browser.json'):
        if path.exists():inputs.append(path)
    manifest={str(p.relative_to(HERE.parent)):sha256(p.read_bytes()).hexdigest() for p in sorted(set(inputs))}
    (HERE/'导航音频阶段证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(len(manifest),'artifacts;',len(versions),'unique path+SHA versions')


if __name__=='__main__':build()
