"""Actual completed-query source erasure and subsequent SDK/Web model inputs."""
from contextlib import closing
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import urllib.request

import avatar.main
from avatar.brain.conversations import ConversationStore
from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.config import config
from avatar.paths import temporary_dir
from avatar.web import create_server
from run_history_capture import CaptureModel, projection
from run_regression import ROOT, snapshot, digest

BASE = Path(__file__).resolve().parents[1]
WORK = BASE/'审计/工作目录/005-完成查询后的实际遗忘'
SECRET = 'C46待遗忘查询标题'


def main():
    assert not WORK.exists(); WORK.mkdir()
    source = snapshot(); cases = []
    original = avatar.main.Avatar
    old_embedding = config.embedding.model; config.embedding.model = ''
    try:
        for arm in ('sdk','web'):
            stage = {'name':'startup'}; model = CaptureModel(stage)
            calls, sessions = [], []
            bot = server = thread = None
            with tempfile.TemporaryDirectory(prefix='c46-history-erase-',dir=temporary_dir()) as directory:
                db_path = str(Path(directory)/'actual.db')
                try:
                    if arm == 'sdk':
                        bot = original(db_path=db_path,llm=model,session_id='c46-erasure-sdk')
                    else:
                        class CapturedAvatar(original):
                            def __init__(self,*args,**kwargs):
                                kwargs['llm'] = model
                                super().__init__(*args,**kwargs)
                        avatar.main.Avatar = CapturedAvatar
                        server = create_server(db_path,port=0)
                        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
                        sessions.append(server.session_id)
                    def run(name,text,mode='chat'):
                        stage['name'] = name
                        before = [len(model.analysis),len(model.generation)]
                        if arm == 'sdk':
                            result = bot.respond(text,mode=mode)
                        else:
                            data = {'text':text,'mode':mode}
                            req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1/chat',
                                data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Avatar-Token':server.token})
                            with urllib.request.urlopen(req,timeout=15) as response:
                                assert response.status == 200; result = json.loads(response.read())['data']
                        calls.append({'stage':name,'text':text,'mode':mode,'result':result})
                        if mode == 'reminder_query' or name == 'independent_return_to_reality':
                            assert before == [len(model.analysis),len(model.generation)]
                        return result
                    with closing(MemoryStore(db_path)) as memory:
                        ReminderStore(memory).create('提醒我2099年1月1日上午十点，'+SECRET+'。')
                        business = projection(memory)
                    query = run('explicit_query','提醒编号1现在是什么状态？','reminder_query')
                    assert not model.analysis and not model.generation
                    ordinary = run('ordinary_before_forget','接着聊聊')
                    assert len(model.analysis) == len(model.generation) == 1
                    assert SECRET in str(model.analysis[0]) and SECRET in str(model.generation[0])
                    with closing(MemoryStore(db_path)) as writer:
                        before_file = WORK/(arm+'-before-forget.sql')
                        before_file.write_text('\n'.join(writer._conn.iterdump())+'\n')
                        fragment = writer.remember('查询来源删除控制',source_message_id=query['conversation']['user_message_id'])
                        writer.forget(fragment)
                        after_forget_revision = writer.context_revision
                        public = ConversationStore(writer).read('erasure-observation')
                        for value in (query,ordinary):
                            row = next(r for r in public['items'] if r['id'] == value['conversation']['assistant_message_id'])
                            assert row['redacted'] is True and 'result' not in row and SECRET not in row['text']
                        assert projection(writer) == business  # Independent reminder itself was not deleted.
                    if arm == 'web':
                        server.shutdown(); thread.join(); server.server_close(); server = thread = None
                        server = create_server(db_path,port=0)
                        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
                        sessions.append(server.session_id)
                        assert sessions[0] != sessions[1]
                    control = run('independent_return_to_reality','回到现实。')
                    assert control['generation_mode'] == 'rules_speaker_control'
                    later = run('ordinary_after_forget','重新开始聊聊')
                    assert len(model.analysis) == len(model.generation) == 2
                    assert SECRET not in str(model.analysis[-1]) and SECRET not in str(model.generation[-1])
                    assert '历史提醒查询快照（' not in str(model.generation[-1])
                    assert later['conversation']['revision'] == after_forget_revision
                    with closing(MemoryStore(db_path)) as memory:
                        after_file = WORK/(arm+'-after-forget.sql')
                        after_file.write_text('\n'.join(memory._conn.iterdump())+'\n')
                        assert projection(memory) == business and not memory.get_user_profile()
                    cases.append({'arm':arm,'calls':calls,'analysis':model.analysis,'generation':model.generation,
                        'sessions':sessions,'public_after_forget':public,'business_before':business,
                        'business_after':business,'revision_after_forget':after_forget_revision,
                        'before_SQL_sha256':digest(before_file),'after_SQL_sha256':digest(after_file),
                        'query_turns':1,'query_model_calls':0,'ordinary_turns':2,'independent_control_turns':1})
                finally:
                    if server: server.shutdown(); thread.join(); server.server_close()
                    if bot: bot.memory.close()
                    avatar.main.Avatar = original
        assert snapshot() == source
        (WORK/'erasure-evidence.json').write_text(json.dumps({'verified':True,
            'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'collector_sha256':digest(Path(__file__)),'source_sha256':source,'cases':cases,
            'native_external_calls':0,'scope':'actual SQLite source erasure and next actual SDK/HTTP capture-model input; Web process restart'},
            ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        print('C46 erasure:SDK+Web completed query and derived reply redacted;Web restarted;next model input has no erased query title;4SQL')
    finally:
        avatar.main.Avatar = original; config.embedding.model = old_embedding


if __name__ == '__main__':
    main()
