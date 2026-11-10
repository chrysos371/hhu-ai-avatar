"""Disposable, offline browser-test fixture. Never opens the user's database."""

from pathlib import Path
import tempfile
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
server = create_server(
    str(Path(folder.name) / "browser.db"), port=18765, legacy_writes=False
)
server.token = "mission-control-disposable-e2e-token"
try:
    server.serve_forever()
finally:
    server.server_close()
    folder.cleanup()
