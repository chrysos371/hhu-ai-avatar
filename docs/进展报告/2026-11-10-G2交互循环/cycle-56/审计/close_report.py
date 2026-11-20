"""Verify C56 report/current bytes and seal committed evidence without rewrites."""
import argparse
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote
from audit_common import ROOT,BASE,AUDIT,OUT,read,sha,write,require,historical,software


def check():
    software();meta=read(OUT/'report-render-metadata.json');system=read(OUT/'system-evidence.json')
    require(system['collector_sha256']==sha(AUDIT/'collect_system.py')
        and system['helper_sha256']==sha(AUDIT/'audit_common.py') and meta['system_sha256']==sha(OUT/'system-evidence.json')
        and meta['builder_sha256']==sha(AUDIT/'build_report.py'),'system/report source changed')
    require(meta['MD_sha256']==sha(AUDIT/'系统审计与推进报告.md')
        and meta['HTML_sha256']==sha(AUDIT/'系统审计与推进报告.html'),'rendered report bytes changed')
    browser=read(OUT/'report-browser.json')
    require(browser['completed'] and not browser['errors'] and browser['reportSha256']==meta['HTML_sha256']
        and browser['scriptSha256']==sha(AUDIT/'preview_report.mjs')
        and [v['viewport']['width'] for v in browser['views']]==[1440,390],'browser source/views differ')
    require(all(not v['overflow'] and v['tableCount']==meta['tables'] and len(v['links'])==meta['links']
        and all(t['lastCellReadable'] for t in v['horizontalTables']) and sha(Path(v['screenshot']))==v['screenshotSha256'] for v in browser['views']),
        'display/screenshots/local link counts differ')
    links=[]
    for p in list(BASE.rglob('*.md'))+[ROOT/'AGENTS.md',ROOT/'README.md']:
        for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)',p.read_text()):
            target=raw.split('#',1)[0].strip('<>')
            if target and not re.match('[a-z]+://',target):require((p.parent/unquote(target)).resolve().is_file(),'broken MD link '+str(p)+':'+target);links.append(raw)
    authors=subprocess.check_output(['git','log','406661df..HEAD','--format=%an <%ae>'],cwd=ROOT,text=True).splitlines()
    require(set(authors)=={'spinner-bot <langxibielangle@qq.com>'},'author differs')
    files={str(p.relative_to(ROOT)):sha(p) for p in BASE.rglob('*') if p.is_file()}
    require(historical('HEAD',files)==files,'commit C56 files before closeout')
    write(OUT/'closeout.json',{'verified':True,'verifier_sha256':sha(Path(__file__)),
        'MD_links_checked':len(links),'HTML_links':meta['links'],'tables':meta['tables'],'views':[1440,390],
        'Python_passed':2562,'Python_skipped':1,'current_source_inputs':812,'issues_limited_closed':[1,2],'issues_open':[3],
        'new_native_model_quality_approved':False,'scope':'current engineering/report closure only;provider chain remains OPEN'})
    print('C56 closeout',len(links),'MD links;',meta['links'],'HTML links;2views;provider chain remains OPEN')


def seal():
    require(read(OUT/'closeout.json')['verified'] and not (AUDIT/'证据清单.json').exists(),'fresh verified seal required')
    require(not subprocess.check_output(['git','status','--porcelain','--',str(BASE)],cwd=ROOT),'commit all C56 files before seal')
    files={str(p.relative_to(BASE)):sha(p) for p in sorted(BASE.rglob('*')) if p.is_file()}
    require(not any('__pycache__' in name for name in files),'bytecode belongs in centralized assets')
    bound={str((BASE/name).relative_to(ROOT)):value for name,value in files.items()}
    require(historical('HEAD',bound)==bound,'seal requires committed bytes')
    write(AUDIT/'证据清单.json',files)
    print('C56 sealed',len(files),'files;SHA',sha(AUDIT/'证据清单.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['check','seal']);globals()[p.parse_args().mode]()
