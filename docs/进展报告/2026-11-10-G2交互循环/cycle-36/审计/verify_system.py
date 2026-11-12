"""Independent C36 Git/runtime/raw-browser reconstruction and immutable history checks."""
import hashlib, io, json
from pathlib import Path
import subprocess, tarfile
ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
WORK = BASE / '审计/工作目录/001-日常浏览器回归'
def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):
    return json.loads(Path(path).read_text())
def history(ref, names):
    raw = subprocess.check_output(['git','archive','--format=tar',ref,'--',*sorted(names)],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive if m.isfile()}
def main():
    output = BASE / '审计/收尾核验/system-evidence.json'
    assert not output.exists()
    bindings=[]
    for name in ['first-browser_targeted','esm-fixed-browser_targeted','witness-fixed-browser_targeted','stable-python','stable-frontend','stable-build','full-browser']:
        p=WORK/(name+'-final-binding.json'); data=read(p); inputs=data['source_git_sha256']
        assert len(inputs)==426 and data['source_unchanged']
        assert history(data['head'],inputs)==inputs
        driver=str((BASE/'审计/run_regression.py').relative_to(ROOT))
        driver_bytes=subprocess.check_output(['git','show',data['head']+':'+driver],cwd=ROOT)
        assert hashlib.sha256(driver_bytes).hexdigest()==data['driver_sha256']
        assert digest(WORK/(name+'-final.log'))==data['log_sha256']
        if name.startswith(('stable-','full-','witness-')):
            assert data['exit_code']==0
            for key,sha in inputs.items():assert digest(ROOT/key)==sha,key
        if name in ('witness-fixed-browser_targeted','full-browser'):
            assert data['runtime_matches'] and data['optional_e2e_flags_cleared']
            runtime=read(WORK/(name.replace('browser_targeted','browser')+'-final-runtime.json'))
            assert runtime['frontend_sha256']==data['runtime_artifact_sha256']
            assert runtime['state_privacy_protocol_sha256']==inputs['evals/interaction/cycle-36/maintained-state-privacy-protocol.json']
            assert len(runtime['module_paths'])==8
            for module,path in runtime['module_paths'].items():
                assert runtime['module_sha256'][module]==inputs[str(Path(path).relative_to(ROOT))]
        bindings.append({'name':name,'sha256':digest(p),'source_ref':data['head'],'test_exit_code':data['exit_code'],'runtime_matches':data.get('runtime_matches')})
    assert read(WORK/'first-browser_targeted-final-binding.json')['exit_code']==1
    assert 'needs an import attribute' in (WORK/'first-browser_targeted-final.log').read_text()
    assert '2 passed' in (WORK/'esm-fixed-browser_targeted-final.log').read_text()
    assert 'runtime_matches' not in read(WORK/'esm-fixed-browser_targeted-final-binding.json')
    assert read(WORK/'esm-fixed-runtime-reconstruction.json')['verified']
    assert '1835 passed, 1 skipped' in (WORK/'stable-python-final.log').read_text()
    assert '192 passed (192)' in (WORK/'stable-frontend-final.log').read_text()
    assert '17 passed' in (WORK/'full-browser-final.log').read_text() and '16 skipped' in (WORK/'full-browser-final.log').read_text()
    rows=[]
    for group in ['esm-fixed','witness-fixed','full']:
        for which in ['emotion','dashboard']:
            p=WORK/(group+'-browser-records')/(which+'.json'); data=read(p)
            assert data['completed'] and data['failure'] is None and not data['errors']
            assert data['noReloadNavigationOrUiPrivacyNoticeAfterErasure'] and data['nativeOrGpuClaim'] is False
            assert data['prepared']['user_arousal']==.4
            listing = [row for call in data['calls'] if call['path'].startswith('/memory?q=')
                       for row in call['response']['data'] if row['id']==data['fragment']['id']]
            assert len(listing)==1 and listing[0]['confirmation_status']=='source_backed'
            assert any(s['source_message_id']==data['prepared']['conversation']['user_message_id'] for s in data['fragment']['sources'])
            before=data['beforeApi']; after=data['afterApi']; auto=after.get('automatic',after.get('emotion'))
            assert auto['valence']==auto['arousal']==0 and after['context']['revision']==before['context']['revision']+1
            assert data['sourceAfter']['redacted'] and data['sampleMs']>=1000
            dom=[v.replace(' ','') for v in data['fixedDom']]
            assert dom==(['P0.00/A0.00']*3 if which=='emotion' else ['愉悦度0.00·唤醒度0.00'])
            if which=='emotion':assert data['form']=={'valence':'0','arousal':'0'}
            assert all(200<=c['status']<300 for c in data['calls'])
            rows.append({'group':group,'page':which,'sha256':digest(p),'sample_ms':data['sampleMs'],'source_redacted':True,'stale_dom':False})
    fixture=read(WORK/'controlled-analysis-exact-match.json'); assert fixture['verified'] and len(fixture['cases'])==3
    assert history('9f55b1a',fixture['source_sha256'])==fixture['source_sha256']
    seals=[]
    for p in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(p.parents[1].name[6:])>=36:continue
        for n,sha in read(p).items():assert digest(p.parents[1]/n)==sha
        seals.append({'cycle':p.parents[1].name,'items':len(read(p)),'sha256':digest(p)})
    assert len(seals)==33 and seals[-1]['sha256']=='41ba6fa01e266884c7afe704ed4fa491f1d4795529e60f1d8ee891da6b3559e3'
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert digest(migration)=='717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
    for n,sha in read(migration).items():assert digest(migration.parent/n)==sha
    links=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True));assert len(links)==9 and all(r['valid'] for r in links)
    result={'verified':True,'source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'verifier_sha256':digest(Path(__file__)),
        'bindings':bindings,'browser_rows':rows,'actual_maintained_browser_chat_preparations':6,'direct_controlled_fixture_http_requests':3,'native_or_gpu_calls':0,
        'old_cycle_seals':seals,'migration_items_unchanged':len(read(migration)),'source_count_per_run':426,'data_links':links,
        'scope':'controlled engineering regression; all tool failures retained; no independent human or native-model quality approval'}
    output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C36 system evidence verified:17default,6actual maintained page cases,426Git inputs,34old seals,0native')
if __name__=='__main__':main()
