"""Validate the isolated combined system without relabelling frozen model data."""
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
WORK=HERE/'工作目录/011-集成与系统复核'
AUDIO=HERE/'工作目录/012-导航音频释放时序'
TITLE='集成系统验证阶段报告'


def read(path):return json.loads(path.read_text())


def build():
    versions={}
    def bind(name,expected,refs=('af58669','96c73ca','81b8dda')):
        for ref in refs:
            value=subprocess.run(['git','show',ref+':'+name],cwd=ROOT,capture_output=True)
            if value.returncode==0 and sha256(value.stdout).hexdigest()==expected:
                versions.setdefault(name+':'+expected,{'path':name,'sha256':expected,'git_ref':ref});return
        raise AssertionError('Unbound source '+name)
    original=read(WORK/'integration-regression-binding.json')
    for name,expected in original['source_sha256'].items():bind(name,expected,(original['source_ref'],))
    for name,expected in original['log_sha256'].items():assert sha256((WORK/name).read_bytes()).hexdigest()==expected
    assert all(sha256(path.read_bytes()).hexdigest()==original['source_sha256'][str(path.relative_to(ROOT))]
               for path in ROOT.glob('src/avatar/**/*.py'))
    front=read(AUDIO/'frontend-fixed-binding.json')
    for name,expected in front['source_sha256'].items():
        bind(name,expected,(front['source_ref'],));assert sha256((ROOT/name).read_bytes()).hexdigest()==expected
    job=read(WORK/'browser-job-final-check.json');assert job['state']=='completed' and job['return_code']==0
    assert not job['worker_verified_alive'] and not job['child_verified_alive']
    config=read(WORK/'browser-audits-job/config.json');script=ROOT/'scripts/lab/run_integrated_browser_audits.sh'
    controller='scripts/lab/run_frozen_capability_job.py'
    assert sha256((ROOT/controller).read_bytes()).hexdigest()==config['controller_sha256']
    bind(controller,config['controller_sha256'],('81b8dda',))
    assert sha256(script.read_bytes()).hexdigest()==config['context']['script_sha256']
    bind(str(script.relative_to(ROOT)),config['context']['script_sha256'],(config['context']['source_ref'],))
    base=WORK/'browser-system-audits';reports=[]
    for case in ('actions','pcm','notifications','external-erase','restore','history100'):
        runtime=read(base/(case+'-runtime.json'));origin=Path(runtime['project_root']);assert origin==ROOT
        for module,path in runtime['module_paths'].items():
            local=Path(path);assert local.is_relative_to(ROOT/'src')
            bind(str(local.relative_to(ROOT)),runtime['module_sha256'][module])
        assert runtime['frontend_sha256']==front['bundle_sha256']
        for path in (base/case).glob('*.json'):
            data=read(path);assert data['completed'] and data.get('failure') is None
            assert not data.get('errors') and not data.get('violations')
            for name,expected in data.get('sourceSha256',{}).items():
                local=(ROOT/'frontend'/name).resolve();assert local.is_relative_to(ROOT)
                if local.is_relative_to(ROOT/'frontend/dist'):
                    assert runtime['frontend_sha256'][str(local.relative_to(ROOT))]==expected
                else:bind(str(local.relative_to(ROOT)),expected)
            for name,expected in data.get('servedBundleSha256',{}).items():assert runtime['frontend_sha256']['frontend/'+name]==expected
            reports.append(str(path.relative_to(HERE.parent)))
    history=read(base/'history100/history.json');restore=read(base/'restore/restore.json')
    assert len(history['turns'])==100 and len(history['checkpoints'])==3 and history['allCheckpointsObserved']
    assert len(restore['turns'])==54 and restore['elapsedSeconds']==59.051 and history['elapsedSeconds']==118.055
    actions=read(base/'actions/receipt-browser.json');assert len(actions['created']['items'])==1
    assert len(actions['cancelled']['items'])==2 and actions['afterForget']['items']==[]
    check=read(WORK/'阶段清单复核.json');assert check['passed'] and len(check['manifests'])==6
    for row in check['manifests']:
        assert row['frozen_artifact_mismatches']==0
        for doc in row['historical_canonical_docs']:
            assert sha256((ROOT/doc['copy']).read_bytes()).hexdigest()==doc['expected']
    tests=[(WORK/'python-full-integration-first.log','1449 passed, 1 skipped in 101.20s'),
           (AUDIO/'frontend-full-fixed.log','Tests  145 passed'),
           (AUDIO/'browser-default-fixed.log','15 passed (36.9s)'),
           (base/'actions.log','1 passed (5.0s)'),(base/'pcm.log','3 passed (24.1s)'),
           (base/'notifications.log','1 passed (9.8s)'),(base/'external-erase.log','1 passed (4.3s)')]
    for path,expected in tests:assert expected in path.read_text(),path
    (WORK/'集成来源核验.json').write_text(json.dumps({'passed':True,'unique_path_sha_versions':len(versions),
        'source_versions':list(versions.values()),'python_full_ref':'81b8dda','frontend_final_ref':'96c73ca',
        'current_python_matches_full':True,'current_frontend_matches_145_and_new_bundle':True,
        'system_probe_reports':reports,'frozen_model_quality_data_included':False},ensure_ascii=False,indent=2)+'\n')
    lines=['# '+TITLE,'',
        '日期2026-11-12，作者spinner-bot。独立integration/cycle21-source-actions组合阶段，产品Python由81b8dda完整验证，当前前端由96c73ca验证。报告归档时尚未合主树：主树14B仍在254冻结输入上运行。本报告不是全轮终结或代际跃迁批准。','',
        '## 已形成的组合行为','',
        '| 组合路径 | 当前已验证行为 |','| --- | --- |',
        '| 来源与认知 | 原turn版本/取消贯穿模型派发与事实批次，公共遗忘/纠正不能重授权旧事实 |',
        '| 实际动作 | 提醒事务内复核，真实metadata回执同提交；回复取消后已提交动作仍可查询 |',
        '| 声音生命周期 | SDK/TTS提交与导出边界、原子文件发布和页面同步卸载释放组合 |',
        '| 可复现运行 | 独立会话监督、真实PID身份/退出记录、冻结后端协议及浏览器本工作树来源核验 |','',
        '这是工程能力的可审查进展。普通模型仍可能无依据承诺短信/邮件/电话；没有新增这些执行接口，没有批准C19/C21能力提示候选，没有把本地认领说成通知已送达。','',
        '| 当前组合验证 | 结果 | 来源界定 |','| --- | --- | --- |',
        '| 完整Python | 1449通过/1跳过，101.20s | 81b8dda，当前全部产品Python字节一致 |',
        '| 前端初组合 | 143通过，7.91s；类型/build/lint通过 | 旧DHh6-woO阶段 |',
        '| 首组合浏览器 | 14通过/1失败/12跳过，37.0s | 暴露012导航音频被动清理窗口，原失败保留 |',
        '| 修复后前端全量 | 145通过/34文件，7.54s；类型/build/lint通过 | 96c73ca，当前BSMr8F_e独有构建 |',
        '| 修后默认浏览器 | 15通过/13跳过，36.9s | 原speech断言未改，新增诊断默认跳过项 |',
        '| 导航实际PCM诊断 | 固定20轮即时旧audio活动2→0 | 单项012独立报告，非现场发生率 |','',
        '| 独立新夹具系统探针 | 结果 |','| --- | --- |',
        '| 实际回执UI | 1项5.0s；创建/取消1→2，重载重读，独立forget清空 |',
        '| PCM时钟/分段/预取停止 | 3项24.1s |',
        '| 通知故障/重连/播放和生成中遗忘 | 1项9.8s |',
        '| 外部API遗忘，无前端通知 | 1项4.3s |',
        '| 跨标签/持久化历史恢复 | 54轮及取消正反控，59.051s |',
        '| 百轮交互与资源 | 100轮/3检查点，118.055s，零violations/页面错误 |','',
        '六个协议逐次使用全新夹具数据库/服务，避免前一探针遗忘资料污染后一探针。全部实际runtime模块属于本集成树，服务包哈希均为新BSMr8F_e。独立会话作业completed、child退出0，最终worker/child均不活动。它们是不同协议下受控HTTP/SSE/媒体oracle的数据，不能拼成独立真人语义样本；PCM复制到单项012不另计次数。','',
        '| 证据与发布边界 | 当前状态 |','| --- | --- |',
        '| 六个既有阶段清单 | 阶段冻结artifact字节零不匹配；入口数有共享输入，不加总冒充唯一证据 |',
        '| 演进中的规范文档 | 原回执阶段backend.md输入按b090960/不可变副本核验，保留主树新增Web边界说明；不回写旧清单 |',
        '| 来源可信度 | 旧未绑定SDK/提醒浏览器声明已勘误，实际分支重新测试；磁盘源码SHA不替代执行来源 |',
        '| 模型与设备 | 无独立人评、物理麦克风/扬声器、多日或通用语义批准 |',
        '| 当前主树 | 254冻结模型实验与本分支新产品源严格分开，尚未合并/部署 |',
        '| 下一步 | 模型完成并核对生命周期/清理后合并，核对默认源码与服务包，形成全轮报告并继续下一循环 |','',
        '## 单项与过程资料','',
        '[隐私阶段](隐私修复阶段报告.md)、[SDK/文件阶段](独立SDK与语音修复报告.md)、[提醒事务阶段](本地动作事务边界修复报告.md)、[回执/来源复核](真实动作回执与验收来源复核报告.md)、[认知事实阶段](认知事实事务来源修复报告.md)、[同步音频释放](导航音频同步释放修复报告.md)。',
        '[SDK浏览器勘误](SDK修复阶段浏览器勘误.md)、[提醒浏览器勘误](本地动作修复阶段勘误.md)。这些历史阶段不因本次组合复写。']
    inputs=[p for p in WORK.rglob('*') if p.is_file() and p.name!='report-browser.json']
    inputs += [AUDIO/'frontend-fixed-binding.json',AUDIO/'frontend-full-fixed.log',AUDIO/'frontend-build-fixed.log',
               AUDIO/'frontend-lint-fixed.log',AUDIO/'browser-default-fixed.log',AUDIO/'runtime-default-fixed.json']
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
    inputs += list(HERE.glob('integration-report-*.png'))
    for path in (HERE/'preview_integration_report.mjs',WORK/'report-browser.json'):
        if path.exists():inputs.append(path)
    manifest={str(p.relative_to(HERE.parent)):sha256(p.read_bytes()).hexdigest() for p in sorted(set(inputs))}
    (HERE/'集成阶段证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(len(manifest),'artifacts;',len(versions),'unique path+SHA versions')


if __name__=='__main__':build()
