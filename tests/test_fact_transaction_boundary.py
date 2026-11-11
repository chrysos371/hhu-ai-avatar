from contextlib import closing
import json

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar


class Engine:
    available=True
    def chat_analysis(self,*args,**kwargs):return json.dumps({'emotion':{'valence':.7,'arousal':0},'facts':[]})
    def chat(self,*args,**kwargs):return '已收到你的消息。'


@pytest.mark.parametrize('change',['normal','cancel','same_forget','same_correct','external_forget','external_correct'])
def test_verified_facts_cannot_cross_immutable_turn_boundary(tmp_path,change):
    path=str(tmp_path/'db');bot=Avatar(db_path=path,llm=Engine());token=CancellationToken()
    fragment=bot.memory.remember_user('名字','旧名' if change in ('normal','cancel') else '小岚')
    original=bot._analyze_with_llm
    def analysed(*args,**kwargs):
        result=original(*args,**kwargs);assert result[2]
        if change=='cancel':token.cancel()
        elif change=='same_forget':bot.forget_memory(fragment)
        elif change=='same_correct':bot.correct_memory(fragment,'名字: 阿澄')
        elif change.startswith('external'):
            with closing(MemoryStore(path)) as writer:
                if change=='external_forget':writer.forget(fragment)
                else:writer.correct(fragment,'名字: 阿澄')
        return result
    bot._analyze_with_llm=analysed
    try:
        if change=='normal':assert bot.respond('我叫小岚。',cancel=token)['reply']
        else:
            with pytest.raises(Cancelled):bot.respond('我叫小岚。',cancel=token)
        expected={'名字':'小岚'} if change=='normal' else {'名字':'旧名'} if change=='cancel' else {} if change.endswith('forget') else {'名字':'阿澄'}
        assert bot.memory.get_user_profile()==expected
        if change!='normal':
            assert not bot.memory._conn.execute("SELECT 1 FROM memory_sources WHERE evidence='我叫小岚'").fetchone()
            assert bot.memory._conn.execute("SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]==0
    finally:bot.memory.close()


def test_cancelled_empty_analysis_does_not_apply_late_emotion(tmp_path):
    bot=Avatar(db_path=str(tmp_path/'db'),llm=Engine());token=CancellationToken()
    def analyse(*args,**kwargs):token.cancel();return .8,.7,[]
    bot._analyze_with_llm=analyse;before=(bot.emotion.state.valence,bot.emotion.state.arousal)
    try:
        with pytest.raises(Cancelled):bot.respond('你好',cancel=token)
        assert (bot.emotion.state.valence,bot.emotion.state.arousal)==before
    finally:bot.memory.close()


@pytest.mark.parametrize('text',['我叫小岚。','我叫小岚，我喜欢游泳。'])
def test_cancel_before_fact_batch_commit_rolls_back_all_facts(tmp_path,text):
    bot=Avatar(db_path=str(tmp_path/'db'),llm=Engine());token=CancellationToken()
    bot.memory.remember_user('名字','旧名');original=bot.memory.remember_user
    def stored(key,*args,**kwargs):
        result=original(key,*args,**kwargs)
        if key=='名字':token.cancel()
        return result
    bot.memory.remember_user=stored
    try:
        with pytest.raises(Cancelled):bot.respond(text,cancel=token)
        assert bot.memory.get_user_profile()=={'名字':'旧名'}
        assert bot.memory._conn.execute('SELECT count(*) FROM memory_sources').fetchone()[0]==0
    finally:bot.memory.close()


def test_rule_facts_check_cancellation_inside_write_transaction(tmp_path):
    class NoModel:
        available=False
    bot=Avatar(db_path=str(tmp_path/'db'),llm=NoModel());token=CancellationToken()
    original=bot._fact_context
    def context(*args):
        result=original(*args);token.cancel();return result
    bot._fact_context=context
    try:
        with pytest.raises(Cancelled):bot.respond('我叫小岚。',cancel=token)
        assert bot.memory.get_user_profile()=={}
    finally:bot.memory.close()
