"""Verify historical baselines, actual runtime bindings and current regressions."""
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import subprocess

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[3]
W1=BASE/'审计/工作目录/001-提醒投递基线与故障边界'
W2=BASE/'审计/工作目录/002-持久提醒确认'
W3=BASE/'审计/工作目录/003-集成后并发与隐私审计'

def read(path):return json.loads(path.read_text())
def digest(path):return sha256(path.read_bytes()).hexdigest()
@lru_cache(None)
def historical(ref,path):
    return sha256(subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT)).hexdigest()

def processes(rows):
    for row in rows:
        assert row['exit_code']==0 and row['identity_after_wait'] is None
        assert not row.get('forced_cleanup')
        pid=row['pid']; expected=row['ready']['identity']['start_ticks']
        try: fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(') ',1)[1].split()
        except (FileNotFoundError,ProcessLookupError):continue
        assert int(fields[19])!=expected, 'Owned historical process still exists'

def browser(path,runtime,current=False):
    data=read(path);served=read(runtime)
    assert data['completed'] and data['errors']==[]
    assert not data.get('overflow',False)
    for name,value in data['sourceSha256'].items():
        actual='frontend/'+name if not name.startswith('../') else name[3:]
        if name.startswith('dist/'):
            assert served['frontend_sha256'][actual]==value
        else:
            assert historical(data['head'],actual)==value
            if current and (actual.startswith('src/avatar/') or actual.startswith('frontend/src/')):
                assert digest(ROOT/actual)==value
    for name,path in served['module_paths'].items():
        relative=str(Path(path).relative_to(ROOT))
        assert relative.startswith('src/avatar/')
        assert data['sourceSha256']['../'+relative]==served['module_sha256'][name]
    assert len(served['module_paths'])==4 and len(served['frontend_sha256'])==5
    return data

def verify():
    old=[]
    for number,count in ((21,432),(22,81),(23,80)):
        directory=BASE.parent/('cycle-'+str(number));path=directory/'审计/证据清单.json';manifest=read(path)
        assert len(manifest)==count
        assert all(digest(directory/name)==value for name,value in manifest.items())
        old.append({'cycle':number,'entries':count,'manifest_sha256':digest(path),'mismatches':0})
    protocol=read(ROOT/'evals/interaction/cycle-24/reminder-delivery-protocol.json')
    for name,value in protocol['source_sha256'].items():assert historical(protocol['baseline'],name)==value
    baseline=read(W1/'http-os-before/baseline.json')
    assert baseline['completed'] and baseline['owned_temporary_directory_removed']
    for name,value in baseline['source_sha256'].items():assert historical(baseline['head'],name)==value
    cases=baseline['http_cases']+baseline['os_protocols'];assert len(cases)==10
    assert sum(len(r['processes']) for r in cases)==13
    for case in cases:assert case['completed'];processes(case['processes'])
    before=[]
    for name in ('normal_claim','response_drop_after_commit'):
        before.append(browser(W1/f'browser-before/{name}/reminder-browser.json',W1/f'browser-before/{name}-runtime.json'))
    before.append(browser(W1/'browser-navigation-corrected/reminder-browser.json',W1/'browser-navigation-corrected-runtime.json'))
    assert [x['firstNoticeVisible'] for x in before]==[True,False,False]
    assert all(x['afterReloadNoticeVisible'] is False and x['secondUpstream']['data']==[] for x in before)
    assert all('本机已提示' in x['listLabelAfterReload'] for x in before)
    label=browser(W1/'browser-label-only/reminder-browser.json',W1/'browser-label-only-runtime.json')
    assert '显示未确认' in label['listLabelAfterReload']
    recovered=[]
    for name in ('normal_claim','response_drop_after_commit','navigation_before_response','ack_response_drop_after_commit'):
        data=browser(W2/f'browser-recovery/{name}/recovery-browser.json',W2/f'browser-recovery/{name}-runtime.json',True)
        assert data['noAckBeforeExplicitClick'] and data['finalPending']['items']==[]
        assert data['pendingResponses'][0]['data']['items'][0]['delivery_id']==data['recoveredEvent']['delivery_id']
        assert data['afterAckList'][0]['delivery_acknowledged_at']==data['ack']['data']['acknowledged_at']
        recovered.append(data)
    assert all(x['sourceSha256']==recovered[0]['sourceSha256'] for x in recovered)
    restart=read(W2/'os-recovery/restart-recovery.json')
    assert restart['completed'] and restart['source_unchanged_after_run'] and restart['owned_temporary_directory_removed']
    assert restart['process_count']==6 and restart['http_request_count']==28 and len(restart['cases'])==3
    for row in restart['cases']:assert row['completed'];processes(row['processes'])
    concurrent=read(W3/'concurrency/concurrency.json')
    assert concurrent['completed'] and concurrent['source_unchanged_after_run'] and concurrent['owned_temporary_directory_removed']
    assert len(concurrent['rounds'])==20 and concurrent['http_request_count']==100
    assert len(concurrent['final_http_sql']['deliveries'])==20
    processes(concurrent['processes'])
    assert [r['rejected'] for r in concurrent['lock_wait_controls']]==['delivery_revision_changed','delivery_not_pending']
    for row in concurrent['lock_wait_controls']:
        events={e['event']:e['monotonic'] for e in row['events']}
        assert events['writer_lock_held']<=events['ack_begin_attempt']<=events['invalidation_before_commit']<=events['ack_finished']
        assert row['completed'] and row['final_sql']['deliveries'][0]['acknowledged_at'] is None
    privacy=browser(W3/'browser-privacy/privacy-browser.json',W3/'browser-privacy-runtime.json',True)
    assert privacy['oldResponseDidNotInstallWhileNewResponseHeld'] and privacy['staleAck']['status']==409
    assert privacy['finalPending']['items']==[]
    full=read(W2/'python-full-binding.json')
    assert full['completed'] and full['exit_code']==0 and full['source_unchanged']
    for name,value in full['source_sha256'].items():
        assert historical(full['head'],name)==value and digest(ROOT/name)==value
    assert '1529 passed, 1 skipped in 110.20s' in (W2/'python-full.log').read_text()
    assert '153 passed (153)' in (W2/'frontend-full.log').read_text()
    assert '15 skipped' in (W2/'default-browser.log').read_text() and '15 passed (36.4s)' in (W2/'default-browser.log').read_text()
    runtime=read(W2/'default-browser-runtime.json')
    assert all(digest(ROOT/name)==h for name,h in runtime['frontend_sha256'].items())
    for record in (restart,concurrent):
        for name,value in record['source_sha256'].items():assert historical(record['head'],name)==value
    result={'verified':True,'prior_manifests':old,'baseline_http_cases':8,'baseline_os_protocols':2,'baseline_server_processes':13,
            'valid_baseline_browser_cases':3,'retained_failed_navigation_probe':1,'label_only_browser_cases':1,
            'recovery_browser_cases':4,'recovery_os_protocols':3,'recovery_server_processes':6,'recovery_http_requests':28,
            'concurrency_http_rounds':20,'concurrency_http_requests':100,'concurrency_server_processes':1,'lock_wait_controls':2,'privacy_browser_cases':1,
            'python_full':{'passed':1529,'skipped':1,'seconds':110.20,'head':full['head'],'bound_python_inputs':len(full['source_sha256'])},
            'frontend_unit_passed':153,'frontend_unit_seconds':6.98,'default_browser':{'passed':15,'optional_skipped':15,'seconds':36.4,'scope':'Before new optional privacy probe was added; no rerun implied'},
            'bundle':'index-CYNSx0Ec.js','model_gpu_used':False,'human_read_or_physical_notification_verified':False,'general_semantic_P1_closed':False,'generational_leap_approved':False}
    out=BASE/'审计/收尾核验';out.mkdir(exist_ok=True);path=out/'阶段来源与系统收尾核验.json';data=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if path.exists():assert path.read_text()==data
    else:path.write_text(data)
    print('Verified reminder baselines/recovery/concurrency/privacy, source-bound full1529/frontend153; C21/22/23 unchanged.')

if __name__=='__main__':verify()
