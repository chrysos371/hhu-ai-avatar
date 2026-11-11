"""Seal real action evidence and the browser provenance correction together."""
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
WORK=HERE/'工作目录/008-真实动作回执'
BROWSER=HERE/'工作目录/009-浏览器夹具工作树绑定'
TITLE='真实动作回执与验收来源复核报告'


def read(path):return json.loads(path.read_text())


def build():
    versions={}
    def bind(name,expected,refs):
        for ref in refs:
            value=subprocess.run(['git','show',ref+':'+name],cwd=ROOT,capture_output=True)
            if value.returncode==0 and sha256(value.stdout).hexdigest()==expected:
                versions.setdefault(name+':'+expected,{'path':name,'sha256':expected,'git_ref':ref});return
        raise AssertionError('Unbound source '+name)
    refs=('bf1d7a4','0baaef2','b366445','f3c8253','a5af6e2','b49da81')
    http=read(WORK/'receipts-http-first.json');osdata=read(WORK/'receipts-os-first.json')
    assert http['completed'] and len(http['cases'])==12
    for row in http['cases']:
        normal=row['change']=='normal';post=row['operation']=='create_after_commit'
        assert row['cleanup'] and row['terminal']==('result' if normal else 'cancelled')
        assert row['business_changed'] is (normal or post)
        assert len(row['receipt_http']['items'])==int(row['change']!='forget' and (normal or post))
        assert len(row['ledger_rows'])==int(normal or post)
        assert row['assistant_count']==int(normal)
    assert osdata['completed'] and len(osdata['cases'])==3
    for row,count in zip(osdata['cases'],(2,1,0)):
        assert row['producer_exit']==row['server_exit']==0 and row['cleanup'] and row['integrity_check']=='ok'
        assert row['producer']['pid']!=row['server_pid'] and len(row['http']['data']['items'])==count
    for data in (http,osdata):
        for name,expected in data['source_sha256'].items():bind(name,expected,refs)
    full=read(WORK/'full-backend-binding.json')
    assert sha256((WORK/'python-full-receipts-compat-final.log').read_bytes()).hexdigest()==full['log_sha256']
    for name,expected in full['sha256'].items():bind(name,expected,(full['git_ref'],))
    assert all(sha256(path.read_bytes()).hexdigest()==full['sha256'][str(path.relative_to(ROOT))]
               for path in ROOT.glob('src/avatar/**/*.py'))
    frontend=read(WORK/'frontend-final-checks.json')
    assert frontend['lint_exit_code']==frontend['typescript_exit_code']==0
    for name,expected in frontend['sha256'].items():bind(name,expected,(frontend['source_ref'],))
    # Unit suite is an explicitly earlier committed source snapshot, not silently
    # relabelled after the one-word UI hint and browser-probe additions.
    for name in subprocess.check_output(['git','ls-tree','-r','--name-only','ee9c952','frontend/src'],cwd=ROOT,text=True).splitlines():
        if name.endswith(('.ts','.tsx')):
            expected=sha256(subprocess.check_output(['git','show','ee9c952:'+name],cwd=ROOT)).hexdigest()
            bind(name,expected,('ee9c952',))
    runtime_rows=[]
    for path,root_suffix,ref in [(WORK/'browser-second-runtime.json','hhu-ai-avatar-action-receipts','f2ec8c4'),
        (WORK/'browser-default-runtime.json','hhu-ai-avatar-action-receipts','97e27b3'),
        (BROWSER/'sdk-browser-runtime.json','hhu-ai-avatar-sdk-privacy','47a244d'),
        (BROWSER/'reminder-browser-runtime.json','hhu-ai-avatar-reminder-transaction','38219ca')]:
        data=read(path);origin=Path(data['project_root']);assert origin.name==root_suffix
        for module,name in data['module_paths'].items():
            actual=Path(name);assert actual.is_relative_to(origin/'src')
            bind(str(actual.relative_to(origin)),data['module_sha256'][module],(ref,))
        runtime_rows.append({'evidence':str(path.relative_to(HERE.parent)),'git_ref':ref,
                             'actual_modules':data['module_paths'],'served_frontend_sha256':data['frontend_sha256']})
    browser=read(WORK/'browser-second/receipt-browser.json')
    assert browser['completed'] and browser['errors']==[]
    assert len(browser['created']['items'])==1 and len(browser['cancelled']['items'])==2
    assert browser['afterForget']['items']==[]
    for name,expected in browser['sourceSha256'].items():
        local=(ROOT/'frontend'/name).resolve();assert local.is_relative_to(ROOT)
        relative=str(local.relative_to(ROOT))
        if relative.startswith('frontend/dist/'):
            assert read(WORK/'browser-second-runtime.json')['frontend_sha256'][relative]==expected
        else:bind(relative,expected,refs)
    checks=[(WORK/'python-full-receipts-first.log','2 failed, 1411 passed, 1 skipped in 89.27s'),
            (WORK/'python-full-receipts-compat-final.log','1424 passed, 1 skipped in 93.42s'),
            (WORK/'receipts-sdk-compat-fixed.log','71 passed in 7.07s'),
            (WORK/'frontend-full-receipts.log','Tests  143 passed'),
            (WORK/'frontend-receipts-fixed.log','Tests  21 passed'),
            (WORK/'browser-default-receipts-bound.log','15 passed (36.4s)'),
            (WORK/'browser-receipts-second.log','1 passed (5.5s)'),
            (BROWSER/'sdk-browser-bound.log','15 passed (36.5s)'),
            (BROWSER/'reminder-browser-bound.log','15 passed (36.6s)'),
            (BROWSER/'binding-fixed-tests.log','2 passed in 3.21s')]
    for path,expected in checks:assert expected in path.read_text(),path
    (WORK/'来源核验.json').write_text(json.dumps({'passed':True,'unique_path_sha_versions':len(versions),
        'source_versions':list(versions.values()),'current_product_matches_full_b366445':True,
        'full_test_count_not_including_two_later_fixture_tests':1424,'runtime_evidence':runtime_rows,
        'withdrawn_unbound_browser_results':['007 old15/11/36.9s','SDK old15/11/36.8s','008 old15/11/37.1s'],
        'old_source_inventory_is_not_runtime_proof':True},ensure_ascii=False,indent=2)+'\n')
    issue=BROWSER/'单项归档快照.md'
    if not issue.exists():issue.write_bytes((HERE/'issues/009-P1-浏览器夹具误用主树源码.md').read_bytes())
    lines=['# '+TITLE,'',
        '日期2026-11-12，作者spinner-bot。独立feat/local-action-receipts-cycle22阶段，包含已封SDK和提醒事务修复，尚未合并主树；主树254冻结的14B开发队列仍运行。本报告不代表全轮、代际跃迁或模型语义验收完成。','',
        '## 已形成的能力','',
        '真实本地提醒动作与metadata-only回执在同一SQLite写事务内提交；回执失败或本轮来源失效则一起回滚。来源绑定实际user消息、session和revision，只存动作/提醒ID/记录时间，不复制标题、姓名、原文或联系人。旧无来源Store API不补造聊天回执。',
        '新增鉴权只读GET /conversation/actions，支持来源过滤、分页和隐私版本409冲突。对话页按需核验；卸载、隐私版本/服务变化或读取失败清空旧状态，不从模型措辞推断执行。合法动作提交后，即使回复随后取消，仍可单独读取已提交回执。','',
        '| 验证阶段 | 结果 | 实际范围 |','| --- | --- | --- |',
        '| SDK/存储首验 | 121相关通过2.04s，含19新项 | 原子可见/回滚/五类伪来源/真实取消/隐私 |',
        '| 首完整 | 1411通过/2失败/1跳过，89.27s | 新409先于旧Cancelled契约，保留原日志 |',
        '| 兼容修复后完整 | 1424通过/1跳过，93.42s，b366445 | 当前全部产品Python字节仍一致 |',
        '| 后加夹具绑定 | 2真实子进程通过3.21s | 不冒称1426完整重跑 |',
        '| 前端单元 | 143通过7.84s，ee9c952 | 定向21项包含在143，不相加 |',
        '| 后续指路文案/浏览器采证 | 类型/lint退出0，新包DHh6-woO | 只有一处指路文案及新增E2E，未冒称重跑143 |','',
        '| 实际HTTP/SSE时序 | 业务 | 当前可见回执 |','| --- | --- | --- |',
        '| 创建/取消/认领正常3例 | 3/3实际更新 | 各1 |',
        '| 三动作事务前取消/forget共6例 | 0/6更新 | 0 |',
        '| 创建提交后正常 | 1条提醒 | 1 |',
        '| 创建提交后取消回复 | 1条提醒，assistant0 | 1 |',
        '| 创建提交后forget | 合法已提交提醒仍存在 | 旧账1，当前revision可见0 |','',
        '上述12例含真实鉴权HTTP、/turns、/cancel、SSE和独立SQLite forget，模型关闭，自有库均清理。另3全新库/6独立OS进程：生产进程退出后，新服务HTTP分别读到正常创建+取消2条、业务后取消1条、forget后0条；六进程退出0，3库integrity_check=ok，全部目录清理。不是同进程重开或页面reload替代服务进程证据。','',
        '## C21-009 验收来源问题与纠正','',
        '真实新面板首浏览器失败后，解释器探针确认：npm把cwd切到frontend，相对PYTHONPATH=src不指向项目src，共享editable环境导入主树，服务也读取主树旧dist。仅在磁盘记录分支源码SHA，不能证明测试实际执行该分支。旧SDK/007/008浏览器通过作为分支验收均撤回；原封存报告与证据不回写，以新增勘误覆盖。仓库cwd的完整Python、SDK/HTTP逐源证据保持有效。',
        'f2ec8c4在fixture进口前固定自身绝对src，启动核验实际module路径并记录字节与dist SHA；frontend.sh为e2e设绝对PYTHONPATH。故意错误cwd/继承路径的两子进程通过，各修复树均单独复测。','',
        '| 真正绑定来源的补测 | 结果 | 实际构建 |','| --- | --- | --- |',
        '| SDK修复树，47a244d入口 | 15通过/11跳过，36.5s | C18原包，未重建 |',
        '| 提醒事务修复树，38219ca入口 | 15通过/11跳过，36.6s | 独有复制的C18原包 |',
        '| 回执研究树，97e27b3入口 | 15通过/12跳过，36.4s | 新DHh6-woO，含新增默认跳过专项 |',
        '| 回执真实专项，f2ec8c4入口 | 1通过，5.5s | 创建/取消1→2回执，重载重读，独立forget清空；1440/390无溢出/错误 |','',
        '| 边界 | 本阶段结论 |','| --- | --- |',
        '| 回执证据 | 当前可见的本地SQL提交，不是模型自述或当前业务状态 |',
        '| 停止回复 | 不撤销此前合法提交动作；事务检查前失效不写业务/回执 |',
        '| 遗忘与空列表 | 旧revision隐藏，不表示历史从无操作或已撤回提醒 |',
        '| 到期认领 | 仅本地标记，notification_delivery_verified=false |',
        '| 通用语义 | 不修辞删改、不批准短信/邮件/电话能力；C19-001与原候选拒绝不改变 |',
        '| 设备与时间 | 无真实Edge、物理麦克风/扬声器、多日或独立人评验收 |',
        '| 合并与后续 | 主树冻结研究收尾后合并，再作最终全轮审计，Goal保持active |','',
        '## 当前说明与原始材料','',
        '[SDK浏览器勘误](SDK修复阶段浏览器勘误.md)、[提醒阶段勘误](本地动作修复阶段勘误.md)、[009当前单项](issues/009-P1-浏览器夹具误用主树源码.md)。当前单项可随合并更新，本阶段快照/证据封存。']
    user_doc=Path(os.path.relpath(ROOT/'docs/本地动作回执.md',HERE)).as_posix()
    lines.append(f'[用户与API说明]({user_doc})。')
    inputs=[p for directory in (WORK,BROWSER) for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='report-browser.json']
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
    inputs += [Path(__file__),HERE/(TITLE+'.md'),HERE/(TITLE+'.html'),HERE/'SDK修复阶段浏览器勘误.md',HERE/'本地动作修复阶段勘误.md',ROOT/'docs/本地动作回执.md',ROOT/'docs/backend.md',HERE/'独立SDK与语音修复报告.html']
    inputs += list(HERE.glob('action-report-*.png'))
    for path in (HERE/'preview_action_report.mjs',WORK/'report-browser.json'):
        if path.exists():inputs.append(path)
    manifest={Path(os.path.relpath(p,HERE.parent)).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(set(inputs))}
    (HERE/'动作回执阶段证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(len(manifest),'artifacts;',len(versions),'unique path+SHA versions')


if __name__=='__main__':build()
