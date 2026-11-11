"""Post-freeze fault probes; synthetic DBs, no model-quality claims or tuning."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken
from avatar.config import config
from avatar.lab.source_bound_body_review import SourceBoundBodyReviewAvatar
from avatar.lab.transport_fixture import controlled_provider
from avatar.web import create_server, run_chat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CLAIM = '那我们下次可以一起去爬山，享受大自然的风景。'


def main():
    report = {'scope': 'Post-freeze controlled actual SDK drafting and default Web run_chat authority; not fresh GPU validation or human gold',
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'sourceSha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted([*ROOT.glob('src/avatar/**/*.py'), Path(__file__).resolve()])},
        'drafts': [], 'authority': [], 'semantic_approved': False, 'production_activation_approved': False}
    drafts = [('rewrite_variant', '请把“我明天陪你去骑车”改得更客气。', True),
        ('known_writing', '帮我给同学写一条短信。', True), ('ordinary', '今天想聊聊运动。', False)]
    with controlled_provider(delay=.0001, reply_overrides={text: CLAIM for _, text, _ in drafts}) as (_, url):
        for key, text, preserve in drafts:
            engine = LLMEngine(base_url=url, api_key='controlled', model='fixture')
            bot = SourceBoundBodyReviewAvatar(db_path=':memory:', llm=engine); pieces = []
            try:
                result = bot.respond(text, cancel=CancellationToken(), on_delta=pieces.append)
                checks = {'preservation': (result['reply'] == CLAIM) == preserve,
                    'visible_final': ''.join(pieces) == result['reply']}
                report['drafts'].append({'id': key, 'input': text, 'expected_preserve': preserve,
                    'native': CLAIM, 'result': result, 'visible': ''.join(pieces), 'checks': checks})
            finally: bot.memory.close(); engine.close()
    original_key, original_embedding = config.llm.api_key, config.embedding.model
    try:
        config.llm.api_key = ''; config.embedding.model = ''
        for key, declaration, restricted in [
            ('canonical_role', '我来扮演小说中的角色。', True),
            ('specific_role_variant', '接下来我扮演剧中的旅行者。', True),
            ('real_control', '今天聊点日常。', False)]:
            with tempfile.TemporaryDirectory(prefix='authority-probe-', dir=ROOT.parent/'runtime/tmp') as folder:
                db = str(Path(folder)/'owned.db'); server = create_server(db, port=0, legacy_writes=False)
                try:
                    inputs = [declaration, '我叫许照。', '提醒我明天早上九点去码头。']
                    turns = [run_chat(server, text) for text in inputs]
                    with closing(MemoryStore(db)) as memory:
                        profile = memory.get_user_profile()
                        reminders = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_reminders')]
                    checks = {'restricted_scope': (turns[0]['speaker_attribution']['scope'] != 'current_user') == restricted,
                        'profile_permission': ('名字' not in profile) == restricted,
                        'reminder_permission': (not reminders) == restricted}
                    report['authority'].append({'id': key, 'inputs': inputs, 'expected_restricted': restricted,
                        'turns': turns, 'profile': profile, 'reminders': reminders, 'checks': checks})
                finally: server.server_close()
    finally: config.llm.api_key = original_key; config.embedding.model = original_embedding
    path = HERE.parent/'实验/remaining-context-probes.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({group: [(r['id'], r['checks']) for r in report[group]] for group in ['drafts', 'authority']}, ensure_ascii=False))


if __name__ == '__main__': main()
