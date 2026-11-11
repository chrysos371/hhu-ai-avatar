"""Real SQLite BEGIN contention after completed analysis/source preparation."""
from contextlib import closing
import json
import threading

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar


@pytest.mark.parametrize('route',['llm','rules'])
@pytest.mark.parametrize('change',['cancel','forget'])
def test_fact_write_rechecks_after_waiting_for_other_writer(tmp_path,route,change):
    path=str(tmp_path/'db');token=CancellationToken()
    entered,proceed,attempting=threading.Event(),threading.Event(),threading.Event()
    result={};errors=[]
    with closing(MemoryStore(path)) as writer:
        fragment=writer.remember_user('名字','旧名')
        def run():
            class Engine:
                available=route=='llm'
                def chat_analysis(self,*args,**kwargs):return json.dumps({'emotion':{},'facts':[]})
                def chat(self,*args,**kwargs):return '正常回复。'
            bot=Avatar(db_path=path,llm=Engine())
            name='_analyze_with_llm' if route=='llm' else '_fact_context'
            original=getattr(bot,name)
            def paused(*args,**kwargs):
                value=original(*args,**kwargs);entered.set();assert proceed.wait(5)
                bot.memory._conn.set_trace_callback(lambda sql:attempting.set() if sql=='BEGIN IMMEDIATE' else None)
                return value
            setattr(bot,name,paused)
            checked=bot._check_fact_context
            def check():
                try:checked()
                except Cancelled:
                    result['rejected_inside_transaction']=bot.memory._conn.in_transaction
                    raise
            bot._check_fact_context=check
            try:
                try:result['reply']=bot.respond('我叫小岚。',cancel=token)
                except Cancelled:result['cancelled']=True
            except BaseException as error:errors.append(error)
            finally:bot.memory.close()
        thread=threading.Thread(target=run);thread.start()
        try:
            assert entered.wait(5)
            with writer.transaction():
                proceed.set();assert attempting.wait(5)
                if change=='cancel':token.cancel()
                else:writer.forget(fragment)
        finally:proceed.set();thread.join(10)
        assert not thread.is_alive() and not errors,errors
        assert result=={'rejected_inside_transaction':True,'cancelled':True}
        assert writer.get_user_profile()==({'名字':'旧名'} if change=='cancel' else {})
        assert writer._conn.execute('SELECT count(*) FROM memory_sources').fetchone()[0]==0
