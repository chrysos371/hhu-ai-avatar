"""Observe original explicit-query coverage and due-claim side effects, no model."""
import argparse
import re
from contextlib import closing
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.main import Avatar
from avatar.paths import project_data_root


class NoModel:
    available=False


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def projection(memory):
    return {name:[dict(r) for r in memory._conn.execute('SELECT * FROM '+name+' ORDER BY id')]
        for name in ['memory_reminders','memory_reminder_deliveries','memory_action_receipts']}


def main(tag=""):
    assert not tag or re.fullmatch(r"[a-z0-9_-]+",tag)
    out=BASE/('审计/工作目录/001-状态查询调查/baseline'+('-'+tag if tag else ''))
    out.mkdir(exist_ok=False)
    protocol=ROOT/'evals/interaction/cycle-39/explicit-reminder-query-protocol.json'
    report={'scope':'actual_Avatar_SQL_no_model_same_material_query_contract_probe_not_quality_score', 'tag':tag,
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_sha256':{p:digest(ROOT/p) for p in ['src/avatar/main.py','src/avatar/brain/reminders.py',str(protocol.relative_to(ROOT)),str(Path(__file__).relative_to(ROOT))]},
        'cases':[],'native_or_GPU_calls':0,'completed':False}
    helper=ROOT/'src/avatar/brain/reminder_queries.py'
    if helper.exists():report['source_sha256'][str(helper.relative_to(ROOT))]=digest(helper)
    try:
        for case in json.loads(protocol.read_text())['baseline_probes']:
            with tempfile.TemporaryDirectory(prefix='c39-baseline-',dir=project_data_root(ROOT)/'tmp') as folder:
                with closing(MemoryStore(str(Path(folder)/'owned.db'))) as memory:
                    store=ReminderStore(memory)
                    tick=time.time()
                    memory._conn.execute("INSERT INTO memory_reminders(title,due_at,created_at) VALUES (?,?,?)",('受控到期记录',tick-60,tick-3600))
                    memory._conn.commit()
                    bot=Avatar(memory=memory,llm=NoModel(),summary_enabled=False)
                    before=projection(memory)
                    changes=memory._conn.total_changes
                    listing=store.list_with_delivery()
                    assert memory._conn.total_changes==changes and projection(memory)==before
                    result=bot.respond(case['text'])
                    after=projection(memory)
                    row={'id':case['id'],'input':case['text'],'direct_synthetic_sql_seed':True,
                         'before':before,'after':after,'existing_management_listing':listing,
                         'new_query_mode_present':result['generation_mode']==case['required_new_mode'],
                         'business_unchanged':before==after,'result':result}
                    report['cases'].append(row)
                    dump=out/(case['id']+'.sql')
                    dump.write_text('\n'.join(memory._conn.iterdump())+'\n')
                    row['after_sql_dump_sha256']=digest(dump)
        report['completed']=True
    finally:
        (out/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('C39 same-material probe ['+tag+']:',len(report['cases']),'actual Avatar results;',sum(c['new_query_mode_present'] for c in report['cases']),'new query modes;',sum(c['business_unchanged'] for c in report['cases']),'unchanged business projections;0model/GPU')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',default='')
    main(parser.parse_args().tag)
