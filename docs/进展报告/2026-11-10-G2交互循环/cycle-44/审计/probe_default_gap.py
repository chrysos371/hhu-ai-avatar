"""Actual unconfigured SDK probes of current delivery gap; no model/network."""
from contextlib import closing
import inspect
import json
from pathlib import Path
import subprocess
import time

from native_common import ROOT,BASE,read,digest
from avatar.brain.memory import MemoryStore
from avatar.brain.reminder_queries import parse_query
from avatar.main import Avatar


class Offline:
    available=False


def business(memory):
    return {name:[dict(row) for row in memory._conn.execute('SELECT * FROM '+name+' ORDER BY id')]
        for name in ('memory_reminders','memory_reminder_deliveries','memory_action_receipts')}


def main():
    output=BASE/'审计/工作目录/005-系统复核/default-integration-gap.json';assert not output.exists()
    cases=['提醒编号1能通过短信送给我吗？','提醒编号1现在是什么状态？'];results=[]
    sources=[ROOT/'src/avatar/main.py',ROOT/'src/avatar/brain/reminder_queries.py',Path(__file__)]
    hashes={str(p.relative_to(ROOT)):digest(p) for p in sources}
    for text in cases:
        with closing(MemoryStore(':memory:')) as memory:
            avatar=Avatar(memory=memory,llm=Offline(),session_id='c44-default-gap')
            memory._conn.execute('INSERT INTO memory_reminders(id,title,due_at,created_at) VALUES(1,?,?,?)',
                ('默认接入差距控制',time.time()+3600,time.time()));memory._conn.commit()
            before=business(memory);result=avatar.respond(text);after=business(memory)
            assert parse_query(text) is None and 'reminder_query' not in result
            assert before==after
            results.append({'text':text,'explicit_parser_matched':False,'generation_mode':result['generation_mode'],
                'analysis_mode':result['analysis_mode'],'reply':result['reply'],
                'has_verified_query_metadata':False,'business_unchanged':True,'conversation':result['conversation']})
    assert hashes=={str(p.relative_to(ROOT)):digest(p) for p in sources}
    receipt={'scope':'actual Avatar.respond unconfigured SDK only; not all configured/default Web behavior or model quality',
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_sha256':hashes,'respond_signature':str(inspect.signature(Avatar.respond)),
        'default_read_mode_parameter_present':False,'cases':results,'native_calls':0,'actual_SDK_turns':2,
        'default_feature_delivery_proven':False}
    output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print('Actual offline SDK2 turns: natural queries lack verified read metadata;0 model;product integration remains pending')


if __name__=='__main__':main()
