"""Actual analysis HTTP then deterministic scheduling before fact transaction."""
from contextlib import closing
from hashlib import sha256
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from avatar.brain.memory import MemoryStore
from avatar.brain.llm import LLMEngine
from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.transport_fixture import controlled_provider
from avatar.main import Avatar

ROOT=Path(__file__).resolve().parents[2]
NAME='小岚'


def audit(output):
    if output.exists():raise FileExistsError(output)
    paths=[*ROOT.glob('src/avatar/**/*.py'),Path(__file__).resolve()]
    report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'source_sha256':{str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
            'scope':'Real default Avatar, analysis-provider HTTP and SQLite, deterministic post-analysis scheduling. Fixture responses/known source-supported name, no native quality or incidence claim.',
            'cases':[],'completed':False}
    def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    save()
    for change in ('normal','cancel','same_forget','external_forget','same_correct','external_correct'):
        row={'change':change,'requests':[],'cleanup':False};report['cases'].append(row)
        with tempfile.TemporaryDirectory(prefix='fact-boundary-',dir=ROOT.parent/'runtime/tmp') as folder:
            path=str(Path(folder)/'owned.db');token=CancellationToken()
            with controlled_provider(delay=.0001) as (provider,url):
                handler=provider.RequestHandlerClass;original_post=handler.do_POST
                def capture(self):
                    row['requests'].append({'ordinal':len(row['requests'])+1})
                    return original_post(self)
                handler.do_POST=capture
                engine=LLMEngine(base_url=url,api_key='fixture-only',model='fixture')
                bot=Avatar(db_path=path,llm=engine)
                try:
                    fragment=bot.memory.remember_user('名字',NAME)
                    original=bot._analyze_with_llm
                    def analysed(*args,**kwargs):
                        result=original(*args,**kwargs)
                        row['verified_facts']=result[2]
                        row['before_change']={'turn_revision':bot._turn_context_revision,
                            'speaker_revision':bot.speaker_scope.revision,'source_id':bot._current_message_id}
                        if change=='cancel':token.cancel()
                        elif change=='same_forget':bot.forget_memory(fragment)
                        elif change=='same_correct':bot.correct_memory(fragment,'名字: 阿澄')
                        elif change.startswith('external'):
                            with closing(MemoryStore(path)) as writer:
                                if change=='external_forget':writer.forget(fragment)
                                else:writer.correct(fragment,'名字: 阿澄')
                        row['after_change']={'revision':bot.memory.context_revision,
                            'speaker_revision':bot.speaker_scope.revision,'source_id':bot._current_message_id,
                            'profile':bot.memory.get_user_profile(),'token_cancelled':token.cancelled}
                        return result
                    bot._analyze_with_llm=analysed
                    try:
                        result=bot.respond('我叫'+NAME+'。',cancel=token)
                        row['terminal']='result';row['reply']=result['reply']
                    except Cancelled as error:row['terminal']='cancelled';row['error']=str(error)
                    row['final_profile']=bot.memory.get_user_profile()
                    row['fragments']=[dict(r) for r in bot.memory._conn.execute('SELECT id,content,status FROM memory_fragments')]
                    row['sources']=[dict(r) for r in bot.memory._conn.execute('SELECT * FROM memory_sources')]
                    row['assistant_count']=bot.memory._conn.execute("SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]
                    row['facts_after_change']=row['final_profile']!=row['after_change']['profile']
                    assert row['verified_facts'] and row['terminal']==('result' if change=='normal' else 'cancelled')
                finally:bot.memory.close();engine.close();save()
        row['cleanup']=not Path(folder).exists();save()
    assert all(sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in report['source_sha256'].items())
    report['completed']=True;save();return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    result=audit(parser.parse_args().output)
    for row in result['cases']:print(row['change'],row['terminal'],'HTTP',len(row['requests']),
        'profile at change',row['after_change']['profile'],'final',row['final_profile'],'sources',row['sources'])
