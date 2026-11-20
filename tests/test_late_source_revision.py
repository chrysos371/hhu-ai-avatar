"""An observed privacy change must synchronize SDK automatic affect at late gates."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


class Emotional(Recorder):
    def chat_analysis(self,messages,**kwargs):
        self.analysis.append(messages)
        return ('{"emotion":{"valence":-0.4,"arousal":0.3},"facts":[]}' if len(self.analysis)==1
            else '{"emotion":{"valence":0,"arousal":0},"facts":[]}')


@pytest.mark.parametrize('stage',['prompt_after_cognition','direct_source_after_cognition'])
def test_foreign_forget_observed_at_late_gate_clears_automatic_state(tmp_path,monkeypatch,stage):
    with closing(MemoryStore(str(tmp_path/'late.db'))) as memory:
        engine=Emotional('我在。')
        bot=Avatar(memory=memory,llm=engine,capability_contract_enabled=True)
        first=bot.respond('我很难过。')
        assert abs(bot.emotion.state.valence)+abs(bot.emotion.state.arousal)>0
        fragment=memory.remember('受控情绪来源',source_message_id=first['conversation']['user_message_id'])
        def forget():
            with closing(MemoryStore(memory.db_path)) as writer:writer.forget(fragment)
        if stage=='prompt_after_cognition':
            original=bot._system_prompt
            def system(*args):
                text=original(*args);forget();return text
            monkeypatch.setattr(bot,'_system_prompt',system)
            text='聊聊别的。'
        else:
            from avatar.brain import writing_templates
            original=writing_templates.build_fallback
            def build(*args,**kwargs):
                artifact=original(*args,**kwargs);assert artifact is not None
                forget();return artifact
            monkeypatch.setattr(writing_templates,'build_fallback',build)
            text='原样输出这句话：“甲”'
        with pytest.raises(Cancelled):bot.respond(text)
        assert memory.context_revision==1
        assert bot.emotion.context_revision==memory.context_revision
        assert bot.emotion.state.valence==bot.emotion.state.arousal==0
        assert bot.emotion.user_state.valence==bot.emotion.user_state.arousal==0
        assert len(engine.native)==1
