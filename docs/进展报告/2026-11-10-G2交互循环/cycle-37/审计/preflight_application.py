"""Fixed scenario routing/reminder controls via actual offline app HTTP, no native model."""
from contextlib import closing
import argparse,json,re,tempfile,threading
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
from native_common import ROOT,BASE,PROTOCOL,WORK,digest,read
from avatar.paths import temporary_dir
from avatar.config import config
from avatar.web import create_server
from avatar.brain.memory import MemoryStore
parser=argparse.ArgumentParser();parser.add_argument('--tag',default='');args=parser.parse_args()
assert not args.tag or re.fullmatch(r'[a-z0-9_-]+',args.tag)
out=WORK/('application-preflight'+('-'+args.tag if args.tag else ''));out.mkdir(exist_ok=False)
protocol=read(PROTOCOL);config.llm.api_key='';config.embedding.model=''
opener=build_opener(ProxyHandler({}))
report={'scope':'fixed_scenario_rule_routing_and_reminder_counts_only_not_native_quality','protocol_sha256':digest(PROTOCOL),
    'cases':[],'completed':False,'failure':None,'native_calls':0}
def save():(out/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
save()
try:
 for case in protocol['cases']:
  with tempfile.TemporaryDirectory(prefix='c37-preflight-',dir=temporary_dir()) as folder:
   server=create_server(str(Path(folder)/'owned.db'),port=0,legacy_writes=False)
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   row={'id':case['id'],'turns':[],'completed':False,'server_closed':False};report['cases'].append(row)
   try:
    for text,count in zip(case['turns'],case.get('expected_reminders',[0]*len(case['turns']))):
     request=Request(f'http://127.0.0.1:{server.server_port}/api/v1/chat',data=json.dumps({'text':text}).encode(),headers={'Content-Type':'application/json','X-Avatar-Token':server.token})
     with opener.open(request,timeout=15) as response:raw=response.read().decode()
     result=json.loads(raw)['data'];assert result['generation_mode']!='llm'
     with closing(MemoryStore(server.db_path)) as memory:reminders=[dict(r) for r in memory._conn.execute('SELECT * FROM memory_reminders')]
     row['turns'].append({'text':text,'raw_response':raw,'reminders':reminders,'expected_count':count});save();assert len(reminders)==count
    with closing(MemoryStore(server.db_path)) as memory:(out/(case['id']+'.sql')).write_text('\n'.join(memory._conn.iterdump())+'\n')
    row['completed']=True
   finally:
    server.shutdown();thread.join(10);server.server_close();row['server_closed']=not thread.is_alive();save()
 report['completed']=True
except BaseException as error:report['failure']=repr(error);raise
finally:save()
print('Application preflight completed12scenarios/24offline results;SQL reminder controls;0native')
