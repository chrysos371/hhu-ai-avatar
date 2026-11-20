"""Independently inspect CPU receipts/current regression and preserve old seals."""
from pathlib import Path
import subprocess
from audit_common import ROOT,BASE,AUDIT,OUT,ASSETS,require,read,sha,write,historical,software,load


def main():
    require(not (OUT/'system-evidence.json').exists(),'fresh system collection required')
    regression=software();old=[];items=0
    for number in range(3,56):
        cycle=BASE.parent/f'cycle-{number:02}';p=cycle/'审计/证据清单.json';manifest=read(p)
        require(all(sha(cycle/n)==v for n,v in manifest.items()),'prior sealed bytes changed')
        items+=len(manifest);old.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'items':len(manifest)})
    p=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json';manifest=read(p)
    require(all(sha(p.parent/n)==v for n,v in manifest.items()),'migration seal changed')
    items+=len(manifest);old.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'items':len(manifest)})
    require(len(old)==54 and items==12694,'old seal totals differ')
    c55=BASE.parent/'cycle-55';freeze=read(c55/'审计/工作目录/002-真实执行输入/freeze-v1.json')
    require(historical(freeze['source_ref'],freeze['sha256'])==freeze['sha256'],'C55 original historical source identity differs')
    changed=[n for n,v in freeze['sha256'].items() if sha(ROOT/n)!=v]
    require(changed==['scripts/lab/run_frozen_capability_job.py'],'unexpected change from C55 frozen input names')
    require(all(sha(Path(n))==v for n,v in freeze['external_sha256'].items()),'old frozen external data changed')
    raw_items=0
    for stage in ('base','old_adapter','train','reload','new_adapter'):
        proof=read(c55/f'审计/工作目录/002-真实执行输入/{stage}-verified.json');path=Path(proof['artifact_manifest'])
        require(sha(path)==proof['artifact_manifest_sha256'] and all(sha(path.parent/n)==v for n,v in read(path).items()),'old C55 actual model artifacts changed')
        raw_items+=len(read(path))
    adapter=read(c55/'审计/收尾核验/adapter-files.json');adapter_root=ASSETS/'artifacts/c55/real-target-transfer-v1/adapter'
    require(all(sha(adapter_root/n)==v for n,v in adapter.items()) and raw_items==1867 and len(adapter)==14,'old model artifact counts differ')
    aliases=__import__('json').loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    require(len(aliases)==9 and all(row['valid'] for row in aliases),'centralized asset aliases differ')
    controls=AUDIT/'工作目录/001-父死亡保护与终态留痕'
    counts=[]
    for name,count in [('supervisor-green',28),('guard-controls',10),('claim-controls',2)]:
        p=read(controls/f'{name}-binding-v1.json')
        require(p['passed']==count and p['failed']==0 and p['log_sha256']==sha(controls/f'{name}-v1.log')
            and all(sha(ROOT/n)==v for n,v in p['source_sha256'].items()),'targeted test binding differs')
        counts.append(count)
    red=read(controls/'red-binding-v1.json')
    require(red['failed']==2 and red['exit_code']==1 and red['log_sha256']==sha(controls/'red-v1.log')
        and historical(red['head'],red['source_sha256'])==red['source_sha256'],'original red evidence changed')
    receipt=read(AUDIT/'工作目录/003-独立CPU留痕复核/cpu-receipts-v1.json')
    require(receipt['verified'] and len(receipt['existing_actual_job_receipts'])==9
        and receipt['inspector_sha256']==sha(AUDIT/'工作目录/003-独立CPU留痕复核/inspect_cpu_receipts.py')
        and all(sha(Path(n))==v for n,v in receipt['external_sha256'].items()),'actual CPU receipts changed')
    after=receipt['actual_stop_after_payload_exec']['after']
    require(after['state']=='interrupted' and after['return_code']==-2,'actual post-exec wait differs')
    chain=read(AUDIT/'工作目录/004-多级进程链边界/chain-cpu-v1.json');observation=chain['observation_after_supervisor_SIGKILL']
    require(chain['probe_sha256']==sha(AUDIT/'工作目录/004-多级进程链边界/probe_chain.py') and chain['all_owned_identities_cleaned']
        and observation['grandchild_alive'] and observation['manager_pdeath_signal']==9 and observation['grandchild_pdeath_signal']==0
        and not observation['manager_alive'] and observation['unrelated_owned_control_alive']
        and all(sha(Path(chain['external_root'])/n)==v for n,v in chain['external_sha256'].items()),'actual chain boundary evidence changed')
    jobs=load('c56_independent_current_jobs',ROOT/'scripts/lab/run_frozen_capability_job.py')
    require(all(not jobs.matches(i) for i in chain['identities_before_injection']),'owned chain identity still live')
    value={'verified':True,'scope':'current Linux direct-child/terminal engineering audit;CPU only;no model/physical/general approval',
        'collector_sha256':sha(Path(__file__)),'helper_sha256':sha(AUDIT/'audit_common.py'),
        'Python_passed':2562,'Python_skipped':1,'current_software_inputs':812,'regression_source_ref':regression['head'],
        'source_sha256':regression['source_git_sha256'],'targeted_tests_passed':sum(counts),'red_failed':2,
        'actual_CPU_job_receipts_rechecked':9,'actual_post_exec_stop_child_wait':-2,
        'direct_guard_kernel_signal':9,'hard_parent_death_original_wait_code_known':False,
        'chain_manager_signal':9,'chain_grandchild_signal':0,'chain_grandchild_remained_alive':True,
        'all_owned_chain_fixtures_cleaned':True,'old_seals':old,'old_items':items,'central_aliases':9,
        'C55_original_frozen_source_history_verified':534,'C55_current_changed_frozen_names':changed,
        'C55_preserved_raw_stage_items':1867,'C55_preserved_adapter_files':14,
        'issues_limited_closed':[1,2],'issues_open':[3],'new_actual_model_calls':0,'new_training_steps':0,'GPU_allocations':0,
        'default_model_changed':False,'candidate_adapters_isolated':True,'native_provider_GPU_chain_verified':False}
    write(OUT/'system-evidence.json',value)
    print('C56 system:2562/1 full Python;812 current inputs;40 targeted;54seals12694items;chain boundary OPEN')


if __name__=='__main__':main()
