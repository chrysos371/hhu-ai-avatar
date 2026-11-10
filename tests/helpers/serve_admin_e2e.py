"""Disposable, offline browser-test fixture. Never opens the user's database."""

from pathlib import Path
import tempfile
import os
import time
from avatar.config import config
from avatar.brain.memory import MemoryStore
from avatar.web import create_server

root = Path(__file__).resolve().parents[3]
folder = tempfile.TemporaryDirectory(prefix="admin-e2e-", dir=root / "runtime/tmp")
config.llm.api_key = ""
config.embedding.model = ""
memory = MemoryStore(str(Path(folder.name) / "browser.db"))
memory.remember_user("名字", "浏览器测试原名")
memory.close()
# QQ browser actions only target disposable accounts and databases.
qq_root = Path(folder.name) / 'qq'
os.environ['AVATAR_ONEBOT_STATE_DIR'] = str(qq_root)
os.environ['AVATAR_QQ_ADMIN_DB'] = str(Path(folder.name) / 'browser.db')
from avatar.channels.qq.engine import AvatarEngine
from avatar.channels.qq.protocol import Incoming
for user in ('23456', '34567'):
    def seed(message, memory):
        memory.remember_user('名字', '浏览器QQ原名' if message.user_id == '23456' else '其他QQ原名')
        return '离线浏览器种子回复'
    message = Incoming('onebot:12345', 'private', user, user, user, '你好', time.time())
    AvatarEngine(generate=seed).respond(message, qq_root / 'contexts' / message.context_key)
server = create_server(
    str(Path(folder.name) / "browser.db"), port=18765, legacy_writes=False
)
server.character_root = Path(folder.name) / 'characters'
class OfflineCharacterModel:
    available = True
    def chat_analysis(self, *args, **kwargs): return '{}'
    def chat(self, messages, **kwargs): return '这是当前角色的离线测试回复。'
server.character_llm_factory = OfflineCharacterModel
server.token = "mission-control-disposable-e2e-token"
try:
    server.serve_forever()
finally:
    server.server_close()
    folder.cleanup()
